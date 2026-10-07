"""How many compilers a build may run at once on this Home Assistant machine (app 0.4.65).

A build of a screen runs ESP-IDF's ninja, which compiles as many files at once as it is allowed. Most of ESPHome's files
take a few hundred MB of memory each, but the screen's own `main.cpp` and the two .cpp files of components/smart_display
each pull the whole of runtime_tiles.h in, and compiling one of those takes well over a gigabyte (1.36 GB for main.cpp
and 1.09 GB for page_receiver.cpp on the Guition, measured 2026-10-04 with ESPHome 2026.9.0). On a Raspberry Pi or a
small virtual machine, with Home Assistant and its add-ons beside it, that is more than is free: Linux then stops a
compiler ("Killed signal terminated program cc1plus", GitHub #162) and the build fails without a line of code being
wrong.

So before a build this reads how much memory is free and lets ninja run only as many compilers as fit. When a compiler
is killed all the same, the build runs again with one compiler at a time, from where it stopped (ninja keeps every file
that was done). And when one compiler alone is more than the machine has, the build says so in plain words instead of
the compiler's. The editor shows each of these to the person installing, not only in the log: a slower build they
understand is better than one that looks stuck or fails for no visible reason.
"""
import re

# What the largest file needs, with some room: one compiler must have this much or the build cannot finish.
HEAVY_MB = 1500
# What each further compiler beside it is counted at: a second heavy file, or a few of ESPHome's own.
EXTRA_MB = 700
# How a compiler that ran out of memory shows in the log: GCC's driver reports the signal the kernel sent cc1plus, the
# linker says it its own way, and a compiler whose allocation is refused (a memory limit) says it ran out.
KILLED = re.compile(r'Killed signal terminated program|terminated with signal 9 \[Killed\]|out of memory|'
                    r'virtual memory exhausted|Cannot allocate memory', re.I)


def available_mb(path='/proc/meminfo', cgroup='/sys/fs/cgroup'):
    """The memory free for a build in MB, or None where nothing says (a Mac, a test). Linux's own count (MemAvailable:
    free plus what the cache gives back), and less when this container has a memory limit of its own: Docker's
    `--memory` and some NAS systems set one, and /proc/meminfo still shows the whole machine there. cgroup v2 keeps the
    limit in memory.max, v1 in memory/memory.limit_in_bytes (an enormous number when there is none)."""
    found = []
    try:
        with open(path, encoding='ascii', errors='replace') as handle:
            for line in handle:
                if line.startswith('MemAvailable:'):
                    found.append(int(line.split()[1]) // 1024)
                    break
    except (OSError, ValueError, IndexError):
        pass
    for limit, used in (('memory.max', 'memory.current'),
                        ('memory/memory.limit_in_bytes', 'memory/memory.usage_in_bytes')):
        try:
            with open(f'{cgroup}/{limit}', encoding='ascii') as handle:
                cap = handle.read().strip()
            with open(f'{cgroup}/{used}', encoding='ascii') as handle:
                current = int(handle.read().strip())
        except (OSError, ValueError):
            continue
        if cap.isdigit() and int(cap) < 1 << 50:
            found.append(max(0, int(cap) - current) // (1024 * 1024))
        break
    return min(found) if found else None


def compilers(free_mb, cores):
    """How many compilers fit at once: one for the heaviest file, one more for every EXTRA_MB beyond it, never more than
    the cores (ninja would only queue them) and never fewer than one. Unknown memory means as many as there are cores."""
    cores = max(1, int(cores or 1))
    if free_mb is None:
        return cores
    return max(1, min(cores, 1 + max(0, free_mb - HEAVY_MB) // EXTRA_MB))


def plan(cores, free_mb, limit=None):
    """What a build starts with, for the job the editor shows: the cores and free memory of the machine, the compilers
    it runs at once, and the reason when that is fewer than the cores: 'low' (memory decides the count) or 'tight' (less
    free than the heaviest file needs; one compiler tries all the same). The build adds 'retry', 'out' and 'limit' later
    (firmware.Firmware.run). `limit` is a cap the owner set in the add-on's
    environment, kept as it was. No reason means the machine has room and the editor shows nothing."""
    cores = max(1, int(cores or 1))
    jobs = compilers(free_mb, cores)
    if limit:
        jobs = max(1, min(jobs, int(limit)))
    reason = None
    if free_mb is not None and free_mb < HEAVY_MB:
        reason = 'tight'
    elif free_mb is not None and compilers(free_mb, cores) < cores:
        reason = 'low'
    return {'cores': cores, 'free_mb': free_mb, 'need_mb': HEAVY_MB, 'jobs': jobs, 'reason': reason}


def killed(line):
    """True when this line of the build log says a compiler or linker was stopped for lack of memory."""
    return bool(KILLED.search(line))


def killed_exit(code):
    """True when ESPHome itself ended on SIGKILL, which is what Linux sends when the memory runs out and it picks
    ESPHome rather than a compiler: no line in the log says so then (-9 from asyncio, 137 from a shell)."""
    return code in (-9, 137)
