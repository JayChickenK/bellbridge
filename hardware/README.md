# BellBridge hardware (v1.12)

The board is not drawn by hand. [`generate.py`](generate.py) places and routes every part,
checks the result, and writes the KiCad board and the PCBWay order files. To change the
board, change the script and run it again (see [Regenerating](#regenerating)).

## Overview

- **26.2 × 27.5 mm** board, 2 layers, 1.6 mm FR-4, no mounting holes; with the module's
  antenna sticking out past the left edge, 31.4 × 27.5 mm overall. v1.0 was
  36.4 × 31.5 mm; [CHANGELOG.md](../CHANGELOG.md) lists what changed.
- **ESP32-C6-MINI-1-N4** module with PCB antenna, soldered by the assembler (not a plug-in
  XIAO board). It is turned 90°: its antenna sticks out 5.2 mm past the left edge, and the
  antenna's feed end sits at the board's lower-left corner, as Espressif recommends.
- **USB-C** at the top edge, directly above the module. As in HRO's drawing, the receptacle
  front sits 0.46 mm past the board edge.
- **Screw terminal J1** on the right edge. Its wire openings face outward and the body
  overhangs the edge by 0.9 mm. At 8.4 mm, J1 is the tallest part; the module is about
  2.4 mm.
- **Two grounds:** `GND_MCU` (USB, module) and `GND_BUS` (intercom) are never joined. A
  straight 1.6 mm copper-free barrier on both layers separates all copper of the two sides,
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

| J1, top to bottom (top view) | Function | Direction | Module GPIO |
| --- | --- | --- | --- |
| DOOR | door opener (Ritto terminal 5) | output, OK1 pulls it to `GND_BUS` | GPIO19 |
| CHIME | chime, any ring (Ritto terminal 2, KLINGEL) | input | GPIO18 |
| FLOOR | apartment bell (Ritto terminal 4, ETAGE) | input | GPIO20 |
| GND | bus ground (Ritto terminal 1 or 6) | — | — |

**Inputs (OK2, OK3).** The LED sits on the bus side behind 1.5 kΩ. ritto-esp measured
CHIME and FLOOR at about 5 V (the scope traces top out around 4.8 V). That gives about
2.4 mA of LED current, or 2.5 mA at a full 5 V. The 10 kΩ pull-ups (R4, R5) need 0.33 mA,
far less than the transistor sinks at that LED current. The 1.5 kΩ resistors (R2, R3) are
YAGEO RC1210 parts rated 0.5 W at 70 °C (derated linearly to zero at 155 °C; 27 V
continuous at 1.5 kΩ), because Ritto terminal 3 (+24 V) sits between KLINGEL and ETAGE.
If a wire lands there by mistake, 15 mA flows and each resistor takes 22.8 V and
dissipates about 0.35 W, which the derating curve allows up to about 95 °C ambient.

**Output (OK1).** GPIO19 drives the LED through 220 Ω (about 9.5 mA). The collector is on
DOOR and the emitter on `GND_BUS`, so the transistor pulls the opener line to bus ground.
The LTV-357T is rated V<sub>CEO</sub> 35 V and 50 mA collector current. The suffix -C is
CTR rank C, 200–400 % at I<sub>F</sub> = 5 mA (Lite-On datasheet, rank table), so the
output sinks about 19 mA. R6 (10 kΩ to ground) holds GPIO19 low from reset until the
firmware drives it, so the door does not buzz while the module boots. Only while the chip
itself is held in reset is the pin's weak internal pull-up on (ESP32-C6 IO MUX table,
GPIO19 = SDIO_CLK); against 10 kΩ it lifts the pin to only about 0.6 V, below the LED's
forward voltage, so OK1 stays off. While the firmware switches the LED on (9.5 mA), R6
draws another 0.33 mA.

**Straps and test pads.** GPIO8 and GPIO9 are strapping pins. GPIO8 has a 10 kΩ pull-up
(R12); GPIO9 relies on the module's internal pull-up, as in the MINI-1 datasheet's
peripheral schematic (figure 7: GPIO9 only goes to a jumper to ground). Espressif's chip
design guide recommends an external pull-up on GPIO9; one would not fit beside the
module's GPIO9 pin without moving R12 and the USB parts. There are no buttons: `esptool`
puts the module into download mode over the USB serial/JTAG port, and replugging USB
resets it. If a broken firmware stops that from working, bridge the two bare pads on the
back, TP1 (BOOT, GPIO9) and TP2 (GND), with tweezers while you plug in USB; the module then
starts in download mode. The test pads sit on the back right of the module, beside its
GPIO9 pin. EN has 10 kΩ (R8) and 10 µF (C6, the same part as C1 and C3), which holds the
chip in reset for about 0.1 s after power-up; Espressif gives 10 kΩ + 1 µF as values to
adjust to the power-up timing. Pin 8 is on the module's bottom side, so EN runs 11 mm on
the back to R8 and C6 beside the regulator. GPIO15 stays open.

**Firmware.** The firmware uses the three GPIOs directly. The XIAO ESP32-C6 antenna switch
(GPIO3, GPIO14) does not exist here, so do not use the `seeed_xiao_esp32c6` board profile;
see [../firmware](../firmware/).

## Power

USB-C only, 5 V, with all four VBUS contacts connected. CC1 and CC2 each have 5.1 kΩ to
ground (R7, R10); SBU1/SBU2 stay open.

U3 (USBLC6-2P6) sits in the D+/D− path right below the receptacle, 2–5 mm from its pads.
D+ runs through U3's pin 1, and D− taps pin 4 0.65 mm from its track (measured to the pad
centre). Both lines then go to the back, run under the module and come up inside its pad
ring next to pins 18 and 17 (15–16 mm from U3), so a discharge into the receptacle meets U3
before it reaches the module. U3's ground pin has its own via 1.2 mm away. Its VBUS pin
runs 0.8 mm to C7 (100 nF to ground, with its own ground via), as in the layout figure of
ST's USBLC6-2 datasheet, and is tied to the VBUS via above it.

The AP2112K-3.3 (600 mA, stable with ceramic capacitors) makes 3.3 V; its EN is tied to
VBUS. Capacitors: 10 µF + 100 nF at the input (C1, C4; 4.0 mm and 6.3 mm of track from
VIN), 10 µF at the output (C3, 4.1 mm from VOUT), and 100 nF + 22 µF at module pin 3 (C5,
C2; 1.4 mm and 2.6 mm from the pin, in a strip along the bottom edge). VBUS runs as 0.5 mm
tracks, on the back from the receptacle to the regulator column, where two vias bring it
to the front, and 0.4 mm in the short
pieces at the right-hand receptacle pad, C4 and the regulator's EN pin; U3's VBUS track is
0.3 mm between U3's pins and 0.4 mm on to C7. The 3V3 trunk runs at 0.45 mm from VOUT along
the bottom edge, between the module's bottom pins and the capacitor strip, with the last
piece into pin 3 and the stubs into C2, C3 and C5 at 0.4 mm; the feeds to the pull-up
resistors are 0.3 mm.

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
over 20 mm of line. UART0 is not brought out
either; the guide wants it for Espressif's RF test firmware, while BellBridge loads its
firmware over USB, with TP1/TP2 forcing download mode.

## Layout rules

- **Isolation:** one straight barrier line runs from the top edge to the bottom edge at
  x = 23.45 mm, through the optocouplers. All copper of either ground domain keeps 0.8 mm
  from this line on both layers, so the two domains are at least 1.6 mm apart. The
  optocouplers' pad rows are 4.3 mm apart, and no MCU-side pad comes closer than 3.2 mm
  to a bus-side pad. The LTV-357T is rated 3,750 V<sub>rms</sub> input to output. There
  is no milled slot. Both sides are low voltage (5 V USB, 24 V bus), so this is functional
  isolation, not mains safety isolation. `generate.py` checks pads, tracks, vias and the
  ground pour outlines on every run.
- **Antenna:** Espressif's ESP32-C6 hardware design guidelines (section 1.4.7, figures
  23–25) want the module's PCB antenna outside the base board, with the antenna's feed
  point at the board edge. The MINI-1's feed is at its pin-1 end (the two legs of the
  antenna in the module datasheet's drawing), so the module is turned 90° (figure 24,
  position 5): the antenna section sticks out past the left edge, and the module's feed
  end, pins 1–11, runs along the bottom edge 2.0 mm from it (the guide allows 2 mm; the
  strip holds C5 and C2 for pin 3). The board's left edge is 0.2 mm into the antenna
  section and 0.5 mm from the module's last pads. The antenna section is a KiCad rule area
  (`Antenna keep-out`, F.Cu and B.Cu: no tracks, vias, pads or pours). A column of ground
  vias along the module's antenna end (every 1.6 mm, between its ground pad column and its
  exposed pad) ties both ground layers together there, as the guide asks.
- **USB-C receptacle:** its steel bottom plate lies on the board (HRO's drawing: 6.28 mm
  back from the front face). No signal copper runs under it on the front and no signal via
  sits under it, only ground vias, so a scratch in the solder mask cannot short a line to
  the grounded shell. CC1 leaves its pad through a via behind the pad row and runs on the
  back to R7. The D+ link between B6 and A6 has to cross in front of the pads, because the
  pins alternate D+, D−, D+, D− at 0.5 mm pitch and no via fits between them. It runs
  0.2 mm in front of the pads, under the plastic rear part of the receptacle.
- **Thermal spokes:** the ground pads of the 0603 parts (C1–C7, R6, R7, R10) join the
  pours through 0.4 mm spokes instead of solid copper, so both ends of each part heat
  alike during reflow and the parts do not stand up (tombstoning). The module's and the
  ICs' ground pads stay solid.
- **Vias** keep at least 0.15 mm of copper-free mask to every SMD pad and are tented.
  Their holes keep 0.30 mm to the holes of J1 and the receptacle lugs. No via sits under
  silkscreen text. Vias may sit under the module (tented) but keep 0.15 mm of mask to its
  pads.
- **Optocoupler land:** KiCad's `SO-4_4.4x3.6mm_P2.54mm` (2.0 × 0.64 mm pads, 6.3 mm row
  pitch). Lite-On recommends 0.8 mm pads on a 6.5 mm row pitch; the KiCad pads cover those
  lead feet and add room for the fillets.
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
| OK1–OK3 | Optocoupler, SO-4, CTR rank C | Lite-On | LTV-357T-C | C119091 |
| R1 | 220 Ω 0603 | UNI-ROYAL | 0603WAF2200T5E | C22962 |
| R2, R3 | 1.5 kΩ 0.5 W 1210 | YAGEO | RC1210FR-071K5L | C309587 |
| R4, R5, R6, R8, R12 | 10 kΩ 0603 | UNI-ROYAL | 0603WAF1002T5E | C25804 |
| R7, R10 | 5.1 kΩ 0603 | UNI-ROYAL | 0603WAF5101T5E | C23186 |
| C1, C3, C6 | 10 µF 10 V X5R 0603 | Samsung | CL10A106KP8NNNC | C19702 |
| C2 | 22 µF 6.3 V X5R 0603 | Samsung | CL10A226MQ8NRNC | C59461 |
| C4, C5, C7 | 100 nF 50 V X7R 0603 | Samsung | CL10B104KB8NNNC | C1591 |

Every part has its LCSC number in the BOM's "Vendor Part #" column, and its "Customer Reply"
column tells PCBWay per line what may be substituted: resistors and capacitors by parts of
the same value, size, rating and dielectric; R2/R3 must stay 1210 and at least 0.5 W. Do not
substitute U1, U3, OK1–OK3, J1 or J2 (J2's land follows HRO's drawing).

J1's footprint, overhang, CPL centre and silkscreen follow the DORABO drawing
DB125-2.54-XXP-C-S (2022-04-06): pitch 2.54 mm, 0.50 × 0.85 mm pins in 1.20 mm holes
(2.0 mm pads), body 6.30 mm deep and 8.40 mm high, the pin row 3.10 mm from the wire face
and 3.20 mm from the back. Wires 26–18 AWG (1.0 mm²), stripped 4–5 mm, M1.6 screws at
most 0.1 N·m. Rated 150 V / 7 A (UL), −40 to +105 °C.

## Files

| File | Content |
| --- | --- |
| `generate.py` | the design: placement, routing, checks, all outputs |
| `bellbridge.kicad_pcb`, `bellbridge.kicad_pro` | KiCad board (ground pours are unfilled; press **B** in KiCad to fill them) |
| `bellbridge.kicad_sch` | schematic of the board with the same references, values, footprints and net names, so KiCad's ERC and its schematic-to-board check can run; `generate.py` does not write it, so update it by hand after a board change |
| `bom.csv`, `bom.xlsx` | bill of materials in the columns of PCBWay's BOM quotation: Item #, *Designator, *Qty, Manufacturer, *Mfg Part #, Description / Value, Vendor Part # (LCSC), *Package/Footprint, Mounting Type, Customer Reply (what may be substituted); the same table as text and as a spreadsheet |
| `cpl.csv` | placement: origin at the board's lower-left corner, mm, Y up, KiCad rotation; J1 at its body centre |
| `pcbway/` | Gerbers, drill files, job file, BOM, CPL, `PCBWAY-REMARKS.txt` and the order zip `bellbridge-v1.12-pcbway.zip` |
| `drc-report.json` | KiCad DRC report of the last run |
| `plots/` | quick previews from `generate.py` (net colours, both sides) |

## Regenerating

Requirements: Python 3.9 or later (tested with 3.11 and 3.13); Pillow (optional, only for
`plots/`); KiCad 10 for the Gerbers and the DRC (tested with 10.0.6). On Windows
`generate.py` finds a default KiCad 10 install; elsewhere `kicad-cli` must be on `PATH`.

```bash
cd hardware
python generate.py
```

The run takes well under a minute. It places all parts and routes them with a deterministic
router. Then it runs its own checks: isolation barrier, clearances, antenna keep-out,
via-to-pad and via-to-hole distances and pin-1 marks. It writes the board, BOM, CPL and
previews. After that, `kicad-cli` exports Gerbers, drill and position files and runs the
DRC with refilled pours. `pcbway/` and the order zip are written only when the DRC reports
**0 violations and 0 unconnected items**. The output ends with:

```
python-drc 0
kicad-drc violations 0 unconnected 0 {}
zip .../pcbway/bellbridge-v1.12-pcbway.zip
```

## Design verification (v1.12)

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
- Firmware: the GPIOs are the same as on v1.0. Compiled without warnings with ESPHome
  2026.9.1 for the ESP32-C6; not yet flashed (see [../firmware/README.md](../firmware/README.md)).

Still open: the built board. See [../docs/testing.md](../docs/testing.md).

## Differences from ritto-esp

Same circuit as the ritto-esp perfboard build: same terminal order (door opener, chime,
floor, ground), same polarity, the same GPIOs (XIAO D8 = GPIO19, D9 = GPIO20,
D10 = GPIO18), 220 Ω in front of the door-opener LED, and an isolated bus side.
Differences:

- 1.5 kΩ input resistors instead of 680 Ω: 2.4 mA instead of about 5 mA, and the inputs
  survive a wire on +24 V.
- External 10 kΩ pull-ups on GPIO18 and GPIO20; `pullup: true` in the firmware does no harm.
- 10 kΩ from GPIO19 to ground, so the opener stays off during boot.
- LTV-357T-C (CTR rank C, SO-4) instead of a PC817.
- ESP32-C6-MINI-1-N4 module instead of a XIAO ESP32-C6, plus USB ESD protection.
