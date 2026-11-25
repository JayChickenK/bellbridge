# BellBridge hardware (v2.0)

[`generate.py`](generate.py) places and routes every part, checks the result, and writes the
KiCad board and the PCBWay order files. For v2.0 the tracks of every net but VBUS were routed
by `generate.py` and then smoothed in the style of the tracks redrawn by hand for v1.15
(45° corners, no stair steps); [`hand_routes.json`](hand_routes.json) holds them, and
`generate.py` lays them down instead of its own routes for those nets. To change the board,
change the script or `hand_routes.json` and run it again (see [Regenerating](#regenerating));
edits made only in KiCad are overwritten by the next run.

## Overview

- **27.5 × 22.8 mm** board, 2 layers, 1.6 mm FR-4, no mounting holes; with the module's
  antenna sticking out past the top edge, 27.5 × 28.0 mm overall. Laid out for mounting in
  the Ritto 7630: antenna up, both cables leave at the bottom. v1.15 was 26.2 × 27.5 mm
  with the antenna to the left, v1.0 36.4 × 31.5 mm; [CHANGELOG.md](../CHANGELOG.md) lists
  what changed.
- **ESP32-C6-MINI-1-N4** module with PCB antenna, soldered by the assembler (not a plug-in
  XIAO board). It stands upright: its antenna sticks out 5.2 mm past the top edge.
- **USB-C** at the bottom edge, below the module, opening downward. As in HRO's drawing, the
  receptacle front sits 0.46 mm past the board edge.
- **Screw terminal J1** at the bottom edge, right of USB-C. Its wire openings face downward
  and the body overhangs the edge by 0.9 mm. At 8.4 mm, J1 is the tallest part; the module
  is about 2.4 mm.
- **Two grounds:** `GND_MCU` (USB, module) and `GND_BUS` (intercom) are never joined. An
  L-shaped 1.6 mm copper-free barrier on both layers separates all copper of the two sides,
  ground pours included. The optocouplers stand across it.
- **+24 V is not connected.** There is no pad and no net for it.

```
USB-C ─ USBLC6-2P6 ─ ESP32-C6-MINI-1        D+/D− run through U3 to the module
  └─ VBUS ─ AP2112K-3.3 ─ 3V3 ┘
                                     │ GPIO19     │ GPIO18     │ GPIO20
                                    OK1 (LED)    OK2 (photo)  OK3 (photo)
 GND_MCU   ════════════════ isolation barrier, 1.6 mm ═════════════════
 GND_BUS                            OK1 (photo)  OK2 (LED)    OK3 (LED)
                                     │            │ 1.5 kΩ     │ 1.5 kΩ
                                    DOOR         CHIME        FLOOR       GND
                                    └──────── J1, to the Ritto 7630 ────────┘
```

## Signals

| J1, right to left (top view) | Function | Direction | Module GPIO |
| --- | --- | --- | --- |
| DOOR | door opener (Ritto terminal 5) | output, OK1 pulls it to `GND_BUS` | GPIO19 |
| CHIME | chime, any ring (Ritto terminal 2, KLINGEL) | input | GPIO18 |
| FLOOR | apartment bell (Ritto terminal 4, ETAGE) | input | GPIO20 |
| GND | bus ground (Ritto terminal 1 or 6) | — | — |

**Inputs (OK2, OK3).** The LED sits on the bus side behind 1.5 kΩ. ritto-esp measured CHIME
and FLOOR at about 5 V (the scope traces top out around 4.8 V). That gives about 2.4 mA of
LED current, or 2.5 mA at a full 5 V. The 10 kΩ pull-ups (R4, R5) need 0.33 mA, far less
than the transistor sinks at that LED current: the TLP293's rank GB guarantees a CTR of
100–600 % at 0.5 mA as well as at 5 mA (Toshiba datasheet, table 8.1). The 1.5 kΩ resistors
(R2, R3) are Panasonic ERJ-P06F1501V, anti-surge thick-film parts in 0805 rated 0.5 W at
70 °C (derated linearly to zero at 155 °C; 27 V continuous at 1.5 kΩ), because Ritto
terminal 3 (+24 V) sits between KLINGEL and ETAGE. If a wire lands there by mistake, 15 mA
flows and each resistor takes 22.8 V and dissipates about 0.35 W, which the derating curve
allows up to about 95 °C ambient. A standard 0805 resistor (0.125 W) would not survive
that; KOA's SG73P2ATTD1501F (0805, rated 0.75 W at 70 °C) may replace the Panasonic part.
This covers a CHIME or FLOOR wire on +24 V, not the GND wire: with J1's GND on +24 V, the
LEDs of OK2 and OK3 would be driven backward (rated 5 V) and OK1's output from emitter to
collector (rated 7 V).

**Output (OK1).** GPIO19 drives the LED through 150 Ω (about 12 mA). The collector is on
DOOR and the emitter on `GND_BUS`, so the transistor pulls the opener line to bus ground.
The TLP293 is rated V<sub>CEO</sub> 80 V and 50 mA collector current. Rank GB guarantees 100
% CTR at I<sub>F</sub> = 5 mA, and Toshiba's CTR curve stays flat up to about 20 mA, so the
output sinks about 12 mA or more, typically about 24 mA (the LTV-357T-C of earlier versions:
rank C, 200 % at 5 mA, about 19 mA at 220 Ω). R6 (10 kΩ to ground) holds GPIO19 low from
reset until the firmware drives it, so the door does not buzz while the module boots. Only
while the chip itself is held in reset is the pin's weak internal pull-up on (ESP32-C6 IO
MUX table, GPIO19 = SDIO_CLK); against 10 kΩ it lifts the pin to only about 0.6 V, below the
LED's forward voltage, so OK1 stays off. While the firmware switches the LED on (12 mA), R6
draws another 0.33 mA.

**Straps and test pads.** GPIO8 and GPIO9 are strapping pins. GPIO8 has a 10 kΩ pull-up
(R12); GPIO9 relies on the module's internal pull-up, as in the MINI-1 datasheet's
peripheral schematic (figure 7: GPIO9 only goes to a jumper to ground). Espressif's chip
design guide recommends an external pull-up on GPIO9; one would not fit beside the module's
GPIO9 pin in the v1.1 layout, and v2.0 keeps the circuit. There are no buttons: `esptool`
puts the module into download mode over the USB serial/JTAG port, and replugging USB resets
it. If a broken firmware stops that from working, bridge the two bare pads on the back, TP1
(BOOT, GPIO9) and TP2 (GND), with tweezers while you plug in USB; the module then starts in
download mode. The test pads sit on the back, under the module's lower right corner near its
GPIO9 pin. No 3V3 or VBUS copper comes within 1 mm of them (3V3 is 1.3 mm from TP2), so a
slip of the tweezers cannot short the supply to ground; the nearest other copper is GPIO18's
tented via, 0.7 mm from TP1, an input that a slip cannot harm. EN has 10 kΩ (R8) and
10 µF (C6, the same part as C1 and C3), which holds the chip in reset for about 0.1 s after
power-up; Espressif gives 10 kΩ + 1 µF as values to adjust to the power-up timing. Pin 8 is
on the module's left side, right beside R8 and C6, so EN reaches them over 2.4 and 3.6 mm of
track on the front, without a via. GPIO15 stays open.

**Firmware.** The firmware uses the three GPIOs directly. The XIAO ESP32-C6 antenna switch
(GPIO3, GPIO14) does not exist here, so do not use the `seeed_xiao_esp32c6` board profile;
see [../firmware](../firmware/).

## Power

USB-C only, 5 V, with all four VBUS contacts connected. CC1 and CC2 each have 5.1 kΩ to
ground (R7, R10); SBU1/SBU2 stay open.

U3 (USBLC6-2P6) sits in the D+/D− path between the receptacle and the module, 2.7–5.2 mm
of track from the receptacle's pads and 2.2–3.0 mm from the module's pins (distances in
this section run along the copper from pad centre to pad centre). D+ runs through U3's
pin 1, and D− taps pin 4 with a 0.6 mm stub. Both lines stay on the front and run straight
up into the module's pins 18 and 17, 5.6–8.1 mm from the receptacle's pads, so a discharge
into the receptacle meets U3 before it reaches the module. U3's ground pin has its own via
0.85 mm away. Its VBUS pin and C7 (100 nF to ground) sit on one line, 1.65 mm apart, as in
the layout figure of ST's USBLC6-2 datasheet; VBUS arrives through a via between the two,
and C7's ground pad shares the via under module pin 14 (1.3 mm of track). CC1 runs from
its receptacle pad to R7 on the front, below C7, without a via.

The AP2112K-3.3 (600 mA, stable with ceramic capacitors) makes 3.3 V; its EN is tied to
VBUS. Capacitors: 10 µF + 100 nF at the input (C1, C4; 3.2 mm and 2.4 mm of track from
VIN), 10 µF at the output (C3, 3.0 mm from VOUT), and 100 nF + 22 µF at module pin 3 (C5,
C2; 2.5 mm and 4.2 mm from the pin, in the column along the left edge). VBUS runs as 0.5 mm
tracks from both pairs of receptacle VBUS pads to the regulator: the left pair on the
front, the right pair through a via and 4.8 mm on the back. On the front it passes C1 and
C4 on its way into VIN. The regulator's EN pin and the branch up to the via beside C7 are
0.4 mm (on into C7 as well), the last piece into U3's VBUS pin 0.3 mm. The 3V3 trunk runs
at 0.45 mm from VOUT up the left edge, beside the capacitor column, with 0.4 mm stubs into
C3, R8 and C5; from C5, 0.4 mm tracks go into pin 3 and on to C2. The feeds to the pull-up
resistors are 0.3 mm: R12's from the trunk at C3, on the back along the module's lower edge;
R4's and R5's from module pin 3, on the back across the module's upper half, clear of the
test pads.

The module draws up to 382 mA while it transmits (802.11b at 20.5 dBm, Espressif's
datasheet), and Espressif asks for a supply of at least 0.5 A; the AP2112K delivers
600 mA. Pin 3 has 22 µF + 100 nF, as in Espressif's reference circuit, another 10 µF sits
at the regulator output, and the module has its own decoupling under the shield. At 5 V in
and about 100 mA on average, the regulator
dissipates about 0.17 W, roughly 30 °C above ambient in SOT-23-5 (184 °C/W). Wi-Fi
transmits in short bursts, and the AP2112K limits its current and shuts down when
overheated.

Espressif's design guide also suggests footprints for 22–33 Ω series resistors and
capacitors to ground on D+/D− near the module, unpopulated at first. They are left out:
the USB serial/JTAG port is full-speed (12 Mbit/s), where neither these parts nor the
guide's 90 Ω differential impedance (not reachable on a 1.6 mm two-layer board) matter
over 10 mm of line. UART0 is not brought out
either; the guide wants it for Espressif's RF test firmware, while BellBridge loads its
firmware over USB, with TP1/TP2 forcing download mode.

## Layout rules

- **Isolation:** the barrier line is an L. It runs from the top edge down through the
  optocouplers, 23.2 mm from the left edge, to 10.85 mm above the bottom edge (just below
  the module), crosses above the input resistors R2 and R3 to 15.7 mm from the left edge,
  and runs down to the bottom edge between USB-C and the terminal. All copper of either
  ground domain keeps 0.8 mm from this line on both layers, so the two domains are at
  least 1.6 mm apart. Each optocoupler has 5.1 mm of bare board between its LED and
  transistor pads; the closest pads of the two sides are 2.4 mm apart, a USB-C shell lug
  and J1's GND pin at the bottom edge (v1.15: 4.3 mm, across the optocouplers). GPIO18
  leaves the module through a via beside its pin and runs on the back to R4 and OK2, so no
  track passes under the module's corner and the step can sit right below the module. The
  TLP293 is rated 3,750 V<sub>rms</sub> input to output, with 5.0 mm creepage and
  clearance. There is no milled slot. Both sides are low voltage (5 V USB, 24 V bus), so
  this is functional isolation, not mains safety isolation. `generate.py` checks pads,
  tracks, vias and the ground pour outlines on every run.
- **Bus side:** drawn by `generate.py` rather than routed, so that no line crosses another.
  FLOOR and CHIME drop straight from R3 and R2 into J1 on the front. LED_FLOOR leaves OK3
  on the front, runs down a lane between the barrier and the optocouplers' bus pads and
  along the barrier step above R2 and R3, and enters R3 from above; LED_CHIME drops from
  OK2 into R2. On the back, the bus ground runs from vias beside OK3 and OK2 (OK1 joins OK2
  on the front) down the same lane, under the resistors through a via between R3 and R2,
  and down the barrier side into J1's GND pin, around the "GND ISOLATED" text; DOOR runs
  from a via beside OK1 down the right side into J1. Seven vias on the bus side, and every
  piece of the bus ground pour on the front has one of them.
- **Antenna:** Espressif's ESP32-C6 hardware design guidelines want the module's PCB
  antenna outside the base board, with the antenna's feed point close to the board edge,
  and metal in the housing at least 15 mm away from the antenna. The module stands
  upright, so the antenna section sticks out 5.2 mm past the top edge. The MINI-1's feed
  is at its pin-1 end (the two legs of the antenna in the module datasheet's drawing),
  here the left end of the antenna: the module's pin-1 side, pins 1–11, runs down the left
  side 3.2 mm from the left edge (v1.15: 2.0 mm from the bottom edge). The column beside
  it holds C5 and C2 for pin 3 and the EN network for pin 8. The guide gives no distance in
  mm. The board's top edge is 0.2 mm into the antenna section and 0.5 mm from the module's
  last pads. The antenna section is a KiCad rule area (`Antenna keep-out`, F.Cu and B.Cu:
  no tracks, vias, pads or pours). A row of ground vias along the module's antenna end
  (every 1.6 mm, between its ground pad row and its exposed pad) ties both ground layers
  together there, as the guide asks.
- **USB-C receptacle:** its steel bottom plate lies on the board (HRO's drawing: 6.28 mm
  back from the front face). No signal copper runs under it on the front and no signal via
  sits under it, only ground vias, so a scratch in the solder mask cannot short a line to
  the grounded shell. CC1 and CC2 leave their pads backward, away from the opening, and
  run on the front to R7 and R10. The D+ link between B6 and A6 has to cross in front of
  the pads, because the pins alternate D+, D−, D+, D− at 0.5 mm pitch and no via fits
  between them. It runs 0.2 mm in front of the pads, under the plastic rear part of the
  receptacle.
- **Chip parts:** KiCad's 0402 lands (R_0402_1005Metric, C_0402_1005Metric) for the
  resistors and the 100 nF capacitors, KiCad's 0603 land for the 10 µF and 22 µF capacitors,
  which keep more of their capacitance at 3.3–5 V in 0603 (X5R loses capacitance under DC
  bias), and KiCad's 0805 land (R_0805_2012Metric) for the 0.5 W input resistors R2/R3.
- **Thermal spokes:** the ground pads of the chip parts (C1–C7, R6, R7, R10) join the
  pours through 0.4 mm spokes instead of solid copper, so both ends of each part heat
  alike during reflow and the parts do not stand up (tombstoning). The module's and the
  ICs' ground pads stay solid.
- **Vias** keep at least 0.15 mm of copper-free mask to every SMD pad and are tented.
  Their holes keep 0.30 mm to the holes of J1 and the receptacle lugs. No via sits under
  silkscreen text. Vias may sit under the module (tented) but keep 0.15 mm of mask to its
  pads. Ground pads close together share one via: OK1's and OK2's LED-side ground pads
  and R6's, module pin 1 and C5, module pin 11 and C6, module pin 14 and C7; R10's ground
  pad runs straight into the USB-C receptacle's shell lug below it. 47 vias in all.
- **Test pads:** TP1 and TP2 get bridged with tweezers, so 3V3 and VBUS keep at least 1 mm
  from them (tracks on the back, vias on either layer); the router and `generate.py`'s
  checks hold every track to it.
- **Optocoupler land:** Toshiba's recommended land for the TLP293 (datasheet section 13):
  0.8 × 1.2 mm pads at 1.27 mm pitch, rows 6.3 mm apart. KiCad has no footprint for it;
  its `SOP-4_4.4x2.6mm_P1.27mm` has the same body (used for the 3D renders) but longer pads
  4.75 mm apart.
- **U3 land:** KiCad's `SOT-666` (outer pads 0.5 × 0.375 mm, centre pads 0.65 × 0.3 mm,
  1.2 mm between the pad columns). ST's datasheet suggests 0.30 × 0.99 mm pads with
  0.62 mm between the rows. Both cover the leads of the SOT-666 outline in ST's table 3;
  only KiCad's leaves room for D+ and D− between the pad columns.
- **J2 land:** HRO's recommended layout (TYPE-C-31-M-12 drawing, 2020-12-08). Signal pads
  0.30 and 0.60 mm wide run from 0.50 to 1.64 mm behind the line through the two 0.60 mm
  locating holes, which are 5.78 mm apart. The power and ground pads sit at ±2.40 and
  ±3.20 mm. KiCad's library footprint has 1.45 mm pads further back, the power and ground
  pads 0.05 mm further out, and 0.65 mm holes. The shell-lug slots follow HRO too:
  0.6 × 1.7 mm for the 1.10 mm lugs beside the pad row and 0.6 × 1.4 mm for the 0.80 mm
  lugs near the opening (KiCad's library: 1.2 mm), so every lug has 0.6 mm of play along
  its slot. The pads keep KiCad's 0.2 mm copper ring (1.0 × 2.1 and 1.0 × 1.8 mm; HRO:
  0.9 mm wide). HRO puts the hole line 5.79 mm from the board edge, so the receptacle
  front overhangs by 0.46 mm.

## Parts

All parts are on the top side. The BOM (`bom.csv`, the same table as `bom.xlsx`) uses the
columns of PCBWay's BOM quotation and has one line per part number. TP1 and
TP2 are bare copper pads on the back, not parts; they are left out of the BOM and CPL.

| Ref | Part | Manufacturer | MPN | LCSC |
| --- | --- | --- | --- | --- |
| U1 | ESP32-C6 module, 4 MB flash, PCB antenna | Espressif | ESP32-C6-MINI-1-N4 | C5736265 |
| U2 | LDO 3.3 V 600 mA, SOT-23-5 | Diodes Incorporated | AP2112K-3.3TRG1 | C51118 |
| U3 | USB ESD protection, 2 lines + VBUS, SOT-666 | STMicroelectronics | USBLC6-2P6 | C15999 |
| J1 | Screw terminal, 4 pins, 2.54 mm, 8.4 mm high | DORABO | DB125-2.54-4P-GN-S | C918122 |
| J2 | USB-C receptacle | HRO | TYPE-C-31-M-12 | C165948 |
| OK1–OK3 | Optocoupler, SO4, CTR rank GB (100–600 %), 80 V | Toshiba | TLP293(GB-TPL,E | C77656 |
| R1 | 150 Ω 1 % 62.5 mW 0402 | UNI-ROYAL | 0402WGF1500TCE | C25082 |
| R2, R3 | 1.5 kΩ 1 % 0.5 W 0805, anti-surge | Panasonic | ERJ-P06F1501V | C543553 |
| R4, R5, R6, R8, R12 | 10 kΩ 1 % 62.5 mW 0402 | UNI-ROYAL | 0402WGF1002TCE | C25744 |
| R7, R10 | 5.1 kΩ 1 % 62.5 mW 0402 | UNI-ROYAL | 0402WGF5101TCE | C25905 |
| C1, C3, C6 | 10 µF 10 V X5R 0603 | Samsung | CL10A106KP8NNNC | C19702 |
| C2 | 22 µF 6.3 V X5R 0603 | Samsung | CL10A226MQ8NRNC | C59461 |
| C4, C5, C7 | 100 nF 16 V X7R 0402 | Samsung | CL05B104KO5NNNC | C1525 |

Every part has its LCSC number in the BOM's "Vendor Part #" column, and its "Customer Reply"
column tells PCBWay per line what may be substituted: resistors and capacitors by parts of
the same value, size, rating and dielectric; R2/R3 must stay 0805 and at least 0.5 W (KOA
SG73P2ATTD1501F fits). Do not substitute U1, U3, OK1–OK3, J1 or J2 (J2's land follows HRO's
drawing).

J1's footprint, overhang, CPL centre and silkscreen follow the DORABO drawing
DB125-2.54-XXP-C-S (2022-04-06): pitch 2.54 mm, 0.50 × 0.85 mm pins in 1.20 mm holes
(2.0 mm pads), body 6.30 mm deep and 8.40 mm high, the pin row 3.10 mm from the wire face
and 3.20 mm from the back. Wires 26–18 AWG (1.0 mm²), stripped 4–5 mm, M1.6 screws at
most 0.1 N·m. Rated 150 V / 7 A (UL), −40 to +105 °C.

## Files

| File | Content |
| --- | --- |
| `generate.py` | the design: placement, routing, checks, all outputs |
| `hand_routes.json` | the tracks of every net but VBUS (v2.0: routed by `generate.py`, then smoothed), laid down by `generate.py` instead of its own routes; delete a net's entry when its pads move, so that `generate.py` routes it again |
| `bellbridge.kicad_pcb`, `bellbridge.kicad_pro` | KiCad board (ground pours are unfilled; press **B** in KiCad to fill them) |
| `bellbridge.kicad_sch` | schematic of the board with the same references, values, footprints and net names, so KiCad's ERC and its schematic-to-board check can run; `generate.py` does not write it, so update it by hand after a board change |
| `bom.csv`, `bom.xlsx` | bill of materials in the columns of PCBWay's BOM quotation: Item #, *Designator, *Qty, Manufacturer, *Mfg Part #, Description / Value, Vendor Part # (LCSC), *Package/Footprint, Mounting Type, Customer Reply (what may be substituted); the same table as text and as a spreadsheet |
| `cpl.csv` | placement: origin at the board's lower-left corner, mm, Y up, KiCad rotation; J1 at its body centre |
| `pcbway/` | Gerbers, drill files, job file, BOM, CPL, `PCBWAY-REMARKS.txt` and the order zip `bellbridge-v2.0-pcbway.zip` |
| `drc-report.json` | KiCad DRC report of the last run |
| `plots/` | quick previews from `generate.py` (net colours, both sides) |

## Regenerating

Requirements: Python 3.9 or later (tested with 3.11 and 3.13); Pillow (optional, only for
`plots/`); KiCad 10 for the Gerbers and the DRC (tested with 10.0.6 and 10.0.8). On Windows
`generate.py` finds a default KiCad 10 install; elsewhere `kicad-cli` must be on `PATH`.

```bash
cd hardware
python generate.py
```

The run takes well under a minute. It places all parts and routes them with a deterministic
router, then puts the tracks from `hand_routes.json` in place of the routes of those nets.
Then it runs its own checks: isolation barrier, clearances, antenna keep-out, J2's steel
plate and U1's ground pad, supply copper 1 mm from the test pads, via-to-pad and via-to-hole
distances and pin-1 marks. It writes
the board, BOM, CPL and previews. After that, `kicad-cli` exports Gerbers, drill and
position files and runs the DRC with refilled pours. `pcbway/` and the order zip are written
only when the DRC reports **0 violations and 0 unconnected items**. The output ends with:

```
python-drc 0
kicad-drc violations 0 unconnected 0 {}
zip .../pcbway/bellbridge-v2.0-pcbway.zip
```

## Design verification (v2.0)

v2.0 has the circuit and nets of v1.15 in a new layout, with Toshiba TLP293 optocouplers
(R1 150 Ω instead of 220 Ω), the 1.5 kΩ input resistors in 0805, the other resistors and the
100 nF capacitors in 0402, and every track new (see [CHANGELOG.md](../CHANGELOG.md)).

- `generate.py` checks for v2.0: 0 errors. KiCad 10.0.8 DRC with all severities and
  refilled pours: 0 violations, 0 unconnected items. KiCad's schematic-to-board check finds
  no difference in nets or parts; it only names the 27 unconnected pins differently.
- The nets rebuilt from the Gerber copper and the plated holes match the schematic's
  netlist (47 nets, 133 pins). Measured on the Gerbers: 0.20 mm smallest gap between nets,
  0.20 mm narrowest track, 0.175 mm via ring, 0.62 mm between holes, 0.475 mm copper to
  edge.
- Measured on the KiCad-filled board: the two grounds stay 1.60 mm apart on both layers,
  pours included, along the whole L-shaped barrier; no signal copper on the front under the
  USB-C shell's steel plate and no signal via under it; on the front, nothing but module
  ground within 1 mm of U1's ground pad; U3 in the D+/D− path; VBUS keeps a 0.5 mm path to
  the regulator and 3V3 a 0.4 mm path to the module; all 47 vias have copper on both
  layers.
- Track shapes: 139 tracks on 19 nets in `hand_routes.json`; against the router's output,
  1 right-angle bend (no 45° cut fits there) instead of 38, and no stair steps or hairpins
  (10 and 1); no leftover copper.
- 0402 parts: KiCad's library lands, checked against the KiCad 10 footprints; each CPL
  position sits on its part's pads with the rotation matching pin 1; LCSC lists all four
  part numbers (UNI-ROYAL 0402WGF1002TCE, 0402WGF5101TCE, 0402WGF1500TCE, Samsung
  CL05B104KO5NNNC) in stock. R1 dissipates about 22 mW of its 62.5 mW.
- R2/R3: KiCad's R_0805_2012Metric land; Panasonic ERJ-P06F1501V, 1 %, 0.5 W at 70 °C
  (derated to zero at 155 °C), 400 V limiting voltage, AEC-Q200; each CPL position sits on
  its part's pads with the rotation matching pin 1. LCSC lists it as C543553 but had none
  in stock on 2026-11-25 (nor the YAGEO 1210 part used before); PCBWay buys through its own
  channels, and KOA's SG73P2ATTD1501F (0805, rated 0.75 W at 70 °C) is allowed instead.
  LCSC had no Samsung CL10A106KP8NNNC (C1, C3, C6) in stock that day either; the BOM
  allows any 10 µF 10 V X5R 0603 in its place.
- Datasheet review before release, against the manufacturers' PDFs: the module's 53 pins,
  land, boot straps (GPIO8 pulled up, GPIO9 to TP1, GPIO15 ignored with unburnt eFuses) and
  peripheral circuit (Espressif MINI-1 datasheet v1.5, chip datasheet v1.6, hardware design
  guidelines: antenna placement, 10 µF and ESD at the power entry); AP2112K pinout and
  ratings (Diodes); USBLC6-2P6 pinout and SOT-666 land (ST); TLP293 pins, land and ratings
  (Toshiba Rev. 6.0); USB-C land against HRO's drawing (2020-12-08) and J1 against
  DORABO's (2022-04-06); ERJ-P06 and SG73P ratings (Panasonic, KOA); the part-number codes
  of the Samsung capacitors and UNI-ROYAL resistors; every LCSC number against its part.
  The firmware passes ESPHome 2026.11.0's configuration check.
- TLP293: land and pins (1 anode, 2 cathode, 3 emitter, 4 collector) from Toshiba's
  datasheet (Rev. 6.0, 2019-11-29), checked in the board and against the CPL rotations; LCSC
  lists TLP293(GB-TPL,E with about 48,000 in stock. The schematic's symbol keeps KiCad's
  LTV-357T drawing (same pins), renamed to TLP293.
- Placement: J1's body clears a mated USB-C plug (overmold up to 12.35 mm wide) by
  0.5 mm; the antenna section is free of copper on both layers.

v1.15 keeps the parts, vias and copper pours of v1.14 and replaces 123 tracks on 17 nets with
98 smoother ones, redrawn by hand in KiCad (`hand_routes.json`). VBUS keeps its v1.14 routing.

- `generate.py` checks for v1.15: 0 errors, with clearances now measured against the pads'
  real outline (rounded corners, oval ends), and the keep-outs of J2's steel plate and U1's
  ground pad checked for hand-drawn tracks too. KiCad 10.0.8 DRC with all severities and
  refilled pours: 0 violations, 0 unconnected items; the schematic-to-board check finds no
  difference in nets or parts.
- Track shapes on the 17 redrawn nets (v1.14 in brackets): 21 % of the track length at 45°
  (2 %), 4 right-angle corners (52), no stair steps (11), 4 pieces under 0.3 mm (35), 234 mm
  of track (243); no leftover copper.
- The nets rebuilt from the Gerber copper and the plated holes match the schematic's
  netlist (47 nets, 133 pins). The isolation between the two grounds stays at 1.60 mm on
  both layers, pours included; no signal copper lies under the USB-C shell's steel plate; U3
  stays in the D+/D− path; VBUS keeps a 0.5 mm path to the regulator and 3V3 a 0.4 mm path to
  the module; every via has copper on both layers. Measured on the Gerbers: 0.20 mm smallest
  gap between nets, 0.175 mm via ring, 0.475 mm copper to edge.

v1.14 changes only the silkscreen: J1's labels are 0.6 mm wide instead of 0.55 mm, so KiCad
plots them with 0.15 mm lines (it caps a text's stroke at a quarter of its character size,
which gave 0.138 mm). Regenerated, its copper, solder mask, paste, outline and drill files,
BOM and CPL are the same as v1.13's (only dates and the KiCad version in the file headers
differ).

- `generate.py` checks for v1.14: 0 errors. KiCad 10.0.8 DRC with all severities and
  refilled pours: 0 violations, 0 unconnected items. KiCad's schematic-to-board check finds
  no difference in nets or parts; it only names the 27 unconnected pins differently.
- An independent check that starts from the order files alone: the nets rebuilt from the
  Gerber copper and the plated holes match the schematic's netlist (47 nets, 133 pins).
  Measured on the Gerbers: 0.20 mm smallest gap between nets, 0.20 mm narrowest track,
  0.175 mm via ring, 0.36 mm between holes, 0.475 mm copper to edge, 0.10 mm narrowest
  mask web; every silkscreen line at least 0.15 mm (the arrows are filled shapes); paste
  only on pads; each CPL position on its part's pads, with the rotation matching pin 1.

v1.13 routes the bus ground (`GND_BUS`) with tracks between OK1, OK2, OK3 and J1: with the bus
ground pour removed as a test, every bus-ground pad stays connected (v1.12: 6 connections
missing). All other nets and every part are unchanged from v1.12.

- `generate.py` checks for v1.13: 0 errors. KiCad 10.0.6 DRC with all severities and
  refilled pours: 0 violations, 0 unconnected items.

v1.12 changes three part values, the PCBWay panel note and the version on the back
silkscreen. Regenerated, its copper, solder mask, paste, outline and drill files and the CPL
are the same as v1.1's (only the revision and date attributes in the file headers differ),
so the v1.1 checks below still hold.

- `generate.py` checks for v1.12: 0 errors. KiCad 10.0.6 DRC with all severities and
  refilled pours: 0 violations, 0 unconnected items.
- The new 22 µF capacitor (Samsung CL10A226MQ8NRNC, LCSC C59461) uses the same 0603 land
  as the other capacitors; LCSC lists it as 22 µF ±20 %, 6.3 V, X5R.

Done for v1.1 before ordering:

- `generate.py` checks: 0 errors. KiCad 10.0.6 DRC with all severities and refilled
  pours: 0 violations, 0 unconnected items.
- An independent review of the KiCad-filled board (pcbnew geometry), 70 checks: outline,
  the turned module (antenna past the left edge with 2.6 of its 71 mm² over the board,
  feed end 2.0 mm from the bottom edge, pads 0.5 mm from the edge), no copper under the
  antenna on either layer and the KiCad rule area there, the ground vias along the
  antenna end, pin and optocoupler nets, isolation of at least 1.6 mm on both layers
  including pours, J2 against HRO's drawing, power path widths, decoupling distances, U3
  in the D+/D− path with C7 at its VBUS pin, no signal copper under the USB-C shell, thermal
  spokes on the 0603 ground pads, two VBUS vias, via distances to pads and holes, pin-1 dots,
  J1 orientation, labels and arrows, the test pads, silkscreen, and BOM/CPL against the
  board (the BOM in PCBWay's quotation columns, CSV and XLSX alike).
- Every footprint except J1 compared pad by pad with the KiCad 10 library, and U1 also with
  Espressif's own KiCad footprint: same copper. The exceptions are J2's signal pads,
  locating holes and the two shell-lug slots near the opening, which follow HRO's drawing
  on purpose (see Layout rules).
- Part fit: every part's datasheet body at maximum size lies inside its courtyard, and
  no two parts come closer than 0.45 mm (pads and bodies; J1 to R3 0.6 mm). A mated USB-C
  plug (overmold up to 12.35 × 6.5 mm) clears the board and every part. J1 (8.4 mm) is the
  tallest part, then J2 (3.3 mm) and the module (2.4 mm).
- Every part checked against its manufacturer's datasheet (Espressif, Diodes, ST, HRO,
  DORABO, Lite-On, YAGEO, UNI-ROYAL, Samsung): pinout, land pattern, ratings and the
  part-number coding of value, tolerance, voltage and dielectric.
- Pin functions of U1, U2, U3 and OK1–OK3 compared with KiCad's symbols. KiCad's
  LTV-357T symbol has unnamed pins; the board follows Lite-On's 1 anode, 2 cathode,
  3 emitter, 4 collector.
- Firmware: the GPIOs are the same as on v1.0. Compiled with ESPHome 2026.11.0 for the
  ESP32-C6, with only ESPHome's note on the OTA password as a warning; not yet flashed
  (see [../firmware/README.md](../firmware/README.md)).

Still open: the built board. See [../docs/testing.md](../docs/testing.md).

## Differences from ritto-esp

Same circuit as the ritto-esp perfboard build: same terminal order (door opener, chime,
floor, ground), same polarity, the same GPIOs (XIAO D8 = GPIO19, D9 = GPIO20, D10 = GPIO18),
a resistor in front of the door-opener LED (150 Ω here, 220 Ω there), and an isolated bus
side. Differences:

- 1.5 kΩ input resistors instead of 680 Ω: 2.4 mA instead of about 5 mA, and the CHIME
  and FLOOR inputs survive their wire landing on +24 V (not the GND wire, see Signals).
- External 10 kΩ pull-ups on GPIO18 and GPIO20; `pullup: true` in the firmware does no harm.
- 10 kΩ from GPIO19 to ground, so the opener stays off during boot.
- TLP293 (CTR rank GB, SO4) instead of a PC817.
- ESP32-C6-MINI-1-N4 module instead of a XIAO ESP32-C6, plus USB ESD protection.
