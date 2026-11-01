# BellBridge test report

Bring-up and acceptance tests for a manufactured board. Fill in the **Result** column as
you go, then copy the summary into the [main README](../README.md#test-results).

<!-- TODO: fill in -->

| | |
| --- | --- |
| Board revision | v1.12 |
| Boards received / tested | |
| PCBWay order (date, finish) | |
| ESPHome version | |
| Tested by, date | |

## 1. Inspection (unpowered)

| # | Check | Expected | Result |
| --- | --- | --- | --- |
| 1.1 | U1 (module) | antenna sticking out past the left edge, undamaged; silkscreen pin-1 dot beside the module's lower-left corner (the small dot on the module's shield sits at its lower right, as in Espressif's drawing) | |
| 1.2 | J2 (USB-C) | opening at the top edge; signal pads and the four shell lugs soldered | |
| 1.3 | U2, U3 | pin 1 at the dots (U2 lower right; U3 top left, just below J2) | |
| 1.4 | OK1–OK3 | pin 1 at the dots | |
| 1.5 | J1 | wire openings toward the right edge, four pins soldered | |
| 1.6 | Solder joints | no bridges at U1, J2, U3 (0.5 mm pitch) | |

## 2. Isolation and power

| # | Check | Expected | Result |
| --- | --- | --- | --- |
| 2.1 | Resistance J1 GND ↔ USB-C shell | open (meter shows OL) | |
| 2.2 | Resistance J1 DOOR, CHIME, FLOOR ↔ USB-C shell | open | |
| 2.3 | Resistance across C1 (VBUS ↔ GND), unpowered | no short | |
| 2.4 | 3.3 V across C5 or C2, powered from USB | 3.25–3.35 V | |
| 2.5 | Supply current at 5 V, Wi-Fi connected | record (typically below 100 mA) | |

## 3. Firmware and bench tests

For 3.6–3.11 use a separate 5 V source, such as a second USB supply or a lab supply, with
its minus on J1 GND. If you take it from the supply that powers BellBridge, the two grounds
are joined during the test. The tests still work, but the isolation is bypassed.

| # | Check | Expected | Result |
| --- | --- | --- | --- |
| 3.1 | USB-C to a computer | USB JTAG/serial debug unit, VID:PID 303A:1001 | |
| 3.2 | `esphome run firmware/ritto-intercom.yaml` | flashes, boots, joins Wi-Fi | |
| 3.3 | Plug in USB with TP1 and TP2 (back) bridged by tweezers, run `esptool --before no-reset chip-id`; then replug without the bridge | the chip answers (download mode); without the bridge the firmware starts | |
| 3.4 | Home Assistant | device adopted with the API key; the entities listed in `firmware/README.md` present | |
| 3.5 | Wi-Fi signal on the bench | record dBm and distance | |
| 3.6 | CHIME: 5 V for about 0.5 s | "Doorbell Main" on for 4 s | |
| 3.7 | FLOOR held at 5 V, then pulled to GND for about 0.5 s | "Doorbell Apartment" on for 4 s | |
| 3.8 | FLOOR pulled to GND, CHIME pulse within 4 s | only "Doorbell Apartment" | |
| 3.9 | DOOR: 5 V through 1 kΩ to DOOR, voltmeter DOOR ↔ GND, press "Open Door" | about 5 V idle, below 0.4 V for 0.5 s | |
| 3.10 | Same setup, unplug and replug USB, wait for the boot | DOOR stays high, no pulse | |
| 3.11 | Current into CHIME or FLOOR at 5 V (optional) | about 2.5 mA | |
| 3.12 | FLOOR pulled to GND twice, 3 s apart; CHIME pulse about 1.6 s after the second | only "Doorbell Apartment", on until 4 s after the second | |
| 3.13 | Setup of 3.9, "Door Open Duration" set to 2 s, press "Open Door"; then restart the board | DOOR below 0.4 V for 2 s; the setting is still 2 s after the restart | |
| 3.14 | Setup of 3.9, "Auto Open" on, CHIME pulse; then the sequence of 3.8 | "Doorbell Main" and DOOR low about 2 s after the pulse; the sequence of 3.8 does not open | |
| 3.15 | "Auto Open" on, then restart the board | "Auto Open" is off after the restart | |
| 3.16 | "Auto Open Time" 1 min, "Auto Open" on; then "Auto Open Time" 0, "Auto Open" on | off again after about 1 min; with 0 it stays on until switched off | |

Keep FLOOR at 5 V during the bench tests, as on the intercom. With FLOOR open, the input
reads as a held apartment button.

## 4. On the intercom

| # | Check | Expected | Result |
| --- | --- | --- | --- |
| 4.1 | Street bell | only "Doorbell Main" | |
| 4.2 | Apartment bell, short press | only "Doorbell Apartment" | |
| 4.3 | Apartment bell, long press (more than 2 s) | only "Doorbell Apartment" | |
| 4.4 | "Open Door" in Home Assistant | street door buzzes | |
| 4.5 | Handset with BellBridge connected | rings and opens the door as before | |
| 4.6 | Wi-Fi signal, installed | record dBm (−75 dBm or better is comfortable) | |
| 4.7 | Line levels with BellBridge connected (optional) | KLINGEL pulse and ETAGE idle at about 5 V | |
| 4.8 | "Auto Open" on, street bell; turn it off afterwards | street door buzzes about 2 s after the ring | |

## 5. Long-term

| # | Check | Expected | Result |
| --- | --- | --- | --- |
| 5.1 | One week in service | no false or missed rings, no unexpected reboots (uptime) | |

## Problems found

<!-- TODO: list every problem, its workaround, and whether it needs a hardware change (v1.2).
If none: "None." -->

## Photos

<!-- TODO: add to docs/images/ and link here: assembled board (top and bottom), installed
board, and optionally scope captures. Remove names and flat numbers from photos of the
intercom, and strip location data (EXIF) before committing. -->
