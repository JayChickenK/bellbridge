# Changelog

## [2.0] - 2026-11-25

<!-- TODO after testing: add a line about the test result. -->

Released before the first board was built and tested. Same circuit, terminal order and
GPIOs as v1.15, in a new layout for mounting inside the Ritto 7630, with smaller parts:
Toshiba TLP293 optocouplers, the 1.5 kΩ input resistors in 0805, and the other resistors
and the 100 nF capacitors in 0402. The back silkscreen reads "BellBridge v2.0".

### Changed from v1.15

- The board is turned for the Ritto 7630: the module's antenna points up and sticks out
  5.2 mm past the top edge, and USB-C and the screw terminal sit side by side on the bottom
  edge, so both cables leave the board downward. 27.5 × 22.8 mm, 28.0 mm tall with the
  antenna (v1.15: 26.2 × 27.5 mm, 31.4 mm wide with the antenna to the left).
- The USB data lines run straight from the receptacle through U3 into the module, all on
  the front: 5.6–8.1 mm instead of 16–19 mm. U3 stays in their path.
- The 1.6 mm isolation barrier runs down the optocoupler column and steps over to the bottom
  edge between USB-C and the terminal, just below the module. The closest pads of the two
  sides are now 2.4 mm apart, a USB-C shell lug and J1's GND pin at the bottom edge
  (v1.15: 4.3 mm, across the optocouplers); copper of the two sides still keeps the full
  1.6 mm everywhere, pours included.
- J1's pins read DOOR, CHIME, FLOOR, GND from right to left. Their names stand above the
  terminal in two staggered rows, and the arrows point down at the wire openings. "NO +24V"
  sits between USB-C and the terminal.
- Every track is new. `generate.py` draws VBUS and the bus side (FLOOR and CHIME straight
  down into J1, no line crossing another) and routes the other nets; the tracks were then
  smoothed in the style of v1.15's hand-drawn tracks (45° corners wherever a cut fits, no
  stair steps, no leftover copper) and are kept in `hardware/hand_routes.json` (139 tracks
  on 19 nets). VBUS stays 0.5 mm to the regulator, 3V3 0.45/0.4 mm to the module; no track
  is narrower than 0.2 mm.
- Ground pads close together share one via (OK1's and OK2's LED-side ground pads and
  R6's, module pin 1 and C5, module pin 11 and C6, module pin 14 and C7), R10's ground runs
  straight into the USB-C shell lug below it, and the VBUS via sits between C7 and U3, so
  CC1 runs to R7 on the front without a via: 47 vias in all.
- 3V3 and VBUS keep at least 1 mm from the download-mode test pads TP1 and TP2, which get
  bridged with tweezers (v1.15: 3V3 0.7 mm from TP1); `generate.py` checks it.
- Shorter supply and reset paths, along the copper from pad centre to pad centre (v1.15 in
  brackets): C1 and C4 3.2 and 2.4 mm from the regulator's input (4.2, 6.5), C3 3.0 mm from
  its output (4.1), C5 and C2 2.5 and 4.2 mm from module pin 3 (3.3, 4.8), U3's ground via
  0.85 mm (1.7). EN reaches R8 and C6 over 2.4 and 3.6 mm on the front (11.6 and 10.1 mm,
  on the back).
- Resistors and the 100 nF capacitors in 0402 instead of 0603: R1, R4–R8, R10, R12
  (UNI-ROYAL 0402WGF, 62.5 mW; R1 dissipates about 22 mW) and C4, C5, C7 (Samsung
  CL05B104KO5NNNC, 16 V X7R). The 10 µF and 22 µF capacitors (C1, C2, C3, C6) stay 0603:
  in 0402 an X5R part keeps much less of its capacitance at 3.3–5 V, and on VBUS (C1) the
  usual 0402 10 µF part, rated 6.3 V, would leave little margin. The BOM keeps its 13
  lines.
- The 1.5 kΩ input resistors R2 and R3 in 0805 instead of 1210: Panasonic ERJ-P06F1501V
  (LCSC C543553), an anti-surge thick-film part rated 0.5 W at 70 °C like the YAGEO
  RC1210FR-071K5L before, so a CHIME or FLOOR wire on +24 V (0.35 W) stays within its
  rating up to about 95 °C ambient. KOA's SG73P2ATTD1501F (0.75 W) may replace it; a
  standard 0805 part (0.125 W) may not. LCSC had neither the Panasonic nor the YAGEO part
  in stock on 2026-11-25.
- Optocouplers Toshiba TLP293, CTR rank GB (SO4, 1.27 mm pitch; LCSC C77656), instead of
  the Lite-On LTV-357T-C: same pinout and 3,750 V<sub>rms</sub>, collector voltage 80 V
  instead of 35 V, −55 to 125 °C, 5.1 mm instead of 4.3 mm of bare board between input and
  output pads (Toshiba's land), and a CTR of 100–600 % guaranteed at 0.5 mA as well as at
  5 mA, so the bell inputs (about 2.4 mA) have more margin. R1 is 150 Ω instead of 220 Ω:
  OK1's LED gets about 12 mA, and as the TLP293's CTR stays flat up to about 20 mA, DOOR
  sinks about 12 mA or more (typically about 24 mA; the LTV-357T-C's rank C guaranteed
  200 % at 5 mA).
- A via takes GPIO18 off the module's lower right corner to the back layer, so the barrier
  step sits just below the module and the shorter optocoupler column ends above it.
- The module's lower right ground pad (U1.51) has its own via to the back pour, and
  `generate.py`'s router keeps 0.25 mm between via holes while it routes, as its final check
  already required.
- CPL, renders and the PCBWay remarks follow the new layout. The panel note now asks for
  7 mm free above each board and tabs only at two places on the left and right edges, the
  only stretches of edge with no part and no track within 1.2 mm (see docs/ordering.md).

### Firmware

- Unchanged. It runs on v1.0, v1.1, v1.12 to v1.15 and v2.0.

## [1.15] - 2026-11-23

<!-- TODO after testing: add a line about the test result. -->

Released before the first board was built and tested. Same parts, values, placement, vias and
copper pours as v1.14, with smoother tracks. The back silkscreen reads "BellBridge v1.15".

### Changed from v1.14

- Smoother tracks on 17 nets, redrawn by hand in KiCad: 98 tracks replace 123 stair-stepped
  ones. The USB data lines are about 2 mm shorter, and U3 stays in their path. The 1.6 mm
  isolation barrier and the power track widths (VBUS 0.5 mm, 3V3 0.4 mm) are unchanged.
  `hardware/hand_routes.json` holds these tracks, and `generate.py` lays them down instead
  of its own routes for those nets.
- The redrawn EN track ends its diagonal 0.25 mm earlier and turns into its via from below,
  so it keeps 1 mm from U1's ground pad like every routed track (it came within 0.79 mm).
- VBUS keeps the routing of v1.14, so both vias next to the regulator still carry the
  supply. A short GND_BUS track that lay inside a wider one at OK1 is gone; the copper is
  the same.
- `generate.py` checks clearances against the pads' real outline (rounded corners, oval
  ends), as KiCad's DRC does. The new tracks pass some pad corners at 0.20 mm, which the old
  rectangular model reported as too close.
- `generate.py` also checks hand-drawn tracks against the router's own keep-outs: no
  signal track on the front over J2's steel plate or within 1 mm of U1's ground pad, no
  signal via under the plate. KiCad's DRC does not know these rules.
- New renders of the top, the bottom and the assembled board.

## [1.14] - 2026-11-20

<!-- TODO after testing: add a line about the test result. -->

Released before the first board was built and tested. Same parts, values, placement and
copper as v1.13; only the silkscreen changes. The back silkscreen reads "BellBridge v1.14".

### Changed from v1.13

- J1's labels (DOOR, CHIME, FLOOR, GND) are 0.6 mm wide instead of 0.55 mm. KiCad caps a
  text's stroke at a quarter of its character size, so they were plotted with 0.138 mm
  lines, below PCBWay's 0.15 mm minimum; now they get the full 0.15 mm. `generate.py`
  refuses silkscreen text that would plot thinner.
- Schematic: TP1 and TP2 are left out of the bill of materials, as on the board, so a BOM
  exported from the schematic no longer lists them.
- New renders of the top, the bottom and the assembled board.

### Firmware

- OTA updates need a password again (`ota_password` in `secrets.yaml`) instead of
  `encryption: {}` under `ota:`. ESPHome 2026.8 and older, including older ESPHome Builder
  add-ons, reject that option. The Home Assistant API stays encrypted with
  `api_encryption_key`. Add `ota_password` to an existing `secrets.yaml`.

## [1.13] - 2026-11-09

<!-- TODO after testing: add a line about the test result. -->

Released before the first board was built and tested. Same parts, values and placement as
v1.12; the bus ground gets its own tracks. The back silkscreen reads "BellBridge v1.13".

### Changed from v1.12

- KiCad schematic `hardware/bellbridge.kicad_sch`, drawn from the board with the same
  references, values, footprints and net names. KiCad's ERC and its schematic-to-board check
  can now run; `generate.py` does not update the schematic.
- `generate.py` gives the project's Default net class a wire width, so the schematic's wires
  appear in KiCad's PDF and SVG plots.
- Bus ground (`GND_BUS`) is routed with tracks between OK1, OK2, OK3 and J1 (23.8 mm instead
  of 17.7 mm, 11 vias instead of 8), so these pads no longer depend on the ground pour alone.
  `generate.py` now places the bus-ground pad vias after the routing search. No other net
  changed. The EN capacitor stays beside the regulator: in the strip at pin 8 its pad would
  be boxed in by the 3V3 track to the module, which would then need two vias.

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
