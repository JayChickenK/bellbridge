# Ordering BellBridge from PCBWay

All order files are in [`hardware/pcbway/`](../hardware/pcbway/), and `generate.py`
rebuilds them (see [hardware/README.md](../hardware/README.md#regenerating)).

| Upload | File |
| --- | --- |
| PCB (Gerber) | `bellbridge-v1.0-pcbway.zip` (Gerbers, PTH and NPTH drill files, job file, BOM, CPL, remarks) |
| Assembly BOM | `bom.csv` (one line per part number, with manufacturer, MPN and LCSC number) |
| Assembly centroid | `cpl.csv` (designator, X, Y, layer, rotation) |
| Remarks | the text of `PCBWAY-REMARKS.txt` |

## PCB options

| Option | Value |
| --- | --- |
| Size | 36.4 × 31.5 mm |
| Layers | 2 |
| Material | FR-4 (standard Tg) |
| Thickness | 1.6 mm (the USB-C shell lugs are made for it) |
| Min track / spacing | 6/6 mil or coarser; the design uses 0.2 mm / 0.2 mm |
| Min hole size | 0.3 mm (vias 0.65 mm pad / 0.30 mm drill) |
| Solder mask / silkscreen | any colour / white |
| Surface finish | ENIG recommended (flat pads under the module), HASL lead-free works |
| Via process | tented vias |
| Copper | 1 oz |

Also in the design: an internal milled slot (14.4 × 1.5 mm, unplated), four plated 0.6 mm
slots for the USB-C shell lugs, two 0.65 mm unplated locating holes, and four 1.30 mm
plated holes for J1. Silkscreen text is at least 0.8 mm high with a 0.15 mm stroke.

## Assembly options

| Option | Value |
| --- | --- |
| Service | Turnkey (PCBWay sources all parts) |
| Side | top side only |
| Number of unique parts | **15** |
| Number of SMD parts | **24** (all SMD parts except U1 and J2) |
| Number of ICs with more than 16 pins and SMD irregular parts with more than 10 pins | **2**: U1 (ESP32-C6 module, 53 pads) and J2 (USB-C receptacle, 12 SMD pads plus 4 shell lugs) |
| Number of through-hole parts | **1** (J1) |

These counts add up to the 27 placements. If the form wants every SMD part in "SMD parts",
enter 26 there. Older versions of the form ask for "BGA/QFP parts" instead: enter 1 (U1)
and 25 SMD parts. The numbers only feed the instant estimate; PCBWay prices the order from
the BOM. Choose an assembly line that also solders through-hole parts:
some economic lines do SMT only, and J1 plus the USB-C shell lugs need through-hole
soldering.

Alternatives: equivalent resistors and capacitors are fine (same value, size, rating and
dielectric; R2/R3 stay 2512 and at least 1 W). Do not accept substitutes for U1, U3,
OK1–OK3 or J1.

## Remarks for PCBWay

Paste the contents of `hardware/pcbway/PCBWAY-REMARKS.txt`: 561 characters, and the field
takes at most 600 (`generate.py` refuses a longer text). It covers the unplated slot and
locating holes, the through-hole joints, J1's orientation, the overhangs of J1 and J2, U3
pin 4 (left without a track on purpose), the separated grounds, the parts that must not be
substituted, and the centroid conventions.

## Check the preview before paying

The CPL uses KiCad's rotation (counter-clockwise, origin lower left, Y up). PCBWay's
library may use a different zero orientation, so check every polarised part in the
assembly preview:

- **U1 (module):** antenna toward the **bottom** edge of the top view; pin 1 at the
  silkscreen dot at the lower right of the module.
- **J2 (USB-C):** opening toward the **left** edge; the solder pads face the board centre.
- **U2 (AP2112K, SOT-23-5):** pin 1 (VIN) at the dot, lower right of the regulator.
- **U3 (USBLC6-2SC6, SOT-23-6):** pin 1 at the dot, top left, next to R7.
- **OK1–OK3:** pin 1 (LED anode) at the dots. OK1 is turned the opposite way to OK2/OK3.
- **J1 (terminal):** wire openings toward the **right** edge, as the silkscreen arrows show;
  the body overhangs the edge by 1.15 mm.

## Part availability

In October 2026 the LCSC snapshots showed low stock for C69809 (J1, KANGNEX
WJ124-3.81-04P-14-00A) and C453383 (R2/R3, FH RC-12K1501FT). PCBWay buys parts through its
own channels. If they report a shortage, approve only equivalents as listed above, or
supply the part yourself.

<!-- TODO after ordering: note what you ordered (quantity, finish), price, lead time, and any
questions PCBWay's engineers asked, so others can order the same way. -->
