# BellBridge

**An isolated ESP32-C6 board that brings a Ritto 7630 TwinBus apartment intercom into Home Assistant.**

BellBridge connects to four terminals of the indoor station. It tells the
**apartment bell** from the **street bell** and can **open the street door**, all
locally through [ESPHome](https://esphome.io/) with no cloud involved. It is the circuit of
[duramson/ritto-esp](https://github.com/duramson/ritto-esp) turned into a
36.4 × 31.5 mm board that PCBWay assembles completely, ESP32-C6 module included.

<!-- TODO after testing: replace the status line, e.g.
> **Status:** v1.0 built and tested on a Ritto 7630 (YYYY-MM-DD), see the [test report](docs/testing.md).
-->
> [!WARNING]
> **Status:** hardware v1.0 is designed and checked, but it has not yet been built or
> tested on an intercom.

> [!NOTE]
> **v1.1** is the smaller follow-up with the same circuit, terminal order and GPIOs: see
> the [main branch](https://github.com/JayChickenK/bellbridge). Its firmware also runs on v1.0 and fixes a bell-logic bug in
> the firmware of this version.

<!-- TODO: add photos, e.g.
![BellBridge v1.0, assembled](docs/images/assembled-top.jpg)
![BellBridge installed behind a Ritto 7630](docs/images/installed.jpg)
-->

| Top (render) | Bottom (render) |
| --- | --- |
| ![BellBridge top side](docs/images/render-top.png) | ![BellBridge bottom side](docs/images/render-bottom.png) |

## Features

- **Two bells told apart:** the chime line pulses on every ring, and the floor line drops
  only on an apartment ring. The firmware combines the two into "Doorbell Main" and
  "Doorbell Apartment".
- **Door opener:** an "Open Door" button in Home Assistant pulls the opener line to bus
  ground for 500 ms.
- **Galvanic isolation:** all three lines go through optocouplers. Bus ground and USB
  ground are kept apart by a milled slot and a 1.6 mm copper-free strip on both layers.
- **Powered from USB-C (5 V), not from the bus.** USB ESD protection, 3.3 V LDO.
- **ESP32-C6-MINI-1-N4:** Wi-Fi 6 with a PCB antenna, an encrypted Home Assistant API and
  OTA updates.
- **Fully assembled by PCBWay.** The screw terminal is the only through-hole part.
- **Drop-in for ritto-esp:** same terminal order, same ESPHome node and entity names,
  so existing automations keep working.

## How it works

The Ritto 7630 shares one two-wire TwinBus with both door stations and all flats.
[ritto-esp](https://github.com/duramson/ritto-esp#reverse-engineering-the-bus) measured the
board with an oscilloscope:

| Ritto terminal | Signal | Behaviour |
| --- | --- | --- |
| 2 KLINGEL (chime) | input | about 5 V for ~500 ms on **any** ring |
| 4 ETAGE (floor) | input | idles at about 5 V, **drops to ground** while the apartment button is pressed |
| 5 door opener | output | buzzes the street door when **pulled to ground** |
| 1 / 6 GND | ground | bus ground |
| 3 +24 V | — | bus supply, **never connected to BellBridge** |

A falling ETAGE line means "apartment bell". The chime pulse that follows about 1.6 s later
is blocked for a few seconds, so a chime pulse on its own means "street door".

## Hardware at a glance

| | |
| --- | --- |
| Size | 36.4 × 31.5 mm, 2 layers, 1.6 mm, no mounting holes |
| Tallest part | screw terminal J1, 8.6 mm; the module is about 2.4 mm |
| Controller | Espressif ESP32-C6-MINI-1-N4 (4 MB flash, PCB antenna) |
| Power | USB-C, 5 V; AP2112K-3.3 LDO; USBLC6-2SC6 ESD protection |
| Inputs | CHIME and FLOOR, 1.5 kΩ / 1 W into LTV-817S optocouplers (about 2.5 mA at 5 V) |
| Output | DOOR, LTV-817S transistor to bus ground |
| Isolation | separate grounds, milled slot under the optocouplers, 1.6 mm barrier |
| Terminal | KANGNEX WJ124-3.81, 4 pins: DOOR, CHIME, FLOOR, GND |

Details, the parts list and the design checks are in [hardware/README.md](hardware/README.md).

## Wiring

| BellBridge J1 | Ritto 7630 terminal |
| --- | --- |
| DOOR | 5 (door opener) |
| CHIME | 2 (KLINGEL) |
| FLOOR | 4 (ETAGE) |
| GND | 1 or 6 (GND) |
| — | 3 (+24 V) stays unconnected |

See [docs/installation.md](docs/installation.md) before you open the intercom.

## Getting started

1. **Order** the assembled board: [docs/ordering.md](docs/ordering.md).
2. **Flash** the firmware over USB-C: [firmware/README.md](firmware/README.md).
3. **Test** it on the bench: [docs/testing.md](docs/testing.md).
4. **Install** it at the intercom: [docs/installation.md](docs/installation.md).
5. **Automate** in Home Assistant. The
   [ritto-esp automations](https://github.com/duramson/ritto-esp/tree/main/home-assistant)
   (notifications, parcel mode, personal door webhooks) work unchanged.

## Test results

<!-- TODO after testing: fill in from docs/testing.md -->

| Test | Result |
| --- | --- |
| Assembly inspection, isolation, 3.3 V rail | not yet tested |
| Flashing over USB-C, Wi-Fi signal | not yet tested |
| Bench test of CHIME, FLOOR and DOOR | not yet tested |
| Street bell, apartment bell, door opener on a Ritto 7630 | not yet tested |
| Long-term run without false triggers | not yet tested |

## Repository layout

```
hardware/    board generator (generate.py), KiCad board, BOM, CPL, PCBWay order files
firmware/    ESPHome configuration and secrets template
docs/        ordering, installation and test guides, images
```

## Credits

- [duramson/ritto-esp](https://github.com/duramson/ritto-esp): reverse engineering of the
  7630, the circuit and the ESPHome firmware this board is built on (MIT License).
- [deh0511.de TwinBus](https://deh0511.de/twinbus/) and
  [quhfan.de](https://quhfan.de/post/ritto-twinbus-7630-smart-home-assistant/): terminal
  pinout of the 7630.

## License

[MIT](LICENSE). The firmware is derived from ritto-esp, whose MIT notice is kept in
[LICENSE](LICENSE) and in the firmware file.

Ritto and TwinBus are trademarks of their respective owners. This project is not
affiliated with or endorsed by them. You build and install it at your own risk. In a rented
flat, the intercom usually belongs to the building, so ask before you modify it.
