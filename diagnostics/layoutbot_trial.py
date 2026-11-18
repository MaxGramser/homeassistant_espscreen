"""Try Layoutbot, the editor's chat (screen_manager/app/layoutbot.py) against a real Home Assistant.

Reads only: the app's inventory through its ingress (the screens' documents and the entities), and asks the AI Task
for a plan per prompt, checked as the add-on checks it (layoutbot.answered). Nothing is placed or saved (the editor
places a plan, web/src/model/layoutbot.ts), no action other than `ai_task.generate_data` is called. The result of each
prompt (the answer, the checked plan, notes, seconds) goes to --out as JSON; tokens are never printed.

    uv run --with aiohttp python diagnostics/layoutbot_trial.py --screen "Guition 10.1" --out /tmp/trial.json \
        "Maak een nieuwe pagina met alle lampen van de woonkamer"

`.esphome/ha_url` and `.esphome/ha_token` of the main checkout say where Home Assistant is (AGENTS.md, Owner's machine).
--covers adds made-up blinds and curtains to the entity list (no such entity is created anywhere), for the example
prompt on a home without covers.
"""
import argparse
import asyncio
import json
import pathlib
import sys
import time

import aiohttp

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "screen_manager/app"))
from core import Grid  # noqa: E402
import layoutbot  # noqa: E402

FAKE_COVERS = [
    {"id": "cover.woonkamer_rolgordijn_links", "name": "Rolgordijn links", "area": "Woonkamer"},
    {"id": "cover.woonkamer_rolgordijn_rechts", "name": "Rolgordijn rechts", "area": "Woonkamer"},
    {"id": "cover.slaapkamer_jaloezie", "name": "Jaloezie", "area": "Slaapkamer"},
    {"id": "cover.keuken_screen", "name": "Screen keuken", "area": "Keuken"},
    {"id": "cover.woonkamer_gordijn", "name": "Gordijn", "area": "Woonkamer"},
    {"id": "cover.slaapkamer_gordijnen", "name": "Gordijnen", "area": "Slaapkamer"},
    {"id": "cover.zolder_velux", "name": "Velux zonwering", "area": "Zolder"},
]


def access(checkout):
    folder = pathlib.Path(checkout) / ".esphome"
    return folder.joinpath("ha_url").read_text().strip().rstrip("/"), folder.joinpath("ha_token").read_text().strip()


class HA:
    def __init__(self, url, token):
        self.url, self.token, self.n = url, token, 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(self.url.replace("http", "ws", 1) + "/api/websocket", max_msg_size=0)
        await self.ws.receive_json()
        await self.ws.send_json({"type": "auth", "access_token": self.token})
        answer = await self.ws.receive_json()
        if answer.get("type") != "auth_ok":
            raise SystemExit("Home Assistant refused the token.")
        self.version = answer.get("ha_version")
        return self

    async def __aexit__(self, *_):
        await self.ws.close()
        await self.session.close()

    async def raw(self, message, timeout=180):
        self.n += 1
        await self.ws.send_json({"id": self.n, **message})
        while True:
            answer = await asyncio.wait_for(self.ws.receive_json(), timeout)
            if answer.get("id") == self.n and answer.get("type") == "result":
                return answer

    async def request(self, kind, wait=180, **data):
        """The add-on's HomeAssistant.request: the result, or an error raised."""
        answer = await self.raw({"type": kind, **data}, wait)
        if not answer.get("success"):
            raise RuntimeError((answer.get("error") or {}).get("message") or "failed")
        return answer.get("result")

    async def ingress_get(self, slug, path):
        info = await self.request("supervisor/api", endpoint=f"/addons/{slug}/info", method="get")
        session = (await self.request("supervisor/api", endpoint="/ingress/session", method="post"))["session"]
        async with self.session.get(self.url + info["ingress_url"].rstrip("/") + "/" + path,
                                    cookies={"ingress_session": session}) as response:
            response.raise_for_status()
            return json.loads(await response.text())


def summary(plan):
    """The checked plan in one line per page: where it goes, its sections and loose tiles."""
    out = []
    for page in plan["pages"]:
        where = "NEW" if page["page"] == "new" else f"page {page['page']}"
        parts = [f'{where} "{page["title"]}"']
        parts += [f'[{s["title"]}: ' + ", ".join(e.split(".", 1)[1] for e in s["entities"]) + "]" for s in page["sections"]]
        if page["tiles"]:
            parts.append("loose: " + ", ".join(e.split(".", 1)[1] for e in page["tiles"]))
        out.append(" ".join(parts))
    if plan["remove"]:
        out.append("remove: " + ", ".join(plan["remove"]))
    return out


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompts", nargs="+")
    parser.add_argument("--screen", default="Guition 10.1")
    parser.add_argument("--slug", default="fa6a7b50_esp_screen_manager")
    parser.add_argument("--agent", default="ai_task.openai_ai_task")
    parser.add_argument("--checkout", default="/Users/maxgramser/Documents/Code/esphome-cyd-display")
    parser.add_argument("--covers", action="store_true")
    parser.add_argument("--domains", help="comma-separated: only these domains go in the prompt")
    parser.add_argument("--restructure", help="page:<n> or screen: restructure the saved document's own tiles "
                        "(docs/LAYOUTBOT.md, \"Restructuring\"); the prompts are the person's words beside it")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    async with HA(*access(args.checkout)) as ha:
        inventory = await ha.ingress_get(args.slug, "api/inventory")
        screen = next(s for s in inventory["screens"] if s["name"] == args.screen)
        record = screen["page_document"]
        shape = screen["shape"]
        grid = Grid(record["sourceGrid"]["columns"], record["sourceGrid"]["rows"], shape["max_pages"], shape["max_tiles"],
                    shape["max_bar_items"])
        sections = "sections" in shape.get("modules", [])
        entities = inventory["entities"] + (FAKE_COVERS if args.covers else [])
        domains = set(args.domains.split(",")) if args.domains else None
        text = layoutbot.instructions("x", record["layout"], grid, entities, sections, domains)
        print(f"HA {ha.version}, screen {args.screen} {grid.columns}x{grid.rows}, sections {sections}, "
              f"{len(entities)} entities, prompt {len(text)} chars", flush=True)
        restructure = None
        if args.restructure:
            scope, _, number = args.restructure.partition(":")
            restructure = {"scope": scope, **({"page": int(number)} if scope == "page" else {})}
        results = []
        for prompt in args.prompts:
            started = time.monotonic()
            entry = {"prompt": prompt}
            try:
                plan, seconds = await layoutbot.ask(ha.request, prompt, record["layout"], grid, entities,
                                                           sections, args.agent, domains, restructure=restructure)
                entry.update(answer=plan, seconds=round(seconds, 1))
                if restructure:
                    checked, notes = layoutbot.restructured(plan, record["layout"], restructure, entities)
                else:
                    checked, notes, _ = layoutbot.answered(plan, record["layout"], {e["id"] for e in entities}, [], False)
                entry.update(valid=True, notes=notes, summary=summary(checked), plan=checked)
            except Exception as error:  # noqa: BLE001 - a trial reports every failure and goes on
                entry.update(valid=False, error=f"{type(error).__name__}: {error}")
            entry["total_seconds"] = round(time.monotonic() - started, 1)
            results.append(entry)
            print(json.dumps({k: entry.get(k) for k in ("prompt", "seconds", "valid", "error", "notes", "summary")},
                             ensure_ascii=False, indent=1), flush=True)
            print("reply:", (entry.get("answer") or {}).get("reply"), flush=True)
        pathlib.Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1))


asyncio.run(main())
