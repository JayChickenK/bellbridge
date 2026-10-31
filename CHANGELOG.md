# Changelog

## [1.0] - 2026-10-31

<!-- TODO after testing: add a line about the test result. -->

First revision meant for manufacturing, released before the first board was built and
tested. During development it was called KLEIN3. v1.1 is its smaller follow-up.

### Changed in the final review before ordering

- Renamed to BellBridge: silkscreen, KiCad title block and file names.
- The first of U1's nine ground pads is now 1.45 mm like the others, as in Espressif's land
  pattern (it was 0.8 mm).
- Silkscreen strokes are 0.15 mm, PCBWay's minimum (they were 0.12 mm).
- The BOM has one line per part number, with quantities and descriptions.
- The optocoupler footprint carries its real name, KiCad's `SMDIP-4_W9.53mm_Clearance8mm`
  (the copper did not change).
- `generate.py` finds KiCad in the standard install folders or on `PATH`.

## Development revisions (not released)

### KLEIN3

- Lower screw terminal: KANGNEX WJ124-3.81-04P-14-00A (8.6 mm high) instead of a Phoenix
  MKDS (13.8 mm). Wire openings face the right edge with 1.15 mm overhang, and the
  silkscreen shows the body outline and arrows toward the openings.
- USB ESD protection U3 (USBLC6-2SC6) in the corner above the USB-C receptacle.
- CC pull-downs R7/R10 changed to 0603 to make room. The receptacle moved 0.2 mm down and
  the buttons 0.12 mm. CC1/CC2 run on the bottom layer.
- Button contact pairs checked against the XKB drawing.
- No reverse-polarity protection on the bus inputs (not needed).

### KLEIN2

- USB-C turned so it opens at the left edge (KLEIN1 had the opening facing into the board).
- 10 kΩ pull-up on the strapping pin GPIO8.
- A 1.6 mm isolation barrier, checked for all copper on both layers, not only at the slot.
- Pin-1 marks placed and checked automatically (KLEIN1 had the OK3 mark at pin 2).
- Buttons wired on two diagonal pads, without bridge tracks.
- AP2112K-3.3 LDO instead of an AMS1117 with damping network.
- 0.5 mm power tracks, decoupling capacitors at their pins.
- Nothing beside the antenna; the module end is 0.1 mm from the board edge.
- Terminal labels beside the terminal, J1 centroid at its body centre, and no vias in pads.

### KLEIN1

- First layout of the compact board, derived from a larger 43.6 × 33.3 mm assembly board.
