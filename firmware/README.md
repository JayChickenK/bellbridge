# BellBridge firmware (ESPHome)

[`ritto-intercom.yaml`](ritto-intercom.yaml) is the ESPHome configuration for BellBridge
(v1.0 and v1.1 use the same GPIOs).
It is the configuration of [duramson/ritto-esp](https://github.com/duramson/ritto-esp)
adapted to this board:

- ESP32-C6-MINI-1-N4: `board: esp32-c6-devkitc-1`, `flash_size: 4MB`, ESP-IDF framework.
- GPIO19 (door opener), GPIO20 (floor/apartment) and GPIO18 (chime) instead of the XIAO
  pins D8/D9/D10.
- No XIAO antenna switch (the module has a PCB antenna and no RF switch).
- Encrypted Home Assistant API and OTA updates, both with the API key.
- The bell logic runs in scripts with mode `restart`, so a repeated ring extends the 4 s
  window. In ritto-esp a second copy ran in parallel, and two presses on the apartment
  bell 2.5–4 s apart could report a false "Doorbell Main".
- Additions: adjustable door-opener pulse, an [Auto Open](#auto-open) switch and
  diagnostics.

The node name (`ritto-intercom`) and the entity names of ritto-esp are unchanged, so
Home Assistant automations written for ritto-esp keep working; the new entities come on
top.

Needs ESPHome 2026.9.0 or later for the OTA encryption (2026.8.2 and older reject it).
Validated with ESPHome 2026.9.0, 2026.9.1 and 2026.10.0 (`esphome config`). Compiled
without warnings with ESPHome 2026.9.1 (ESP-IDF 5.5.5): the image takes 862 kB, 47 % of
the 1.75 MB app partition, so OTA updates have room; RAM use is 32 %.
<!-- TODO after testing: "Built and flashed with ESPHome <version> on BellBridge v1.1." -->

## Entities in Home Assistant

| Entity | Meaning |
| --- | --- |
| `binary_sensor.ritto_intercom_doorbell_apartment` | apartment bell rang (on until 4 s after the last ring) |
| `binary_sensor.ritto_intercom_doorbell_main` | street door bell rang (on until 4 s after the last ring) |
| `button.ritto_intercom_open_door` | pulses the door opener for the Door Open Duration |
| `number.ritto_intercom_door_open_duration` | length of the opener pulse, 0.2–5 s, default 0.5 s (configuration) |
| `switch.ritto_intercom_auto_open` | while on, every street ring opens the door 2 s later; off after the Auto Open Time and on every restart |
| `number.ritto_intercom_auto_open_time` | how long Auto Open stays on, 0–1440 min, default 30; 0 keeps it on until switched off (configuration) |
| `button.ritto_intercom_restart` | restarts the board (configuration) |
| `sensor.ritto_intercom_wifi_signal` | Wi-Fi signal strength (diagnostic) |
| `sensor.ritto_intercom_uptime` | time since the last start (diagnostic) |
| `sensor.ritto_intercom_chip_temperature` | ESP32-C6 chip temperature (diagnostic) |
| `sensor.ritto_intercom_ip_address`, `sensor.ritto_intercom_connected_ssid` | IP address and Wi-Fi name (diagnostic) |
| `sensor.ritto_intercom_esphome_version` | ESPHome version of the firmware (diagnostic) |

The raw inputs and the opener output are internal and not exposed.

## First flash (USB-C)

1. Install ESPHome 2026.9 or later (`pip install esphome`, or use the ESPHome add-on /
   device builder).
2. Create the secrets file and fill it in:
   ```bash
   cp firmware/secrets.yaml.example firmware/secrets.yaml
   python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
   ```
   Put the generated key into `api_encryption_key`; it also secures OTA updates.
   `secrets.yaml` is ignored by git; never commit or share it.
3. Connect BellBridge to the computer with a USB-C data cable. The module shows up as a
   USB serial/JTAG device (Espressif VID 303A).
4. Build and flash:
   ```bash
   esphome run firmware/ritto-intercom.yaml
   ```
   `esptool` switches the module into download mode over USB by itself; BellBridge has no
   buttons. If no port is found or flashing fails: unplug the board, bridge the two bare
   pads on the back, **TP1 (BOOT)** and **TP2 (GND)**, with tweezers, plug the cable in,
   remove the tweezers and try again. If the board does not start after flashing, unplug
   it and plug it in again.
5. In Home Assistant the device appears under *Settings → Devices & services*. Enter
   the API key from `secrets.yaml` when asked.

Later updates go over the air: `esphome run firmware/ritto-intercom.yaml` and choose the
network target. Logs: `esphome logs firmware/ritto-intercom.yaml`.

## Replacing a ritto-esp node

Delete the old XIAO node in Home Assistant before you adopt BellBridge. Both use the name
`ritto-intercom`, so the entities get the same IDs again and existing automations keep
working.

To run BellBridge next to an existing node, or to give it another name, change `name:`
and `friendly_name:` at the top of the YAML file. The entity IDs change to match.

## Auto Open

**Auto Open** is a switch in Home Assistant: turn it on and off by hand, from a dashboard
or in automations, for example when you expect someone. While it is on, every street ring
opens the street door 2 s later, without anyone pressing a button. The apartment bell
never triggers it; its chime pulse stays blocked as usual.

It turns itself off after **Auto Open Time** (default 30 minutes; 0 keeps it on until you
switch it off). A new time set while it is on starts the countdown again. It is also off
after every restart: after a power cut, an OTA update, the **Restart** button, and when
Home Assistant has been away for 15 minutes (ESPHome then restarts the board). Anyone who
rings while it is on gets in, so leave it off otherwise and limit who can switch it in
Home Assistant.

The delay after the ring is the substitution `auto_open_delay` at the top of the YAML
file. Check it on your intercom ([testing.md](../docs/testing.md), 4.8): if the door does
not buzz while the Ritto is still ringing, raise it.

## Security

The API and OTA updates are encrypted with the same key (`api_encryption_key`); without
it, no device on the network can press **Open Door**, switch on **Auto Open** or flash
other firmware. ESPHome 2026.8 and older reject `encryption: {}` under `ota:`; there,
use `password: !secret ota_password` instead and add `ota_password` to `secrets.yaml`.
