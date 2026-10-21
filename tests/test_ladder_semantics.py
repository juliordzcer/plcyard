"""Classic ladder patterns, checked against SLC-500 rules (manual 1747-RM001)."""

import itertools

from plcyard import labs
from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


def program(*rungs: str) -> str:
    lines = ["FILE,LAD 2"]
    for n, r in enumerate(rungs):
        lines += [f"SOR,{n} {r} EOR,{n}", "RCM,"]
    lines += [f"SOR,{len(rungs)} END,{len(rungs)}", "RCM,"]
    return "\r\n".join(lines) + "\r\n"


class Rig:
    def __init__(self, *rungs: str, nc: tuple = ()):
        self.panel = IoPanelModel()
        for bit in nc:
            self.panel.switch(1, bit).normally_closed = True
        self.plc = Processor()
        self.plc.device = self.panel
        assert self.plc.download(rsl.loads(program(*rungs))) == []
        self.plc.set_mode(Processor.RUN)

    def press(self, bit: int, on: bool = True, scans: int = 1):
        self.panel.set_pressed(1, bit, on)
        self.scan(scans)

    def scan(self, n: int = 1):
        self.plc.tick(10 * n)

    def out(self, bit: int) -> bool:
        return self.panel.lamp(2, bit)

    def b(self, addr: str) -> bool:
        return self.plc.dt.read_bit(addr)


SEAL_IN = "XIC,I:1/1 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 OTE,O:2/0"


def test_seal_in_holds_after_start_released():
    r = Rig(SEAL_IN, nc=(1,))
    r.scan()
    assert not r.out(0)
    r.press(0)
    assert r.out(0)
    r.press(0, False, scans=5)
    assert r.out(0)


def test_seal_in_stop_has_priority_over_start():
    r = Rig(SEAL_IN, nc=(1,))
    r.press(0)
    r.press(1)                 # stop while start still held
    assert not r.out(0)
    r.press(1, False)          # stop released, start still held: restarts
    assert r.out(0)
    r.press(0, False)
    r.press(1)
    r.press(1, False, scans=3)
    assert not r.out(0), "stays off once stopped"


def test_seal_in_drops_when_returning_to_run():
    r = Rig(SEAL_IN, nc=(1,))
    r.press(0)
    r.press(0, False)
    assert r.out(0)
    r.plc.set_mode(Processor.PGM)
    assert not r.out(0), "physical outputs off in PGM"
    r.plc.set_mode(Processor.RUN)
    r.scan(3)
    assert not r.out(0), "OTE is reset on entry to RUN, so the seal is lost"


def test_latch_survives_mode_change_but_ote_does_not():
    r = Rig("XIC,I:1/0 OTL,O:2/0", "XIC,I:1/1 OTU,O:2/0", "XIC,I:1/2 OTE,O:2/1")
    r.press(0)
    r.press(2)
    r.press(0, False)
    r.press(2, False)
    r.plc.set_mode(Processor.PGM)
    r.panel.set_pressed(1, 2, False)
    r.plc.set_mode(Processor.RUN)
    r.scan()
    assert r.out(0), "OTL is retentive"
    assert not r.out(1)
    r.press(1)
    assert not r.out(0)


def test_unlatch_in_later_rung_wins_same_scan():
    r = Rig("XIC,I:1/0 OTL,O:2/0", "XIC,I:1/1 OTU,O:2/0")
    r.panel.set_pressed(1, 0, True)
    r.press(1)
    assert not r.out(0)


def test_duplicate_ote_last_rung_wins():
    r = Rig("XIC,I:1/0 OTE,O:2/0", "XIC,I:1/1 OTE,O:2/0")
    r.press(0)
    assert not r.out(0), "rung 1 is false and writes last"
    r.press(1)
    assert r.out(0)


def test_rung_order_gives_one_scan_delay():
    # Rung 0 reads B3:0/0 before rung 1 writes it.
    r = Rig("XIC,B3:0/0 OTE,O:2/0", "XIC,I:1/0 OTE,B3:0/0")
    r.press(0)
    assert r.b("B3:0/0") and not r.out(0)
    r.scan()
    assert r.out(0)


def test_interlock_forward_reverse():
    fwd = "XIC,I:1/2 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 XIO,O:2/1 OTE,O:2/0"
    rev = "XIC,I:1/2 BST,1 XIC,I:1/1 NXB,1 XIC,O:2/1 BND,1 XIO,O:2/0 OTE,O:2/1"
    r = Rig(fwd, rev, nc=(2,))
    r.press(0)
    r.press(0, False)
    r.press(1)
    assert r.out(0) and not r.out(1), "reverse blocked while forward runs"
    r.press(1, False)
    r.press(2)
    r.press(2, False)
    assert not r.out(0)
    r.press(1)
    assert r.out(1) and not r.out(0)


def test_push_on_push_off_with_osr():
    pulse = "XIC,I:1/0 OSR,B3:0/0 OTE,B3:0/1"
    toggle = "BST,1 XIC,B3:0/1 XIO,O:2/0 NXB,1 XIO,B3:0/1 XIC,O:2/0 BND,1 OTE,O:2/0"
    r = Rig(pulse, toggle)
    states = []
    for _ in range(4):
        r.press(0, scans=3)        # held several scans: must toggle once only
        r.press(0, False, scans=2)
        states.append(r.out(0))
    assert states == [True, False, True, False]


def test_osr_true_one_scan_and_storage_follows_rung():
    r = Rig("XIC,I:1/0 OSR,B3:0/0 OTE,B3:0/1")
    r.press(0)
    assert r.b("B3:0/1") and r.b("B3:0/0")
    r.scan()
    assert not r.b("B3:0/1") and r.b("B3:0/0")
    r.press(0, False)
    assert not r.b("B3:0/0")


def test_first_pass_bit_only_on_first_scan():
    r = Rig("XIC,S:1/15 OTL,B3:0/0", "XIO,S:1/15 OTL,B3:0/1", "XIC,B3:0/1 XIC,S:1/15 OTL,B3:0/2")
    r.scan(3)
    assert r.b("B3:0/0") and r.b("B3:0/1") and not r.b("B3:0/2")
    assert not r.b("S:1/15")


def test_nested_branches_full_truth_table():
    rung = ("BST,1 XIC,I:1/2 XIC,I:1/3 NXB,1 XIC,I:1/4 XIO,I:1/5 "
            "BST,2 XIC,I:1/6 NXB,2 XIC,I:1/7 BND,2 BND,1 OTE,O:2/4")
    r = Rig(rung)
    for bits in itertools.product((False, True), repeat=6):
        for i, on in zip(range(2, 8), bits):
            r.panel.set_pressed(1, i, on)
        r.scan()
        i2, i3, i4, i5, i6, i7 = bits
        assert r.out(4) == ((i2 and i3) or (i4 and not i5 and (i6 or i7))), bits


def test_outputs_in_branch_follow_their_own_conditions():
    r = Rig("XIC,I:1/0 BST,1 OTE,O:2/1 NXB,1 XIC,I:1/1 OTE,O:2/2 NXB,1 XIO,I:1/1 OTE,O:2/3 BND,1")
    r.press(0)
    assert r.out(1) and not r.out(2) and r.out(3)
    r.press(1)
    assert r.out(1) and r.out(2) and not r.out(3)
    r.press(0, False)
    assert not (r.out(1) or r.out(2) or r.out(3)), "false rung-in turns all OTE off"


def test_every_branch_executes_even_after_one_is_true():
    # An OSR in the second leg must still see its rung-in when the first leg is true.
    r = Rig("BST,1 XIC,I:1/0 NXB,1 XIC,I:1/1 OSR,B3:0/0 BND,1 OTE,O:2/0")
    r.panel.set_pressed(1, 0, True)
    r.press(1)
    assert r.b("B3:0/0")


def test_inputs_are_read_once_per_scan():
    class Flicker(IoPanelModel):
        def input_words(self):
            self.calls = getattr(self, "calls", 0) + 1
            return super().input_words()

    p = Flicker()
    plc = Processor()
    plc.device = p
    plc.download(rsl.loads(program("XIC,I:1/0 OTE,O:2/0")))
    plc.set_mode(Processor.RUN)
    p.calls = 0
    plc.tick(30)
    assert p.calls == 3


def test_switch_types_from_symbols():
    p = IoPanelModel()
    p.configure_from_symbols({
        "I:1/0": "Start (NO)", "I:1/1": "Stop (NC)", "I:1/2": "Stop - NC,PB", "I:1/3": "Stop N.C.",
        "I:1/4": "Open - NO,PB", "I:1/5": "Stop (NC, pushbutton)", "I:1/6": "Level NO reached",
        "I:1/7": "Motor NCX", "O:2/0": "Motor (NC)",
    })
    nc = {b for b in range(8) if p.switch(1, b).normally_closed}
    mom = {b for b in range(8) if p.switch(1, b).momentary}
    assert nc == {1, 2, 3, 5}
    assert mom == {2, 4, 5}


def test_shipped_start_stop_sample():
    prog = rsl.load(labs.SAMPLES / "start-stop.rsl")
    panel = IoPanelModel()
    panel.configure_from_symbols(prog.symbols)
    plc = Processor()
    plc.device = panel
    assert plc.download(prog) == []
    plc.set_mode(Processor.RUN)
    plc.tick(20)
    assert not panel.lamp(2, 0) and panel.lamp(2, 2), "idle: motor off, stopped lamp on"
    panel.set_pressed(1, 0, True)
    plc.tick(10)
    panel.set_pressed(1, 0, False)
    plc.tick(20)
    assert panel.lamp(2, 0) and panel.lamp(2, 1) and not panel.lamp(2, 2)
    panel.set_pressed(1, 1, True)
    plc.tick(10)
    panel.set_pressed(1, 1, False)
    plc.tick(20)
    assert not panel.lamp(2, 0) and panel.lamp(2, 2)
