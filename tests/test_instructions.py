"""Instruction behaviour checked against the SLC-500 reference (1747-RM001)."""

import pytest

from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


def build(main: list[str], subs: dict[int, list[str]] | None = None, tables: dict | None = None) -> str:
    lines = []

    def file(kind, n, rungs):
        lines.append(f"FILE,{kind} {n}" + (":" if kind == "SBR" else ""))
        for k, r in enumerate(rungs):
            lines.extend([f"SOR,{k} {r} EOR,{k}", "RCM,"])
        lines.extend([f"SOR,{len(rungs)} END,{len(rungs)}", "RCM,"])

    file("LAD", 2, main)
    for n in range(3, 10):
        file("SBR", n, (subs or {}).get(n, []))
    for t, vals in (tables or {}).items():
        lines.append(t)
        lines += [str(v) for v in vals] + ["0"] * (100 - len(vals))
    return "\r\n".join(lines) + "\r\n"


class Rig:
    def __init__(self, *rungs, subs=None, tables=None):
        self.panel = IoPanelModel()
        self.plc = Processor()
        self.plc.device = self.panel
        problems = self.plc.download(rsl.loads(build(list(rungs), subs, tables)))
        assert problems == [], problems
        self.plc.set_mode(Processor.RUN)

    def inp(self, bit, on=True):
        self.panel.set_pressed(1, bit, on)

    def ms(self, n):
        self.plc.tick(n)

    def w(self, a):
        return self.plc.dt.read_word(a)

    def b(self, a):
        return self.plc.dt.read_bit(a)

    def setw(self, a, v):
        self.plc.dt.write_word(a, v)


# -- timers ------------------------------------------------------------------

def test_ton_times_in_tenths_and_caps_at_preset():
    r = Rig("XIC,I:1/0 TON,T4:0,10")
    assert r.w("T4:0.PRE") == 10, "preset written on download"
    r.inp(0)
    r.ms(10)
    assert r.b("T4:0/EN") and r.b("T4:0/TT") and not r.b("T4:0/DN")
    r.ms(500)
    assert r.w("T4:0.ACC") == 5
    r.ms(600)
    assert r.w("T4:0.ACC") == 10 and r.b("T4:0/DN") and not r.b("T4:0/TT")
    r.inp(0, False)
    r.ms(10)
    assert r.w("T4:0.ACC") == 0 and not (r.b("T4:0/EN") or r.b("T4:0/DN"))


def test_ton_accuracy_does_not_depend_on_tick_size():
    a, b = Rig("XIC,I:1/0 TON,T4:0,50"), Rig("XIC,I:1/0 TON,T4:0,50")
    for r in (a, b):
        r.inp(0)
    for _ in range(300):
        a.ms(10)
    for _ in range(100):
        b.ms(30)
    assert a.w("T4:0.ACC") == b.w("T4:0.ACC") == 29


def test_cascaded_timers_traffic_style():
    # red 2 s, green 1 s, repeating with T4:1/DN resetting T4:0
    r = Rig("XIO,T4:1/DN TON,T4:0,20", "XIC,T4:0/DN TON,T4:1,10",
            "XIO,T4:0/DN OTE,O:2/0", "XIC,T4:0/DN OTE,O:2/2")
    seen = []
    for _ in range(70):
        r.ms(100)
        seen.append("R" if r.panel.lamp(2, 0) else "G")
    text = "".join(seen)
    assert text.startswith("R" * 20 + "G" * 10 + "R" * 20), text


def test_tof():
    r = Rig("XIC,I:1/0 TOF,T4:0,10", "XIC,T4:0/DN OTE,O:2/0")
    r.inp(0)
    r.ms(10)
    assert r.b("T4:0/DN") and r.b("T4:0/EN")
    r.inp(0, False)
    r.ms(500)
    assert r.b("T4:0/TT") and r.b("T4:0/DN") and r.panel.lamp(2, 0)
    r.ms(600)
    assert not r.b("T4:0/DN") and not r.b("T4:0/TT") and not r.panel.lamp(2, 0)
    assert r.w("T4:0.ACC") == 10


def test_rto_retains_until_res():
    r = Rig("XIC,I:1/0 RTO,T4:0,10", "XIC,I:1/1 RES,T4:0")
    r.inp(0)
    r.ms(410)
    r.inp(0, False)
    r.ms(1000)
    assert r.w("T4:0.ACC") == 4
    r.inp(0)
    r.ms(700)
    assert r.b("T4:0/DN") and r.w("T4:0.ACC") == 10
    r.inp(0, False)
    r.ms(10)
    assert r.b("T4:0/DN"), "DN is retained"
    r.inp(1)
    r.ms(10)
    assert r.w("T4:0.ACC") == 0 and not r.b("T4:0/DN")


def test_ton_restarts_after_leaving_run_while_timing():
    r = Rig("XIC,I:1/0 TON,T4:0,10")
    r.inp(0)
    r.ms(510)
    r.plc.set_mode(Processor.PGM)
    assert r.w("T4:0.ACC") == 5 and r.b("T4:0/TT"), "values kept in PGM"
    r.plc.set_mode(Processor.RUN)
    r.ms(10)
    assert r.w("T4:0.ACC") == 0


def test_negative_timer_preset_rejected_at_download():
    plc = Processor()
    problems = plc.download(rsl.loads(build(["XIC,I:1/0 TON,T4:0,-5"])))
    assert problems and "0 to 32767" in str(problems[0])


def test_negative_preset_written_at_runtime_is_a_major_fault():
    r = Rig("XIC,I:1/0 TON,T4:0,5", "MOV,-5,T4:0.PRE")
    r.inp(0)
    r.ms(20)
    assert r.plc.mode == Processor.FAULT and r.b("S:1/13") and r.w("S:6") == 0x34


# -- counters ----------------------------------------------------------------

def test_ctu_counts_transitions_not_scans():
    r = Rig("XIC,I:1/0 CTU,C5:0,3", "XIC,I:1/1 RES,C5:0")
    r.ms(10)
    for _ in range(4):
        r.inp(0)
        r.ms(50)
        r.inp(0, False)
        r.ms(50)
    assert r.w("C5:0.ACC") == 4 and r.b("C5:0/DN"), "keeps counting past the preset"
    r.inp(1)
    r.ms(10)
    assert r.w("C5:0.ACC") == 0 and not r.b("C5:0/DN")


def test_ctu_does_not_count_on_entry_to_run():
    r = Rig("XIC,I:1/0 CTU,C5:0,3")
    r.ms(10)
    r.inp(0)
    r.ms(10)
    r.inp(0, False)
    r.ms(10)
    r.inp(0)
    r.plc.set_mode(Processor.PGM)
    r.plc.set_mode(Processor.RUN)
    r.ms(30)
    assert r.w("C5:0.ACC") == 1, "CU is set before the first scan"


def test_ctu_overflow_and_ctd_underflow():
    r = Rig("XIC,I:1/0 CTU,C5:0,0", "XIC,I:1/1 CTD,C5:1,0")
    r.ms(10)
    r.setw("C5:0.ACC", 32767)
    r.setw("C5:1.ACC", -32768)
    r.inp(0)
    r.inp(1)
    r.ms(10)
    assert r.w("C5:0.ACC") == -32768 and r.b("C5:0/OV")
    assert r.w("C5:1.ACC") == 32767 and r.b("C5:1/UN")


def test_up_down_counter_done_follows_acc():
    r = Rig("XIC,I:1/0 CTU,C5:0,2", "XIC,I:1/1 CTD,C5:0,2")
    r.ms(10)
    for bit in (0, 0):
        r.inp(bit)
        r.ms(10)
        r.inp(bit, False)
        r.ms(10)
    assert r.b("C5:0/DN")
    r.inp(1)
    r.ms(10)
    assert r.w("C5:0.ACC") == 1 and not r.b("C5:0/DN")


# -- compare -----------------------------------------------------------------

@pytest.mark.parametrize("rung,a,expected", [
    ("EQU,N7:0,5", 5, True), ("EQU,N7:0,5", 4, False), ("NEQ,N7:0,5", 4, True),
    ("LES,N7:0,5", 4, True), ("LEQ,N7:0,5", 5, True), ("GRT,N7:0,5", 6, True),
    ("GEQ,N7:0,5", 4, False),
    ("LIM,10,N7:0,20", 15, True), ("LIM,10,N7:0,20", 21, False),
    ("LIM,20,N7:0,10", 15, False), ("LIM,20,N7:0,10", 25, True), ("LIM,20,N7:0,10", 5, True),
    ("MEQ,N7:0,00FFh,0034h", 0x1234, True), ("MEQ,N7:0,00FFh,0035h", 0x1234, False),
])
def test_compare(rung, a, expected):
    r = Rig(f"{rung} OTE,O:2/0")
    r.setw("N7:0", a)
    r.ms(10)
    assert r.panel.lamp(2, 0) is expected


# -- math ----------------------------------------------------------------------

def test_add_sub_mul_and_flags():
    r = Rig("ADD,N7:0,N7:1,N7:2", "SUB,N7:0,N7:1,N7:3", "MUL,N7:0,N7:1,N7:4")
    r.setw("N7:0", 7)
    r.setw("N7:1", 9)
    r.ms(10)
    assert (r.w("N7:2"), r.w("N7:3"), r.w("N7:4")) == (16, -2, 63)
    assert not r.b("S:0/3"), "flags reflect the last instruction (MUL, positive)"


def test_overflow_saturates_and_faults_at_end_of_scan():
    r = Rig("ADD,N7:0,1,N7:1")
    r.setw("N7:0", 32767)
    r.ms(10)
    assert r.w("N7:1") == 32767 and r.b("S:0/1")
    assert r.plc.mode == Processor.FAULT and r.w("S:6") == 0x20


def test_overflow_cleared_by_program_does_not_fault():
    r = Rig("ADD,N7:0,1,N7:1", "OTU,S:5/0")
    r.setw("N7:0", 32767)
    r.ms(50)
    assert r.plc.mode == Processor.RUN and r.w("N7:1") == 32767


@pytest.mark.parametrize("a,b,q,unrounded,rem", [
    (11, 2, 6, 5, 1),        # manual example: 5.5 rounds up, S:14 = 5, S:13 = 1
    (10, 4, 3, 2, 2),
    (9, 4, 2, 2, 1),
    (-11, 2, -6, -5, -1),
])
def test_div_rounds_and_fills_math_register(a, b, q, unrounded, rem):
    r = Rig(f"DIV,{a},{b},N7:0")
    r.ms(10)
    assert (r.w("N7:0"), r.w("S:14"), r.w("S:13")) == (q, unrounded, rem)


def test_div_by_zero():
    r = Rig("DIV,5,N7:0,N7:1")
    r.ms(10)
    assert r.w("N7:1") == 32767 and r.plc.mode == Processor.FAULT


def test_sqr_neg_and_float_math():
    r = Rig("SQR,N7:0,N7:1", "NEG,N7:0,N7:2", "DIV,N7:0,4.0,F8:0", "MOV,F8:1,N7:3")
    r.setw("N7:0", 30)
    r.setw("F8:1", 2.5)
    r.ms(10)
    assert r.w("N7:1") == 5 and r.w("N7:2") == -30
    assert r.w("F8:0") == 7.5
    assert r.w("N7:3") == 3, "float to integer rounds"


def test_bcd_conversions():
    r = Rig("TOD,N7:0,O:2", "FRD,I:5,N7:1")
    r.setw("N7:0", 1234)
    r.panel.thumbwheels = [0, 9, 8, 7]
    r.ms(10)
    assert r.plc.dt.read_slot(0, 2) == 0x1234
    assert r.w("N7:1") == 987


def test_tod_out_of_range_sets_overflow():
    r = Rig("TOD,N7:0,N7:1")
    r.setw("N7:0", 10000)
    r.ms(10)
    assert r.plc.mode == Processor.FAULT and r.w("S:6") == 0x20


def test_logic_and_moves():
    r = Rig("AND,N7:0,00F0h,N7:1", "OR,N7:0,0F00h,N7:2", "XOR,N7:0,FFFFh,N7:3",
            "NOT,N7:0,N7:4", "MVM,N7:0,000Fh,N7:5", "CLR,N7:6")
    r.setw("N7:0", 0x1234)
    r.setw("N7:5", 0x7770)
    r.setw("N7:6", 99)
    r.ms(10)
    assert r.w("N7:1") == 0x0030
    assert r.w("N7:2") == 0x1F34
    assert r.w("N7:3") & 0xFFFF == 0xEDCB
    assert r.w("N7:4") & 0xFFFF == 0xEDCB
    assert r.w("N7:5") == 0x7774
    assert r.w("N7:6") == 0 and r.b("S:0/2")


def test_indirect_move():
    r = Rig("MOV,16,N7:[C5:0.ACC]")
    r.setw("C5:0.ACC", 3)
    r.ms(10)
    assert r.w("N7:3") == 16


def test_indirect_out_of_range_faults():
    r = Rig("MOV,1,N7:[N7:0]")
    r.setw("N7:0", 5000)
    r.ms(10)
    assert r.plc.mode == Processor.FAULT


def test_download_loads_data_tables():
    r = Rig("NOP", tables={"BTBL": [5], "NTBL": [0, 42], "FTBL": [1.5]})
    assert r.w("B3:0") == 5 and r.w("N7:1") == 42 and r.w("F8:0") == 1.5


# -- bit shift and sequencers ----------------------------------------------

def test_bsl_shifts_on_each_rising_edge():
    r = Rig("XIC,I:1/0 BSL,#B3:0,R6:0,I:1/1,20")
    assert r.w("R6:0.LEN") == 20
    pattern = [1, 0, 1, 1]
    for v in pattern:
        r.inp(1, bool(v))
        r.inp(0)
        r.ms(30)
        r.inp(0, False)
        r.ms(10)
    assert r.w("B3:0") & 0xF == 0b1011, "first loaded bit is now the highest of the four"
    for _ in range(20):
        r.inp(1, False)
        r.inp(0)
        r.ms(10)
        r.inp(0, False)
        r.ms(10)
    assert r.w("B3:0") == 0 and (r.w("B3:1") & 0xF) == 0


def test_bsl_unload_bit_and_bsr():
    r = Rig("XIC,I:1/0 BSR,#B3:0,R6:0,I:1/1,4")
    r.setw("B3:0", 0b0001)
    r.inp(1)
    r.inp(0)
    r.ms(10)
    assert r.b("R6:0/UL") and r.w("B3:0") & 0xF == 0b1000


def test_sqo_steps_wraps_and_masks():
    tables = {"NTBL": [0, 0b0001, 0b0010, 0b0100]}
    r = Rig("XIC,I:1/0 SQO,#N7:0,000Fh,O:2,R6:0,3,0", tables=tables)
    r.plc.dt.write_slot(0, 2, 0)
    seen = []
    for _ in range(5):
        r.inp(0)
        r.ms(10)
        seen.append((r.w("R6:0.POS"), r.plc.dt.read_slot(0, 2) & 0xF, r.b("R6:0/DN")))
        r.inp(0, False)
        r.ms(10)
    assert seen == [(1, 1, False), (2, 2, False), (3, 4, True), (1, 1, False), (2, 2, False)]


def test_sqc_found_bit():
    r = Rig("XIC,I:1/0 SQC,#N7:0,FFFFh,N7:9,R6:0,2,0", tables={"NTBL": [0, 7, 9]})
    r.setw("N7:9", 7)
    r.inp(0)
    r.ms(10)
    assert r.b("R6:0/FD")


# -- subroutines ---------------------------------------------------------------

def test_jsr_runs_subroutine_and_ret_returns_early():
    r = Rig("XIC,I:1/0 JSR,U:3",
            subs={3: ["SBR,U:3", "XIC,I:1/1 OTE,O:2/0", "XIC,I:1/2 RET", "OTE,O:2/1"]})
    r.inp(0)
    r.inp(1)
    r.ms(10)
    assert r.panel.lamp(2, 0) and r.panel.lamp(2, 1)
    r.inp(2)
    r.ms(10)
    assert r.panel.lamp(2, 0) and r.panel.lamp(2, 1), "OTE after RET keeps its last state"
    r.inp(0, False)
    r.inp(1, False)
    r.ms(10)
    assert r.panel.lamp(2, 0), "subroutine not scanned: its OTE stays as it was"


def test_jsr_to_missing_file_rejected():
    plc = Processor()
    problems = plc.download(rsl.loads("FILE,LAD 2\r\nSOR,0 JSR,U:12 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n"))
    assert problems and "does not exist" in str(problems[0])


def test_recursion_faults():
    r = Rig("JSR,U:3", subs={3: ["JSR,U:3"]})
    r.ms(10)
    assert r.plc.mode == Processor.FAULT and r.w("S:6") == 0x21
