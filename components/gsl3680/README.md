# GSL3680 external component

Vendored from the `espcontrol` repository:

- Source repository: https://github.com/jtenniswood/espcontrol
- Original license: `LICENSE.md` in this directory
- Required copyright notice: Copyright (c) 2026 jtenniswood

This copy keeps the 10-inch P4 touchscreen driver in the same release stream as the dashboard firmware so crash fixes can be shipped without waiting for the upstream branch.

Local changes:

- Decode all five points returned by the controller before calling the vendor touch tracking routine.
- Feed the watchdog during the long firmware upload to the touch controller.

The PolyForm Noncommercial License 1.0.0 applies to this directory. It is not
relicensed under the repository's top-level MIT license. See
`THIRD_PARTY_NOTICES.md` at the repository root for the distribution notice.
