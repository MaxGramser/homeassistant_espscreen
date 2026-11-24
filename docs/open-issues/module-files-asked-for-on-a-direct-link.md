# A page opened on a screen asks for the plugins' modules of the other screens

## The symptom
Open the editor straight on a screen's page (a link to it, or a reload there). The page asks the add-on for the list of
modules of every screen that runs a plugin (`api/plugins/modules`), and fetches each module file those lists name
(`api/plugins/<id>/module`), also when the screen that is open runs no plugin and nothing draws with them. Seen on
2026-11-24 in a browser's own list of requests, on a home with four screens of which three run plugins: three lists
and two module files on a load of the fourth screen's page.

Nobody sees it. No firmware is made from those files (since cc96f3df a preview that has left makes none), and a
browser keeps a module file for a day, so it costs a few small requests and some tens of kilobytes once a day per
browser.

## What we know
- The overview draws every screen with a preview of its own (`HomeView.vue`, one `FirmwarePreview` per screen). A page
  that opens on a screen shows the overview for a moment first: `App.vue` shows it until the session has read the
  address and chosen the screen.
- Each of those previews starts by asking `codeFor(screen)` in `web/src/stores/plugin-code.ts`. Since 2cb269b6 that
  waits for the add-on's list of plugins, then reads the screen's module list and fetches its files. The overview is
  gone by then, but `codeFor` does not know who asked: it finishes.
- `FirmwarePreview.vue` looks whether it is still there after `codeFor` and makes no firmware then. That look comes
  after the files were fetched, not before.

## Ruled out
- Not asking for the code of the overview's previews at all: the overview draws plugin tiles with it when it stays.
- Leaving the cache out: the module files are kept by the browser on purpose (docs/EMULATOR_ARCHITECTURE.md,
  "Plugins"), which is why this costs so little after the first time.

## The fix
One change of order in `FirmwarePreview.vue`'s start: wait for the plugins' first answer (`plugins.loadPlugins()`,
which `codeFor` waits for too), look whether the preview is still there, and only then ask `codeFor`. A preview that
left while the add-on's plugins were on their way then asks for nothing.

Its test, in `web/tests/plugin-faces.spec.ts` beside "makes no firmware for a preview that left while the plugins were
awaited": a preview unmounted before the add-on's plugins answer asks for no module list and no module file
(`getJson` and `api` are not called for it), and one that stays asks once.

A second, larger way would be to not show the overview at all while the address names a screen (`App.vue`). That also
saves mounting four previews for a moment, and is a change to how the page starts: its own piece of work.

## Pointers
`web/src/components/FirmwarePreview.vue` (`onMounted`), `web/src/stores/plugin-code.ts` (`codeFor`, `read`),
`web/src/stores/plugins.ts` (`loadPlugins`), `web/src/App.vue` (which view is shown), `web/tests/plugin-faces.spec.ts`.
