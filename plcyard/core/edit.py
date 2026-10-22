"""Program editing operations. Pure functions on the model, no Qt, so they are testable.

Positions inside a rung use the same paths as the processor trace and the layout:
(k,) item k of the rung; (k, b) branch b of the parallel at k; (k, b, j) item j in it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from . import isa
from .program import Instr, Parallel, ProgramFile, Rung, Series


class EditError(ValueError):
    pass


@dataclass(frozen=True)
class Slot:
    """An insertion point: before index `index` of the series at `series`."""
    series: tuple
    index: int


def new_instr(mnemonic: str, specs: dict[str, isa.Spec] | None = None) -> Instr:
    spec = (isa.SPECS if specs is None else specs)[mnemonic]
    return Instr(mnemonic, ["?"] * (len(spec.operands) - spec.optional))


def node_at(body: Series, path: tuple):
    node = body
    for i, k in enumerate(path):
        if isinstance(node, Series):
            node = node.items[k]
        elif isinstance(node, Parallel):
            node = node.branches[k]
        else:
            raise EditError(f"bad path {path}")
    return node


def series_at(body: Series, path: tuple) -> Series:
    node = node_at(body, path)
    if not isinstance(node, Series):
        raise EditError(f"{path} is not a series")
    return node


def parent_slot(path: tuple) -> tuple[tuple, int]:
    """Series path and index of the item at `path`."""
    if not path:
        raise EditError("the rung itself has no parent")
    return path[:-1], path[-1]


def _has_output(series: Series, specs=None) -> bool:
    return any(isinstance(i, Instr) and isa.is_output(i.mnemonic, specs) for i in series.items)


def default_slot(body: Series, mnemonic: str, specs: dict[str, isa.Spec] | None = None) -> Slot:
    """Where a new instruction goes when the whole rung is selected: inputs before the
    first output, outputs at the end."""
    if isa.is_output(mnemonic, specs) or mnemonic in ("BST",):
        return Slot((), len(body.items))
    for k, item in enumerate(body.items):
        if isinstance(item, Instr) and isa.is_output(item.mnemonic, specs):
            return Slot((), k)
    return Slot((), len(body.items))


def insert(body: Series, slot: Slot, node) -> tuple:
    s = series_at(body, slot.series)
    if not 0 <= slot.index <= len(s.items):
        raise EditError("insertion point out of range")
    s.items.insert(slot.index, node)
    return slot.series + (slot.index,)


def remove(body: Series, path: tuple):
    """Remove the node at path. Removing a branch leg removes that leg; a parallel left
    with one leg is unwrapped into its series. Returns the removed node."""
    parent_path, idx = parent_slot(path)
    parent = node_at(body, parent_path)
    if isinstance(parent, Parallel):
        removed = parent.branches.pop(idx)
        _normalise(body, parent_path)
        return removed
    removed = parent.items.pop(idx)
    if parent_path:   # the series is a leg: maybe its parallel needs tidying
        _normalise(body, parent_path[:-1])
    return removed


def _normalise(body: Series, par_path: tuple) -> None:
    par = node_at(body, par_path)
    if not isinstance(par, Parallel):
        return
    if len(par.branches) <= 1:
        owner_path, k = parent_slot(par_path)
        owner = series_at(body, owner_path)
        owner.items[k:k + 1] = par.branches[0].items if par.branches else []


def wrap_in_branch(body: Series, path: tuple) -> tuple:
    """Put the item at path in a new branch with an empty second leg. Returns the parallel path."""
    sp, k = parent_slot(path)
    s = series_at(body, sp)
    item = s.items[k]
    s.items[k] = Parallel([Series([item]), Series([])])
    return sp + (k,)


def add_leg(body: Series, par_path: tuple) -> tuple:
    par = node_at(body, par_path)
    if not isinstance(par, Parallel):
        raise EditError("select a branch to add a leg")
    par.branches.append(Series([]))
    return par_path + (len(par.branches) - 1,)


def move(body: Series, src: tuple, dest: Slot) -> tuple:
    """Move a node to another slot of the same rung."""
    if dest.series[:len(src)] == src:
        raise EditError("cannot move a branch into itself")
    node = copy.deepcopy(node_at(body, src))
    marker = Instr("__moving__")
    sp, k = parent_slot(src)
    holder = node_at(body, sp)
    if isinstance(holder, Parallel):
        raise EditError("drag the instructions, not the leg")
    holder.items[k] = marker
    insert(body, dest, node)
    return _remove_marker(body, marker, node)


def _remove_marker(body: Series, marker: Instr, node) -> tuple:
    def find(n, path):
        if n is marker:
            return path
        if n is node:
            found.append(path)
        kids = n.items if isinstance(n, Series) else n.branches if isinstance(n, Parallel) else []
        for i, c in enumerate(kids):
            r = find(c, path + (i,))
            if r is not None:
                return r
        return None

    found: list = []
    remove(body, find(body, ()))
    found.clear()
    find(body, ())
    return found[0]


def toggle_contact(body: Series, path: tuple) -> None:
    node = node_at(body, path)
    if not isinstance(node, Instr) or node.mnemonic not in ("XIC", "XIO"):
        raise EditError("only contacts can be toggled")
    node.mnemonic = "XIO" if node.mnemonic == "XIC" else "XIC"


def set_operands(body: Series, path: tuple, operands: list[str], profile=None, program=None,
                 routine: int | None = None) -> list[str]:
    """Store the typed operands; returns their problems."""
    from .profiles import get
    profile = profile or get()
    node = node_at(body, path)
    if not isinstance(node, Instr):
        raise EditError("not an instruction")
    node.operands = [profile.normalize(o) if o.strip() else "?" for o in operands]
    return profile.validate(node.mnemonic, node.operands, program, routine)


def instructions_in_order(body: Series) -> list[tuple]:
    """Paths of every instruction, left to right, top to bottom (keyboard navigation)."""
    out = []

    def walk(n, path):
        if isinstance(n, Instr):
            out.append(path)
        elif isinstance(n, Series):
            for i, c in enumerate(n.items):
                walk(c, path + (i,))
        else:
            for b, br in enumerate(n.branches):
                walk(br, path + (b,))

    walk(body, ())
    return out


def new_rung(f: ProgramFile, index: int) -> int:
    index = max(0, min(index, len(f.rungs)))
    f.rungs.insert(index, Rung(Series([])))
    return index
