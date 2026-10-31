# BellBridge v1.1: generator for the PCBWay-assembled Ritto 7630 TwinBus / ESP32-C6 board.
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
# v1.1: 31.4 x 27.5 mm instead of 36.4 x 31.5. SO-4 optocouplers (LTV-357T-C) without a
# slot, 1210 input resistors, 0603 passives, 2.54 mm terminal (DORABO DB125), no buttons
# (BOOT and GND test pads on the back), USB-C opening at the top edge above the module, USB
# ESD array as USBLC6-2P6 (SOT-666) in the D+/D- path between the receptacle and the module.
# USB-C signal pads and board-edge position as in HRO's 2020 drawing. Module turned 90 degrees
# after Espressif's ESP32-C6 module placement guide: antenna past the left edge, feed end at the
# board's lower-left corner; the board itself is 26.2 x 27.5 mm. Layout review: no signal copper
# under the USB-C shell's steel plate (CC1 on the back), thermal spokes on the 0603 ground pads,
# a second VBUS via next to the regulator. Part-fit review: USB-C front lug slots 1.4 mm long
# as in HRO's drawing (KiCad's library: 1.2 mm).

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
NAME, VERSION = "BellBridge", "1.1"
SLUG = NAME.lower()
BOARD_W = 31.4
BOARD_H = 27.5
CLEARANCE = 0.20
EDGE_COPPER = 0.45
M3_COPPER = 0.55
# The SO-4 optocouplers need no milled slot.
SLOT = None
# Espressif's ESP32-C6 hardware design guidelines (1.4.7, figures 23-25): the module's PCB
# antenna outside the base board, its feed point at the board edge. The MINI-1's feed is at its
# pin-1 end, so U1 is turned 90 degrees (antenna pointing left, figure 24 position 5): the
# antenna sticks out past the left edge of the board and the feed end of the module (pins 1-11)
# runs along the bottom edge, 2.0 mm from it (the guide allows 2 mm), with room for the pin-3
# capacitors. The board starts at BOARD_X0, 0.2 mm into the antenna section and 0.5 mm from the
# module's last pads; x = 0 is the antenna tip. BOARD_W and BOARD_H are the overall size with
# the antenna. ANT is the antenna section: no copper there on either layer.
U1_X, U1_Y = 8.30, 18.90
BOARD_X0 = round(U1_X - 3.10, 3)
ANT = (0.0, round(U1_Y - 6.6, 3), round(U1_X - 2.9, 3), round(U1_Y + 6.6, 3))
# Isolation barrier: centre line of a copper-free strip between the two grounds. GND_MCU
# copper stays ISO_HALF to the left of it, bus copper ISO_HALF to the right, on both layers.
# It runs straight down through the optocoupler column, between the LED and transistor pads.
XB = 23.45
BARRIER = ((XB, 0.0), (XB, BOARD_H))
ISO_HALF = 0.80
BUS_NETS = ("GND_BUS", "DOOR", "CHIME", "FLOOR", "LED_CHIME", "LED_FLOOR")
# Pin-1 dots on F.SilkS. place_pin1_dots() puts each one at the nearest spot that check_silk()
# accepts, after routing; check_silk() re-checks them, including that pin 1 is clearly the
# nearest pin of the part. U1's pads 49-53 are ground pads, not pins. Pin 1 must be nearer
# than any other pin by 0.3 mm; U3 (SOT-666, 0.54 mm pitch, wider middle pads, boxed in
# between the J2 and U1 courtyards) gets 0.1 mm, with its dot at the corner beside pin 1.
PIN1_REFS = ("U1", "U2", "U3", "OK1", "OK2", "OK3")
PIN_MAX = {"U1": 48}
PIN1_MARGIN = {"U3": 0.10}
# Package bodies (local frame) that a part's own dot must stay off, where the ring search could
# otherwise land between the pad columns: U3's channel is under its body.
PIN1_BODY = {"U3": (-0.65, -0.85, 0.65, 0.85)}
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


def silk_notes():
    # Name and warnings: (text, x, y, character width, layer, rotation). "NO +24V" on the front
    # below J1; name and "GND ISOLATED" upright on the back of the bus side, reading upward.
    # Front text runs to +x from its anchor; back text is mirrored and right-justified, so it
    # also runs to +x in the top view, or toward -y when turned 90 degrees.
    j1 = next(q for q in PARTS if q.ref == "J1")
    yb = j1.y + 3 * TB_PITCH + TB_END
    return [
        ("NO +24V", XB + ISO_HALF + 0.55, round(yb + 1.0, 2), 0.65, "F.SilkS", 0),
        (f"{NAME} v{VERSION}", 30.35, 13.40, 0.7, "B.SilkS", 90),
        ("GND ISOLATED", 29.05, 13.40, 0.6, "B.SilkS", 90),
    ]


def _note_box(text, x, y, width, rot):
    # Top-view box of a note: about width + 0.1 mm per character, 0.8 mm high, 0.15 mm margin.
    length = (width + 0.1) * len(text)
    if rot == 90:
        return (x - 0.55, y - length - 0.15, x + 0.55, y + 0.15)
    return (x - 0.15, y - 0.55, x + length + 0.15, y + 0.55)


def label_boxes():
    # Silkscreen labels that no via may sit under (a via under a 0.8 mm letter breaks it): the
    # J1 terminal names on the front and the test-pad labels on the back. About 0.6 mm per
    # character at 0.8 mm height, plus 0.15 mm all round. Top-view coordinates.
    boxes = []
    j1 = next(q for q in PARTS if q.ref == "J1")
    xr = j1.x - TB_BACK - 0.25
    for name, pin in (("DOOR", "1"), ("CHIME", "2"), ("FLOOR", "3"), ("GND", "4")):
        y = pads_of("J1", pin)[0].y
        boxes.append((xr - 0.6 * len(name) - 0.15, y - 0.55, xr + 0.15, y + 0.55))
    for ref, label in (("TP1", "BOOT"), ("TP2", "GND")):
        q = pads_of(ref)[0]
        x0 = q.x + 1.15
        boxes.append((x0 - 0.15, q.y - 0.55, x0 + 0.6 * len(label) + 0.15, q.y + 0.55))
    for text, x, y, width, _layer, rot in silk_notes():
        boxes.append(_note_box(text, x, y, width, rot))
    return boxes


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


def r0603_pads(net1, net2):
    # KiCad R_0603_1608Metric.
    return [
        {"pin": "1", "x": -0.825, "y": 0, "sx": 0.8, "sy": 0.95, "net": net1},
        {"pin": "2", "x": 0.825, "y": 0, "sx": 0.8, "sy": 0.95, "net": net2},
    ]


def opto_pads(n1, n2, n3, n4):
    # KiCad Package_SO:SO-4_4.4x3.6mm_P2.54mm (Lite-On LTV-357T): 1 anode, 2 cathode,
    # 3 emitter, 4 collector; 4.3 mm between the LED and the transistor pad rows.
    return [
        {"pin": "1", "x": -3.15, "y": -1.27, "sx": 2.0, "sy": 0.64, "net": n1},
        {"pin": "2", "x": -3.15, "y": 1.27, "sx": 2.0, "sy": 0.64, "net": n2},
        {"pin": "3", "x": 3.15, "y": 1.27, "sx": 2.0, "sy": 0.64, "net": n3},
        {"pin": "4", "x": 3.15, "y": -1.27, "sx": 2.0, "sy": 0.64, "net": n4},
    ]


def r1210_pads(net1, net2):
    # KiCad R_1210_3225Metric.
    return [
        {"pin": "1", "x": -1.4625, "y": 0, "sx": 1.125, "sy": 2.65, "net": net1},
        {"pin": "2", "x": 1.4625, "y": 0, "sx": 1.125, "sy": 2.65, "net": net2},
    ]


def c0603_pads(net1, net2):
    # KiCad C_0603_1608Metric.
    return [
        {"pin": "1", "x": -0.775, "y": 0, "sx": 0.9, "sy": 0.95, "net": net1},
        {"pin": "2", "x": 0.775, "y": 0, "sx": 0.9, "sy": 0.95, "net": net2},
    ]


def test_pad(net):
    # KiCad TestPoint_Pad_D1.5mm, on the back: copper and mask only, nothing to assemble.
    return [{"pin": "1", "x": 0, "y": 0, "sx": 1.5, "sy": 1.5, "net": net, "layer": "B", "round": True}]


def sot23_5_pads(vin, gnd, en, vout):
    # KiCad Package_TO_SOT_SMD:SOT-23-5. AP2112K: 1 VIN, 2 GND, 3 EN, 4 NC, 5 VOUT.
    return [
        {"pin": "1", "x": -1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": vin},
        {"pin": "2", "x": -1.1375, "y": 0.0, "sx": 1.325, "sy": 0.6, "net": gnd},
        {"pin": "3", "x": -1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": en},
        {"pin": "4", "x": 1.1375, "y": 0.95, "sx": 1.325, "sy": 0.6, "net": ""},
        {"pin": "5", "x": 1.1375, "y": -0.95, "sx": 1.325, "sy": 0.6, "net": vout},
    ]


def usblc6_p6_pads(io1, gnd, io2, vbus):
    # KiCad Package_TO_SOT_SMD:SOT-666. USBLC6-2P6: 1 I/O1, 2 GND, 3 I/O2, 4 I/O2, 5 VBUS,
    # 6 I/O1; 1/6 and 3/4 are joined inside the package. D+ runs through pin 1 and D- taps
    # pin 4, both in the 1.2 mm channel between the pad columns, so pins 6 and 3 stay bare.
    return [
        {"pin": "1", "x": -0.85, "y": -0.5375, "sx": 0.5, "sy": 0.375, "net": io1},
        {"pin": "2", "x": -0.925, "y": 0.0, "sx": 0.65, "sy": 0.3, "net": gnd},
        {"pin": "3", "x": -0.85, "y": 0.5375, "sx": 0.5, "sy": 0.375, "net": ""},
        {"pin": "4", "x": 0.85, "y": 0.5375, "sx": 0.5, "sy": 0.375, "net": io2},
        {"pin": "5", "x": 0.925, "y": 0.0, "sx": 0.65, "sy": 0.3, "net": vbus},
        {"pin": "6", "x": 0.85, "y": -0.5375, "sx": 0.5, "sy": 0.375, "net": ""},
    ]


# DORABO DB125-2.54-04P-GN-S (drawing DB125-2.54-XXP-C-S, 2022-04-06): pitch 2.54, holes
# 1.20, pins 0.50 x 0.85, body N x 2.54 + 0.48 long (outer pins 1.51 from the ends), 6.30
# deep, 8.40 high. The side view (third-angle projection) puts the pin row 3.10 from the wire
# face and 3.20 from the back. Wires 26-18 AWG, strip 4-5 mm, M1.6 screws, 0.1 N*m max.
# Local frame: pins along +X from pin 1, wire face at -Y. Pads 2.0 mm (0.4 mm ring, 0.54 mm
# between pads).
TB_PITCH, TB_DRILL, TB_PAD = 2.54, 1.20, 2.0
TB_BACK, TB_FRONT, TB_END = 3.20, 3.10, 1.51


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


# HRO TYPE-C-31-M-12 signal pads, from HRO's drawing (2020-12-08, "recommend P.C.B layout"):
# 0.30/0.60 mm wide, from 0.50 to 1.64 mm behind the line through the two locating holes.
# KiCad's library footprint has them 1.45 mm long and about 0.5 mm further back; the lead tips
# end 0.40 mm behind the body, so HRO's pads also cover the leads under the body edge.
USB_HOLE_Y = -2.60
# HRO TYPE-C-31-M-12: the steel bottom plate of the shell runs 6.28 mm back from the front
# face (local +y 3.65); behind it, where the pins leave, the underside is the plastic body.
USB_FRONT_Y, USB_SHELL_LEN = 3.65, 6.28
# Ground pads of the 0603 parts join the pours through thermal spokes instead of solid
# copper, so both ends of each part heat alike in reflow (less tombstoning). The module and
# the other SMD ground pads stay solid.
THERMAL_RELIEF_REFS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "R6", "R7", "R10")
USB_PAD_Y, USB_PAD_LEN = USB_HOLE_Y - (0.50 + 1.64) / 2.0, 1.64 - 0.50


def usb_pads():
    # HRO TYPE-C-31-M-12. Shell-lug slots as HRO's drawing: 0.6 x 1.7 mm for the 1.10 mm lugs
    # beside the pad row, 0.6 x 1.4 mm for the 0.80 mm lugs near the opening (KiCad's library:
    # 1.2 mm), both 0.6 mm longer than the lug; pads with KiCad's 0.2 mm ring (HRO: 0.90 mm
    # pads). Signal pads and the 0.60 mm locating holes (KiCad: 0.65 mm) as HRO recommends.
    # The body runs -3.65..+3.65 and the cable opening is local +Y. Rotation 180 turns +Y to
    # -Y, so the opening faces the top edge.
    # HRO places the 0.60 mm power and ground pads at +-2.40 and +-3.20 (KiCad: +-2.45, +-3.25).
    spec = [
        ("A1", -3.20, "GND_MCU", 0.6),
        ("A4", -2.40, "VBUS", 0.6),
        ("A5", -1.25, "CC1", 0.3),
        ("A6", -0.25, "USB_DP", 0.3),
        ("A7", 0.25, "USB_DM", 0.3),
        ("A8", 1.25, "", 0.3),
        ("A9", 2.40, "VBUS", 0.6),
        ("A12", 3.20, "GND_MCU", 0.6),
        ("B12", -3.20, "GND_MCU", 0.6),
        ("B9", -2.40, "VBUS", 0.6),
        ("B8", -1.75, "", 0.3),
        ("B7", -0.75, "USB_DM", 0.3),
        ("B6", 0.75, "USB_DP", 0.3),
        ("B5", 1.75, "CC2", 0.3),
        ("B4", 2.40, "VBUS", 0.6),
        ("B1", 3.20, "GND_MCU", 0.6),
    ]
    pads = []
    for pin, x, net, sx in spec:
        pads.append({"pin": pin, "x": x, "y": USB_PAD_Y, "sx": sx, "sy": USB_PAD_LEN, "net": net})
    shells = [
        (-4.32, -3.13, 1.0, 2.1, 0.6, 1.7),
        (-4.32, 1.05, 1.0, 1.8, 0.6, 1.4),
        (4.32, -3.13, 1.0, 2.1, 0.6, 1.7),
        (4.32, 1.05, 1.0, 1.8, 0.6, 1.4),
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
                "y": USB_HOLE_Y,
                "sx": 0.60,
                "sy": 0.60,
                "net": "",
                "layer": "*",
                "drill": 0.60,
                "npth": True,
                "round": True,
            }
        )
    return pads


def place_all():
    # 31.4 x 27.5 mm overall; the board itself runs from BOARD_X0 to the right edge. U1 in the
    # lower left, turned 90 degrees: antenna out past the left edge, pins 1-11 (3V3, EN) along
    # the bottom, USB and GPIO8/9/18 on its right side, GPIO19/20 on its top side. J2 at the top
    # edge (rot 180, front 0.46 mm past the edge), the ESD array and the CC pull-downs between
    # J2 and the module. Right of the module a column with the GPIO8 pull-up, the EN network and
    # the regulator; the pin-3 capacitors and the output capacitors in a strip along the bottom.
    # Then a column of resistors beside the optocouplers, which stand in a column on the
    # barrier (x = XB): OK1 with its LED on the MCU side, OK2/OK3 with theirs on the bus side.
    # Bus side: input resistors beside OK2/OK3, terminal below.
    add_part(
        "U1", "ESP32-C6-MINI-1-N4", "ESP32-C6-MINI-1",
        U1_X, U1_Y, 90, module_pads(), "smd",
        "Espressif", "ESP32-C6-MINI-1-N4", "C5736265",
        (-6.8, -8.5, 6.8, 8.5),
    )
    add_part(
        "J2", "USB-C", "USB_C_HRO_TYPE-C-31-M-12",
        10.75, 3.19, 180, usb_pads(), "smd",
        "HRO", "TYPE-C-31-M-12", "C165948",
        (-5.32, USB_PAD_Y - USB_PAD_LEN / 2 - 0.50, 5.32, 4.15),
    )
    # ESD array right under the receptacle's pad row, before the lines leave for the module.
    # Courtyard 0.1 mm around the body. KiCad's SOT-666 land, not ST's (0.30 x 0.99 mm pads
    # 0.62 mm apart): both cover the leads, and only KiCad's leaves room for D+ and D- between
    # the pad columns.
    add_part(
        "U3", "USBLC6-2P6", "SOT-666",
        10.95, 9.63, 0, usblc6_p6_pads("USB_DP", "GND_MCU", "USB_DM", "VBUS"),
        "smd", "STMicroelectronics", "USBLC6-2P6", "C15999",
        (-1.5, -0.95, 1.5, 0.95),
    )
    oc = (-4.4, -2.05, 4.4, 2.05)
    lite = ("smd", "Lite-On", "LTV-357T-C", "C119091", oc)
    add_part("OK1", "LTV-357T", "SO-4_4.4x3.6mm_P2.54mm", XB, 2.55, 0,
             opto_pads("LED_DOOR", "GND_MCU", "GND_BUS", "DOOR"), *lite)
    add_part("OK2", "LTV-357T", "SO-4_4.4x3.6mm_P2.54mm", XB, 6.95, 180,
             opto_pads("LED_CHIME", "GND_BUS", "GND_MCU", "GPIO18"), *lite)
    add_part("OK3", "LTV-357T", "SO-4_4.4x3.6mm_P2.54mm", XB, 11.35, 180,
             opto_pads("LED_FLOOR", "GND_BUS", "GND_MCU", "GPIO20"), *lite)
    add_part(
        "J1", "2.54mm 4P", "TerminalBlock_DORABO_DB125-2.54_1x04_P2.54mm",
        29.20, 16.00, 270, terminal_pads(("DOOR", "CHIME", "FLOOR", "GND_BUS")),
        "through_hole", "DORABO", "DB125-2.54-4P-GN-S", "C918122",
        (-TB_END - 0.25, -TB_FRONT - 0.25, 3 * TB_PITCH + TB_END + 0.25, TB_BACK + 0.25),
    )
    uni = "UNI-ROYAL"
    c6 = (-1.48, -0.73, 1.48, 0.73)
    rc12 = (-2.28, -1.58, 2.28, 1.58)
    yag = ("smd", "YAGEO", "RC1210FR-071K5L", "C309587", rc12)
    add_part("R2", "1.5k 0.5W", "R_1210", 29.43, 7.00, 90, r1210_pads("LED_CHIME", "CHIME"), *yag)
    add_part("R3", "1.5k 0.5W", "R_1210", 29.43, 11.85, 90, r1210_pads("LED_FLOOR", "FLOOR"), *yag)
    # CC pull-downs: CC2 left of the ESD array, CC1 upright between the receptacle and the
    # resistor column (its line comes round on the back, below the receptacle).
    add_part("R10", "5.1k", "R_0603", 7.85, 9.63, 0, r0603_pads("GND_MCU", "CC2"), "smd", uni, "0603WAF5101T5E", "C23186", c6)
    add_part("R7", "5.1k", "R_0603", 16.81, 4.00, 90, r0603_pads("GND_MCU", "CC1"), "smd", uni, "0603WAF5101T5E", "C23186", c6)
    # Column beside the optocouplers' MCU pads: LED resistor, GPIO19 pull-down, pull-ups. R4 is
    # turned so that its 3V3 pad faces R5's.
    add_part("R1", "220", "R_0603", 18.29, 1.90, 90, r0603_pads("GPIO19", "LED_DOOR"), "smd", uni, "0603WAF2200T5E", "C22962", c6)
    add_part("R6", "100k", "R_0603", 18.29, 5.15, 90, r0603_pads("GND_MCU", "GPIO19"), "smd", uni, "0603WAF1003T5E", "C25803", c6)
    add_part("R4", "10k", "R_0603", 18.29, 8.40, 270, r0603_pads("GPIO18", "3V3"), "smd", uni, "0603WAF1002T5E", "C25804", c6)
    add_part("R5", "10k", "R_0603", 18.29, 11.65, 90, r0603_pads("GPIO20", "3V3"), "smd", uni, "0603WAF1002T5E", "C25804", c6)
    # Column right of the module: GPIO8 pull-up level with pin 22, the EN network (pin 8 is on
    # the bottom side; its line comes over on the back) and the regulator's input capacitor.
    add_part("R12", "10k", "R_0603", 19.60, 15.80, 0, r0603_pads("GPIO8", "3V3"), "smd", uni, "0603WAF1002T5E", "C25804", c6)
    add_part("R8", "10k", "R_0603", 19.60, 17.30, 0, r0603_pads("EN", "3V3"), "smd", uni, "0603WAF1002T5E", "C25804", c6)
    sam = "Samsung"
    add_part("C6", "1uF", "C_0603", 19.60, 18.80, 0, c0603_pads("EN", "GND_MCU"), "smd", sam, "CL10A105KB8NNNC", "C15849", c6)
    add_part("C4", "100nF", "C_0603", 19.60, 20.30, 0, c0603_pads("GND_MCU", "VBUS"), "smd", sam, "CL10B104KB8NNNC", "C1591", c6)
    add_part(
        "U2", "AP2112K-3.3", "SOT-23-5",
        20.00, 22.80, 180, sot23_5_pads("VBUS", "GND_MCU", "VBUS", "3V3"),
        "smd", "Diodes Incorporated", "AP2112K-3.3TRG1", "C51118",
        (-2.05, -1.84, 2.05, 1.7),
    )
    # Strip along the bottom edge, below the module's pins 1-11: 100 nF under pin 3 (its ground
    # pad toward the module's ground pins 1 and 2), 10 uF beside it, the regulator's output and input capacitors at the right. The 3V3 trunk
    # runs between these and the module's pins.
    ys = 26.55
    add_part("C5", "100nF", "C_0603", 9.40, ys, 180, c0603_pads("3V3", "GND_MCU"), "smd", sam, "CL10B104KB8NNNC", "C1591", c6)
    add_part("C2", "10uF", "C_0603", 12.40, ys, 0, c0603_pads("3V3", "GND_MCU"), "smd", sam, "CL10A106KP8NNNC", "C19702", c6)
    add_part("C3", "10uF", "C_0603", 18.30, ys, 0, c0603_pads("3V3", "GND_MCU"), "smd", sam, "CL10A106KP8NNNC", "C19702", c6)
    add_part("C1", "10uF", "C_0603", 21.30, ys, 0, c0603_pads("GND_MCU", "VBUS"), "smd", sam, "CL10A106KP8NNNC", "C19702", c6)
    # 100 nF from U3's VBUS pin to ground, as in ST's USBLC6-2 layout (datasheet figure 18): a
    # positive hit on D+/D- leaves through U3's upper diodes into VBUS.
    add_part("C7", "100nF", "C_0603", 14.20, 9.63, 0, c0603_pads("VBUS", "GND_MCU"), "smd", sam, "CL10B104KB8NNNC", "C1591", c6)
    # Download-mode test pads on the back, beside the module's GPIO9 pin: bridge BOOT to GND
    # while plugging in.
    tp = (-1.0, -1.0, 1.0, 1.0)
    add_part("TP1", "BOOT", "TestPoint_Pad_D1.5mm", 17.55, 15.50, 0, test_pad("GPIO9"), "board_only", "", "", "", tp)
    add_part("TP2", "GND", "TestPoint_Pad_D1.5mm", 17.55, 18.00, 0, test_pad("GND_MCU"), "board_only", "", "", "", tp)


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
    plated = []

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
        if p.drill:
            plated.append((p.x, p.y, p.drill / 2.0))
        lay = "*" if p.layer == "*" else p.layer
        strict = 1.0 if p.ref == "U1" and p.pin.isdigit() and int(p.pin) <= 48 else 0.0
        rect = ("pad", p.x - p.hw, p.y - p.hh, p.x + p.hw, p.y + p.hh, lay, p.net, strict)
        add_obs(rect, rect[1], rect[2], rect[3], rect[4])

    def forbidden(x, y, reach):
        if x - reach < BOARD_X0 + 0.45 or y - reach < 0.45:
            return True
        if x + reach > BOARD_W - 0.45 or y + reach > BOARD_H - 0.45:
            return True
        ax0, ay0, ax1, ay1 = ANT
        if x + reach > ax0 + 0.01 and x - reach < ax1 - 0.01 and y + reach > ay0 + 0.01 and y - reach < ay1 - 0.01:
            return True
        # The slot is an Edge.Cuts opening. KiCad wants 0.30 mm from the copper edge.
        if SLOT:
            sx0, sy0, sx1, sy1 = SLOT
            gap = 0.32
            if x + reach > sx0 - gap and x - reach < sx1 + gap and y + reach > sy0 - gap and y - reach < sy1 + gap:
                return True
        for hx, hy, hr in npth:
            if math.hypot(x - hx, y - hy) < hr + 0.32 + reach:
                return True
        return False

    side_cache = {}
    label_keepout = label_boxes()
    # The receptacle's steel bottom plate lies on the board: no signal copper on the front and
    # no signal via under it, where only solder mask would separate them from the shell.
    j2s = next(q for q in PARTS if q.ref == "J2")
    _sx = [rot_xy(lx, ly, j2s.rot) for lx in (-4.47, 4.47) for ly in (USB_FRONT_Y, USB_FRONT_Y - USB_SHELL_LEN)]
    J2_SHELL = (j2s.x + min(a for a, _ in _sx), j2s.y + min(b for _, b in _sx),
                j2s.x + max(a for a, _ in _sx), j2s.y + max(b for _, b in _sx))

    def blocked(x, y, layer_name, half, net, clr, is_via):
        reach = VIA_R if is_via else half
        if forbidden(x, y, reach):
            return True
        # No via under a silkscreen label: the hole would break the letters.
        if is_via and any(_point_rect(x, y, *b) < VIA_R for b in label_keepout):
            return True
        # Isolation barrier: every track and via stays ISO_HALF clear of the barrier line,
        # on its own ground's side, on both layers.
        key = (round(x, 3), round(y, 3), round(reach, 3), domain_of(net))
        ok = side_cache.get(key)
        if ok is None:
            ok = side_cache[key] = domain_ok(x, y, reach, key[3])
        if not ok:
            return True
        if (layer_name == "F" or is_via) and net != "GND_MCU":
            sx0, sy0, sx1, sy1 = J2_SHELL
            if x + reach > sx0 and x - reach < sx1 and y + reach > sy0 and y - reach < sy1:
                return True
        # Via holes keep 0.30 mm to plated pad holes, own net included (KiCad wants 0.25).
        if is_via:
            for hx, hy, hr in plated:
                if math.hypot(x - hx, y - hy) < 0.15 + hr + 0.30:
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
    # J2 shell lugs: front and rear lug of each side joined on the back, each rear lug tied on
    # the front to the ground pad beside it.
    j2 = next(q for q in PARTS if q.ref == "J2")
    lugs = pads_of("J2", "SH")
    left = sorted((q for q in lugs if q.x < j2.x), key=lambda q: q.y)
    right = sorted((q for q in lugs if q.x > j2.x), key=lambda q: q.y)
    for front, rear in (left, right):
        add_poly("GND_MCU", "B", [(front.x, front.y), (rear.x, rear.y)], 0.30)
    gl, gr = at("J2", "A12"), at("J2", "A1")
    ytie = j2.y + 3.80
    add_poly("GND_MCU", "F", [(left[1].x, ytie), (gl[0], ytie)], 0.30)
    add_poly("GND_MCU", "F", [(right[1].x, ytie), (gr[0], ytie)], 0.30)
    for p in list(lugs) + [q for pin in ("A1", "A12", "B1", "B12") for q in pads_of("J2", pin)]:
        seed_pad(p)

    # VBUS, 0.5 mm. Both J2 VBUS pads drop to vias just below the pad row; a back trunk joins
    # them (dipping under the CC1 via), runs right above the USB lines to the barrier side and
    # down to two vias level with C4; a front spine there feeds C4, U2's EN and VIN and C1 at
    # the bottom. U3's VBUS pin reaches the right-hand via through C7's pad.
    pw = 0.50
    vl, vr = at("J2", "A9"), at("J2", "A4")
    yv = 8.25
    vbl, vbr = (vl[0], yv), (vr[0], 8.40)
    add_poly("VBUS", "F", [vl, vbl], pw)
    add_poly("VBUS", "F", [vr, vbr], 0.40)
    vin, ven, c4v, c1v = at("U2", "1"), at("U2", "3"), at("C4", "2"), at("C1", "2")
    sx, sy = 22.30, round(c4v[1] - 0.90, 3)
    xd, yd = 11.40, 8.90
    add_poly("VBUS", "B", [vbl, (xd, yv), (xd, yd), (vbr[0], yd), vbr], pw)
    add_poly("VBUS", "B", [vbr, (vbr[0], yv), (sx, yv), (sx, sy)], pw)
    sy2 = round(sy - 0.75, 3)
    add_poly("VBUS", "F", [(sx, sy2), (sx, c1v[1]), c1v], pw)
    add_poly("VBUS", "F", [(sx, vin[1]), vin], pw)
    add_poly("VBUS", "F", [(sx, ven[1]), ven], 0.40)
    add_poly("VBUS", "F", [(sx, c4v[1]), c4v], 0.40)
    for v in (vbl, vbr, (sx, sy), (sx, sy2)):
        add_via("VBUS", *v)
    for ref, pin in (("J2", "A4"), ("J2", "B9"), ("J2", "A9"), ("J2", "B4"),
                     ("C1", "2"), ("C4", "2"), ("U2", "1"), ("U2", "3")):
        for q in pads_of(ref, pin):
            seed_pad(q)

    # 3V3 trunk, 0.45 mm: VOUT down into the strip below the module and left between the
    # module's bottom pins and the capacitor row to pin 3, with stubs into the 3V3 pads of C3,
    # C2 and C5 (C5 right under pin 3).
    vout, p3 = at("U2", "5"), at("U1", "3")
    yt3 = 25.625
    add_poly("3V3", "F", [vout, (vout[0], yt3), (p3[0], yt3)], 0.45)
    add_poly("3V3", "F", [(p3[0], yt3), p3], 0.40)
    for ref in ("C3", "C2", "C5"):
        c = at(ref, "1")
        add_poly("3V3", "F", [(c[0], yt3), c], 0.40)
    for ref, pin in (("U2", "5"), ("U1", "3"), ("C2", "1"), ("C5", "1"), ("C3", "1")):
        seed_pad(pads_of(ref, pin)[0])

    # USB pair through the ESD array. D+ joins B6/A6 in a loop right in front of the pad row,
    # under the receptacle's plastic rear part (its steel bottom plate ends just in front of
    # the loop; at 0.5 mm pitch the two links must cross, and vias do not fit between the
    # pads), D- joins A7/B7 in a loop just below it. U3 sits right under the loops:
    # D+ drops from B6 into U3 pin 1 (I/O1) and leaves it into the channel between U3's pad
    # columns; D- drops from its loop into the same channel and taps pin 4 (I/O2). So an ESD
    # hit on the receptacle meets U3 first. Below U3 both lines go to the back, run down under
    # the module and come up again inside its pad ring, next to pins 18 and 17. The right side
    # of the module stays free on the back for the GPIO lines.
    tw = 0.20
    a6, b6, a7, b7 = at("J2", "A6"), at("J2", "B6"), at("J2", "A7"), at("J2", "B7")
    p17, p18 = at("U1", "17"), at("U1", "18")
    u1p, u2p, u4p, u5p = (at("U3", n) for n in ("1", "2", "4", "5"))
    u3 = next(q for q in PARTS if q.ref == "U3")
    yt = round(a6[1] - USB_PAD_LEN / 2 - CLEARANCE - tw / 2 - 0.005, 3)
    yl = a7[1] + USB_PAD_LEN / 2 + CLEARANCE + tw / 2
    xdp, xdm = u3.x - 0.20, u3.x + 0.20
    dp1, dm1 = (round(xdp - 0.25, 3), 10.95), (round(xdm + 0.40, 3), 11.40)
    yb_dp, xb_dp, xb_dm = 10.70, 13.25, 12.60
    dp2 = (15.00, round(p18[1] - 0.35, 3))
    dm2 = (15.00, round(p17[1] + 0.35, 3))
    add_poly("USB_DP", "F", [b6, (b6[0], yt), (a6[0], yt), a6], tw)
    add_poly("USB_DM", "F", [a7, (a7[0], yl), (b7[0], yl), b7], tw)
    add_poly("USB_DP", "F", [b6, (b6[0], u1p[1]), (xdp, u1p[1]), (xdp, dp1[1] - 0.35), dp1], tw)
    add_poly("USB_DM", "F", [(xdm, yl), (xdm, dm1[1] - 0.40), dm1], tw)
    add_poly("USB_DM", "F", [(xdm, u4p[1]), u4p], tw)
    add_poly("USB_DP", "B", [dp1, (dp1[0], yb_dp), (xb_dp, yb_dp), (xb_dp, dp2[1]), dp2], tw)
    add_poly("USB_DM", "B", [dm1, (xb_dm, dm1[1]), (xb_dm, dm2[1]), dm2], tw)
    add_poly("USB_DP", "F", [dp2, (15.30, p18[1]), p18], tw)
    add_poly("USB_DM", "F", [dm2, (15.30, p17[1]), p17], tw)
    for v, net in ((dp1, "USB_DP"), (dm1, "USB_DM"), (dp2, "USB_DP"), (dm2, "USB_DM")):
        add_via(net, *v)
    # U3 ground: out of pin 2 to a via below-left of the package, clear of R10. VBUS: out of
    # pin 5 straight to C7 (0.3 mm beside U3's pins, then 0.4 mm), with a tie up to the
    # right-hand VBUS via on the way.
    gv = (round(u3.x - 1.50, 3), 10.95)
    add_poly("GND_MCU", "F", [u2p, (gv[0], u2p[1]), gv], 0.25)
    add_via("GND_MCU", *gv)
    c7v = at("C7", "1")
    xw = u5p[0] + 0.475
    add_poly("VBUS", "F", [u5p, (xw, u5p[1])], 0.30)
    add_poly("VBUS", "F", [(xw, u5p[1]), c7v], 0.40)
    add_poly("VBUS", "F", [(vbr[0], u5p[1]), vbr], 0.40)
    # CC1 stays out from under the shell: down out of A5 into the pocket between the D- loop,
    # the VBUS pad and U3, through a via to the back, right between the rear shell lug and the
    # VBUS trunk, up beside the lugs and over to a via above R7 (GPIO19 passes below R7's
    # CC1 pad on the front).
    a5, r7c = at("J2", "A5"), at("R7", "2")
    cv1, cv2 = (round(a5[0] + 0.35, 3), 7.98), (r7c[0], round(r7c[1] - 1.075, 3))
    xc = 15.95
    add_poly("CC1", "F", [a5, (a5[0], 7.75), cv1], tw)
    add_poly("CC1", "B", [cv1, (round(cv1[0] + 0.28, 3), 7.70), (xc, 7.70), (xc, cv2[1]), cv2], tw)
    add_poly("CC1", "F", [cv2, r7c], tw)
    for v in (cv1, cv2):
        add_via("CC1", *v)
    for ref, pin in (("J2", "A5"), ("R7", "2")):
        seed_pad(pads_of(ref, pin)[0])
    # The GPIO lines out of pins 24 and 25 box in the module's corner ground pad 51: a via
    # straight above it, between the two back USB lines' ends. C5's ground pad sits below the
    # end of the 3V3 trunk: a via left of it, tied up to the module's ground pin 2.
    q51 = at("U1", "51")
    v51 = (q51[0], 12.05)
    add_poly("GND_MCU", "F", [q51, v51], 0.30)
    add_via("GND_MCU", *v51)
    c5g, p2 = at("C5", "2"), at("U1", "2")
    v5 = (round(c5g[0] - 1.0, 3), c5g[1])
    add_poly("GND_MCU", "F", [c5g, v5], 0.30)
    add_poly("GND_MCU", "F", [p2, (p2[0], 25.95), v5], 0.25)
    add_via("GND_MCU", *v5)
    for ref, pin in (("U1", "51"), ("U1", "2"), ("C5", "2")):
        seed_pad(pads_of(ref, pin)[0])
    # C7's ground: a via just below its pad.
    c7g = at("C7", "2")
    c7gv = (c7g[0], round(c7g[1] + 1.12, 3))
    add_poly("GND_MCU", "F", [c7g, c7gv], 0.40)
    add_via("GND_MCU", *c7gv)
    for ref, pin in (("J2", "A6"), ("J2", "B6"), ("J2", "A7"), ("J2", "B7"), ("U1", "17"), ("U1", "18"),
                     ("U3", "1"), ("U3", "2"), ("U3", "4"), ("U3", "5"), ("C7", "1"), ("C7", "2")):
        for q in pads_of(ref, pin):
            seed_pad(q)

    # GPIO lines out of the module's top-right corner, drawn before the search so that they fan
    # out without crossing: GPIO19 (pin 25) up beside the receptacle and between R7's pads to
    # R6 (R1 joins it there), GPIO18 (pin 24) up beside it to R4, GPIO20 (pin 26) under both on
    # the back to R5. OK2 and OK3 join R4 and R5 in the search.
    p24, p25, p26 = at("U1", "24"), at("U1", "25"), at("U1", "26")
    r6g, r4g, r5g = at("R6", "2"), at("R4", "1"), at("R5", "1")
    x19, y19, x18 = 15.95, 11.40, 16.60
    add_poly("GPIO19", "F", [p25, (p25[0], y19), (x19, y19), (x19, r6g[1] - 0.325), (r6g[0], r6g[1] - 0.325)], 0.20)
    add_poly("GPIO18", "F", [p24, (x18, p24[1]), (x18, r4g[1]), r4g], 0.20)
    g20a, g20b = (p26[0], 12.05), (17.30, 12.75)
    add_poly("GPIO20", "F", [p26, g20a], 0.20)
    add_poly("GPIO20", "B", [g20a, (g20a[0], g20b[1]), g20b], 0.20)
    add_poly("GPIO20", "F", [g20b, (r5g[0], g20b[1]), r5g], 0.20)
    add_via("GPIO20", *g20a)
    add_via("GPIO20", *g20b)
    for ref, pin in (("U1", "24"), ("U1", "25"), ("U1", "26"), ("R6", "2"), ("R4", "1"), ("R5", "1")):
        seed_pad(pads_of(ref, pin)[0])

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

    # Ground vias beside each ground pad (in the pad only when nothing fits beside it), placed
    # before the signal search so the signals route around them. Stitching vias across both
    # pours on a 2.4 mm grid follow after the search.
    for ref in ("C1", "C2", "C3", "C4", "C5", "C6", "R6", "R7", "R10", "U2"):
        for p in pads_of(ref, net="GND_MCU"):
            if not try_gnd_via_beside("GND_MCU", p):
                try_gnd_via("GND_MCU", p.x, p.y)
    for ref, pin in (("OK1", "2"), ("OK2", "3"), ("OK3", "3"), ("U1", "14"), ("U1", "11"), ("U1", "1")):
        p = pads_of(ref, pin)[0]
        if not try_gnd_via_beside("GND_MCU", p):
            try_gnd_via("GND_MCU", p.x, p.y)
    for ref, pin in (("OK1", "3"), ("OK2", "2"), ("OK3", "2")):
        p = pads_of(ref, pin)[0]
        if not try_gnd_via_beside("GND_BUS", p):
            try_gnd_via("GND_BUS", p.x, p.y)
    # Espressif's module placement guide asks for ground copper and dense ground vias on the
    # base board near the antenna: a row under the module every 1.6 mm, between its ground pad
    # and the pin row at the antenna end.
    u1 = next(q for q in PARTS if q.ref == "U1")
    for lx in (-4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8):
        dx, dy = rot_xy(lx, -0.9, u1.rot)
        try_gnd_via("GND_MCU", round(u1.x + dx, 2), round(u1.y + dy, 2))
    # The search adds everything else: signals at 0.20 mm, the 3V3 branches to the pull-ups at
    # 0.30 mm, the bus lines at 0.30 mm. Supply trunks are drawn above.
    order = (
        ("VBUS", (0.50, 0.40, 0.30)),
        ("GPIO8", (0.20, 0.15)), ("GPIO9", (0.20, 0.15)),
        ("GPIO18", (0.20, 0.15)), ("GPIO20", (0.20, 0.15)), ("GPIO19", (0.20, 0.15)),
        ("LED_DOOR", (0.20, 0.15)),
        ("CC1", (0.20, 0.15)), ("CC2", (0.20, 0.15)), ("EN", (0.25, 0.20)),
        ("3V3", (0.30, 0.25, 0.20)),
        ("LED_CHIME", (0.25, 0.20)), ("LED_FLOOR", (0.25, 0.20)),
        ("DOOR", (0.30, 0.25)), ("CHIME", (0.30, 0.25)), ("FLOOR", (0.30, 0.25)), ("GND_BUS", (0.30, 0.25)),
    )
    failed = []
    for net, widths in order:
        pads = [p for p in PADS if p.net == net and p.pin != ""]
        # Start from the pad nearest the others and add the rest nearest first, so short local
        # links exist before the long runs.
        if len(pads) > 2:
            hub = min(pads, key=lambda p: sum(math.hypot(p.x - q.x, p.y - q.y) for q in pads))
            pads.sort(key=lambda p: math.hypot(p.x - hub.x, p.y - hub.y))
        loose = []
        seeded = False
        for p in pads:
            ix, iy = to_i(p.x), to_i(p.y)
            if any((ix, iy, layer_i) in occupied.get(net, ()) for layer_i in layers_of(p)):
                seeded = True
            else:
                loose.append(p)
        if not seeded and loose:
            seed_pad(loose.pop(0))
        for p in loose:
            ix, iy = to_i(p.x), to_i(p.y)
            if any((ix, iy, layer_i) in occupied.get(net, ()) for layer_i in layers_of(p)):
                continue
            t1 = _time.perf_counter()
            ok = False
            for width in widths:
                for margin in (16.0, None):
                    if search(p, width, 0.24 if width >= 0.2 else 0.20, margin):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                ok = search(p, widths[-1], 0.20, None)
            print(f"{net} {p.ref}.{p.pin} {'ok' if ok else 'FAIL'} {_time.perf_counter() - t1:.1f}s", flush=True)
            if ok:
                seed_pad(p)
            else:
                failed.append(f"{net} {p.ref}.{p.pin}")

    labels = label_boxes()
    for name, layer, poly in zones():
        if layer != "F.Cu":
            continue
        xs = [q[0] for q in poly]
        ys = [q[1] for q in poly]
        y = min(ys) + 0.9
        while y < max(ys) - 0.5:
            x = min(xs) + 0.9
            while x < max(xs) - 0.5:
                under_label = any(
                    _point_rect(x, y, bx0, by0, bx1, by1) < VIA_R for bx0, by0, bx1, by1 in labels
                )
                if _inside(x, y, poly) and not under_label:
                    try_gnd_via(name, round(x, 2), round(y, 2))
                x += 2.4
            y += 2.4
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
    # is at least 2 * ISO_HALF from the other. GND_MCU fills the board left of the barrier,
    # the bus pour the column right of it.
    h = ISO_HALF
    x0 = BOARD_X0 + 0.50
    mcu = [(x0, 0.50), (XB - h, 0.50), (XB - h, BOARD_H - 0.50), (x0, BOARD_H - 0.50)]
    bus = [(XB + h, 0.50), (BOARD_W - 0.50, 0.50), (BOARD_W - 0.50, BOARD_H - 0.50), (XB + h, BOARD_H - 0.50)]
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
    sx0, sy0, sx1, sy1 = SLOT or (-9.0, -9.0, -9.0, -9.0)
    ax0, ay0, ax1, ay1 = ANT
    holes = [p for p in PADS if p.drill >= 3.0]
    npth = [p for p in PADS if p.pin == "" and p.drill > 0]

    def consider_box(net, layer, x0, y0, x1, y1, label):
        if x0 < BOARD_X0 + EDGE_COPPER or y0 < EDGE_COPPER or BOARD_W - x1 < EDGE_COPPER or BOARD_H - y1 < EDGE_COPPER:
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
    for v in VIAS:
        for p in PADS:
            if not p.drill:
                continue
            # A slot counts as a round hole of its long side, which covers it.
            gap = math.hypot(v.x - p.x, v.y - p.y) - v.drill / 2 - p.drill / 2
            if gap < 0.25:
                errors.append(f"via hole ({v.x:.2f},{v.y:.2f}) is {gap:.2f} mm from the hole of {p.ref}.{p.pin or 'NPTH'}, min 0.25")
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
    sx0, sy0, sx1, sy1 = SLOT or (-9.0, -9.0, -9.0, -9.0)
    tag = f"silk dot {ref} ({x:.2f},{y:.2f})"
    probs = []
    if min(x - BOARD_X0, y, BOARD_W - x, BOARD_H - y) - out < 0.4:
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
    if "1" not in dist or (others and dist["1"] + PIN1_MARGIN.get(ref, 0.3) > min(others)):
        near = min(dist, key=dist.get) if dist else "?"
        probs.append(f"{tag} nearest pin is {ref}.{near}, not pin 1")
    # Visible: not under the part's own body.
    if ref in PIN1_BODY:
        part = next(q for q in PARTS if q.ref == ref)
        x0, y0, x1, y1 = PIN1_BODY[ref]
        pts = [rot_xy(a, b, part.rot) for a, b in ((x0, y0), (x1, y1))]
        bx0, bx1 = part.x + min(p[0] for p in pts), part.x + max(p[0] for p in pts)
        by0, by1 = part.y + min(p[1] for p in pts), part.y + max(p[1] for p in pts)
        if _point_rect(x, y, bx0, by0, bx1, by1) < out + 0.1:
            probs.append(f"{tag} under the body of {ref}")
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
        back = part_side(part) == "B"
        fl = "B" if back else "F"
        w(f'\t(footprint "{part.footprint}"')
        w(f'\t\t(layer "{fl}.Cu") (uuid "{uid()}")')
        rot = f" {num(part.rot)}" if part.rot else ""
        w(f"\t\t(at {num(part.x)} {num(part.y)}{rot})")
        prop("Reference", part.ref, f"{fl}.SilkS", True)
        prop("Value", part.value, f"{fl}.Fab", True)
        prop("Footprint", part.footprint, f"{fl}.Fab")
        prop("Datasheet", "", f"{fl}.Fab")
        if part.mpn:
            ident = f"LCSC {part.lcsc}" if str(part.lcsc).startswith("C") else "order by MPN"
            prop("Description", f"{part.mfr} {part.mpn} {ident}", f"{fl}.Fab")
        else:
            prop("Description", "test pad, not assembled", f"{fl}.Fab")
        attr = "smd exclude_from_pos_files exclude_from_bom" if part.attr == "board_only" else part.attr
        w(f"\t\t(attr {attr})")
        if part.courtyard:
            x0, y0, x1, y1 = part.courtyard
            w(f'\t\t(fp_rect (start {num(x0)} {num(y0)}) (end {num(x1)} {num(y1)}) (stroke (width 0.05) (type default)) (fill none) (layer "{fl}.CrtYd") (uuid "{uid()}"))')
        for p in part.pads:
            _emit_pad(w, p, part.rot, thermal=part.ref in THERMAL_RELIEF_REFS and p.get("net") == "GND_MCU")
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

    # Outline: a rectangle from BOARD_X0; the module's antenna sticks out past its left edge.
    # Then the unplated isolation slot, if any.
    line(BOARD_X0, 0, BOARD_W, 0, "Edge.Cuts")
    line(BOARD_W, 0, BOARD_W, BOARD_H, "Edge.Cuts")
    line(BOARD_W, BOARD_H, BOARD_X0, BOARD_H, "Edge.Cuts")
    line(BOARD_X0, BOARD_H, BOARD_X0, 0, "Edge.Cuts")
    if SLOT:
        x0, y0, x1, y1 = SLOT
        line(x0, y0, x1, y0, "Edge.Cuts")
        line(x1, y0, x1, y1, "Edge.Cuts")
        line(x1, y1, x0, y1, "Edge.Cuts")
        line(x0, y1, x0, y0, "Edge.Cuts")

    def silk(text, x, y, rot=0, size=0.9, justify="left", width=None, layer="F.SilkS"):
        parts = [justify] if justify != "center" else []
        if layer.startswith("B."):
            parts.append("mirror")
        just = f" (justify {' '.join(parts)})" if parts else ""
        w(
            f'\t(gr_text "{text}" (at {num(x)} {num(y)} {num(rot)}) (layer "{layer}") (uuid "{uid()}") '
            f"(effects (font (size {size} {width or size}) (thickness 0.15)){just}))"
        )

    # Terminal names behind J1's body (back face 3.20 mm left of the pin row), one per pin,
    # right-aligned against it, so they stay readable after assembly.
    j1 = next(q for q in PARTS if q.ref == "J1")
    xb = j1.x - TB_BACK
    for name, pin in (("DOOR", "1"), ("CHIME", "2"), ("FLOOR", "3"), ("GND", "4")):
        silk(name, xb - 0.25, at("J1", pin)[1], 0, 0.8, "right", 0.55)
    # J1 assembly marks. The holes do not show which way round the block goes, so the back
    # face and both ends of the body are drawn, and an arrow between each pair of pins points
    # at the wire openings (the right edge).
    yt, yb = j1.y - TB_END, j1.y + 3 * TB_PITCH + TB_END
    for x1, y1, x2, y2 in ((xb, yt, xb, yb), (xb, yt, BOARD_W - 0.4, yt), (xb, yb, BOARD_W - 0.4, yb)):
        line(x1, y1, x2, y2, "F.SilkS", 0.15)
    for k in range(3):
        ym = j1.y + (k + 0.5) * TB_PITCH
        ax = j1.x + TB_PAD / 2.0 + 0.30
        pts = " ".join(f"(xy {num(x)} {num(y)})" for x, y in ((ax, ym - 0.32), (ax + 0.75, ym), (ax, ym + 0.32)))
        w(f'\t(gr_poly (pts {pts}) (stroke (width 0.1) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{uid()}"))')
    for text, x, y, width, layer, rot in silk_notes():
        silk(text, x, y, rot, 0.8, "right" if layer.startswith("B.") else "left", width, layer=layer)
    # Test pads on the back: bridge BOOT to GND while plugging in USB for download mode.
    for ref, label in (("TP1", "BOOT"), ("TP2", "GND")):
        tpp = pads_of(ref)[0]
        silk(label, tpp.x + 1.15, tpp.y, 0, 0.8, "right", 0.6, layer="B.SilkS")
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
    # The antenna keep-out as KiCad rule areas, so KiCad's DRC enforces it too.
    ant = [(ANT[0], ANT[1]), (ANT[2], ANT[1]), (ANT[2], ANT[3]), (ANT[0], ANT[3])]
    for layer in ("F.Cu", "B.Cu"):
        _zone(w, "", layer, ant, keepout=True, pads="not_allowed", rule_name="Antenna keep-out")
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


def _emit_pad(w, p, rot=0, thermal=False):
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
    if kind == "smd" and p.get("layer") == "B":
        w('\t\t\t(layers "B.Cu" "B.Mask")')
    elif kind == "smd":
        w('\t\t\t(layers "F.Cu" "F.Paste" "F.Mask")')
        w("\t\t\t(roundrect_rratio 0.15)")
    else:
        w('\t\t\t(layers "*.Cu" "*.Mask")')
        w("\t\t\t(remove_unused_layers no)")
    net = p.get("net") or ""
    if net:
        w(f'\t\t\t(net {net_id(net)} "{net}")')
    if thermal:
        w("\t\t\t(zone_connect 1)")
    w(f'\t\t\t(uuid "{uid()}")')
    w("\t\t)")


def _zone(w, name, layer, poly, keepout, allow_tracks=False, pads="allowed", rule_name=None):
    nid = net_id(name) if name else 0
    w("\t(zone")
    w(f"\t\t(net {nid})")
    w(f'\t\t(net_name "{name}")')
    w(f'\t\t(layer "{layer}")')
    w(f'\t\t(uuid "{uid()}")')
    if rule_name:
        w(f'\t\t(name "{rule_name}")')
    w("\t\t(hatch edge 0.5)")
    w("\t\t(priority 0)")
    # SMD pads connect solid unless the pad asks for spokes (THERMAL_RELIEF_REFS); through-hole
    # pads keep a thermal spoke.
    # Clearance to every other net stays 0.3 mm.
    if keepout:
        w("\t\t(connect_pads (clearance 0.3))")
    else:
        w("\t\t(connect_pads thru_hole_only (clearance 0.3))")
    w("\t\t(min_thickness 0.2)")
    w("\t\t(filled_areas_thickness no)")
    if keepout:
        tracks = "allowed" if allow_tracks else "not_allowed"
        w(f"\t\t(keepout (tracks {tracks}) (vias {tracks}) (pads {pads}) (copperpour not_allowed) (footprints allowed))")
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
    order = ("U", "J", "OK", "R", "C", "SW", "TP")
    prefix = part.ref.rstrip("0123456789")
    return (order.index(prefix) if prefix in order else len(order), int(part.ref[len(prefix):] or 0))


# Short descriptions for the BOM, so that a substitute keeps value, rating and package.
DESCRIPTION = {
    "ESP32-C6-MINI-1-N4": "ESP32-C6 module, 4 MB flash, PCB antenna",
    "AP2112K-3.3TRG1": "LDO 3.3 V 600 mA",
    "USBLC6-2P6": "USB ESD protection, 2 lines + VBUS, SOT-666",
    "DB125-2.54-4P-GN-S": "Screw terminal, 4 pins, pitch 2.54 mm, 8.4 mm high",
    "TYPE-C-31-M-12": "USB-C receptacle 16P, SMD with through-hole shell lugs",
    "LTV-357T-C": "Optocoupler SO-4, transistor output, CTR rank C (200-400 %)",
    "0603WAF2200T5E": "Resistor 220 ohm 1 % 0603",
    "RC1210FR-071K5L": "Resistor 1.5 kohm 1 % 0.5 W 1210",
    "0603WAF1002T5E": "Resistor 10 kohm 1 % 0603",
    "0603WAF1003T5E": "Resistor 100 kohm 1 % 0603",
    "0603WAF5101T5E": "Resistor 5.1 kohm 1 % 0603",
    "CL10A106KP8NNNC": "Capacitor 10 uF 10 V X5R 0603",
    "CL10B104KB8NNNC": "Capacitor 100 nF 50 V X7R 0603",
    "CL10A105KB8NNNC": "Capacitor 1 uF 50 V X5R 0603",
}


def part_side(part):
    return "B" if part.pads and all(q.get("layer") == "B" for q in part.pads) else "F"


def assembled(part):
    return part.attr != "board_only"


# BOM columns as in PCBWay's BOM quotation (the customer's columns; PCBWay adds prices and
# delivery times). The LCSC number goes in "Vendor Part #", as PCBWay put it there.
BOM_HEADER = ["Item #", "*Designator", "*Qty", "Manufacturer", "*Mfg Part #", "Description / Value",
              "Vendor Part #", "*Package/Footprint", "Mounting Type", "Customer Reply"]
BOM_WIDTHS = [7, 18, 6, 18, 20, 56, 13, 46, 14, 52]
# Parts PCBWay must not swap: the module, the ESD array, the optocouplers and both connectors
# (J2's land follows HRO's drawing, J1's DORABO's).
NO_SUBSTITUTE = ("ESP32-C6-MINI-1-N4", "USBLC6-2P6", "LTV-357T-C", "DB125-2.54-4P-GN-S", "TYPE-C-31-M-12")


def bom_note(part):
    # Sourcing note for the "Customer Reply" column.
    if part.mpn in NO_SUBSTITUTE:
        return "No substitute"
    if part.mpn == "RC1210FR-071K5L":
        return "Any 1.5 kohm 1210, min. 0.5 W"
    if part.ref.startswith("R"):
        return "Equivalent OK: same value, size and rating"
    if part.ref.startswith("C"):
        return "Equivalent OK: same value, size, voltage and dielectric"
    return ""


def bom_rows():
    # One line per part number with its quantity, as PCBWay's BOM template asks.
    groups = {}
    for p in sorted((q for q in PARTS if assembled(q)), key=bom_order):
        groups.setdefault(p.mpn, []).append(p)
    rows = [BOM_HEADER]
    for item, parts in enumerate(groups.values(), start=1):
        p = parts[0]
        kind = "THT" if p.attr == "through_hole" else "SMD"
        rows.append([item, ", ".join(q.ref for q in parts), len(parts), p.mfr, p.mpn, DESCRIPTION[p.mpn],
                     p.lcsc, p.footprint, kind, bom_note(p)])
    return rows


def write_bom(path: Path):
    rows = bom_rows()
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    write_xlsx(path.with_suffix(".xlsx"), "BOM", rows, BOM_WIDTHS)


def write_xlsx(path: Path, sheet: str, rows, widths):
    # A plain one-sheet workbook from the standard library: bold, shaded header row frozen at
    # the top, thin borders, fixed column widths, printed landscape on one page width. Fixed zip
    # dates keep the file reproducible.
    from xml.sax.saxutils import escape

    def ref(r, c):
        name = ""
        c += 1
        while c:
            c, rem = divmod(c - 1, 26)
            name = chr(65 + rem) + name
        return f"{name}{r + 1}"

    def cell(r, c, v):
        style = 1 if r == 0 else 2
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref(r, c)}" s="{style}"><v>{v}</v></c>'
        return f'<c r="{ref(r, c)}" s="{style}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    ct = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, start=1))
    data = "".join(f'<row r="{r + 1}">' + "".join(cell(r, c, v) for c, v in enumerate(row)) + "</row>"
                   for r, row in enumerate(rows))
    last = ref(len(rows) - 1, len(rows[0]) - 1)
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{ct}.sheet.main+xml"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{ct}.worksheet+xml"/>'
            f'<Override PartName="/xl/styles.xml" ContentType="{ct}.styles+xml"/></Types>',
        "_rels/.rels":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}">'
            f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {ns} xmlns:r="{rel}">'
            f'<sheets><sheet name="{escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}">'
            f'<Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{rel}/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet {ns}>'
            '<fonts count="2"><font><sz val="10"/><name val="Arial"/></font>'
            '<font><b/><sz val="10"/><name val="Arial"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFD9D9D9"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet {ns}>'
            '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
            f'<dimension ref="A1:{last}"/>'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{data}</sheetData>'
            '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
            '<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>',
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text)


def write_cpl(path: Path):
    # Origin lower left, Y up, rotation CCW. The board file is Y down from the top left, so the
    # outline's lower-left corner is (BOARD_X0, BOARD_H): Mid X is x - BOARD_X0 and Mid Y is
    # BOARD_H - y. The angle needs no
    # change: KiCad's positive angle is counter-clockwise on screen, as in a Y-up top view.
    # PCBWay's library zero-rotation can differ. Confirm the preview before paying.
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in sorted((q for q in PARTS if assembled(q)), key=bom_order):
            # J1's footprint origin is pin 1; its body centre is 3.81 mm along the pin row and
            # 0.05 mm toward the back face. Every other footprint's origin is its body centre.
            ox, oy = BODY_CENTRE.get(p.footprint, (0.0, 0.0))
            dx, dy = rot_xy(ox, oy, p.rot)
            writer.writerow([p.ref, f"{p.x + dx - BOARD_X0:.4f}", f"{BOARD_H - (p.y + dy):.4f}", "top", f"{p.rot:.1f}"])


BODY_CENTRE = {"TerminalBlock_DORABO_DB125-2.54_1x04_P2.54mm": (1.5 * TB_PITCH, (TB_BACK - TB_FRONT) / 2.0)}


def write_remarks(path: Path):
    # Pasted as is into PCBWay's remark field, which takes at most 600 characters.
    # The panel note keeps tabs off the bottom edge beside C1, C2, C3 and C5 (0.5 mm in).
    text = (
        "2x 0.6 mm NPTH = USB-C locating pegs. "
        "Solder all 4 USB-C shell lugs and all 4 J1 pins. "
        "J1 wire openings face the right edge (arrows). "
        "On purpose: J1 overhangs the right edge 0.9 mm, USB-C the top edge 0.46 mm, "
        "U1 antenna the left edge 5.2 mm; U3 pins 3 and 6 have no track; "
        "GND_MCU and GND_BUS are separate. "
        "TP1/TP2 (back): bare pads. "
        "Panel: tab-route, 6 mm free left of each board, no tabs on bottom edge left of J1. "
        "No substitutes for U1, U3, OK1-OK3, J1, J2. R2/R3: 1.5k 1210, min. 0.5 W. "
        "Other R/C: equivalents OK. "
        "CPL: mm, origin lower left of board, Y up, KiCad CCW angles, J1 at body centre."
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

        corners = [(BOARD_X0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (BOARD_X0, BOARD_H)]
        dr.polygon([xy(x, y) for x, y in corners], outline=(20, 20, 20))
        if SLOT:
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
    shutil.copy(ROOT / "bom.xlsx", out / "bom.xlsx")
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
