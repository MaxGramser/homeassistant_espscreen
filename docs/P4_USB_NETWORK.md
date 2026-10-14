# Optional USB networking on the Waveshare P4 panel

This experimental configuration turns the panel's native **USB OTG** port into a CDC-NCM
network interface. A computer can share its network connection with the panel over a USB
data cable. It is an optional firmware build, not a feature of the default Wi-Fi build.
macOS is the initial test host. Other hosts with NCM support need their own validation.
Physical enumeration, host sharing and reconnect tests are required before treating it as supported.

The separate **USB TO UART** connector remains the port for serial installation and logs.
It cannot carry this network interface. The board's RJ45/IP101 Ethernet interface is a separate,
unimplemented transport in this change.

## Enable it

Use ESPHome 2026.9.0 or newer and this branch's source. An exact ESPHome release is not required.
The USB component, its network extension and the package must come from the same revision.
Keep the existing board, Wi-Fi, API and OTA configuration.

For a local checkout, add to the screen's Override YAML, adjusting the paths to that checkout:

```yaml
external_components:
  - source: /path/to/checkout/components
    components: [network, usb_network]

packages:
  usb_network: !include /path/to/checkout/packages/hardware/wavesharep4-usb.yaml
```

The normal board entry continues to select its existing components. Only this explicit opt-in
replaces ESPHome's network helpers and brings in TinyUSB. Other boards and Wi-Fi-only builds
do not acquire these dependencies. USB networking cannot share the OTG controller with
`tinyusb:`, `usb_host:` or `logger.hardware_uart: USB_CDC`. Keep the board's UART0 logger.
This first configuration supports IPv4, USB and Wi-Fi only, without a custom `network.priority`.

## Connect the computer

1. Install the optional firmware through USB TO UART, preserving the panel's existing keys.
2. Connect a data cable from the computer to the panel's native USB OTG port.
3. Check that the computer lists a new **ESPHome USB network** Ethernet interface.
4. On macOS, open **System Settings → General → Sharing → Internet Sharing**. Share the
   working internet connection to that USB network interface. macOS supplies DHCP to the panel.
   These host settings are not changed by Tessera.
5. Read the USB address on the startup screen or under **Settings → This screen**. Confirm that
   Home Assistant can reach it. An address assigned on the USB subnet is not proof that Home
   Assistant, DNS or the internet is reachable from that subnet.

See Apple's [Internet Sharing instructions](https://support.apple.com/guide/mac-help/share-internet-connection-mac-network-users-mchlp1540/mac).
For Docker-based Home Assistant, check the published API address and media/TTS URLs too;
an address reachable only from the container's internal network will not work on the panel.

An explicitly configured local network can use `usb_network.manual_ip` with `static_ip`,
`gateway`, `subnet` and optional `dns1`. Both ends of the cable must be configured for that subnet.

## Switching and diagnostics

USB is preferred once it is attached, has an IPv4 address and its local gateway responds.
Wi-Fi stays connected as a fallback. A cable without host sharing does not displace connected
Wi-Fi, even when an old DHCP lease is still present. The panel checks the USB gateway with an
ARP request every three seconds: three unanswered requests select Wi-Fi (about seven to ten
seconds), and two consecutive replies make USB eligible again. These requests stay on USB,
so a reply through Wi-Fi cannot make a broken USB link look healthy. ICMP ping need not be
allowed by the host firewall. Unplugging or suspending USB removes it immediately.

This checks the host's local sharing interface, not its upstream internet connection or Home
Assistant's application health. If the gateway still answers but its internet connection is
down, that alone does not select Wi-Fi. A static configuration must have a reachable gateway.

The screen keeps its device identity, API key, Home Assistant entities and Tessera layout.
Do not add or bind it again when its address changes. Home Assistant's existing ESPHome
integration discovers new addresses and verifies the device identity before updating a
disconnected entry. It deliberately keeps an existing working API connection, so a session
on Wi-Fi may remain there even while USB becomes the panel's preferred outbound route.
Both networks must be reachable from Home Assistant and discovery must reach it for automatic
address recovery. USB Internet Sharing does not relay mDNS between subnets; installations with
Home Assistant on another host or isolated Docker networks need suitable routing/discovery.
Tessera does not rewrite Home Assistant's stored addresses or create replacement devices.

The optional package disables Wi-Fi's disconnected reboot timer, so a working USB-only connection
does not cause a reboot. API and other application watchdog settings are unchanged.

Startup and This screen report **USB** and its address while USB is selected. The Wi-Fi signal
indicator and Wi-Fi details are hidden then; they return when Wi-Fi is selected. A disconnected
backup radio does not produce a Wi-Fi problem overlay while USB is connected. Home Assistant
and Tessera connection status remain separate from network status.

## Implementation and attribution

- [ESPHome network extension](../components/network/README.md): a source snapshot with narrow
  USB additions. Updating ESPHome does not silently replace it. This reduces drift but still
  requires compatibility review when ESPHome core or ESP-IDF changes. New versions are allowed,
  not automatically certified by a successful version comparison.
- [Espressif esp_tinyusb 2.2.1](https://components.espressif.com/components/espressif/esp_tinyusb/versions/2.2.1)
  and [TinyUSB](https://docs.tinyusb.org/en/latest/reference/class/network.html) supply the USB
  stack and Ethernet transport. Their source and licenses remain in the managed dependencies.
- [ESP-IDF USB device support](https://docs.espressif.com/projects/esp-idf/en/latest/esp32p4/api-reference/peripherals/usb_device.html)
  supplies the P4 high-speed peripheral and `esp_netif`/lwIP integration.
- [Waveshare's board documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-4B)
  supplies connector and hardware information.

This profile selects the **high-speed** OTG controller with full-speed and high-speed NCM
descriptors from Espressif. The stock ESPHome TinyUSB controller selection must not be copied blindly:
the P4 full-speed OTG pins overlap this panel's display reset and backlight pins.
The USB VID/PID are currently Espressif development defaults; obtain an appropriate assignment
before distributing this as a USB product.

## Hardware acceptance

Compile only the P4 USB variant, then check on the actual panel and host:

- Enumeration, DHCP, native ESPHome API discovery and Tessera layout delivery over USB.
- Boot without a cable, a cable without sharing, USB unplug/replug, host sleep and panel restart.
- Turn host sharing off and on with the cable still attached and an existing DHCP lease.
- Working Wi-Fi after USB loss, and USB selection after a lease arrives or returns.
- Accurate startup/IP information and no Wi-Fi signal indication while USB is selected.
- Display, touch, UART logs and audio remain functional, including media-sized network transfers.
- Loss of the host's upstream connection is reported as an application/connectivity failure;
  it is not currently an automatic switch to Wi-Fi while USB keeps its address.

A compile proves none of these physical tests. Keep the existing working image until they pass.
