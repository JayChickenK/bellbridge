# BellBridge v1.0: generator for the PCBWay-assembled Ritto 7630 TwinBus / ESP32-C6 board.
# Writes the KiCad board, BOM and CPL and, when KiCad's DRC is clean, the PCBWay order zip.
# Millimetres, KiCad 20240108. KiCad reads this file with the origin at the TOP left and Y
# pointing DOWN: y = 0 is the top edge of the top view, y = BOARD_H the bottom edge. Footprints
# use KiCad's local frame (pin 1 top left, numbered counter-clockwise on screen). cpl.csv is
# converted to origin lower left / Y up in write_cpl(); render() draws the true top view.
# Derived from a larger 43.6 x 33.3 mm assembly board: no M3 holes, USB and the terminal moved,
# outline shrunk. The pre-release revisions were called KLEIN1..KLEIN3; KLEIN3 became v1.0.
# KLEIN2: USB-C turned to face the left edge, GPIO8 pull-up, AP2112K instead of AMS1117 and
# damper, one isolation barrier checked for all copper, nothing beside the antenna, button
# pads wired diagonally without tie tracks, 0.5 mm power paths, pin-1 dots placed and checked.
# KLEIN3: USB ESD array U3 (USBLC6-2SC6) above J2, CC pull-downs as 0603 beside it, J2 0.2 mm
# and the buttons 0.12 mm lower, 8.6 mm KANGNEX WJ124-3.81 terminal instead of the 13.8 mm MKDS.
# v1.0: KLEIN3 renamed to BellBridge, full-size first thermal pad as in Espressif's land,
# silkscreen strokes 0.15 mm (PCBWay minimum), BOM with one line per part number.

from __future__ import annotations

import csv
import heapq
import json
import math
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME, VERSION = "BellBridge", "1.0"
SLUG = NAME.lower()
BOARD_W = 36.4
BOARD_H = 31.5
CLEARANCE = 0.20
EDGE_COPPER = 0.45
M3_COPPER = 0.55
# Slot crosses the optocoupler bodies only. The 2512s and the terminal stay to its right.
SLOT = (11.0, 5.40, 25.4, 6.90)  # x0, y0, x1, y1
# U1 sits at (14.80, 23.10); its antenna section starts 2.9 mm past the centre (y = 26.0).
# The official footprint asks for 15 mm of clear board on each side. That does not fit, so
# no copper and no parts on either layer across the whole MCU width below y = 26.0.
ANT = (0.0, 26.00, 30.40, 31.5)
# Isolation barrier: centre line of a copper-free strip between the two grounds. GND_MCU
# copper stays ISO_HALF to one side, bus copper ISO_HALF to the other, on both layers.
# Top edge -> left of OK1 pin 4 -> down into the slot -> along it -> round R3 -> right side.
BARRIER = (
    (9.45, 0.0), (9.45, 3.12), (11.40, 3.12), (11.40, 6.15), (26.35, 6.15),
    (26.35, 9.40), (30.75, 9.40), (30.75, BOARD_H),
)
ISO_HALF = 0.80
BUS_NETS = ("GND_BUS", "DOOR", "CHIME", "FLOOR", "LED_CHIME", "LED_FLOOR")
# Pin-1 dots on F.SilkS. place_pin1_dots() puts each one at the nearest spot that check_silk()
# accepts, after routing; check_silk() re-checks them, including that pin 1 is clearly the
# nearest pin of the part. U1's pads 49-53 are ground pads, not pins.
PIN1_REFS = ("U1", "U2", "U3", "OK1", "OK2", "OK3")
PIN_MAX = {"U1": 48}
PIN1_DOTS: list[tuple[str, float, float]] = []
DOT_R, DOT_W = 0.20, 0.15


def m3_holes():
    # This board has no mounting holes.
    return ()

# KiCad 10 on Windows (per-user and all-users install); anywhere else kicad-cli must be on PATH.
KICAD = (
    Path(os.environ.get("LOCALAPPDATA", "~")).expanduser() / "Programs" / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
)


def uid() -> str:
    return str(uuid.uuid4())


def num(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def rot_xy(x: float, y: float, deg: float) -> tuple[float, float]:
    # KiCad's positive angle is counter-clockwise on screen. In the file's Y-down coordinates
    # 90° maps (x, y) to (y, -x).
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (x * c + y * s, -x * s + y * c)


class Pad:
    def __init__(self, ref, pin, net, layer, x, y, hw, hh, drill=0.0, round_pad=False):
        self.ref = ref
        self.pin = pin
        self.net = net
        self.layer = layer  # F, B, or *
        self.x = x
        self.y = y
        self.hw = hw
        self.hh = hh
        self.drill = drill
        self.round_pad = round_pad


class Seg:
    def __init__(self, net, layer, x1, y1, x2, y2, w):
        self.net = net
        self.layer = layer
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.w = w


class Via:
    def __init__(self, net, x, y, size=0.65, drill=0.30):
        self.net = net
        self.x = x
        self.y = y
        self.size = size
        self.drill = drill


class Part:
    def __init__(self, ref, value, footprint, x, y, rot, attr, mfr, mpn, lcsc):
        self.ref = ref
        self.value = value
        self.footprint = footprint
        self.x = x
        self.y = y
        self.rot = rot
        self.attr = attr
        self.mfr = mfr
        self.mpn = mpn
        self.lcsc = lcsc
        self.pads = []  # local pad dicts
        self.courtyard = None  # (x0, y0, x1, y1) local
        self.silk = []


PADS: list[Pad] = []
SEGS: list[Seg] = []
VIAS: list[Via] = []
PARTS: list[Part] = []
NOTES: list[str] = []


def add_part(ref, value, footprint, x, y, rot, pads, attr, mfr, mpn, lcsc, courtyard=None):
    part = Part(ref, value, footprint, x, y, rot, attr, mfr, mpn, lcsc)
    part.pads = pads
    part.courtyard = courtyard
    PARTS.append(part)
    for p in pads:
        px, py = rot_xy(p["x"], p["y"], rot)
        prot = (p.get("rot", 0) + rot) % 180
        sx, sy = p["sx"], p["sy"]
        if prot % 180 != 0:
            sx, sy = sy, sx
        # 90 and 270 both swap the axis-aligned box; 180 does not.
        if int(round((p.get("rot", 0) + rot))) % 180 != 0:
            sx, sy = p["sy"], p["sx"]
        PADS.append(
            Pad(
                ref,
                p["pin"],
                p.get("net") or "",
                p.get("layer", "F"),
                x + px,
                y + py,
                sx / 2.0,
                sy / 2.0,
                p.get("drill", 0.0),
                p.get("round", False),
            )
        )
    return part


def track(net, layer, pts, w):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            continue
        SEGS.append(Seg(net, layer, x1, y1, x2, y2, w))


def via(net, x, y, size=0.65, drill=0.30):
    VIAS.append(Via(net, x, y, size, drill))


def pads_of(ref, pin=None, net=None):
    out = []
    for p in PADS:
        if p.ref != ref:
            continue
        if pin is not None and p.pin != pin:
            continue
        if net is not None and p.net != net:
            continue
        out.append(p)
    return out


def at(ref, pin, n=0):
    hit = pads_of(ref, pin)
    p = hit[n]
    return p.x, p.y


def closest(ref, net, x, y):
    hit = pads_of(ref, net=net)
    return min(hit, key=lambda p: (p.x - x) ** 2 + (p.y - y) ** 2)


def r_pads(net1, net2):
    return [
        {"pin": "1", "x": -0.9125, "y": 0, "sx": 1.025, "sy": 1.4, "net": net1},
        {"pin": "2", "x": 0.9125, "y": 0, "sx": 1.025, "sy": 1.4, "net": net2},
    ]


def r0603_pads(net1, net2):
    # KiCad R_0603_1608Metric.
    return [
        {"pin": "1", "x": -0.825, "y": 0, "sx": 0.8, "sy": 0.95, "net": net1},
        {"pin": "2", "x": 0.825, "y": 0, "sx": 0.8, "sy": 0.95, "net": net2},
    ]


def c_pads(net1, net2):
    return [
        {"pin": "1", "x": -0.95, "y": 0, "sx": 1.0, "sy": 1.45, "net": net1},
        {"pin": "2", "x": 0.95, "y": 0, "sx": 1.0, "sy": 1.45, "net": net2},
    ]


def r2512(net1, net2):
    return [
        {"pin": "1", "x": -2.9625, "y": 0, "sx": 1.225, "sy": 3.35, "net": net1},
        {"pin": "2", "x": 2.9625, "y": 0, "sx": 1.225, "sy": 3.35, "net": net2},
    ]


def opto_pads(n1, n2, n3, n4):
    # KiCad Package_DIP:SMDIP-4_W9.53mm_Clearance8mm: 1.5 mm pads, 8 mm between the pad rows.
    return [
        {"pin": "1", "x": -4.765, "y": -1.27, "sx": 1.5, "sy": 1.78, "net": n1},
        {"pin": "2", "x": -4.765, "y": 1.27, "sx": 1.5, "sy": 1.78, "net": n2},
        {"pin": "3", "x": 4.765, "y": 1.27, "sx": 1.5, "sy": 1.78, "net": n3},
        {"pin": "4", "x": 4.765, "y": -1.27, "sx": 1.5, "sy": 1.78, "net": n4},
    ]


def button_pads(gnd, sig, gnd_corner="TL"):
    # Pad numbers as in KiCad's SW_Push_1P1T_XKB_TS-1187A: the two pads at the same y share a
    # number. Which pairs the switch joins inside was not confirmed against the XKB drawing,
    # so only two diagonal pads carry nets and nothing ties a pair in copper. Diagonal pads
    # sit in different pairs either way, so the switch works and never shorts sig to ground.
    # gnd_corner names the local corner (TL, TR, BL, BR) that carries GND; sig goes diagonally
    # opposite and the other two pads get no net.
    opposite = {"TL": "BR", "TR": "BL", "BL": "TR", "BR": "TL"}
    nets = {gnd_corner: gnd, opposite[gnd_corner]: sig}
    return [
        {"pin": "1", "x": -3.0, "y": -1.875, "sx": 1.0, "sy": 0.75, "net": nets.get("TL", "")},
        {"pin": "1", "x": 3.0, "y": -1.875, "sx": 1.0, "sy": 0.75, "net": nets.get("TR", "")},
        {"pin": "2", "x": -3.0, "y": 1.875, "sx": 1.0, "sy": 0.75, "net": nets.get("BL", "")},
        {"pin": "2", "x": 3.0, "y": 1.875, "sx": 1.0, "sy": 0.75, "net": nets.get("BR", "")},
    ]


def sot23_5_pads(vin, gnd, en, vout):
    # KiCad Package_TO_SOT_SMD:SOT-23-5. AP2112K: 1 VIN, 2 GND, 3 EN, 4 NC, 5 VOUT.
    return [
        {"pin": "1", "x": -1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": vin},
        {"pin": "2", "x": -1.1375, "y": 0.0, "sx": 1.325, "sy": 0.6, "net": gnd},
        {"pin": "3", "x": -1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": en},
        {"pin": "4", "x": 1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": ""},
        {"pin": "5", "x": 1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": vout},
    ]


def usblc6_pads(io1, io2, gnd, vbus):
    # KiCad Package_TO_SOT_SMD:SOT-23-6. USBLC6-2SC6: 1 I/O1, 2 GND, 3 I/O2, 4 I/O2, 5 VBUS,
    # 6 I/O1; 1/6 and 3/4 are joined inside the package. Pin 4 carries no net here: the ground
    # track leaves pin 2 through the gap between 3 and 4, so it is reached through pin 3.
    return [
        {"pin": "1", "x": -1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": io1},
        {"pin": "2", "x": -1.1375, "y": 0.0, "sx": 1.325, "sy": 0.6, "net": gnd},
        {"pin": "3", "x": -1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": io2},
        {"pin": "4", "x": 1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": ""},
        {"pin": "5", "x": 1.1375, "y": 0.0, "sx": 1.325, "sy": 0.6, "net": vbus},
        {"pin": "6", "x": 1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": io1},
    ]


# KANGNEX WJ124-3.81-04P-14-00A (customer drawing rev A, 2024-03-10): pitch 3.81, holes 1.30,
# body 7.30 deep and 8.60 high, pin row 3.60 from the back and 3.70 from the wire face, outer
# pins 2.31 from the body ends (dovetail tabs included). Local frame: pins along +X from pin 1,
# wire face at -Y. Pads 2.3 mm (0.5 mm ring).
TB_PITCH, TB_DRILL, TB_PAD = 3.81, 1.30, 2.3
TB_BACK, TB_FRONT, TB_END = 3.60, 3.70, 2.31


def terminal_pads(nets):
    return [
        {"pin": str(i + 1), "x": round(i * TB_PITCH, 3), "y": 0, "sx": TB_PAD, "sy": TB_PAD, "net": n,
         "layer": "*", "drill": TB_DRILL, "round": True}
        for i, n in enumerate(nets)
    ]


def module_pads():
    # Official ESP32-C6-MINI-1 land. Antenna is local -Y.
    # Nets follow the Espressif module pin list. NC pins stay unconnected.
    gnd = {1, 2, 11, 14} | set(range(36, 54))
    named = {
        3: "3V3",
        8: "EN",
        17: "USB_DM",
        18: "USB_DP",
        22: "GPIO8",
        23: "GPIO9",
        24: "GPIO18",
        25: "GPIO19",
        26: "GPIO20",
    }
    pads = []
    # Left 1..11, bottom 12..24, right 25..35, top 36..48.
    coords = []
    for i, y in enumerate([v * 0.1 for v in range(-13, 68, 8)]):
        coords.append((i + 1, -5.9, round(y, 2), 90))
    xs = [round(v * 0.1, 2) for v in range(-48, 49, 8)]
    for i, x in enumerate(xs):
        coords.append((12 + i, x, 7.6, 0))
    for i, y in enumerate([v * 0.1 for v in range(67, -14, -8)]):
        coords.append((25 + i, 5.9, round(y, 2), 90))
    for i, x in enumerate([round(v * 0.1, 2) for v in range(48, -49, -8)]):
        coords.append((36 + i, x, -2.2, 0))
    assert [c[0] for c in coords] == list(range(1, 49)), [c[0] for c in coords]
    for pin, x, y, prot in coords:
        net = "GND_MCU" if pin in gnd else named.get(pin, "")
        pads.append({"pin": str(pin), "x": x, "y": y, "sx": 0.4, "sy": 0.8, "rot": prot, "net": net})
    # Nine 1.45 mm ground squares. Espressif chamfers one corner of the first as an orientation
    # mark (a custom pad); here it is a plain square like the others, as in KiCad's library.
    thermal = [
        (-1.975, 0.725, 1.45, 1.45, 90),
        (-1.975, 2.7, 1.45, 1.45, 90),
        (-1.975, 4.675, 1.45, 1.45, 90),
        (0, 0.725, 1.45, 1.45, 90),
        (0, 2.7, 1.45, 1.45, 90),
        (0, 4.675, 1.45, 1.45, 90),
        (1.975, 0.725, 1.45, 1.45, 90),
        (1.975, 2.7, 1.45, 1.45, 90),
        (1.975, 4.675, 1.45, 1.45, 90),
    ]
    for x, y, sx, sy, prot in thermal:
        pads.append({"pin": "49", "x": x, "y": y, "sx": sx, "sy": sy, "rot": prot, "net": "GND_MCU"})
    for pin, x, y in ((50, 5.95, -2.25), (51, 5.95, 7.65), (52, -5.95, 7.65), (53, -5.95, -2.25)):
        pads.append({"pin": str(pin), "x": x, "y": y, "sx": 0.7, "sy": 0.7, "rot": 90, "net": "GND_MCU"})
    return pads


def usb_pads():
    # HRO TYPE-C-31-M-12, KiCad USB_C_Receptacle_HRO_TYPE-C-31-M-12. The solder pads are at the
    # back of the receptacle (local y = -4.045); the body runs -3.65..+3.65 and the cable
    # opening is local +Y. Rotation 270 turns +Y to -X, so the opening faces the left edge.
    spec = [
        ("A1", -3.25, "GND_MCU", 0.6),
        ("A4", -2.45, "VBUS", 0.6),
        ("A5", -1.25, "CC1", 0.3),
        ("A6", -0.25, "USB_DP", 0.3),
        ("A7", 0.25, "USB_DM", 0.3),
        ("A8", 1.25, "", 0.3),
        ("A9", 2.45, "VBUS", 0.6),
        ("A12", 3.25, "GND_MCU", 0.6),
        ("B12", -3.25, "GND_MCU", 0.6),
        ("B9", -2.45, "VBUS", 0.6),
        ("B8", -1.75, "", 0.3),
        ("B7", -0.75, "USB_DM", 0.3),
        ("B6", 0.75, "USB_DP", 0.3),
        ("B5", 1.75, "CC2", 0.3),
        ("B4", 2.45, "VBUS", 0.6),
        ("B1", 3.25, "GND_MCU", 0.6),
    ]
    pads = []
    for pin, x, net, sx in spec:
        pads.append({"pin": pin, "x": x, "y": -4.045, "sx": sx, "sy": 1.45, "net": net})
    shells = [
        (-4.32, -3.13, 1.0, 2.1, 0.6, 1.7),
        (-4.32, 1.05, 1.0, 1.6, 0.6, 1.2),
        (4.32, -3.13, 1.0, 2.1, 0.6, 1.7),
        (4.32, 1.05, 1.0, 1.6, 0.6, 1.2),
    ]
    for x, y, sx, sy, dx, dy in shells:
        pads.append(
            {
                "pin": "SH",
                "x": x,
                "y": y,
                "sx": sx,
                "sy": sy,
                "net": "GND_MCU",
                "layer": "*",
                "drill": max(dx, dy),
                "drill_oval": (dx, dy),
                "round": False,
                "oval": True,
            }
        )
    for x in (-2.89, 2.89):
        pads.append(
            {
                "pin": "",
                "x": x,
                "y": -2.6,
                "sx": 0.65,
                "sy": 0.65,
                "net": "",
                "layer": "*",
                "drill": 0.65,
                "npth": True,
                "round": True,
            }
        )
    return pads


def place_all():
    # Antenna toward high file-Y (rot 180), 0.1 mm short of the edge. USB opening at the left
    # edge (rot 270, front 0.25 mm past the edge). Terminal on the right edge (rot 270), wire
    # face toward +X, 1.15 mm past the edge. No mounting holes. Nothing sits beside the
    # antenna (y > ANT[1]). Left column, top to bottom: R7/R10 and U3, J2, SW2, SW1; the
    # courtyards touch, SW1 ends 0.7 mm above the antenna strip.
    add_part(
        "U1", "ESP32-C6-MINI-1-N4", "ESP32-C6-MINI-1",
        14.80, 23.10, 180, module_pads(), "smd",
        "Espressif", "ESP32-C6-MINI-1-N4", "C5736265",
        (-6.8, -8.5, 6.8, 8.5),
    )
    # LDO that is stable with ceramic capacitors; replaces AMS1117 + damper branch.
    add_part(
        "U2", "AP2112K-3.3", "SOT-23-5",
        27.15, 21.60, 180, sot23_5_pads("VBUS", "GND_MCU", "VBUS", "3V3"),
        "smd", "Diodes Incorporated", "AP2112K-3.3TRG1", "C51118",
        (-2.05, -1.84, 2.05, 1.7),
    )
    add_part(
        "J2", "USB-C", "USB_C_HRO_TYPE-C-31-M-12",
        3.40, 8.75, 270, usb_pads(), "smd",
        "HRO", "TYPE-C-31-M-12", "C165948",
        (-5.32, -5.27, 5.32, 4.15),
    )
    # OK1 LED on the MCU side (rot 90). OK2/OK3 LEDs on the bus side (rot 270).
    add_part(
        "OK1", "LTV-817S", "SMDIP-4_W9.53mm_Clearance8mm",
        12.45, 6.33, 90, opto_pads("LED_DOOR", "GND_MCU", "GND_BUS", "DOOR"),
        "smd", "Lite-On", "LTV-817S-TA1-C", "C109227", (-5.77, -2.79, 5.77, 2.79),
    )
    add_part(
        "OK2", "LTV-817S", "SMDIP-4_W9.53mm_Clearance8mm",
        18.23, 6.33, 270, opto_pads("LED_CHIME", "GND_BUS", "GND_MCU", "GPIO18"),
        "smd", "Lite-On", "LTV-817S-TA1-C", "C109227", (-5.77, -2.79, 5.77, 2.79),
    )
    add_part(
        "OK3", "LTV-817S", "SMDIP-4_W9.53mm_Clearance8mm",
        24.01, 6.33, 270, opto_pads("LED_FLOOR", "GND_BUS", "GND_MCU", "GPIO20"),
        "smd", "Lite-On", "LTV-817S-TA1-C", "C109227", (-5.77, -2.79, 5.77, 2.79),
    )
    # ESD array for D+/D-/VBUS in the corner above J2: stubs from the J2 pads, ground straight
    # to the shell lug (see route()).
    add_part(
        "U3", "USBLC6-2SC6", "SOT-23-6",
        6.40, 1.72, 0, usblc6_pads("USB_DP", "USB_DM", "GND_MCU", "VBUS"),
        "smd", "STMicroelectronics", "USBLC6-2SC6", "C7519",
        (-2.05, -1.7, 2.05, 1.7),
    )
    add_part(
        "J1", "3.81mm 4P", "TerminalBlock_Kangnex_WJ124-3.81_1x04_P3.81mm",
        33.85, 12.00, 270, terminal_pads(("DOOR", "CHIME", "FLOOR", "GND_BUS")),
        "through_hole", "KANGNEX", "WJ124-3.81-04P-14-00A", "C69809",
        (-TB_END - 0.25, -TB_FRONT - 0.25, 3 * TB_PITCH + TB_END + 0.25, TB_BACK + 0.25),
    )
    rc = (-1.68, -0.95, 1.68, 0.95)
    cc = (-1.7, -0.98, 1.7, 0.98)
    uni = "UNI-ROYAL"
    add_part("R2", "1.5k 1W", "R_2512", 30.95, 2.65, 0, r2512("LED_CHIME", "CHIME"), "smd", "FH", "RC-12K1501FT", "C453383", (-3.83, -1.93, 3.83, 1.93))
    add_part("R3", "1.5k 1W", "R_2512", 30.95, 6.75, 0, r2512("LED_FLOOR", "FLOOR"), "smd", "FH", "RC-12K1501FT", "C453383", (-3.83, -1.93, 3.83, 1.93))
    # Row between the optocouplers and the module.
    add_part("R1", "220", "R_0805", 10.45, 13.10, 180, r_pads("LED_DOOR", "GPIO19"), "smd", uni, "0805W8F2200T5E", "C17557", rc)
    add_part("R12", "10k", "R_0805", 13.85, 13.10, 0, r_pads("GPIO8", "3V3"), "smd", uni, "0805W8F1002T5E", "C17414", rc)
    add_part("R4", "10k", "R_0805", 18.60, 13.10, 180, r_pads("GPIO18", "3V3"), "smd", uni, "0805W8F1002T5E", "C17414", rc)
    add_part("R9", "10k", "R_0805", 22.55, 14.03, 90, r_pads("3V3", "GPIO9"), "smd", uni, "0805W8F1002T5E", "C17414", rc)
    add_part("R5", "10k", "R_0805", 24.50, 14.03, 90, r_pads("3V3", "GPIO20"), "smd", uni, "0805W8F1002T5E", "C17414", rc)
    add_part("R6", "100k", "R_0805", 26.45, 14.03, 90, r_pads("GND_MCU", "GPIO19"), "smd", uni, "0805W8F1003T5E", "C149504", rc)
    # CC pull-downs above the receptacle, 0603 so that U3 fits beside them.
    r6c = (-1.48, -0.73, 1.48, 0.73)
    add_part("R7", "5.1k", "R_0603", 1.70, 0.94, 0, r0603_pads("GND_MCU", "CC1"), "smd", uni, "0603WAF5101T5E", "C23186", r6c)
    add_part("R10", "5.1k", "R_0603", 1.70, 2.42, 0, r0603_pads("GND_MCU", "CC2"), "smd", uni, "0603WAF5101T5E", "C23186", r6c)
    # EN network at module pin 8, decoupling at pin 3, regulator column beside it.
    add_part("R8", "10k", "R_0805", 23.30, 16.85, 0, r_pads("EN", "3V3"), "smd", uni, "0805W8F1002T5E", "C17414", rc)
    add_part("C6", "1uF", "C_0805", 23.30, 18.80, 0, c_pads("EN", "GND_MCU"), "smd", "Samsung", "CL21B105KBFNNNE", "C28323", cc)
    add_part("C5", "100nF", "C_0805", 23.30, 22.80, 0, c_pads("3V3", "GND_MCU"), "smd", "Samsung", "CL21B104KBFNNNE", "C136621", cc)
    add_part("C2", "10uF", "C_0805", 23.30, 24.80, 0, c_pads("3V3", "GND_MCU"), "smd", "Samsung", "CL21A106KOQNNNE", "C1713", cc)
    add_part("C4", "100nF", "C_0805", 27.15, 16.90, 180, c_pads("VBUS", "GND_MCU"), "smd", "Samsung", "CL21B104KBFNNNE", "C136621", cc)
    add_part("C1", "10uF", "C_0805", 27.15, 18.87, 180, c_pads("VBUS", "GND_MCU"), "smd", "Samsung", "CL21A106KOQNNNE", "C1713", cc)
    add_part("C3", "10uF", "C_0805", 27.15, 24.70, 0, c_pads("3V3", "GND_MCU"), "smd", "Samsung", "CL21A106KOQNNNE", "C1713", cc)
    add_part("SW2", "BOOT", "SW_TS-1187A", 4.00, 16.87, 0, button_pads("GND_MCU", "GPIO9", "BL"), "smd", "XKB", "TS-1187A-B-A-B", "C318884", (-3.75, -2.8, 3.75, 2.8))
    add_part("SW1", "RESET", "SW_TS-1187A", 4.00, 22.47, 0, button_pads("GND_MCU", "EN", "BL"), "smd", "XKB", "TS-1187A-B-A-B", "C318884", (-3.75, -2.8, 3.75, 2.8))


def route():
    # Short copper is drawn by hand. Every other net is a clearance-checked
    # search on a 0.05 mm grid, front and back, with 0.65 / 0.30 vias.
    # GND_MCU is not searched: the pours join it, plus the hand-drawn ground ties below.
    # Signal nets cannot use that.
    import heapq as _hq
    import time as _time

    RES = 0.05
    VIA_R = 0.325
    VIA_COST = 0.40
    VIA_PAD_GAP = 0.15      # via copper stays this far from the module's perimeter pads

    t0 = _time.perf_counter()
    bins = {}
    occupied = {}
    linked = {}
    npth = []

    def to_i(v):
        return int(math.floor(v / RES + 0.5))

    def xy_of(ix, iy):
        return (round(ix * RES, 3), round(iy * RES, 3))

    def add_obs(it, x0, y0, x1, y1):
        margin = 1.6
        ix0 = int(math.floor((min(x0, x1) - margin) / 2.0))
        ix1 = int(math.floor((max(x0, x1) + margin) / 2.0))
        iy0 = int(math.floor((min(y0, y1) - margin) / 2.0))
        iy1 = int(math.floor((max(y0, y1) + margin) / 2.0))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                bins.setdefault((ix, iy), []).append(it)

    def near(x, y):
        return bins.get((int(math.floor(x / 2.0)), int(math.floor(y / 2.0))), ())

    def layers_of(p):
        if p.layer == "*":
            return (0, 1)
        return (0 if p.layer == "F" else 1,)

    for p in PADS:
        if p.pin == "" and p.drill:
            npth.append((p.x, p.y, p.drill / 2.0))
            continue
        lay = "*" if p.layer == "*" else p.layer
        strict = 1.0 if p.ref == "U1" and p.pin.isdigit() and int(p.pin) <= 48 else 0.0
        rect = ("pad", p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh, lay, p.net, strict)
        add_obs(rect, rect[1], rect[2], rect[3], rect[4])

    def forbidden(x, y, reach):
        if x - reach < 0.45 or y - reach < 0.45:
            return True
        if x + reach > BOARD_W - 0.45 or y + reach > BOARD_H - 0.45:
            return True
        ax0, ay0, ax1, ay1 = ANT
        if x + reach > ax0 + 0.01 and x - reach < ax1 - 0.01 and y + reach > ay0 + 0.01 and y - reach < ay1 - 0.01:
            return True
        # The slot is an Edge.Cuts opening. KiCad wants 0.30 mm from the copper edge.
        sx0, sy0, sx1, sy1 = SLOT
        gap = 0.32
        if x + reach > sx0 - gap and x - reach < sx1 + gap and y + reach > sy0 - gap and y - reach < sy1 + gap:
            return True
        for hx, hy, hr in npth:
            if math.hypot(x - hx, y - hy) < hr + 0.32 + reach:
                return True
        return False

    side_cache = {}

    def blocked(x, y, layer_name, half, net, clr, is_via):
        reach = VIA_R if is_via else half
        if forbidden(x, y, reach):
            return True
        # Isolation barrier: every track and via stays ISO_HALF clear of the barrier line,
        # on its own ground's side, on both layers.
        key = (round(x, 3), round(y, 3), round(reach, 3), domain_of(net))
        ok = side_cache.get(key)
        if ok is None:
            ok = side_cache[key] = domain_ok(x, y, reach, key[3])
        if not ok:
            return True
        # No front-layer signal copper under U1's exposed ground pad (with 1 mm margin): a
        # track there would sit under the module's own GND pad. Short stubs between the pad
        # ring and that area, vias and the back layer are fine.
        if layer_name == "F" and not is_via and net != "GND_MCU":
            mx0, my0, mx1, my1 = MODULE_EPAD
            if x + reach > mx0 and x - reach < mx1 and y + reach > my0 and y - reach < my1:
                return True
        need = reach + clr
        for it in near(x, y):
            kind, a, b, c, d, lay, inet, sw = it
            if is_via and kind == "pad" and lay != "*" and inet == net and sw == 0:
                # No via in or against an SMD pad of its own net: 0.15 mm of mask stays
                # between them, so paste cannot run down the hole.
                dx = max(a - x, x - c, 0.0)
                dy = max(b - y, y - d, 0.0)
                if dx * dx + dy * dy < (VIA_R + 0.15) ** 2:
                    return True
            if is_via and kind == "pad" and lay != "*" and sw > 0:
                # Perimeter pads of the module are 0.4 x 0.8 mm. A via barrel under one drinks
                # the paste (0.04 mm3 of paste against 0.11 mm3 of barrel) and the joint opens.
                dx = max(a - x, x - c, 0.0)
                dy = max(b - y, y - d, 0.0)
                if dx * dx + dy * dy < (VIA_R + VIA_PAD_GAP) ** 2:
                    return True
            if inet == net:
                # A track that stays inside its own pad is already legal copper.
                if (
                    kind == "pad"
                    and not is_via
                    and lay in ("*", layer_name)
                    and a + half <= x <= c - half
                    and b + half <= y <= d - half
                ):
                    return False
                continue
            if kind == "pad":
                if not is_via and lay not in ("*", layer_name):
                    continue
                dx = max(a - x, x - c, 0.0)
                dy = max(b - y, y - d, 0.0)
                if dx * dx + dy * dy < need * need:
                    return True
            elif kind == "seg":
                if not is_via and lay != layer_name:
                    continue
                gap = _point_seg(x, y, a, b, c, d) - sw / 2.0 - reach
                if gap < clr:
                    return True
            else:
                gap = math.hypot(x - a, y - b) - VIA_R - reach
                if gap < clr:
                    return True
        return False

    u1 = next(p for p in PARTS if p.ref == "U1")
    # Ground pad 49 spans local x -2.7..2.7, y 0..5.4; 1 mm margin on every side.
    ex0, ey0 = rot_xy(-3.7, -1.0, u1.rot)
    ex1, ey1 = rot_xy(3.7, 6.4, u1.rot)
    MODULE_EPAD = (u1.x + min(ex0, ex1), u1.y + min(ey0, ey1), u1.x + max(ex0, ex1), u1.y + max(ey0, ey1))

    def remember_seg(net, layer_name, x1, y1, x2, y2, w):
        seg = ("seg", x1, y1, x2, y2, layer_name, net, w)
        add_obs(seg, x1, y1, x2, y2)
        layer_i = 0 if layer_name == "F" else 1
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(length / 0.02))
        occ = occupied.setdefault(net, set())
        for i in range(steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            occ.add((to_i(x), to_i(y), layer_i))
        linked.setdefault(net, []).append(("s", layer_name, x1, y1, x2, y2))

    def remember_via(net, x, y):
        add_obs(("via", x, y, x, y, "*", net, 0.0), x, y, x, y)
        occ = occupied.setdefault(net, set())
        ix, iy = to_i(x), to_i(y)
        occ.add((ix, iy, 0))
        occ.add((ix, iy, 1))
        linked.setdefault(net, []).append(("v", x, y))

    def seed_pad(p):
        occ = occupied.setdefault(p.net, set())
        x0, y0, x1, y1 = p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh
        # Round terminal pads are circles. The square corners are not copper,
        # and a route that only touches a corner does not reach the pad.
        rad = (min(p.hw, p.hh) - 0.05) if p.round_pad else None
        for layer_i in layers_of(p):
            ix0 = to_i(x0)
            ix1 = to_i(x1)
            iy0 = to_i(y0)
            iy1 = to_i(y1)
            for ix in range(min(ix0, ix1), max(ix0, ix1) + 1):
                cx = round(ix * RES, 3)
                if cx < x0 - 0.001 or cx > x1 + 0.001:
                    continue
                for iy in range(min(iy0, iy1), max(iy0, iy1) + 1):
                    cy = round(iy * RES, 3)
                    if not (y0 - 0.001 <= cy <= y1 + 0.001):
                        continue
                    if rad is not None and math.hypot(cx - p.x, cy - p.y) > rad:
                        continue
                    occ.add((ix, iy, layer_i))
        lay = "F" if p.layer == "F" else ("B" if p.layer == "B" else "*")
        linked.setdefault(p.net, []).append(("p", lay, x0, y0, x1, y1))

    def add_poly(net, layer_name, pts, w):
        track(net, layer_name, pts, w)
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
                continue
            remember_seg(net, layer_name, x1, y1, x2, y2, w)

    def add_via(net, x, y):
        via(net, x, y)
        remember_via(net, x, y)

    def closest_hit(net, x, y, layer_name):
        best = 1e9
        bx, by = x, y
        for item in linked.get(net, ()):
            kind = item[0]
            if kind == "s":
                if item[1] != layer_name:
                    continue
                px, py = _closest_point(x, y, item[2], item[3], item[4], item[5])
                d = math.hypot(x - px, y - py)
            elif kind == "v":
                px, py = item[1], item[2]
                d = max(0.0, math.hypot(x - px, y - py) - VIA_R)
            else:
                lay, x0, y0, x1, y1 = item[1], item[2], item[3], item[4], item[5]
                if lay not in ("*", layer_name):
                    continue
                px = min(max(x, x0), x1)
                py = min(max(y, y0), y1)
                d = math.hypot(x - px, y - py)
            if d < best:
                best = d
                bx, by = px, py
        return best, bx, by

    # --- Hand-drawn copper ---------------------------------------------------------------
    # J2 shell lugs. The lower front/rear pair is joined on the front and tied to the nearest
    # GND pad, the upper rear lug too, so no lug depends on a thermal spoke squeezing past the
    # NPTH pegs. The D+/D- stubs to U3 pass between the upper lugs, so the upper front lug is
    # tied to the R7/R10 ground via instead.
    j2 = next(q for q in PARTS if q.ref == "J2")
    lugs = pads_of("J2", "SH")
    top = sorted((q for q in lugs if q.y < j2.y), key=lambda q: q.x)
    bot = sorted((q for q in lugs if q.y > j2.y), key=lambda q: q.x)
    a1, a12 = at("J2", "A1"), at("J2", "A12")
    add_poly("GND_MCU", "F", [(top[1].x, top[1].y), (a1[0], top[1].y), a1], 0.25)
    add_poly("GND_MCU", "F", [(bot[0].x, bot[0].y), (a12[0], bot[0].y), a12], 0.25)
    rg = (0.85, at("R10", "1")[1] + 1.0)
    add_poly("GND_MCU", "F", [at("R7", "1"), at("R10", "1"), rg, (top[0].x - 0.65, top[0].y)], 0.30)
    add_via("GND_MCU", *rg)
    for p in list(lugs) + [q for pin in ("A1", "A12", "B1", "B12") for q in pads_of("J2", pin)]:
        seed_pad(p)

    # USB pair, front only. DP joins A6/B6 in a loop just left of the pad row (under the body),
    # DM joins B7/A7 just right of it. The pair then runs under the optocoupler bodies on the
    # MCU side of the slot, drops between OK2 and OK3, and turns along the gap above the
    # module's top pin row into pins 17 (DM) and 18 (DP).
    tw = 0.20
    a6, b6, b7, a7 = at("J2", "A6"), at("J2", "B6"), at("J2", "B7"), at("J2", "A7")
    xl = a6[0] - 0.725 - 0.32
    dm_y, dp_y = b7[1], a6[1]                 # 8.00 and 8.50: runs under the opto bodies
    dp_x, dm_x = 20.75, 21.45                 # drops between OK2 pin 4 and OK3 pin 3
    dp_h, dm_h = 14.20, 14.70                 # runs above the module's top row
    p17, p18 = at("U1", "17"), at("U1", "18")
    add_poly("USB_DP", "F", [a6, (xl, a6[1]), (xl, b6[1]), b6], tw)
    add_poly("USB_DP", "F", [b6, (9.10, b6[1]), (9.10, dp_y), (dp_x, dp_y), (dp_x, dp_h),
                             (p18[0], dp_h), p18], tw)
    add_poly("USB_DM", "F", [a7, (8.55, a7[1]), (8.55, b7[1]), b7], tw)
    add_poly("USB_DM", "F", [(8.55, dm_y), (dm_x, dm_y), (dm_x, dm_h), (p17[0], dm_h), p17], tw)
    for p in pads_of("J2", "A6") + pads_of("J2", "B6") + pads_of("J2", "A7") + pads_of("J2", "B7"):
        seed_pad(p)
    seed_pad(pads_of("U1", "17")[0])
    seed_pad(pads_of("U1", "18")[0])

    # USB ESD array U3 above J2. D- and D+ reach it as stubs from the left side of the J2 pad
    # row, under the receptacle body and between the upper shell lugs: D- from B7 up into
    # pin 3 (I/O2), D+ from the A6/B6 loop round to pin 1 (I/O1), which a bridge under the
    # package joins to pin 6. Ground leaves pin 2 down the gap between the pad rows to a via
    # and the rear shell lug, 2.7 mm in all. VBUS (pin 5) comes up the gap right of the pad
    # row from the J2 VBUS pad.
    u3 = next(q for q in PARTS if q.ref == "U3")
    u1p, u2p, u3p, u5p, u6p = (at("U3", n) for n in ("1", "2", "3", "5", "6"))
    add_poly("USB_DP", "F", [u1p, u6p], tw)
    gv = (u3.x, u3p[1] + 0.88)
    add_poly("GND_MCU", "F", [u2p, (u3.x, u2p[1]), gv, (u3.x, top[1].y - top[1].hh + 0.05)], 0.30)
    add_via("GND_MCU", *gv)
    add_poly("VBUS", "F", [u5p, (8.50, u5p[1]), (8.50, at("J2", "A4")[1])], tw)
    xd, xp = 5.00, 4.25                       # stub columns under the J2 body
    add_poly("USB_DM", "F", [b7, (xd, b7[1]), (xd, u3p[1])], tw)
    ym = (a6[1] + b6[1]) / 2.0
    add_poly("USB_DP", "F", [(xl, ym), (xp, ym), (xp, u1p[1]), u1p], tw)
    for n in ("1", "2", "3", "5", "6"):
        seed_pad(pads_of("U3", n)[0])

    # CC lines: CC1 leaves A5 to the left and drops to the back above the D- stub, CC2 leaves
    # B5 to the left below the D+ loop. Both cross under the body on the back and come up
    # through a via beside their pull-down.
    a5, b5 = at("J2", "A5"), at("J2", "B5")
    r7c, r10c = at("R7", "2"), at("R10", "2")
    cc1v, r7v = (5.85, a5[1] - 0.55), (3.45, r7c[1] + 0.51)   # r7v low: U3's pin-1 dot goes above it
    add_poly("CC1", "F", [a5, (6.25, a5[1]), cc1v], tw)
    add_poly("CC1", "B", [cc1v, (4.75, cc1v[1]), (4.75, r7v[1]), r7v], tw)
    add_poly("CC1", "F", [r7v, r7c], tw)
    cc2v, r10v = (5.85, b5[1]), (r10c[0], r10c[1] + 0.95)
    add_poly("CC2", "F", [b5, cc2v], tw)
    add_poly("CC2", "B", [cc2v, (3.80, cc2v[1]), (3.80, r10v[1]), r10v], tw)
    add_poly("CC2", "F", [r10v, r10c], tw)
    for v in (cc1v, r7v):
        add_via("CC1", *v)
    for v in (cc2v, r10v):
        add_via("CC2", *v)
    for ref, pin in (("J2", "A5"), ("J2", "B5"), ("R7", "2"), ("R10", "2")):
        seed_pad(pads_of(ref, pin)[0])

    # VBUS, 0.5 mm: both J2 VBUS pads to vias, joined on the back, one back run under the
    # optocouplers and down the right side, then the front spine of the regulator column.
    pw = 0.50
    vx = 9.00
    vb_t, vb_b = at("J2", "A4"), at("J2", "A9")
    add_poly("VBUS", "F", [vb_t, (vx, vb_t[1])], pw)
    add_poly("VBUS", "F", [vb_b, (vx, vb_b[1])], pw)
    add_via("VBUS", vx, vb_t[1])
    add_via("VBUS", vx, vb_b[1])
    add_poly("VBUS", "B", [(vx, vb_t[1]), (vx, vb_b[1])], pw)
    sx = 29.45
    add_poly("VBUS", "B", [(vx, 7.80), (23.90, 7.80), (23.90, 10.70), (sx, 10.70), (sx, 16.30)], pw)
    add_via("VBUS", sx, 16.30)
    c4v, c1v = at("C4", "1"), at("C1", "1")
    u_vin, u_en = at("U2", "1"), at("U2", "3")
    add_poly("VBUS", "F", [(sx, 16.30), (sx, u_vin[1]), u_vin], pw)
    add_poly("VBUS", "F", [c4v, (sx, c4v[1])], pw)
    add_poly("VBUS", "F", [c1v, (sx, c1v[1])], pw)
    add_poly("VBUS", "F", [u_en, (sx, u_en[1])], 0.30)
    for ref, pin in (("J2", "A4"), ("J2", "B9"), ("J2", "A9"), ("J2", "B4"), ("C4", "1"),
                     ("C1", "1"), ("U2", "1"), ("U2", "3")):
        for p in pads_of(ref, pin):
            seed_pad(p)

    # 3V3 trunk, 0.5 mm: regulator output -> its 10 uF (C3); up and over C5 to the 100 nF
    # (C5) and 10 uF (C2) that sit at module pin 3, then 0.4 mm into the pin.
    vout = at("U2", "5")
    c3p, c5p, c2p, p3 = at("C3", "1"), at("C5", "1"), at("C2", "1"), at("U1", "3")
    add_poly("3V3", "F", [vout, (c3p[0], vout[1]), c3p], pw)
    add_poly("3V3", "F", [(25.60, vout[1]), (25.60, 21.50), (c5p[0], 21.50), c5p, c2p], pw)
    add_poly("3V3", "F", [c5p, p3], 0.40)
    # Pull-up feed for the row above the module (R12, R4): joined on the front, one via
    # between them, a back run under the module's edge and a via beside the trunk.
    r12v, r4v = at("R12", "2"), at("R4", "2")
    add_poly("3V3", "F", [r12v, r4v], 0.30)
    add_via("3V3", 16.20, r12v[1])
    add_poly("3V3", "B", [(16.20, r12v[1]), (16.20, 16.30), (24.40, 16.30), (24.40, 20.40)], 0.30)
    add_via("3V3", 24.40, 20.40)
    add_poly("3V3", "F", [(24.40, 20.40), (24.40, 21.50)], 0.30)
    # R9 and R5 (pull-ups under OK3) share one link down to R8's 3V3 pad, which drops to the
    # trunk under C6's body, between its pads.
    r9v, r5v, r8v = at("R9", "1"), at("R5", "1"), at("R8", "2")
    add_poly("3V3", "F", [r9v, r5v, (r5v[0], r8v[1])], 0.25)
    add_poly("3V3", "F", [r8v, (r8v[0], 17.70), (23.35, 17.70), (23.35, 21.50)], 0.25)
    for ref, pin in (("U2", "5"), ("C3", "1"), ("C5", "1"), ("C2", "1"), ("U1", "3"),
                     ("R12", "2"), ("R4", "2"), ("R9", "1"), ("R5", "1"), ("R8", "2")):
        seed_pad(pads_of(ref, pin)[0])

    # EN: module pin 8 -> 1 uF (C6) -> 10 k pull-up (R8), all within 2 mm of the pin. The
    # search adds the reset button.
    p8, c6e, r8e = at("U1", "8"), at("C6", "1"), at("R8", "1")
    add_poly("EN", "F", [p8, c6e, (c6e[0], r8e[1]), r8e], 0.25)
    for ref, pin in (("U1", "8"), ("C6", "1"), ("R8", "1")):
        seed_pad(pads_of(ref, pin)[0])

    # Regulator ground: stub under the body to a via between the two pin rows.
    ug = at("U2", "2")
    add_poly("GND_MCU", "F", [ug, (27.15, ug[1])], 0.30)
    add_via("GND_MCU", 27.15, ug[1])
    seed_pad(pads_of("U2", "2")[0])
    # Ground ties placed before the search, so it routes around them. The MCU-side ground pin
    # of each optocoupler sits inside the USB pair's loop on the front and between the long
    # signal runs on the back, so neither pour reaches it reliably: each gets a via under the
    # body, a back rail joins them, and a via at the rail's left end drops to a front track
    # into J2's lower GND pad.
    rail_y, rail_x0, rail_vy = 8.60, 9.80, 9.75
    for ref, pin in (("OK1", "2"), ("OK2", "3"), ("OK3", "3")):
        gp = pads_of(ref, pin)[0]
        vy = gp.y - gp.hh - 0.60
        add_poly("GND_MCU", "F", [(gp.x, gp.y), (gp.x, vy)], 0.30)
        add_via("GND_MCU", gp.x, vy)
        add_poly("GND_MCU", "B", [(gp.x, vy), (gp.x, rail_y)], 0.30)
        seed_pad(gp)
    add_poly("GND_MCU", "B", [(rail_x0, rail_y), (at("OK3", "3")[0], rail_y)], 0.30)
    add_poly("GND_MCU", "B", [(rail_x0, rail_y), (rail_x0, rail_vy)], 0.30)
    add_via("GND_MCU", rail_x0, rail_vy)
    add_poly("GND_MCU", "F", [(rail_x0, rail_vy), (rail_x0, 12.00), (a12[0], 12.00), a12], 0.30)
    # The C6/C4/C1 ground pads share a front pocket that only this via joins to the back pour.
    add_via("GND_MCU", 25.20, 17.90)
    # Module corner ground pad 51 sits where GPIO9, GPIO18 and GPIO19 leave the module; give it
    # its own via before they are routed.
    p51 = at("U1", "51")
    add_poly("GND_MCU", "F", [p51, (8.00, 15.70)], 0.30)
    add_via("GND_MCU", 8.00, 15.70)
    seed_pad(pads_of("U1", "51")[0])

    # Local links that must not be left to the search order: each resistor in the row
    # straight up to its optocoupler pin, and GPIO8 from module pin 22 to its pull-up.
    for net, (ra, pa), (rb, pb), lx in (
        ("LED_DOOR", ("R1", "1"), ("OK1", "1"), 11.30),
        ("GPIO18", ("R4", "1"), ("OK2", "4"), 19.51),
        ("GPIO20", ("R5", "2"), ("OK3", "4"), 24.90),
    ):
        a, b = pads_of(ra, pa)[0], pads_of(rb, pb)[0]
        add_poly(net, "F", [(lx, a.y), (lx, b.y)], tw)
        seed_pad(a)
        seed_pad(b)
    p22, r12g = at("U1", "22"), at("R12", "1")
    add_poly("GPIO8", "F", [p22, (p22[0], 14.50), (r12g[0], 14.50), r12g], tw)
    seed_pad(pads_of("U1", "22")[0])
    seed_pad(pads_of("R12", "1")[0])

    def search(p, width, clr, margin):
        half = width / 2.0
        net = p.net
        occ = occupied.get(net, ())
        if not occ:
            return False
        layer_i0 = layers_of(p)[0]
        start = (to_i(p.x), to_i(p.y), layer_i0)
        sx, sy = xy_of(start[0], start[1])
        if not (p.x - p.hw - 0.02 <= sx <= p.x + p.hw + 0.02 and p.y - p.hh - 0.02 <= sy <= p.y + p.hh + 0.02):
            return False
        xs = [c[0] for c in occ]
        ys = [c[1] for c in occ]
        bb = (min(xs), max(xs), min(ys), max(ys))
        if margin is None:
            box = None
        else:
            m = int(margin / RES)
            box = (min(start[0], bb[0]) - m, max(start[0], bb[1]) + m,
                   min(start[1], bb[2]) - m, max(start[1], bb[3]) + m)
        lname = ("F", "B")

        def h_of(ix, iy):
            dx = 0 if bb[0] <= ix <= bb[1] else min(abs(ix - bb[0]), abs(ix - bb[1]))
            dy = 0 if bb[2] <= iy <= bb[3] else min(abs(iy - bb[2]), abs(iy - bb[3]))
            return (dx + dy) * RES

        heap = [(h_of(start[0], start[1]), 0.0, start[0], start[1], start[2])]
        seen = set()
        parent = {start: None}
        found = None
        pops = 0
        while heap:
            _f, g, ix, iy, layer_i = _hq.heappop(heap)
            key = (ix, iy, layer_i)
            if key in seen:
                continue
            seen.add(key)
            pops += 1
            if pops > 900000:
                print(f"  limit {net} {p.ref}.{p.pin}", flush=True)
                return False
            if key in occ and key != start:
                found = key
                break
            x, y = xy_of(ix, iy)
            for dix, diy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dix, iy + diy
                if box and not (box[0] <= jx <= box[1] and box[2] <= jy <= box[3]):
                    continue
                nx, ny = xy_of(jx, jy)
                dest_goal = (jx, jy, layer_i) in occ
                if blocked(nx, ny, lname[layer_i], half, net, clr, False) and not dest_goal:
                    continue
                mx, my = (x + nx) / 2.0, (y + ny) / 2.0
                if blocked(mx, my, lname[layer_i], half, net, clr, False):
                    continue
                nkey = (jx, jy, layer_i)
                if nkey in seen or nkey in parent:
                    continue
                parent[nkey] = key
                ng = g + RES
                _hq.heappush(heap, (ng + h_of(jx, jy), ng, jx, jy, layer_i))
            ox, oy = x, y
            olayer = 1 - layer_i
            if blocked(ox, oy, lname[olayer], half, net, clr, True):
                continue
            vkey = (ix, iy, olayer)
            if vkey in seen or vkey in parent:
                continue
            parent[vkey] = key
            ng = g + VIA_COST
            _hq.heappush(heap, (ng + h_of(ix, iy), ng, ix, iy, olayer))
        if found is None:
            return False
        states = []
        cur = found
        while cur is not None:
            states.append(cur)
            cur = parent[cur]
        states.reverse()
        pts = []
        cx, cy = round(p.x, 3), round(p.y, 3)
        pts.append((cx, cy, states[0][2]))
        for ix, iy, layer_i in states:
            x, y = xy_of(ix, iy)
            if abs(x - pts[-1][0]) < 1e-6 and abs(y - pts[-1][1]) < 1e-6 and layer_i == pts[-1][2]:
                continue
            pts.append((x, y, layer_i))
        gx, gy, gl = pts[-1]
        dist, hx, hy = closest_hit(net, gx, gy, lname[gl])
        if 0.004 < dist < 0.08:
            pts.append((round(hx, 3), round(hy, 3), gl))
        # Compress per layer and emit.
        runs = []
        vias_at = []
        cur_l = pts[0][2]
        cur_pts = [(pts[0][0], pts[0][1])]
        for x, y, layer_i in pts[1:]:
            if layer_i != cur_l:
                vx, vy = cur_pts[-1]
                vias_at.append((vx, vy))
                runs.append((cur_l, cur_pts))
                cur_l = layer_i
                cur_pts = [(round(x, 3), round(y, 3))]
            else:
                cur_pts.append((x, y))
        runs.append((cur_l, cur_pts))
        for li, (layer_i, run) in enumerate(runs):
            run = _compress(run)
            run = _unstair(run, lname[layer_i], half, net, clr, li == len(runs) - 1)
            if len(run) >= 2:
                add_poly(net, lname[layer_i], run, width)
        for vx, vy in vias_at:
            add_via(net, vx, vy)
        return True

    def _clear_line(x1, y1, x2, y2, layer_name, half, net, clr, goal):
        # Same test the search applies to every grid point, every 0.02 mm along the line.
        # The goal end may sit in copper the search was allowed to enter.
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / 0.02))
        for k in range(n + 1):
            t = k / n
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            if goal and math.hypot(x - x2, y - y2) < 0.06:
                continue
            if blocked(x, y, layer_name, half, net, clr, False):
                return False
        return True

    def _unstair(pts, layer_name, half, net, clr, ends_at_goal):
        # The grid search only moves along X and Y, so a diagonal comes out as a staircase of
        # 0.05 mm steps. Each run of short steps becomes one straight segment when that line
        # passes the search's own clearance test; otherwise its halves are tried.
        if len(pts) < 3:
            return pts

        def pull(a, b):
            if b - a < 2:
                return [pts[a]]
            goal = ends_at_goal and b == len(pts) - 1
            if _clear_line(*pts[a], *pts[b], layer_name, half, net, clr, goal):
                return [pts[a]]
            m = (a + b) // 2
            return pull(a, m) + pull(m, b)

        out = []
        i = 0
        while i < len(pts) - 1:
            j = i
            while j < len(pts) - 1 and math.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]) < 0.11:
                j += 1
            if j - i >= 2:
                out += pull(i, j)
                i = j
            else:
                out.append(pts[i])
                i += 1
        out.append(pts[-1])
        return _compress(out)

    # USB, VBUS and the 3V3/EN trunks are already drawn; the search adds the rest. Signals
    # try 0.20 mm first, the 3V3 and EN branches (pull-ups, button) 0.25 mm.
    order = (
        ("GPIO8", 0.20), ("GPIO9", 0.20), ("GPIO18", 0.20), ("GPIO20", 0.20), ("GPIO19", 0.20),
        ("LED_DOOR", 0.20), ("CC1", 0.20), ("CC2", 0.20), ("3V3", 0.25), ("EN", 0.25),
        ("LED_CHIME", 0.20), ("LED_FLOOR", 0.20),
        ("DOOR", 0.25), ("CHIME", 0.25), ("FLOOR", 0.25), ("GND_BUS", 0.25),
    )
    failed = []
    for net, width in order:
        pads = [p for p in PADS if p.net == net and p.pin != ""]
        # Start from the pad nearest the others and add the rest nearest first, so short local
        # links (a pull-up beside its optocoupler pin) exist before the long run to the module.
        if len(pads) > 2:
            hub = min(pads, key=lambda p: sum(math.hypot(p.x - q.x, p.y - q.y) for q in pads))
            pads.sort(key=lambda p: math.hypot(p.x - hub.x, p.y - hub.y))
        loose = []
        seeded = False
        for p in pads:
            ix, iy = to_i(p.x), to_i(p.y)
            hit = any((ix, iy, layer_i) in occupied.get(net, ()) for layer_i in layers_of(p))
            if hit:
                seeded = True
            else:
                loose.append(p)
        if not seeded and loose:
            seed_pad(loose.pop(0))
        elif not seeded and pads:
            seed_pad(pads[0])
        for p in loose:
            ix, iy = to_i(p.x), to_i(p.y)
            if any((ix, iy, layer_i) in occupied.get(net, ()) for layer_i in layers_of(p)):
                continue
            t1 = _time.perf_counter()
            ok = False
            for margin in (16.0, None):
                if search(p, width, 0.24, margin):
                    ok = True
                    break
            if not ok and width > 0.15:
                ok = search(p, 0.15, 0.20, None)
            elif not ok:
                ok = search(p, width, 0.20, None)
            print(f"{net} {p.ref}.{p.pin} {'ok' if ok else 'FAIL'} { _time.perf_counter() - t1:.1f}s", flush=True)
            if ok:
                seed_pad(p)
            else:
                failed.append(f"{net} {p.ref}.{p.pin}")

    def try_gnd_via(net, x, y):
        if forbidden(x, y, VIA_R):
            return False
        if any(math.hypot(v.x - x, v.y - y) < 0.65 for v in VIAS):
            return False
        if blocked(x, y, "F", 0.15, net, 0.22, True):
            return False
        add_via(net, x, y)
        return True

    def try_gnd_via_beside(net, pad, reach=2.4):
        # Ground via beside a pad with a 0.25 mm stub out of the pad centre, its copper at
        # least 0.15 mm off the pad so the mask keeps a dam and no paste runs into the hole.
        # Rings around the pad centre, every 15 degrees, nearest first; the stub is straight.
        for k in range(1, int(reach / 0.05) + 1):
            d = round(k * 0.05, 3)
            for step in range(24):
                ang = math.radians(step * 15)
                dx, dy = math.cos(ang), math.sin(ang)
                x, y = round(pad.x + dx * d, 3), round(pad.y + dy * d, 3)
                if _point_rect(x, y, pad.x - pad.hw, pad.y - pad.hh, pad.x + pad.hw, pad.y + pad.hh) < VIA_R + 0.15:
                    continue
                if any(math.hypot(v.x - x, v.y - y) < 0.65 for v in VIAS):
                    continue
                if forbidden(x, y, VIA_R) or blocked(x, y, "F", 0.15, net, 0.22, True):
                    continue
                n = max(2, int(d / 0.05))
                if any(
                    blocked(pad.x + dx * d * j / n, pad.y + dy * d * j / n, "F", 0.125, net, 0.20, False)
                    for j in range(1, n)
                ):
                    continue
                add_poly(net, "F", [(pad.x, pad.y), (x, y)], 0.25)
                add_via(net, x, y)
                return True
        return False

    # Ground vias beside each ground pad (in the pad only when nothing fits beside it), then
    # stitching vias across both pours.
    for ref in ("C1", "C2", "C3", "C4", "C5", "C6", "R6", "SW1", "SW2"):
        hit = pads_of(ref, net="GND_MCU")
        if not hit:
            continue
        p = min(hit, key=lambda q: q.x * q.x + q.y * q.y)
        if not try_gnd_via_beside("GND_MCU", p):
            try_gnd_via("GND_MCU", p.x, p.y)
    for ref, pin in (("OK1", "2"), ("OK2", "3"), ("OK3", "3")):
        p = pads_of(ref, pin)[0]
        if not try_gnd_via_beside("GND_MCU", p):
            try_gnd_via("GND_MCU", p.x, p.y)
    try_gnd_via_beside("GND_MCU", pads_of("U1", "14")[0])
    mcu_poly = None
    bus_poly = None
    for name, layer, poly in zones():
        if layer == "F.Cu" and name == "GND_MCU":
            mcu_poly = poly
        if layer == "F.Cu" and name == "GND_BUS":
            bus_poly = poly
    for x, y in (
        (1.0, 8.55), (1.0, 25.4), (8.0, 25.5), (11.0, 18.0), (18.6, 18.0),
        (11.0, 22.4), (18.6, 22.4), (14.8, 24.0), (14.8, 17.0), (11.5, 9.7), (16.5, 9.7),
        (22.0, 9.7), (29.5, 11.0), (29.5, 25.4), (21.9, 25.5), (25.2, 25.5), (5.0, 19.67),
        (8.3, 6.6), (8.3, 10.4), (1.0, 12.4),
    ):
        if mcu_poly and _inside(x, y, mcu_poly):
            try_gnd_via("GND_MCU", x, y)
    # Bus side: the top strip, the gaps left of the terminal pins and the column below them.
    # The gaps right of the pins hold the wire-direction arrows on the silkscreen.
    for x, y in ((16.0, 3.2), (24.0, 3.2), (32.4, 3.2), (32.1, 13.9), (32.1, 17.7), (32.1, 21.5),
                 (32.2, 25.0), (32.3, 27.0), (34.6, 26.8), (35.6, 25.0), (35.6, 23.43),
                 (35.6, 19.62), (35.6, 15.81), (35.5, 28.4)):
        if bus_poly and _inside(x, y, bus_poly):
            try_gnd_via("GND_BUS", x, y)
    # Drop signal spurs. A via with copper on only one layer, and the track
    # that ran out to it, are removed. Ground vias stay: the pour joins them.
    def _on_copper(x, y, net, layer, skip):
        for p in PADS:
            if p.net != net or not p.pin or p.layer not in ("*", layer):
                continue
            if p.round_pad:
                if math.hypot(x - p.x, y - p.y) <= p.hw + 0.02:
                    return True
            elif (p.x - p.hw - 0.02 <= x <= p.x + p.hw + 0.02
                  and p.y - p.hh - 0.02 <= y <= p.y + p.hh + 0.02):
                return True
        for v in VIAS:
            if v.net == net and math.hypot(x - v.x, y - v.y) <= 0.02:
                return True
        for s in SEGS:
            if s is skip or s.net != net or s.layer != layer:
                continue
            if _point_seg(x, y, s.x1, s.y1, s.x2, s.y2) <= 0.02:
                return True
        return False

    def _via_layer(v, layer):
        for p in PADS:
            if p.net != v.net or not p.pin or p.layer not in ("*", layer):
                continue
            if p.round_pad:
                if math.hypot(v.x - p.x, v.y - p.y) <= p.hw + 0.02:
                    return True
            elif (p.x - p.hw - 0.02 <= v.x <= p.x + p.hw + 0.02
                  and p.y - p.hh - 0.02 <= v.y <= p.y + p.hh + 0.02):
                return True
        for s in SEGS:
            if s.net == v.net and s.layer == layer and _point_seg(v.x, v.y, s.x1, s.y1, s.x2, s.y2) <= 0.02:
                return True
        return False

    def _junctions(s):
        # Router snaps a T-join by up to 0.08 mm, so the touch test is wider
        # than the 0.02 mm connectivity test. The free end is then moved onto
        # the join, which brings the gap back under 0.02 mm.
        pts = []
        for other in SEGS:
            if other is s or other.net != s.net or other.layer != s.layer:
                continue
            for x, y in ((other.x1, other.y1), (other.x2, other.y2)):
                if _point_seg(x, y, s.x1, s.y1, s.x2, s.y2) <= 0.10:
                    pts.append((x, y))
        for v in VIAS:
            if v.net == s.net and _point_seg(v.x, v.y, s.x1, s.y1, s.x2, s.y2) <= 0.10:
                pts.append((v.x, v.y))
        return pts

    changed = True
    while changed:
        changed = False
        kept = []
        for s in SEGS:
            if s.net in ("GND_MCU", "GND_BUS"):
                kept.append(s)
                continue
            a_ok = _on_copper(s.x1, s.y1, s.net, s.layer, s)
            b_ok = _on_copper(s.x2, s.y2, s.net, s.layer, s)
            if a_ok and b_ok:
                kept.append(s)
                continue
            if not a_ok and not b_ok:
                changed = True
                continue
            anchor = (s.x1, s.y1) if a_ok else (s.x2, s.y2)
            length = math.hypot(s.x2 - s.x1, s.y2 - s.y1)
            best = None
            best_d = -1.0
            for x, y in _junctions(s):
                d_anchor = math.hypot(x - anchor[0], y - anchor[1])
                if d_anchor <= 0.02 or d_anchor > length + 0.02:
                    continue
                if d_anchor > best_d:
                    best = (x, y)
                    best_d = d_anchor
            if best is None:
                changed = True
                continue
            if a_ok:
                s.x2, s.y2 = best
            else:
                s.x1, s.y1 = best
            kept.append(s)
            changed = True
        SEGS[:] = kept
        kept_v = []
        for v in VIAS:
            if v.net in ("GND_MCU", "GND_BUS") or (_via_layer(v, "F") and _via_layer(v, "B")):
                kept_v.append(v)
            else:
                changed = True
        VIAS[:] = kept_v

    print(
        f"route {len(SEGS)} tracks {len(VIAS)} vias failed {len(failed)} in {_time.perf_counter() - t0:.1f}s",
        flush=True,
    )
    for item in failed:
        print("FAIL", item, flush=True)


def _closest_point(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return x1, y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return x1 + t * dx, y1 + t * dy


def _compress(pts):
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-6:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def zones():
    # Both pour outlines sit ISO_HALF from the barrier line, so every point of one ground pour
    # is at least 2 * ISO_HALF from the other, slot or no slot. GND_MCU stops at the antenna
    # keepout (y = ANT[1]) across its whole width. Bus is the strip above the slot and the
    # whole column beside and under the terminal, so J1 pin 4 never hangs on one track.
    h = ISO_HALF
    (bx0, _), (_, by1), (bx2, _), (_, by3), (bx4, _), (_, by5), (bx6, _), _ = BARRIER
    mcu = [
        (0.50, 0.50), (bx0 - h, 0.50), (bx0 - h, by1 + h), (bx2 - h, by1 + h),
        (bx2 - h, by3 + h), (bx4 - h, by3 + h), (bx4 - h, by5 + h), (bx6 - h, by5 + h),
        (bx6 - h, ANT[1]), (0.50, ANT[1]),
    ]
    bus = [
        (12.20, 0.50), (35.90, 0.50), (35.90, 28.90), (bx6 + h, 28.90),
        (bx6 + h, 4.85), (12.20, 4.85),
    ]
    return [
        ("GND_MCU", "F.Cu", mcu), ("GND_MCU", "B.Cu", mcu),
        ("GND_BUS", "F.Cu", bus), ("GND_BUS", "B.Cu", bus),
    ]


def bus_region():
    # Area on the bus side of the barrier line (the barrier plus the board's right edge).
    return list(BARRIER) + [(BOARD_W, BOARD_H), (BOARD_W, 0.0)]


def barrier_dist(x, y):
    return min(_point_seg(x, y, *a, *b) for a, b in zip(BARRIER, BARRIER[1:]))


def domain_of(net):
    return "BUS" if net in BUS_NETS else "MCU"


def domain_ok(x, y, reach, dom, _region=[]):
    # True when copper of radius `reach` at (x, y) stays ISO_HALF clear of the barrier on the
    # side its domain belongs to.
    if not _region:
        _region.extend(bus_region())
    on_bus = _inside(x, y, _region)
    if on_bus != (dom == "BUS"):
        return False
    return barrier_dist(x, y) >= reach + ISO_HALF - 1e-6


def _point_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _seg_rect(x1, y1, x2, y2, rx0, ry0, rx1, ry1):
    def inside(x, y):
        return rx0 <= x <= rx1 and ry0 <= y <= ry1

    if inside(x1, y1) or inside(x2, y2):
        return 0.0
    edges = [((rx0, ry0), (rx1, ry0)), ((rx1, ry0), (rx1, ry1)), ((rx1, ry1), (rx0, ry1)), ((rx0, ry1), (rx0, ry0))]
    for (ax, ay), (bx, by) in edges:
        if _segments_cross(x1, y1, x2, y2, ax, ay, bx, by):
            return 0.0
    d = min(_point_rect(x1, y1, rx0, ry0, rx1, ry1), _point_rect(x2, y2, rx0, ry0, rx1, ry1))
    for cx, cy in ((rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)):
        d = min(d, _point_seg(cx, cy, x1, y1, x2, y2))
    return d


def _point_rect(px, py, rx0, ry0, rx1, ry1):
    nx = min(max(px, rx0), rx1)
    ny = min(max(py, ry0), ry1)
    return math.hypot(px - nx, py - ny)


def _segments_cross(ax, ay, bx, by, cx, cy, dx, dy):
    def side(x, y, x1, y1, x2, y2):
        return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)

    s1 = side(cx, cy, ax, ay, bx, by)
    s2 = side(dx, dy, ax, ay, bx, by)
    s3 = side(ax, ay, cx, cy, dx, dy)
    s4 = side(bx, by, cx, cy, dx, dy)
    return s1 * s2 < 0 and s3 * s4 < 0


def _segseg(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    # Minimum distance between two segments given by their end points.
    if _segments_cross(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        return 0.0
    return min(
        _point_seg(ax1, ay1, bx1, by1, bx2, by2),
        _point_seg(ax2, ay2, bx1, by1, bx2, by2),
        _point_seg(bx1, by1, ax1, ay1, ax2, ay2),
        _point_seg(bx2, by2, ax1, ay1, ax2, ay2),
    )


def _seg_dist(a, b):
    # Minimum distance between two segments.
    if _segments_cross(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1, b.x2, b.y2):
        return 0.0
    return min(
        _point_seg(a.x1, a.y1, b.x1, b.y1, b.x2, b.y2),
        _point_seg(a.x2, a.y2, b.x1, b.y1, b.x2, b.y2),
        _point_seg(b.x1, b.y1, a.x1, a.y1, a.x2, a.y2),
        _point_seg(b.x2, b.y2, a.x1, a.y1, a.x2, a.y2),
    )


def _inside(x, y, poly):
    n = len(poly)
    inn = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
            if x < xint:
                inn = not inn
        j = i
    return inn


def _layers(item_layer):
    if item_layer in ("*", "both"):
        return ("F", "B")
    return (item_layer,)


def check_board():
    errors = []

    def err(msg):
        if len(errors) < 100:
            errors.append(msg)

    copper = []
    for p in PADS:
        if p.drill and p.pin == "" and abs(p.hw * 2 - p.drill) < 0.01:
            continue  # bare NPTH, checked as a hole
        for layer in _layers(p.layer):
            copper.append(("pad", p, layer, p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh))
    for s in SEGS:
        copper.append(("seg", s, s.layer, 0, 0, 0, 0))
    for v in VIAS:
        for layer in ("F", "B"):
            copper.append(("via", v, layer, v.x, v.y, v.size / 2, 0))

    def gap_of(a, b):
        ka, ia, la = a[0], a[1], a[2]
        kb, ib, lb = b[0], b[1], b[2]
        if la != lb:
            return None
        if ka == "pad" and kb == "pad":
            if ia.round_pad and ib.round_pad:
                return math.hypot(ia.x - ib.x, ia.y - ib.y) - ia.hw - ib.hw
            ax0, ay0, ax1, ay1 = a[3], a[4], a[5], a[6]
            bx0, by0, bx1, by1 = b[3], b[4], b[5], b[6]
            dx = max(ax0 - bx1, bx0 - ax1, 0)
            dy = max(ay0 - by1, by0 - ay1, 0)
            return math.hypot(dx, dy)
        if ka == "seg" and kb == "seg":
            return _seg_dist(ia, ib) - ia.w / 2 - ib.w / 2
        if ka == "via" and kb == "via":
            return math.hypot(ia.x - ib.x, ia.y - ib.y) - ia.size / 2 - ib.size / 2
        # seg/via vs pad, seg vs via
        if "seg" in (ka, kb) and "pad" in (ka, kb):
            seg = ia if ka == "seg" else ib
            pad_item = a if ka == "pad" else b
            pad = pad_item[1]
            if pad.round_pad:
                return _point_seg(pad.x, pad.y, seg.x1, seg.y1, seg.x2, seg.y2) - pad.hw - seg.w / 2
            dist = _seg_rect(seg.x1, seg.y1, seg.x2, seg.y2, pad_item[3], pad_item[4], pad_item[5], pad_item[6])
            return dist - seg.w / 2
        if "via" in (ka, kb) and "pad" in (ka, kb):
            via_i = ia if ka == "via" else ib
            pad_item = a if ka == "pad" else b
            pad = pad_item[1]
            if pad.round_pad:
                return math.hypot(via_i.x - pad.x, via_i.y - pad.y) - pad.hw - via_i.size / 2
            return _point_rect(via_i.x, via_i.y, pad_item[3], pad_item[4], pad_item[5], pad_item[6]) - via_i.size / 2
        if "via" in (ka, kb) and "seg" in (ka, kb):
            via_i = ia if ka == "via" else ib
            seg = ia if ka == "seg" else ib
            return _point_seg(via_i.x, via_i.y, seg.x1, seg.y1, seg.x2, seg.y2) - via_i.size / 2 - seg.w / 2
        return None

    def net_of(item):
        return item[1].net

    for i in range(len(copper)):
        for j in range(i + 1, len(copper)):
            a, b = copper[i], copper[j]
            if a[2] != b[2]:
                continue
            na, nb = net_of(a), net_of(b)
            if na and na == nb:
                continue
            # A bare hole has no net and was skipped. NPTH pads that remain are holes.
            g = gap_of(a, b)
            if g is None:
                continue
            if g < CLEARANCE - 1e-3:
                err(
                    f"clearance {g:.2f} {a[2]} {na or '-'} { _tag(a)}  vs  {nb or '-'} {_tag(b)}"
                )

    # Edge, slot, antenna, M3.
    sx0, sy0, sx1, sy1 = SLOT
    ax0, ay0, ax1, ay1 = ANT
    holes = [p for p in PADS if p.drill >= 3.0]
    npth = [p for p in PADS if p.pin == "" and p.drill > 0]

    def consider_box(net, layer, x0, y0, x1, y1, label):
        if x0 < EDGE_COPPER or y0 < EDGE_COPPER or BOARD_W - x1 < EDGE_COPPER or BOARD_H - y1 < EDGE_COPPER:
            err(f"edge {label} box ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f})")
        if x0 < sx1 + 0.31 and x1 > sx0 - 0.31 and y0 < sy1 + 0.31 and y1 > sy0 - 0.31:
            err(f"slot {label}")
        if x0 < ax1 and x1 > ax0 and y0 < ay1 and y1 > ay0:
            err(f"antenna {label}")
        for h in holes:
            d = _point_rect(h.x, h.y, x0, y0, x1, y1)
            if d - h.drill / 2 < M3_COPPER:
                err(f"M3 {label} gap {d - h.drill / 2:.2f}")
        for h in npth:
            d = _point_rect(h.x, h.y, x0, y0, x1, y1)
            if d - h.drill / 2 < 0.20:
                err(f"NPTH {label} gap {d - h.drill / 2:.2f}")

    for p in PADS:
        if p.pin == "" and p.drill:
            continue
        consider_box(p.net, "F" if p.layer != "B" else "B", p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh, f"pad {p.ref}.{p.pin} {p.net}")
        if p.layer == "*":
            consider_box(p.net, "B", p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh, f"pad {p.ref}.{p.pin} {p.net}")
    for s in SEGS:
        samples = 12
        for i in range(samples + 1):
            t = i / samples
            x = s.x1 + (s.x2 - s.x1) * t
            y = s.y1 + (s.y2 - s.y1) * t
            consider_box(s.net, s.layer, x - s.w / 2, y - s.w / 2, x + s.w / 2, y + s.w / 2, f"track {s.net} {s.layer}")
    for v in VIAS:
        consider_box(v.net, "F", v.x - v.size / 2, v.y - v.size / 2, v.x + v.size / 2, v.y + v.size / 2, f"via {v.net}")

    # Connectivity, including a same-net zone when a pad centre lies inside it.
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    nodes = []
    for i, p in enumerate(PADS):
        if p.net:
            nodes.append(("p", i))
    for i, v in enumerate(VIAS):
        nodes.append(("v", i))
    for n in nodes:
        find(n)
    # Same footprint pad number is one pin.
    groups = {}
    for i, p in enumerate(PADS):
        if p.net and p.pin:
            groups.setdefault((p.ref, p.pin), []).append(i)
    for ids in groups.values():
        for i in ids[1:]:
            union(("p", ids[0]), ("p", i))
    # Overlapping same-net copper.
    for i, a in enumerate(copper):
        for b in copper[i + 1 :]:
            if a[2] != b[2] or not net_of(a) or net_of(a) != net_of(b):
                continue
            g = gap_of(a, b)
            if g is not None and g <= 0.02:
                union(_node(a), _node(b))
    for name, layer, poly in zones():
        members = []
        lay = "F" if layer == "F.Cu" else "B"
        for i, p in enumerate(PADS):
            if p.net == name and (p.layer in (lay, "*")) and _inside(p.x, p.y, poly):
                members.append(("p", i))
        for i, v in enumerate(VIAS):
            if v.net == name and _inside(v.x, v.y, poly):
                members.append(("v", i))
        for m in members[1:]:
            union(members[0], m)

    by_net = {}
    seen_root = {}
    for i, p in enumerate(PADS):
        if not p.net:
            continue
        root = find(("p", i))
        by_net.setdefault(p.net, set()).add(root)
        seen_root.setdefault(root, f"{p.ref}.{p.pin}")
    for net, roots in sorted(by_net.items()):
        if len(roots) > 1:
            sample = ", ".join(seen_root[r] for r in list(roots)[:8])
            err(f"open {net} ({len(roots)} groups) e.g. {sample}")

    # Isolation: all copper of each ground domain, both layers, and both pour outlines keep
    # ISO_HALF from the barrier line on their own side. Pads without a net are on the MCU side.
    region = bus_region()
    bar = list(zip(BARRIER, BARRIER[1:]))

    def iso(dom, cx, cy, dist, label):
        if _inside(cx, cy, region) != (dom == "BUS"):
            err(f"isolation {label} on the wrong side of the barrier")
        elif dist < ISO_HALF - 1e-3:
            err(f"isolation {label} {dist:.2f} mm from the barrier, min {ISO_HALF:.2f}")

    for p in PADS:
        if p.pin == "" and p.drill:
            continue
        if p.round_pad:
            dist = barrier_dist(p.x, p.y) - p.hw
        else:
            dist = min(_seg_rect(*a, *b, p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh) for a, b in bar)
        iso(domain_of(p.net), p.x, p.y, dist, f"pad {p.ref}.{p.pin} {p.net or '-'}")
    for s in SEGS:
        dist = min(_segseg(s.x1, s.y1, s.x2, s.y2, *a, *b) for a, b in bar) - s.w / 2
        iso(domain_of(s.net), (s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2, dist, f"track {s.net} {s.layer} ({s.x1:.2f},{s.y1:.2f})")
    for v in VIAS:
        iso(domain_of(v.net), v.x, v.y, barrier_dist(v.x, v.y) - v.size / 2, f"via {v.net} ({v.x:.2f},{v.y:.2f})")
    for name, layer, poly in zones():
        edges = list(zip(poly, poly[1:] + poly[:1]))
        dist = min(_segseg(*e0, *e1, *a, *b) for e0, e1 in edges for a, b in bar)
        iso(domain_of(name), poly[0][0], poly[0][1], dist, f"pour {name} {layer}")

    # The two grounds never share a pad.
    mcu_pts = {(round(p.x, 3), round(p.y, 3)) for p in PADS if p.net == "GND_MCU"}
    for p in PADS:
        if p.net == "GND_BUS" and (round(p.x, 3), round(p.y, 3)) in mcu_pts:
            err("GND_MCU and GND_BUS share a coordinate")
    return errors


def check_holes():
    errors = []
    for i, a in enumerate(VIAS):
        for b in VIAS[i + 1:]:
            gap = math.hypot(a.x - b.x, a.y - b.y) - a.drill / 2 - b.drill / 2
            if gap < 0.25:
                errors.append(f"via holes ({a.x:.2f},{a.y:.2f}) and ({b.x:.2f},{b.y:.2f}) are {gap:.2f} mm apart, min 0.25")
    return errors


def check_module_pads():
    # A via in or against an SMD pad drinks the paste and the joint opens. Every via keeps
    # 0.15 mm of copper-free mask to every SMD pad, own net included (KLEIN1 had 31 in pads).
    errors = []
    for v in VIAS:
        for p in PADS:
            if p.layer == "*" or (p.pin == "" and p.drill):
                continue
            gap = _point_rect(v.x, v.y, p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh) - v.size / 2
            if gap < 0.15 - 1e-3:
                errors.append(f"via ({v.x:.2f},{v.y:.2f}) {v.net} {gap:.2f} mm from pad {p.ref}.{p.pin}")
    return errors


def _dot_problems(ref, x, y, placed):
    out = DOT_R + DOT_W / 2
    sx0, sy0, sx1, sy1 = SLOT
    tag = f"silk dot {ref} ({x:.2f},{y:.2f})"
    probs = []
    if min(x, y, BOARD_W - x, BOARD_H - y) - out < 0.4:
        probs.append(f"{tag} too close to the board edge")
    for p in PADS:
        if p.drill and p.pin == "":
            gap = math.hypot(x - p.x, y - p.y) - p.drill / 2 - out
            if gap < 0.3:
                probs.append(f"{tag} gap {gap:.2f} to hole {p.ref}")
        elif p.round_pad:
            gap = math.hypot(x - p.x, y - p.y) - p.hw - out
            if gap < 0.25:
                probs.append(f"{tag} gap {gap:.2f} to pad {p.ref}.{p.pin}")
        else:
            gap = _point_rect(x, y, p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh) - out
            if gap < 0.25:
                probs.append(f"{tag} gap {gap:.2f} to pad {p.ref}.{p.pin}")
    for v in VIAS:
        gap = math.hypot(x - v.x, y - v.y) - v.size / 2 - out
        if gap < 0.15:
            probs.append(f"{tag} gap {gap:.2f} to via ({v.x:.2f},{v.y:.2f})")
    if _point_rect(x, y, sx0, sy0, sx1, sy1) - out < 0.4:
        probs.append(f"{tag} too close to the slot")
    for qx, qy in placed:
        if math.hypot(x - qx, y - qy) < 2 * out + 0.3:
            probs.append(f"{tag} too close to another silk dot")
    # Pin 1 must be the nearest pin, by a clear margin.
    pins = [p for p in PADS if p.ref == ref and p.pin.isdigit() and int(p.pin) <= PIN_MAX.get(ref, 999)]
    dist = {}
    for p in pins:
        d = _point_rect(x, y, p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh)
        dist[p.pin] = min(d, dist.get(p.pin, 1e9))
    others = [d for pin, d in dist.items() if pin != "1"]
    if "1" not in dist or (others and dist["1"] + 0.3 > min(others)):
        near = min(dist, key=dist.get) if dist else "?"
        probs.append(f"{tag} nearest pin is {ref}.{near}, not pin 1")
    # Visible: not inside another part's courtyard.
    for part in PARTS:
        if part.ref == ref or not part.courtyard:
            continue
        x0, y0, x1, y1 = part.courtyard
        pts = [rot_xy(a, b, part.rot) for a, b in ((x0, y0), (x1, y1))]
        bx0 = part.x + min(p[0] for p in pts)
        bx1 = part.x + max(p[0] for p in pts)
        by0 = part.y + min(p[1] for p in pts)
        by1 = part.y + max(p[1] for p in pts)
        if bx0 - out < x < bx1 + out and by0 - out < y < by1 + out:
            probs.append(f"{tag} inside the courtyard of {part.ref}")
    return probs


def place_pin1_dots():
    # Nearest accepted spot on rings around each pin 1, 0.6 to 3 mm out, every 10 degrees.
    PIN1_DOTS.clear()
    placed = []
    for ref in PIN1_REFS:
        p1 = pads_of(ref, "1")[0]
        best = None
        for k in range(12, 61):
            r = k * 0.05
            for a in range(0, 360, 10):
                x = round(p1.x + r * math.cos(math.radians(a)), 2)
                y = round(p1.y + r * math.sin(math.radians(a)), 2)
                if not _dot_problems(ref, x, y, placed):
                    best = (x, y)
                    break
            if best:
                break
        if best is None:
            raise SystemExit(f"no spot for the pin-1 dot of {ref}")
        PIN1_DOTS.append((ref, *best))
        placed.append(best)


def check_silk():
    errors = []
    placed = []
    if len(PIN1_DOTS) != len(PIN1_REFS):
        errors.append("pin-1 dots missing")
    for ref, x, y in PIN1_DOTS:
        errors.extend(_dot_problems(ref, x, y, placed))
        placed.append((x, y))
    return errors


def _node(item):
    kind, obj = item[0], item[1]
    if kind == "pad":
        return ("p", PADS.index(obj))
    if kind == "via":
        return ("v", VIAS.index(obj))
    return ("s", id(obj))


def _tag(item):
    kind, obj = item[0], item[1]
    if kind == "pad":
        return f"{obj.ref}.{obj.pin}@({obj.x:.2f},{obj.y:.2f})"
    if kind == "via":
        return f"via@({obj.x:.2f},{obj.y:.2f})"
    return f"seg ({obj.x1:.2f},{obj.y1:.2f})-({obj.x2:.2f},{obj.y2:.2f}) w{obj.w}"


# ---------------------------------------------------------------------------
# KiCad output
# ---------------------------------------------------------------------------

NETS = [
    "GND_MCU", "GND_BUS", "VBUS", "3V3", "EN", "GPIO19", "GPIO18", "GPIO20", "GPIO9",
    "USB_DP", "USB_DM", "CC1", "CC2", "DOOR", "CHIME", "FLOOR", "LED_DOOR", "LED_CHIME",
    "LED_FLOOR", "GPIO8",
]


def net_id(name: str) -> int:
    if not name:
        return 0
    return NETS.index(name) + 1


def write_pcb(path: Path):
    L = []
    w = L.append
    w("(kicad_pcb")
    w("\t(version 20240108)")
    w(f'\t(generator "{SLUG}")')
    w('\t(generator_version "1.0")')
    w("\t(general (thickness 1.6) (legacy_teardrops no))")
    w('\t(paper "A4")')
    w("\t(title_block")
    w(f'\t\t(title "{NAME} - Ritto 7630 TwinBus interface, ESP32-C6-MINI-1")')
    w('\t\t(date "2026-10-18")')
    w(f'\t\t(rev "{VERSION}")')
    w('\t\t(comment 1 "Galvanically isolated. Do not join GND_MCU and GND_BUS. Do not connect +24V.")')
    w('\t\t(comment 2 "GPIO19 DOOR, GPIO20 FLOOR, GPIO18 CHIME. USB-C on GPIO12/GPIO13.")')
    w("\t)")
    w(_LAYERS)
    w("\t(setup")
    w("\t\t(pad_to_mask_clearance 0.05)")
    w("\t\t(allow_soldermask_bridges_in_footprints yes)")
    w(_PLOT)
    w("\t)")
    w('\t(net 0 "")')
    for i, name in enumerate(NETS, start=1):
        w(f'\t(net {i} "{name}")')

    def prop(key, value, layer, hide=True):
        vis = " (hide yes)" if hide else ""
        w(
            f'\t\t(property "{key}" "{value}" (at 0 0 0) (layer "{layer}"){vis} '
            f'(uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.12))))'
        )

    for part in PARTS:
        w(f'\t(footprint "{part.footprint}"')
        w(f'\t\t(layer "F.Cu") (uuid "{uid()}")')
        rot = f" {num(part.rot)}" if part.rot else ""
        w(f"\t\t(at {num(part.x)} {num(part.y)}{rot})")
        prop("Reference", part.ref, "F.SilkS", True)
        prop("Value", part.value, "F.Fab", True)
        prop("Footprint", part.footprint, "F.Fab")
        prop("Datasheet", "", "F.Fab")
        ident = f"LCSC {part.lcsc}" if str(part.lcsc).startswith("C") else f"order {part.lcsc}"
        prop("Description", f"{part.mfr} {part.mpn} {ident}", "F.Fab")
        w(f"\t\t(attr {part.attr})")
        if part.courtyard:
            x0, y0, x1, y1 = part.courtyard
            w(f'\t\t(fp_rect (start {num(x0)} {num(y0)}) (end {num(x1)} {num(y1)}) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd") (uuid "{uid()}"))')
        for p in part.pads:
            _emit_pad(w, p, part.rot)
        w("\t)")

    for i, (x, y) in enumerate(m3_holes(), start=1):
        w('\t(footprint "MountingHole_M3"')
        w(f'\t\t(layer "F.Cu") (uuid "{uid()}")')
        w(f"\t\t(at {num(x)} {num(y)})")
        prop("Reference", f"H{i}", "F.SilkS")
        prop("Value", "M3", "F.Fab")
        prop("Footprint", "MountingHole_M3", "F.Fab")
        prop("Datasheet", "", "F.Fab")
        prop("Description", "", "F.Fab")
        w("\t\t(attr board_only exclude_from_pos_files exclude_from_bom)")
        w(f'\t\t(pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))')
        w("\t)")

    def line(x1, y1, x2, y2, layer, width=0.05):
        w(
            f'\t(gr_line (start {num(x1)} {num(y1)}) (end {num(x2)} {num(y2)}) '
            f'(stroke (width {width}) (type default)) (layer "{layer}") (uuid "{uid()}"))'
        )

    # Outline and the unplated isolation slot.
    line(0, 0, BOARD_W, 0, "Edge.Cuts")
    line(BOARD_W, 0, BOARD_W, BOARD_H, "Edge.Cuts")
    line(BOARD_W, BOARD_H, 0, BOARD_H, "Edge.Cuts")
    line(0, BOARD_H, 0, 0, "Edge.Cuts")
    x0, y0, x1, y1 = SLOT
    line(x0, y0, x1, y0, "Edge.Cuts")
    line(x1, y0, x1, y1, "Edge.Cuts")
    line(x1, y1, x0, y1, "Edge.Cuts")
    line(x0, y1, x0, y0, "Edge.Cuts")

    def silk(text, x, y, rot=0, size=0.9, justify="left", width=None):
        just = f" (justify {justify})" if justify != "center" else ""
        w(
            f'\t(gr_text "{text}" (at {num(x)} {num(y)} {num(rot)}) (layer "F.SilkS") (uuid "{uid()}") '
            f"(effects (font (size {size} {width or size}) (thickness 0.15)){just}))"
        )

    # Terminal names behind J1's body (back face at x = 30.25), one per pin, centred on it and
    # read from the right edge. They stay visible after assembly.
    j1 = next(q for q in PARTS if q.ref == "J1")
    for name, pin in (("DOOR", "1"), ("CHIME", "2"), ("FLOOR", "3"), ("GND", "4")):
        silk(name, 29.55, at("J1", pin)[1], 90, 0.8, "center", 0.6)
    # J1 assembly marks. The pin row sits 3.60 mm from the back and 3.70 mm from the wire face,
    # so the holes do not show which way round the block goes: the back face and both ends of
    # the body are drawn, and an arrow between each pair of pins points at the wire openings.
    xb = j1.x - TB_BACK
    yt, yb = j1.y - TB_END, j1.y + 3 * TB_PITCH + TB_END
    for x1, y1, x2, y2 in ((xb, yt, xb, yb), (xb, yt, BOARD_W - 0.4, yt), (xb, yb, BOARD_W - 0.4, yb)):
        line(x1, y1, x2, y2, "F.SilkS", 0.15)
    for k in range(3):
        ym = j1.y + (k + 0.5) * TB_PITCH
        pts = " ".join(f"(xy {num(x)} {num(y)})" for x, y in ((34.45, ym - 0.35), (35.35, ym), (34.45, ym + 0.35)))
        w(f'\t(gr_poly (pts {pts}) (stroke (width 0.1) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{uid()}"))')
    # Notes in the two empty corners beside the antenna (no copper there, visible after
    # assembly; the module covers x 8.2..21.4).
    silk(NAME, 0.8, 27.0, 0, 0.9, width=0.8)
    silk(f"v{VERSION}", 0.8, 28.5, 0, 0.8, width=0.7)
    silk("ANTENNA", 0.8, 29.85, 0, 0.8, width=0.7)
    silk("NO +24V", 21.9, 27.0, 0, 0.8, width=0.65)
    silk("GND ISOLATED", 21.9, 28.3, 0, 0.8, width=0.6)
    silk("OK1 OUTPUT", 11.3, 7.8, 0, 0.8)
    for _ref, dx, dy in PIN1_DOTS:
        w(
            f'\t(gr_circle (center {num(dx)} {num(dy)}) (end {num(dx + DOT_R)} {num(dy)}) '
            f'(stroke (width {DOT_W}) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{uid()}"))'
        )

    for s in SEGS:
        layer = "F.Cu" if s.layer == "F" else "B.Cu"
        w(
            f"\t(segment (start {num(s.x1)} {num(s.y1)}) (end {num(s.x2)} {num(s.y2)}) "
            f"(width {num(s.w)}) (layer \"{layer}\") (net {net_id(s.net)}) (uuid \"{uid()}\"))"
        )
    for v in VIAS:
        w(
            f"\t(via (at {num(v.x)} {num(v.y)}) (size {num(v.size)}) (drill {num(v.drill)}) "
            f'(layers "F.Cu" "B.Cu") (net {net_id(v.net)}) (uuid "{uid()}"))'
        )
    for name, layer, poly in zones():
        _zone(w, name, layer, poly, keepout=False)
    _zone(w, "", "F.Cu", [(ANT[0], ANT[1]), (ANT[2], ANT[1]), (ANT[2], ANT[3]), (ANT[0], ANT[3])], keepout=True)
    _zone(w, "", "B.Cu", [(ANT[0], ANT[1]), (ANT[2], ANT[1]), (ANT[2], ANT[3]), (ANT[0], ANT[3])], keepout=True)
    # Keep the pours off the M3 holes by 0.6 mm.
    for x, y in m3_holes():
        octagon = []
        for k in range(8):
            a = math.radians(22.5 + k * 45)
            octagon.append((x + 2.25 * math.cos(a), y + 2.25 * math.sin(a)))
        _zone(w, "", "F.Cu", octagon, keepout=True)
        _zone(w, "", "B.Cu", octagon, keepout=True)
    w(")")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def _emit_pad(w, p, rot=0):
    # KiCad 10 keeps pad size in the footprint's unrotated frame. For a 90° or
    # 270° footprint the pitch axis would keep the long pad side, so swap here.
    shape = "circle" if p.get("round") else ("oval" if p.get("oval") else "roundrect")
    kind = "np_thru_hole" if p.get("npth") else ("thru_hole" if p.get("layer") == "*" else "smd")
    pin = p["pin"]
    prot = p.get("rot", 0)
    sx, sy = p["sx"], p["sy"]
    swap = int(round(rot)) % 180 != 0
    if swap:
        sx, sy = sy, sx
    at = f'{num(p["x"])} {num(p["y"])}' + (f" {num(prot)}" if prot else "")
    w(f'\t\t(pad "{pin}" {kind} {shape}')
    w(f"\t\t\t(at {at})")
    w(f'\t\t\t(size {num(sx)} {num(sy)})')
    if p.get("drill_oval"):
        dx, dy = p["drill_oval"]
        if swap:
            dx, dy = dy, dx
        w(f"\t\t\t(drill oval {num(dx)} {num(dy)})")
    elif p.get("drill"):
        w(f'\t\t\t(drill {num(p["drill"])})')
    if kind == "smd":
        w('\t\t\t(layers "F.Cu" "F.Paste" "F.Mask")')
        w("\t\t\t(roundrect_rratio 0.15)")
    else:
        w('\t\t\t(layers "*.Cu" "*.Mask")')
        w("\t\t\t(remove_unused_layers no)")
    net = p.get("net") or ""
    if net:
        w(f'\t\t\t(net {net_id(net)} "{net}")')
    w(f'\t\t\t(uuid "{uid()}")')
    w("\t\t)")


def _zone(w, name, layer, poly, keepout, allow_tracks=False):
    nid = net_id(name) if name else 0
    w("\t(zone")
    w(f"\t\t(net {nid})")
    w(f'\t\t(net_name "{name}")')
    w(f'\t\t(layer "{layer}")')
    w(f'\t\t(uuid "{uid()}")')
    w("\t\t(hatch edge 0.5)")
    w("\t\t(priority 0)")
    # SMD pads connect solid; through-hole pads keep a thermal spoke.
    # The module corner pad and R6 have no room for two spokes.
    # Clearance to every other net stays 0.3 mm.
    if keepout:
        w("\t\t(connect_pads (clearance 0.3))")
    else:
        w("\t\t(connect_pads thru_hole_only (clearance 0.3))")
    w("\t\t(min_thickness 0.2)")
    w("\t\t(filled_areas_thickness no)")
    if keepout:
        tracks = "allowed" if allow_tracks else "not_allowed"
        w(f"\t\t(keepout (tracks {tracks}) (vias {tracks}) (pads allowed) (copperpour not_allowed) (footprints allowed))")
        w("\t\t(fill (thermal_gap 0.3) (thermal_bridge_width 0.4))")
    else:
        w("\t\t(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))")
    w("\t\t(polygon (pts")
    for x, y in poly:
        w(f"\t\t\t(xy {num(x)} {num(y)})")
    w("\t\t))")
    w("\t)")


_LAYERS = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)"""

_PLOT = """\t\t(pcbplotparams
\t\t\t(layerselection 0x00010fc_ffffffff)
\t\t\t(plot_on_all_layers_selection 0x0000000_00000000)
\t\t\t(disableapertmacros no) (usegerberextensions yes) (usegerberattributes yes)
\t\t\t(usegerberadvancedattributes yes) (creategerberjobfile yes)
\t\t\t(dashed_line_dash_ratio 12) (dashed_line_gap_ratio 3) (svgprecision 4)
\t\t\t(plotframeref no) (viasonmask no) (mode 1) (useauxorigin no)
\t\t\t(hpglpennumber 1) (hpglpenspeed 20) (hpglpendiameter 15)
\t\t\t(pdf_front_fp_property_popups yes) (pdf_back_fp_property_popups yes)
\t\t\t(dxfpolygonmode yes) (dxfimperialunits yes) (dxfusepcbnewfont yes)
\t\t\t(psnegative no) (psa4output no) (plotreference yes) (plotvalue yes)
\t\t\t(plotfptext yes) (plotinvisibletext no) (sketchpadsonfab no)
\t\t\t(subtractmaskfromsilk no) (outputformat 1) (mirror no) (drillshape 1)
\t\t\t(scaleselection 1) (outputdirectory "gerber/")
\t\t)"""


def write_pro(path: Path):
    path.write_text(
        """{
  "board": {
    "design_settings": {
      "defaults": { "board_outline_line_width": 0.05 },
      "rules": {
        "min_clearance": 0.2,
        "min_track_width": 0.15,
        "min_via_diameter": 0.65,
        "min_via_drill": 0.3,
        "min_through_hole_diameter": 0.3,
        "min_hole_clearance": 0.2,
        "min_hole_to_hole": 0.25,
        "min_copper_edge_clearance": 0.3
      }
    }
  },
  "meta": { "filename": "@SLUG@.kicad_pro", "version": 1 },
  "net_settings": {
    "classes": [
      {
        "name": "Default",
        "clearance": 0.2,
        "track_width": 0.25,
        "via_diameter": 0.65,
        "via_drill": 0.3,
        "diff_pair_width": 0.25,
        "diff_pair_gap": 0.2
      }
    ]
  },
  "pcbnew": { "page_layout_descr_file": "" },
  "schematic": {},
  "sheets": [],
  "text_variables": {}
}
""".replace("@SLUG@", SLUG),
        encoding="utf-8",
    )


def bom_order(part):
    order = ("U", "J", "OK", "R", "C", "SW")
    prefix = part.ref.rstrip("0123456789")
    return (order.index(prefix) if prefix in order else len(order), int(part.ref[len(prefix):] or 0))


# Short descriptions for the BOM, so that a substitute keeps value, rating and package.
DESCRIPTION = {
    "ESP32-C6-MINI-1-N4": "ESP32-C6 module, 4 MB flash, PCB antenna",
    "AP2112K-3.3TRG1": "LDO 3.3 V 600 mA",
    "USBLC6-2SC6": "USB ESD protection, 2 lines + VBUS",
    "WJ124-3.81-04P-14-00A": "Screw terminal, 4 pins, pitch 3.81 mm, 8.6 mm high",
    "TYPE-C-31-M-12": "USB-C receptacle 16P, SMD with through-hole shell lugs",
    "LTV-817S-TA1-C": "Optocoupler, transistor output, CTR rank C (200-400 %)",
    "0805W8F2200T5E": "Resistor 220 ohm 1 % 0805",
    "RC-12K1501FT": "Resistor 1.5 kohm 1 % 1 W 2512",
    "0805W8F1002T5E": "Resistor 10 kohm 1 % 0805",
    "0805W8F1003T5E": "Resistor 100 kohm 1 % 0805",
    "0603WAF5101T5E": "Resistor 5.1 kohm 1 % 0603",
    "CL21A106KOQNNNE": "Capacitor 10 uF 16 V X5R 0805",
    "CL21B104KBFNNNE": "Capacitor 100 nF 50 V X7R 0805",
    "CL21B105KBFNNNE": "Capacitor 1 uF 50 V X7R 0805",
    "TS-1187A-B-A-B": "Tactile switch 5.1 x 5.1 mm, 1.5 mm high",
}


def write_bom(path: Path):
    # One line per part number with its quantity, as PCBWay's BOM template asks.
    groups = {}
    for p in sorted(PARTS, key=bom_order):
        groups.setdefault(p.mpn, []).append(p)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Designator", "Qty", "Manufacturer", "Mfg Part #", "Description",
                         "Value", "Package", "Type", "LCSC"])
        for item, parts in enumerate(groups.values(), start=1):
            p = parts[0]
            kind = "THT" if p.attr == "through_hole" else "SMD"
            value = " / ".join(dict.fromkeys(q.value for q in parts))
            writer.writerow([item, ", ".join(q.ref for q in parts), len(parts), p.mfr, p.mpn,
                             DESCRIPTION[p.mpn], value, p.footprint, kind, p.lcsc])


def write_cpl(path: Path):
    # Origin lower left, Y up, rotation CCW. The board file is Y down from the top left, so the
    # lower-left outline corner is (0, BOARD_H) and Mid Y is BOARD_H - y. The angle needs no
    # change: KiCad's positive angle is counter-clockwise on screen, as in a Y-up top view.
    # PCBWay's library zero-rotation can differ. Confirm the preview before paying.
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in sorted(PARTS, key=bom_order):
            # J1's footprint origin is pin 1; its body centre is 5.715 mm along the pin row and
            # 0.05 mm toward the wire face. Every other footprint's origin is its body centre.
            ox, oy = BODY_CENTRE.get(p.footprint, (0.0, 0.0))
            dx, dy = rot_xy(ox, oy, p.rot)
            writer.writerow([p.ref, f"{p.x + dx:.4f}", f"{BOARD_H - (p.y + dy):.4f}", "top", f"{p.rot:.1f}"])


BODY_CENTRE = {"TerminalBlock_Kangnex_WJ124-3.81_1x04_P3.81mm": (1.5 * TB_PITCH, (TB_BACK - TB_FRONT) / 2.0)}


def write_remarks(path: Path):
    # Pasted as is into PCBWay's remark field, which takes at most 600 characters.
    text = (
        f"{NAME} v{VERSION}. Internal slot is unplated: do not plate or fill it. "
        "2x 0.65 mm NPTH = USB-C locating pegs. "
        "Solder the 4 USB-C shell lugs and all 4 pins of J1. "
        "J1 wire openings face the right edge (silk arrows). "
        "J1 overhangs the right edge 1.15 mm, USB-C the left edge 0.25 mm. "
        "U3 pin 4 has no track on purpose. GND_MCU and GND_BUS are separate on purpose. "
        "No substitutes for U1, U3, OK1-OK3, J1, R2/R3 (1.5k 1W); other R/C: equivalents OK. "
        "CPL: origin lower left, mm, Y up, KiCad CCW rotation, J1 at body centre. "
        "Please confirm part orientation in the preview."
    )
    assert len(text) <= 600, f"PCBWay remark is {len(text)} characters, max 600"
    path.write_text(text + "\n", encoding="utf-8")


def render():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    scale = 14
    pad = 18
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 12) if Path(r"C:\Windows\Fonts\arial.ttf").exists() else ImageFont.load_default()
    colors = {
        "GND_MCU": (40, 90, 40),
        "GND_BUS": (20, 60, 30),
        "3V3": (180, 40, 40),
        "VBUS": (160, 80, 20),
        "DOOR": (20, 80, 160),
        "CHIME": (120, 70, 20),
        "FLOOR": (70, 50, 140),
    }

    def make(side):
        img = Image.new("RGB", (int(BOARD_W * scale) + pad * 2, int(BOARD_H * scale) + pad * 2), (245, 242, 232))
        dr = ImageDraw.Draw(img)

        def xy(x, y):
            px = pad + x * scale
            py = pad + y * scale          # file Y points down, as in KiCad's top view
            if side == "B":
                px = pad + (BOARD_W - x) * scale
            return px, py

        def box(xa, ya, xb, yb, outline=None, fill=None):
            p1, p2 = xy(xa, ya), xy(xb, yb)
            rect = [min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])]
            dr.rectangle(rect, outline=outline, fill=fill)

        box(0, 0, BOARD_W, BOARD_H, outline=(20, 20, 20))
        x0, y0, x1, y1 = SLOT
        box(x0, y0, x1, y1, outline=(180, 40, 40))
        ax0, ay0, ax1, ay1 = ANT
        box(ax0, ay0, ax1, ay1, outline=(180, 140, 40))
        for s in SEGS:
            if (side == "F" and s.layer != "F") or (side == "B" and s.layer != "B"):
                continue
            dr.line([xy(s.x1, s.y1), xy(s.x2, s.y2)], fill=colors.get(s.net, (180, 30, 30)), width=max(1, int(s.w * scale * 0.7)))
        for p in PADS:
            if p.layer not in (side, "*"):
                continue
            col = (150, 150, 150) if not p.net else colors.get(p.net, (30, 90, 160))
            box(p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh, fill=col)
        for v in VIAS:
            r = v.size / 2
            box(v.x - r, v.y - r, v.x + r, v.y + r, outline=(20, 20, 20))
        if side == "F":
            for part in PARTS:
                dr.text(xy(part.x, part.y), part.ref, fill=(0, 0, 0), font=font)
        out = ROOT / "plots"
        out.mkdir(exist_ok=True)
        img.save(out / f"board-{side}.png")

    make("F")
    make("B")


def kicad_cli():
    for cand in KICAD:
        if cand.exists():
            return cand
    found = shutil.which("kicad-cli")
    return Path(found) if found else None


def write_fab(errors: list[str]):
    cli = kicad_cli()
    if cli is None:
        print("kicad-cli missing, fab zip not written")
        return
    pcb = ROOT / f"{SLUG}.kicad_pcb"
    gerber = ROOT / "gerber"
    if gerber.exists():
        shutil.rmtree(gerber)
    gerber.mkdir()
    subprocess.run(
        [str(cli), "pcb", "export", "gerbers", "--output", str(gerber),
         "--layers", "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts",
         "--subtract-soldermask", "--precision", "6", "--check-zones", str(pcb)],
        check=True,
    )
    subprocess.run(
        [str(cli), "pcb", "export", "drill", "--output", str(gerber),
         "--format", "excellon", "--drill-origin", "absolute",
         "--excellon-zeros-format", "decimal", "--excellon-units", "mm",
         "--excellon-separate-th", "--generate-map", "--map-format", "pdf", str(pcb)],
        check=True,
    )
    pos = ROOT / "kicad-pos.csv"
    subprocess.run(
        [str(cli), "pcb", "export", "pos", "--output", str(pos),
         "--format", "csv", "--units", "mm", "--side", "front", str(pcb)],
        check=True,
    )
    drc_path = ROOT / "drc-report.json"
    drc = subprocess.run(
        [str(cli), "pcb", "drc", "--refill-zones", "--severity-all", "--format", "json",
         "--output", str(drc_path), str(pcb)],
        check=False, capture_output=True, text=True,
    )
    print(drc.stdout)
    if drc.returncode not in (0,):
        print(drc.stderr[-2000:])
    viol, unc = [], []
    if drc_path.exists():
        report = json.loads(drc_path.read_text(encoding="utf-8"))
        viol = report.get("violations", [])
        unc = report.get("unconnected_items", [])
        kinds = {}
        for item in viol:
            kinds[item.get("type", "?")] = kinds.get(item.get("type", "?"), 0) + 1
        print(f"kicad-drc violations {len(viol)} unconnected {len(unc)} {kinds}")
        for item in unc:
            print("OPEN", " | ".join(part.get("description", "") for part in item.get("items", [])))
        for item in viol:
            print("DRC", item.get("type"), " | ".join(part.get("description", "") for part in item.get("items", [])))
    if viol or unc or not drc_path.exists():
        for stale in (ROOT / "pcbway").glob("*.zip"):
            stale.unlink()
        print("kicad-drc not clean, order zip removed")
        return
    out = ROOT / "pcbway"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    keep_suffix = {".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gtp", ".gbp", ".gm1", ".drl", ".gbrjob"}
    for f in gerber.iterdir():
        if f.suffix.lower() in keep_suffix or f.name.lower().endswith(".gbrjob"):
            shutil.copy(f, out / f.name)
    write_remarks(out / "PCBWAY-REMARKS.txt")
    shutil.copy(ROOT / "bom.csv", out / "bom.csv")
    shutil.copy(ROOT / "cpl.csv", out / "cpl.csv")
    zip_path = out / f"{SLUG}-v{VERSION}-pcbway.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out.iterdir()):
            if f.suffix.lower() == ".zip":
                continue
            zf.write(f, f.name)
    print(f"zip {zip_path}")


def main():
    place_all()
    route()
    place_pin1_dots()
    errors = check_board() + check_silk() + check_holes() + check_module_pads()
    print(f"parts {len(PARTS)} pads {len(PADS)} tracks {len(SEGS)} vias {len(VIAS)}")
    print(f"python-drc {len(errors)}")
    for line in errors:
        print("ERR", line)
    write_pcb(ROOT / f"{SLUG}.kicad_pcb")
    write_pro(ROOT / f"{SLUG}.kicad_pro")
    write_bom(ROOT / "bom.csv")
    write_cpl(ROOT / "cpl.csv")
    render()
    if errors:
        print("fab export skipped until the python check is clean")
        return
    write_fab(errors)


if __name__ == "__main__":
    main()
