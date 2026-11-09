# Ordering BellBridge from PCBWay

All order files are in [`hardware/pcbway/`](../hardware/pcbway/), and `generate.py`
rebuilds them (see [hardware/README.md](../hardware/README.md#regenerating)).

| Upload | File |
| --- | --- |
| PCB (Gerber) | `bellbridge-v1.13-pcbway.zip` (Gerbers, PTH and NPTH drill files, job file, BOM, CPL, remarks) |
| Assembly BOM | `bom.xlsx` in PCBWay's BOM layout: one line per part number with manufacturer, MPN, LCSC number as "Vendor Part #" and what may be substituted in "Customer Reply" (`bom.csv` is the same table) |
| Assembly centroid | `cpl.csv` (designator, X, Y, layer, rotation) |
| Remarks | the text of `PCBWAY-REMARKS.txt` |

## PCB options

| Option | Value |
| --- | --- |
| Size | 26.2 × 27.5 mm (plain rectangle; the module's antenna sticks out past the left edge, see below) |
| Layers | 2 |
| Material | FR-4 (standard Tg) |
| Thickness | 1.6 mm (the USB-C shell lugs are made for it) |
| Min track / spacing | 6/6 mil or coarser; the design uses 0.2 mm / 0.2 mm |
| Min hole size | 0.3 mm (vias 0.65 mm pad / 0.30 mm drill) |
| Solder mask / silkscreen | green recommended (see below) / white, both sides |
| Surface finish | ENIG recommended (flat pads under the module, 0.5 mm pitch at U3), HASL lead-free works |
| Via process | tented vias |
| Copper | 1 oz |

Also in the design: four plated 0.6 mm slots for the USB-C shell lugs, two 0.60 mm
unplated locating holes, and four 1.20 mm plated holes for J1. There is no milled slot.
The module's antenna overhangs the left edge by 5.2 mm on purpose (Espressif's placement
for a PCB antenna), so the assembled board is 31.4 mm wide. If PCBWay panelizes the boards
for assembly, the panel must keep at least 7 mm to the left of each board free: no
neighbouring board and no rail under the antenna. The antenna takes 5.2 mm of that, and the
neighbour's J1 sticks out 0.9 mm past its right edge at the same height, so 6 mm would let
the two touch. The panel needs routed tabs, not
V-scores, because USB-C, J1 and the antenna overhang three edges. C1, C2, C3 and C5 sit
0.5 mm from the bottom edge, where snapping a tab off could crack them, so no tabs on the
bottom edge left of J1. Good tab positions, measured from the board's left edge: the top
edge at 18 mm (the copper-free isolation strip), the bottom edge at 24–26 mm (under J1,
clear of the "NO +24V" text), and the right edge within 4 mm of the top.

Silkscreen text is at least 0.8 mm high with a 0.15 mm stroke. The bottom silkscreen
labels the two test pads and carries the board name and "GND ISOLATED".

Solder mask: the mask dams between the USB-C signal pads and between U3's pins are 0.10 mm,
PCBWay's minimum for green. With green they stay; with another colour PCBWay may open each
pin row as one window, which is common but makes solder bridges a little more likely. The
board has no fiducials: for a board this small PCBWay normally panelizes it and puts the
fiducials on the panel rails. Confirm this when they ask about the panel.

## Assembly options

| Option | Value |
| --- | --- |
| Service | Turnkey (PCBWay sources all parts) |
| Side | top side only (TP1/TP2 on the back are bare pads, nothing to place) |
| Number of unique parts | **13** |
| Number of SMD parts | **22** (all SMD parts except U1 and J2) |
| Number of ICs with more than 16 pins and SMD irregular parts with more than 10 pins | **2**: U1 (ESP32-C6 module, 53 pads) and J2 (USB-C receptacle, 12 SMD pads plus 4 shell lugs) |
| Number of through-hole parts | **1** (J1) |

These counts add up to the 25 placements. If the form wants every SMD part in "SMD parts",
enter 24 there. Older versions of the form ask for "BGA/QFP parts" instead: enter 1 (U1)
and 23 SMD parts. The numbers only feed the instant estimate; PCBWay prices the order from
the BOM. Choose an assembly line that also solders through-hole parts:
some economic lines do SMT only, and J1 plus the USB-C shell lugs need through-hole
soldering.

The module is moisture sensitive (MSL 3: solder within 168 h of opening the bag) and
rated for a single reflow pass with a 235–250 °C peak. All SMD parts are on the top side,
so it goes through one reflow; J1 is soldered afterwards.

Alternatives: equivalent resistors and capacitors are fine (same value, size, rating and
dielectric; R2/R3 stay 1210 and at least 0.5 W). Do not accept substitutes for U1, U3,
OK1–OK3, J1 or J2 (J2's land follows HRO's drawing). The BOM's "Customer Reply" column says
this for every line.

## Remarks for PCBWay

Paste the contents of `hardware/pcbway/PCBWAY-REMARKS.txt`: 598 characters, and the field
takes at most 600 (`generate.py` refuses a longer text). It covers the locating holes, the
through-hole joints, J1's orientation, the overhangs of J1, J2 and the module's antenna,
U3's pins 3 and 6 (left without a track on purpose), the separated grounds, the bare test
pads on the back, the panel (routed tabs, 7 mm free left of each board, no tabs on the
bottom edge left of J1), the parts that must not be substituted, and the centroid
conventions. Ask in the order chat to see the panel drawing if PCBWay makes one.

## Check the preview before paying

The CPL uses KiCad's rotation (counter-clockwise, Y up). Its origin is the board's
lower-left corner. PCBWay's library
may use a different zero orientation, so check every polarised part in the assembly
preview:

- **U1 (module):** turned on its side, antenna toward the **left** edge of the top view
  and 5.2 mm past it; pin 1 at the silkscreen dot at the lower left of the module. The
  0.5 mm dot on the module's shield is not a pin-1 mark: Espressif puts it at the shield
  corner on the pin-1 side but away from the antenna, here at the lower right.
- **J2 (USB-C):** opening toward the **top** edge; the solder pads face the module.
- **U2 (AP2112K, SOT-23-5):** pin 1 (VIN) at the dot, lower right of the regulator.
- **U3 (USBLC6-2P6, SOT-666):** pin 1 at the dot, top left, just below the receptacle.
- **OK1–OK3:** pin 1 (LED anode) at the dots. OK1 is turned the opposite way to OK2/OK3.
- **J1 (terminal):** wire openings toward the **right** edge, as the silkscreen arrows show;
  the body overhangs the edge by 0.9 mm.

## Part availability

Every BOM line carries manufacturer, MPN and LCSC number ("Vendor Part #"; U3 is C15999,
R2/R3 are C309587). PCBWay buys through its own channels; if they report a shortage, approve only
equivalents as listed above, or supply the part yourself.

<!-- TODO after ordering: note what you ordered (quantity, finish), price, lead time, and any
questions PCBWay's engineers asked, so others can order the same way. -->
