# BellBridge hardware (v1.0)

The board is not drawn by hand. [`generate.py`](generate.py) places and routes every part,
checks the result, and writes the KiCad board and the PCBWay order files. To change the
board, change the script and run it again (see [Regenerating](#regenerating)).

## Overview

- **36.4 × 31.5 mm**, 2 layers, 1.6 mm FR-4, no mounting holes.
- **ESP32-C6-MINI-1-N4** module with PCB antenna, soldered by the assembler (not a plug-in
  XIAO board).
- **USB-C** on the left edge, above the module in the top view. The receptacle front sits
  0.25 mm past the board edge.
- **Screw terminal J1** on the right edge. Its wire openings face outward and the body
  overhangs the edge by 1.15 mm. At 8.6 mm, J1 is the tallest part; the module is about
  2.4 mm.
- **Two grounds:** `GND_MCU` (USB, module) and `GND_BUS` (intercom) are never joined. An
  unplated milled slot runs under the optocouplers. A 1.6 mm copper-free barrier on both
  layers separates all copper of the two sides, ground pours included.
- **+24 V is not connected.** There is no pad and no net for it.

```
USB-C ─ USBLC6-2SC6 ─ AP2112K-3.3 ─ ESP32-C6-MINI-1
                                     │ GPIO19     │ GPIO18     │ GPIO20
                                    OK1 (LED)    OK2 (photo)  OK3 (photo)
 GND_MCU   ═════════════ isolation barrier + slot ═════════════════════
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
2.4 mA of LED current, or 2.5 mA at a full 5 V. With CTR rank C the
transistor then sinks at least about 4 mA; the 10 kΩ pull-up (R4, R5) needs 0.33 mA. The
1.5 kΩ resistors are 2512 parts rated 1 W because Ritto terminal 3 (+24 V) sits between
KLINGEL and ETAGE. If a wire lands there by mistake, 15 mA flows and each resistor dissipates
about 0.35 W.

**Output (OK1).** GPIO19 drives the LED through 220 Ω (about 9.5 mA). The collector is on
DOOR and the emitter on `GND_BUS`, so the transistor pulls the opener line to bus ground.
In Lite-On's rank key, the suffix -C in LTV-817S-TA1-C means CTR 200–400 %, so the output
sinks about 19 mA reliably; check the datasheet. The LTV-817 is rated V<sub>CEO</sub> 35 V.
R6 (100 kΩ to ground) keeps GPIO19 low while the module resets and boots, so the door
does not buzz then.

**Straps and buttons.** GPIO8 and GPIO9 are strapping pins with 10 kΩ pull-ups (R12, R9).
Download mode needs GPIO8 = 1 and GPIO9 = 0. SW2 (BOOT) pulls GPIO9 to ground and SW1
(RESET) pulls EN to ground. EN has 10 kΩ (R8) and 1 µF (C6). GPIO15 stays open. In the
TS-1187A, the two pads at the same height are joined inside the switch. Only two diagonal
pads are wired, so a press joins them and the switch can never short a signal to ground.

**Firmware.** The firmware uses the three GPIOs directly. The XIAO ESP32-C6 antenna switch
(GPIO3, GPIO14) does not exist here, so do not use the `seeed_xiao_esp32c6` board profile;
see [../firmware](../firmware/).

## Power

USB-C only, 5 V, with all four VBUS contacts connected. CC1 and CC2 each have 5.1 kΩ to
ground (R7, R10); SBU1/SBU2 stay open. U3 (USBLC6-2SC6) clamps ESD on D+, D− and VBUS. Its
ground pin reaches a shell lug of the receptacle through a via (2.7 mm), and D+/D− reach
it on short stubs from the receptacle pads (7.8 mm and 12.9 mm; the module is 27 mm away). The AP2112K-3.3
(600 mA, stable with ceramic capacitors) makes 3.3 V; its EN is tied to VBUS. Capacitors:
10 µF + 100 nF at the input (C1, C4), 10 µF at the regulator output (C3), and 10 µF + 100 nF
at module pin 3 (C2, C5). VBUS and 3V3 run as 0.5 mm tracks, with the last piece into pin 3
at 0.4 mm. The module's transmit peaks are about 354 mA.

## Layout rules

- **Isolation:** one barrier line runs from the top edge past OK1 pin 4, through the slot,
  around R3 and down the right side. All copper of either ground domain keeps 0.8 mm from
  this line on both layers, so the two domains are at least 1.6 mm apart. `generate.py`
  checks pads, tracks, vias and the ground pour outlines on every run.
- **Antenna:** below y = 26.0 mm, across the whole module width (x 0–30.4 mm), there is no
  copper and no part on either layer. The antenna end of the module is 0.1 mm from the board
  edge. Espressif's footprint asks for 15 mm of clear board on each side of the antenna,
  which does not fit on this board. Keep metal away from that end when installing.
- **Vias** keep at least 0.15 mm of copper-free mask to every SMD pad and are tented.
- **Optocoupler land:** KiCad's `SMDIP-4_W9.53mm_Clearance8mm`, with 8 mm between the LED pad
  row and the transistor pad row.

## Parts

All parts are on the top side. The BOM (`bom.csv`) has one line per part number.

| Ref | Part | Manufacturer | MPN | LCSC |
| --- | --- | --- | --- | --- |
| U1 | ESP32-C6 module, 4 MB flash, PCB antenna | Espressif | ESP32-C6-MINI-1-N4 | C5736265 |
| U2 | LDO 3.3 V 600 mA, SOT-23-5 | Diodes Incorporated | AP2112K-3.3TRG1 | C51118 |
| U3 | USB ESD protection, SOT-23-6 | STMicroelectronics | USBLC6-2SC6 | C7519 |
| J1 | Screw terminal, 4 pins, 3.81 mm, 8.6 mm high | KANGNEX | WJ124-3.81-04P-14-00A | C69809 |
| J2 | USB-C receptacle | HRO | TYPE-C-31-M-12 | C165948 |
| OK1–OK3 | Optocoupler, CTR rank C | Lite-On | LTV-817S-TA1-C | C109227 |
| R1 | 220 Ω 0805 | UNI-ROYAL | 0805W8F2200T5E | C17557 |
| R2, R3 | 1.5 kΩ 1 W 2512 | FH | RC-12K1501FT | C453383 |
| R4, R5, R8, R9, R12 | 10 kΩ 0805 | UNI-ROYAL | 0805W8F1002T5E | C17414 |
| R6 | 100 kΩ 0805 | UNI-ROYAL | 0805W8F1003T5E | C149504 |
| R7, R10 | 5.1 kΩ 0603 | UNI-ROYAL | 0603WAF5101T5E | C23186 |
| C1–C3 | 10 µF 16 V X5R 0805 | Samsung | CL21A106KOQNNNE | C1713 |
| C4, C5 | 100 nF 50 V X7R 0805 | Samsung | CL21B104KBFNNNE | C136621 |
| C6 | 1 µF 50 V X7R 0805 | Samsung | CL21B105KBFNNNE | C28323 |
| SW1, SW2 | Tactile switch 5.1 × 5.1 mm, 1.5 mm high | XKB | TS-1187A-B-A-B | C318884 |

Substitutes: resistors and capacitors may be replaced by parts of the same value, size,
rating and dielectric; R2/R3 must stay 2512 and at least 1 W. Do not substitute U1, U3,
OK1–OK3 or J1. J1's footprint, overhang and silkscreen follow the KANGNEX drawing (rev A,
2024-03-10): pitch 3.81 mm, 1.30 mm holes, pin row 3.60 mm from the back and 3.70 mm from the
wire face, wires 26–16 AWG, M2 screw, 0.2 N·m, strip 5–6 mm.

## Files

| File | Content |
| --- | --- |
| `generate.py` | the design: placement, routing, checks, all outputs |
| `bellbridge.kicad_pcb`, `bellbridge.kicad_pro` | KiCad board (ground pours are unfilled; press **B** in KiCad to fill them) |
| `bom.csv` | bill of materials, one line per part number (PCBWay layout) |
| `cpl.csv` | placement: origin lower left, mm, Y up, KiCad rotation; J1 at its body centre |
| `pcbway/` | Gerbers, drill files, job file, BOM, CPL, `PCBWAY-REMARKS.txt` and the order zip `bellbridge-v1.0-pcbway.zip` |
| `drc-report.json` | KiCad DRC report of the last run |
| `plots/` | quick previews from `generate.py` (net colours, both sides) |

## Regenerating

Requirements: Python 3.9 or later (tested with 3.11 and 3.13); Pillow (optional, only for
`plots/`); KiCad 10 for the Gerbers and the DRC (tested with 10.0.6). On Windows `generate.py` finds a default KiCad 10 install; elsewhere
`kicad-cli` must be on `PATH`.

```bash
cd hardware
python generate.py
```

The run takes about a minute. It places all parts and routes them with a deterministic
router. Then it runs its own checks: isolation barrier, clearances, antenna strip,
via-to-pad distances and pin-1 marks. It writes the board, BOM, CPL and previews. After
that, `kicad-cli` exports Gerbers, drill and position files and runs the DRC with refilled
pours. `pcbway/` and the order zip are written only when the DRC reports **0 violations and
0 unconnected items**. The output ends with:

```
python-drc 0
kicad-drc violations 0 unconnected 0 {}
zip .../pcbway/bellbridge-v1.0-pcbway.zip
```

## Design verification (v1.0)

Done before ordering:

- `generate.py` checks: 0 errors. KiCad 10.0.6 DRC with all severities and refilled
  pours: 0 violations, 0 unconnected items.
- An independent review of the KiCad-filled board (pcbnew geometry). It checked the pin
  nets, isolation of at least 1.6 mm on both layers including pours, the clear antenna
  strip, power path widths, decoupling distances, the USB ESD routing, and J1 orientation
  and labels.
- Every footprint except J1 compared pad by pad with the KiCad 10 library, and U1 also with
  Espressif's own KiCad footprint: same copper.
- Pin functions of U1, U2, U3 and OK1–OK3 compared with KiCad's symbols.
- Firmware validated with ESPHome 2026.9.1 (configuration check; not yet compiled or
  flashed).

Still open: the built board. See [../docs/testing.md](../docs/testing.md).

## Differences from ritto-esp

Same circuit as the ritto-esp perfboard build: same terminal order (door opener, chime,
floor, ground), same polarity, the same GPIOs (XIAO D8 = GPIO19, D9 = GPIO20,
D10 = GPIO18), 220 Ω in front of the door-opener LED, and an isolated bus side.
Differences:

- 1.5 kΩ input resistors instead of 680 Ω: 2.4 mA instead of about 5 mA, and the inputs
  survive a wire on +24 V.
- External 10 kΩ pull-ups on GPIO18 and GPIO20; `pullup: true` in the firmware does no harm.
- 100 kΩ from GPIO19 to ground, so the opener stays off during boot.
- LTV-817S-TA1-C (CTR rank C) instead of a PC817.
- ESP32-C6-MINI-1-N4 module instead of a XIAO ESP32-C6, plus USB ESD protection.
