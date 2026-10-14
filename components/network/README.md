# Optional USB network extension

These six source files are ESPHome **2026.9.0**, commit
`c6e4c87e525dd343e470d8dea368957a002f6505`, with additions to `util.h`, `util.cpp` and
`network_component.cpp`: recognise USB, report its address, and select USB only after it has an IP and a reachable gateway,
otherwise select connected Wi-Fi. The existing ESPHome default-route arbiter handles switching.
The original [ESPHome source](https://github.com/esphome/esphome/tree/c6e4c87e525dd343e470d8dea368957a002f6505/esphome/components/network)
and its MIT/Python and GPLv3/runtime license are retained in `LICENSE`.

Only an explicit `external_components` selection of `network` and `usb_network` uses this copy.
Normal board builds keep ESPHome's own component. USB requires ESPHome 2026.9.0 or newer,
not an exact release. A newer version is allowed, but is not automatically considered tested.
No files in the installed ESPHome package are patched. Keeping this component here makes its
behaviour reproducible; it does not remove its dependencies on ESPHome core and ESP-IDF.

This is an experimental compatibility layer, not an upstream ESPHome USB networking API.
It should be replaced by upstream interface support when available. Before changing its source
version, review API, mDNS, default-route and disconnect behaviour and repeat the physical USB tests.
The initial USB component permits Wi-Fi fallback but rejects other interfaces and a custom
`network.priority` list. A DHCP request that has not received an address does not displace Wi-Fi.
