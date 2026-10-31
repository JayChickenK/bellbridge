# Installing BellBridge at a Ritto 7630

> [!CAUTION]
> The TwinBus runs on about 24 V DC and is shared by every flat in the building. A short
> between bus lines can disturb the whole intercom system. **Never connect Ritto
> terminal 3 (+24 V) to BellBridge.** In a rented flat the intercom usually belongs to the
> building, so ask before you modify it.

Flash and bench-test the board first ([firmware/README.md](../firmware/README.md),
[testing.md](testing.md)), so that any problem shows up before the intercom is open.

## You need

- BellBridge, flashed and tested
- a USB-C cable and a 5 V USB power supply (0.5 A is plenty)
- four short wires, 26–18 AWG (up to 1.0 mm², solid or flexible), stripped 4–5 mm for J1
- a small flat screwdriver for J1's M1.6 screws (at most 0.1 N·m)
- double-sided foam tape or another insulating mount (the board has no mounting holes)
- a multimeter

## Terminals

The 7630 board's connection points (from
[ritto-esp](https://github.com/duramson/ritto-esp#reverse-engineering-the-bus), confirmed
by [quhfan.de](https://quhfan.de/post/ritto-twinbus-7630-smart-home-assistant/) and
[deh0511.de](https://deh0511.de/twinbus/)):

| Ritto terminal | Signal | BellBridge J1 |
| --- | --- | --- |
| 1 | GND | GND (1 or 6, one is enough) |
| 2 | KLINGEL, chime: ~5 V pulse on any ring | CHIME |
| 3 | +24 V bus voltage | **not connected** |
| 4 | ETAGE, floor: idles at ~5 V, drops to GND on an apartment ring | FLOOR |
| 5 | door opener: buzzes when pulled to GND | DOOR |
| 6 | GND | GND (1 or 6, one is enough) |

J1's pins from top to bottom (top view, wire openings on the right) are DOOR, CHIME,
FLOOR, GND, as printed beside the terminal.

## Steps

1. **Measure before connecting anything.** With the intercom idle, measure against
   terminal 1: terminal 2 about 0 V, terminal 4 about 5 V, terminal 3 about 24 V. Ring the
   street bell: terminal 2 rises to about 5 V for about half a second. If your board
   behaves differently, stop and compare with the ritto-esp measurements.
2. **Wire it.** Connect DOOR to 5, CHIME to 2, FLOOR to 4 and GND to 1 (or 6), as in the
   ritto-esp build. Check that no wire touches terminal 3 or a neighbouring contact.
3. **Place the board.** The module's antenna is the part beyond its metal shield that sticks
   out 5.2 mm past the left edge, along its lower half. Espressif recommends at least 15 mm
   of free space around it in all directions inside the housing: keep metal (back boxes,
   mounting plates, the intercom's chassis), the housing wall and the bus wiring that far
   away, and do not put the board in a metal box. Do not push, wedge or rest the board on
   the antenna.
   Insulate the bottom side with foam tape: the J1 pins, the USB shell lugs and the two
   test pads are exposed there. J1 stands 8.4 mm tall plus the wires, and the USB-C plug
   at the top edge needs room for its cable bend.
4. **Power it** from the USB-C supply. Within a few seconds the node is online in Home
   Assistant.
5. **Test it at the door** (section 4 of [testing.md](testing.md)). Then check that the
   handset still rings and opens the door as before.
6. **Close the housing** and check that the lid and the handset still fit.

<!-- TODO after installing: describe where the board fits in or behind the 7630 housing,
how the USB cable is routed, and add a photo (docs/images/installed.jpg). Blur names and
flat numbers on the photo. -->
