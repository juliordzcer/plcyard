"""Geometry for drawing a rung tree. No Qt: plain numbers, so it is unit-testable.

Every item has its wire at WIRE_Y from its own top, so items in series line up.
Trailing output instructions are pushed against the right rail, like RSLogix.

Nodes are identified by a path of indices from the rung body: (k,) is the k-th
item of the rung, (k, b) branch b of a parallel at k, (k, b, j) item j in it.
Each wire carries (path, side): it is energized when the processor trace for
that node has a true input ("in") or output ("out").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import isa
from ..core.program import Instr, Parallel, Series

CONTACT_W, CONTACT_H = 96, 64
BLOCK_W = 160
BRANCH_GAP = 14
WIRE_Y = 26
ROW_H = 17
LIVE_ROWS = {"TON": ["Accum"], "TOF": ["Accum"], "RTO": ["Accum"], "CTU": ["Accum"], "CTD": ["Accum"],
             "SQO": [], "SQC": [], "SQL": []}

Tag = tuple[tuple, str]   # (path, "in" | "out")


@dataclass
class Placed:
    instr: Instr
    path: tuple
    x: float
    y: float
    w: float
    h: float


@dataclass
class Wire:
    x1: float
    y1: float
    x2: float
    y2: float
    tag: Tag


@dataclass
class RungGeometry:
    width: float
    height: float
    instrs: list[Placed] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)


def is_block(ins: Instr) -> bool:
    return ins.mnemonic not in ("XIC", "XIO", "OTE", "OTL", "OTU", "OSR", "NOP")


def block_rows(ins: Instr) -> int:
    return max(len(ins.operands), 1) + len(LIVE_ROWS.get(ins.mnemonic, []))


def instr_size(ins: Instr) -> tuple[float, float]:
    if is_block(ins):
        return BLOCK_W, 42 + ROW_H * block_rows(ins)
    return CONTACT_W, CONTACT_H


def size(node) -> tuple[float, float]:
    if isinstance(node, Instr):
        return instr_size(node)
    if isinstance(node, Series):
        if not node.items:
            return 40, CONTACT_H
        sizes = [size(i) for i in node.items]
        return sum(w for w, _ in sizes), max(h for _, h in sizes)
    sizes = [size(b) for b in node.branches]
    return max(w for w, _ in sizes) + 2 * BRANCH_GAP, sum(h for _, h in sizes)


def _is_output_item(node) -> bool:
    if isinstance(node, Instr):
        return isa.is_output(node.mnemonic)
    if isinstance(node, Parallel):
        return all(_is_output_item(i) for b in node.branches for i in b.items) and any(
            b.items for b in node.branches)
    return False


def _place_items(items, base: tuple, first: int, x: float, y: float, w: float,
                 in_tag: Tag, g: RungGeometry) -> None:
    """Items in series starting at index `first` of the series at path `base`."""
    cx = x
    tag = in_tag
    for k, item in enumerate(items, start=first):
        iw, _ = size(item)
        place(item, base + (k,), cx, y, iw, g)
        cx += iw
        tag = (base + (k,), "out")
    if cx < x + w:
        g.wires.append(Wire(cx, y + WIRE_Y, x + w, y + WIRE_Y, tag))


def place(node, path: tuple, x: float, y: float, w: float, g: RungGeometry) -> None:
    """Place node with its left edge at x, top at y, stretched to width w."""
    wy = y + WIRE_Y
    if isinstance(node, Instr):
        iw, ih = instr_size(node)
        g.instrs.append(Placed(node, path, x, y, iw, ih))
        if w > iw:
            g.wires.append(Wire(x + iw, wy, x + w, wy, (path, "out")))
        return
    if isinstance(node, Series):
        _place_items(node.items, path, 0, x, y, w, (path, "in"), g)
        return
    by = y
    last_wy = wy
    inner = w - 2 * BRANCH_GAP
    for b, br in enumerate(node.branches):
        _, bh = size(br)
        bwy = by + WIRE_Y
        g.wires.append(Wire(x, bwy, x + BRANCH_GAP, bwy, (path, "in")))
        place(br, path + (b,), x + BRANCH_GAP, by, inner, g)
        g.wires.append(Wire(x + w - BRANCH_GAP, bwy, x + w, bwy, (path + (b,), "out")))
        last_wy = bwy
        by += bh
    g.wires.append(Wire(x, wy, x, last_wy, (path, "in")))
    g.wires.append(Wire(x + w, wy, x + w, last_wy, (path, "out")))


def layout_rung(body: Series, width: float) -> RungGeometry:
    """Lay out a rung between x=0 (left rail) and x=width (right rail)."""
    items = body.items
    split = len(items)
    while split > 0 and _is_output_item(items[split - 1]):
        split -= 1
    inputs, outputs = items[:split], items[split:]
    in_w, in_h = size(Series(inputs)) if inputs else (0, CONTACT_H)
    out_w, out_h = size(Series(outputs)) if outputs else (0, CONTACT_H)
    width = max(width, in_w + out_w + 40)
    g = RungGeometry(width, max(in_h, out_h))
    _place_items(inputs, (), 0, 0, 0, in_w, ((), "in"), g)
    gap_tag = ((split - 1,), "out") if split else ((), "in")
    g.wires.append(Wire(in_w, WIRE_Y, width - out_w, WIRE_Y, gap_tag))
    _place_items(outputs, (), split, width - out_w, 0, out_w, gap_tag, g)
    return g


def natural_width(body: Series) -> float:
    return size(body)[0] + 40
