# A screen's firmware update does not look at its plugins first

## The symptom
A screen's Update builds the new firmware with the plugins the screen has. A plugin that no longer builds on the new
firmware fails in the compiler, and only then does the app say that the plugin needs an update. Nothing stops the
build before it starts, and nothing updates the plugin in the same build.

## What we know
The app and the firmware decide whether a plugin fits by its plugin API version: the same major, a minor at most the
firmware's, and no break between them (`api_fits`, PLUGIN_API_BREAKS `{0: (4,)}`). Plugin API 0.24 removed forms
(`on_touch`, an action with a key and a value, `saver: picture`, `memory: {bytes}`) without a break entry, so a plugin
written for an older minor that uses one passes the check and fails in the compiler. Known case: the Microplant
plugin's `tessera::action` with a key and a value, reported in its own repository. The first-party plugins at their
versions of release 0.4.90 use none of those forms; on the upgrade test of 0.4.91 they built and ran on the new
firmware (2026-10-29). After a failed build `Plugins.blame` names the plugin and the version the index offers.

## Ruled out
A problem for the first-party plugins at the release: they built.

## Candidates
- Before an Update, check each plugin record against the target firmware and offer its update first, or take the
  plugin update into the same build.
- A per-release minimum plugin API in the index, or break entries for removed forms, so `api_fits` knows.

## The deciding experiment
A screen with a plugin that uses a removed form (or a test fixture of one), its Update on the new firmware: the app
should say so before the build and offer the plugin's update, and the build should not start on a version that cannot
build.

## Pointers
screen_manager/app/updates.py (`update_one`), screen_manager/app/plugins.py (`blame`, `fits`, `sidecar`),
screen_manager/app/plugin_manifest.py (`api_fits`, PLUGIN_API_BREAKS), components/smart_display/__init__.py
(PLUGIN_API, PLUGIN_API_BREAKS), docs/PLUGINS.md.
