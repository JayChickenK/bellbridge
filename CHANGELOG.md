# Changelog

## [1.12] - 2026-11-01

<!-- TODO after testing: add a line about the test result. -->

Released before the first board was built and tested. The board of v1.1 with three part
values changed; copper, solder mask, paste, drill files and CPL are the same. The back
silkscreen reads "BellBridge v1.12".

### Changed from v1.1

- R6, the GPIO19 pull-down: 10 kΩ instead of 100 kΩ, the same part as the pull-ups.
  While the chip is held in reset, the pin's weak pull-up now lifts GPIO19 to only about
  0.6 V, so the door optocoupler's LED stays off (v1.1: under 0.1 mA). R6 draws 0.33 mA
  while the door opener is on.
- C6 on EN: 10 µF instead of 1 µF, the same part as C1 and C3; about 0.1 s of reset delay
  at power-up.
- C2 at module pin 3: 22 µF instead of 10 µF (Samsung CL10A226MQ8NRNC), the value of
  Espressif's reference circuit.
- PCBWay counts: 13 unique parts (v1.1: 14), still 25 placements.
- PCBWay panel note: 7 mm free left of each board instead of 6 mm. The antenna (5.2 mm)
  and the J1 overhang of the board to its left (0.9 mm) are at the same height, so 6 mm
  let them touch.
- `generate.py` writes the order files with LF line endings on every platform; kicad-cli
  on Windows writes CRLF.

### Firmware

- No functional change (comments only); it runs on v1.0, v1.1 and v1.12.

## [1.1] - 2026-10-31

<!-- TODO after testing: add a line about the test result. If v1.0 was never built, say
so under [1.0]. -->

Released before the first board was built and tested. A smaller board with the same
circuit and terminal order: 26.2 × 27.5 mm, and 31.4 × 27.5 mm with the module's antenna,
which sticks out past the left edge. v1.0 was 36.4 × 31.5 mm (now 25 % less overall and
37 % less board area).

### Changed from v1.0

- Optocouplers LTV-357T-C (SO-4) instead of LTV-817S-TA1-C (SMDIP-4), and no milled slot.
  The 1.6 mm copper-free barrier is now a straight line through the optocouplers; their
  pad rows are 4.3 mm apart (v1.0: 8 mm).
- Input resistors R2/R3: 1.5 kΩ, 0.5 W in 1210 (YAGEO RC1210FR-071K5L) instead of 1 W in
  2512. A wire on +24 V still stays below the rating (0.35 W).
- All other resistors and capacitors in 0603 instead of 0805.
- Screw terminal DORABO DB125-2.54-4P-GN-S (2.54 mm pitch, 8.4 mm high, wires
  26–18 AWG) instead of KANGNEX WJ124-3.81. It overhangs the right edge by 0.9 mm.
- USB-C at the top edge, directly above the module. Its land follows HRO's drawing:
  signal pads 1.14 mm long and 0.5 mm further forward than KiCad's, power and ground pads
  0.05 mm further in, 0.60 mm locating holes, and 1.4 mm long slots for the two shell lugs
  near the opening (KiCad: 1.2 mm), so all four lugs have 0.6 mm of play. The receptacle
  front overhangs the top edge by 0.46 mm.
- The module is turned 90°: its antenna sticks out 5.2 mm past the left edge, and the
  antenna's feed end sits at the board's lower-left corner, 2.0 mm from the bottom edge,
  as Espressif's ESP32-C6 hardware design guidelines recommend. v1.0 had the module
  upright with bare board under the antenna. The antenna section is a KiCad rule area on
  both layers, so KiCad's DRC keeps copper off the 0.2 mm of it that lies over the board.
  A column of ground vias runs along the module's antenna end.
- USB ESD array USBLC6-2P6 (SOT-666) in the D+/D− path between the receptacle and the
  module, instead of a USBLC6-2SC6 on side branches. A discharge into the receptacle now
  meets U3 before the module. A 100 nF capacitor (C7) at U3's VBUS pin follows the layout
  figure in ST's datasheet.
- No BOOT and RESET buttons and no R9. GPIO9 uses the module's internal pull-up; two bare
  pads on the back (TP1 BOOT, TP2 GND) force download mode when bridged while USB is
  plugged in. Replugging USB resets the board.
- Vias stay clear of silkscreen labels, and via holes keep 0.30 mm to pad holes.
- No signal copper under the USB-C receptacle's steel bottom plate: CC1 runs on the back
  to R7, and the D+ link sits under the receptacle's plastic rear part.
- Thermal spokes on the ground pads of the 0603 parts (C1–C7, R6, R7, R10) against
  tombstoning, and a second VBUS via next to the regulator.
- BOM in the columns of PCBWay's BOM quotation, as `bom.csv` and `bom.xlsx`: the LCSC number
  as "Vendor Part #" and, per line, what PCBWay may substitute in "Customer Reply". J2 joins
  the parts that must not be substituted, since its land follows HRO's drawing.
- PCBWay counts: 14 unique parts and 25 placements (22 SMD, 2 large SMD parts U1 and J2,
  1 through-hole part J1).

### Firmware (for v1.0 and v1.1)

- Fixed: two presses on the apartment bell 2.5–4 s apart could report a false "Doorbell
  Main". The bell logic now runs in scripts with mode `restart`, so a repeated ring extends
  the 4 s window instead of running a second copy in parallel. Entity names are unchanged.
- "Door Open Duration": length of the opener pulse, 0.2–5 s (default 0.5 s), kept across
  restarts.
- "Auto Open": a switch in Home Assistant; while it is on, every street ring opens the
  door 2 s later. It turns itself off after "Auto Open Time" (0–1440 min, default 30,
  0 = never) and on every restart.
- Diagnostics: restart button, uptime, chip temperature, IP address, Wi-Fi name and
  ESPHome version.
- OTA updates are encrypted with the API key instead of an OTA password; `ota_password`
  is gone from `secrets.yaml`.

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
