# BellBridge firmware (ESPHome)

[`ritto-intercom.yaml`](ritto-intercom.yaml) is the ESPHome configuration for BellBridge v1.0.
It is the configuration of [duramson/ritto-esp](https://github.com/duramson/ritto-esp)
adapted to this board:

- ESP32-C6-MINI-1-N4: `board: esp32-c6-devkitc-1`, `flash_size: 4MB`, ESP-IDF framework.
- GPIO19 (door opener), GPIO20 (floor/apartment) and GPIO18 (chime) instead of the XIAO
  pins D8/D9/D10.
- No XIAO antenna switch (the module has a PCB antenna and no RF switch).
- Encrypted Home Assistant API, OTA password, and a Wi-Fi signal sensor.

The logic, the node name (`ritto-intercom`) and the entity names are unchanged, so
Home Assistant automations written for ritto-esp keep working.

Validated with ESPHome 2025.10.5, 2026.6.0 and 2026.9.1 (`esphome config`).
<!-- TODO after testing: "Built and flashed with ESPHome <version> on BellBridge v1.0." -->

## Entities in Home Assistant

| Entity | Meaning |
| --- | --- |
| `binary_sensor.ritto_intercom_doorbell_apartment` | apartment bell rang (on for 4 s) |
| `binary_sensor.ritto_intercom_doorbell_main` | street door bell rang (on for 4 s) |
| `button.ritto_intercom_open_door` | pulses the door opener for 500 ms |
| `sensor.ritto_intercom_wifi_signal` | Wi-Fi signal strength (diagnostic) |

The raw inputs and the opener output are internal and not exposed.

## First flash (USB-C)

1. Install ESPHome (`pip install esphome`, or use the ESPHome add-on / device builder).
2. Create the secrets file and fill it in:
   ```bash
   cp firmware/secrets.yaml.example firmware/secrets.yaml
   python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
   ```
   Put the generated key into `api_encryption_key` and choose a long `ota_password`.
   `secrets.yaml` is ignored by git; never commit or share it.
3. Connect BellBridge to the computer with a USB-C data cable. The module shows up as a
   USB serial/JTAG device (Espressif VID 303A).
4. Build and flash:
   ```bash
   esphome run firmware/ritto-intercom.yaml
   ```
   If no port is found: hold **BOOT**, tap **RESET**, release **BOOT**, and try again.
   If the board does not start after flashing, tap **RESET**.
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

## Security

The API is encrypted and OTA needs a password; without them, any device on the network
could press **Open Door** or flash other firmware. ESPHome 2026.9 and later warn that the
OTA password could be replaced by `encryption: {}`, which reuses the API key. The password
is kept because it works with every ESPHome version.
