"""PLCYard project files (.plcy)."""

import json

import pytest

from plcyard import formats, labs
from plcyard.core.processor import Processor
from plcyard.formats import plcy, rsl

BUNDLED = sorted([*labs.SAMPLES.glob("*.rsl"), *labs.SAMPLES.glob("*.plcy")]) + [lab.solution for lab in labs.load_all()]


@pytest.mark.parametrize("path", BUNDLED, ids=[p.stem for p in BUNDLED])
def test_every_bundled_program_survives_a_plcy_round_trip(path, tmp_path):
    prog = formats.load(path)
    out = tmp_path / "p.plcy"
    formats.save(prog, out)
    back = formats.load(out)
    assert back.profile == "plcyard" and plcy.dumps(back) == plcy.dumps(prog)
    assert Processor().download(back) == []


def test_file_is_readable_json_with_rung_text(tmp_path):
    prog = formats.load(labs.SAMPLES / "start-stop.plcy")
    doc = json.loads(plcy.dumps(prog))
    assert doc["format"] == "plcyard" and doc["version"] == 1 and doc["profile"] == "plcyard"
    main = next(p for p in doc["programs"] if p["number"] == 2)
    assert main["language"] == "LD" and main["rungs"][0]["text"].startswith("XIC,%I0.1")


def test_unicode_is_kept(tmp_path):
    prog = formats.load(labs.SAMPLES / "start-stop.plcy")
    prog.main.rungs[0].comment = "Válvula 🚀 ✓"
    assert formats.save(prog, tmp_path / "x.plcy") == []
    assert formats.load(tmp_path / "x.plcy").main.rungs[0].comment == "Válvula 🚀 ✓"


@pytest.mark.parametrize("text,msg", [
    ("not json", "not a PLCYard project"),
    ('{"format": "other"}', "not a PLCYard project"),
    ('{"format": "plcyard", "version": 99}', "newer PLCYard"),
    ('{"format": "plcyard", "version": 1, "profile": "s5"}', "unknown controller"),
    ('{"format": "plcyard", "version": 1, "programs": []}', "no main program"),
    ('{"format": "plcyard", "version": 1, "programs": [{"number": 2, "language": "SFC"}]}', "not supported yet"),
    ('{"format": "plcyard", "version": 1, "programs": [{"number": 2, "rungs": [{"text": "BST,1 XIC,I:1/0"}]}]}',
     "branch not closed"),
])
def test_bad_files_are_reported(text, msg):
    with pytest.raises(plcy.PlcyError, match=msg):
        plcy.loads(text)


OLD_RSL = ("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 XIC,B3:0/5 TON,T4:2,15 EOR,0\r\nRCM,\r\n"
           "SOR,1 XIC,T4:2/DN OSR,B3/40 OTE,O:2/3 EOR,1\r\nRCM,\r\nSOR,2 MOV,N7:[N7:0],F8:1 JSR,U:3 EOR,2\r\nRCM,\r\n"
           "SOR,3 END,3\r\nRCM,\r\nFILE,SBR 3\r\nSOR,0 XIC,S:1/15 OTE,O:4/0 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n"
           "SYMBOLS\r\nI:1/0 Start\r\n")


def test_older_data_table_files_are_converted():
    prog = rsl.loads(OLD_RSL)
    texts = [rsl.rung_text(r.body) for r in prog.main.rungs]
    assert texts == ["XIC,%I0.0 XIC,Bits[0].5 TON,Timers[2],1500", "XIC,Timers[2].DN ONS,Bits[2].8 OTE,%Q0.3",
                     "MOV,Values[Values[0]],Reals[1] JSR,SBR3"]
    assert rsl.rung_text(prog.files[3].rungs[0].body) == "XIC,FirstScan OTE,%Q2.0"
    assert prog.tags["Timers"]["type"] == "TIMER[3]" and prog.symbols == {"%I0.0": "Start"}
    assert Processor().download(prog) == []


def test_older_tag_projects_are_converted():
    old = {"format": "plcyard", "version": 1, "profile": "logix", "tags": {"T": {"type": "TIMER"}},
           "programs": [{"number": 2, "rungs": [{"text": "XIC,Local:1:I.Data.9 TON,T,500,0 OTE,Local:2:O.Data.0"}]}]}
    prog = plcy.loads(json.dumps(old))
    assert rsl.rung_text(prog.main.rungs[0].body) == "XIC,%I1.1 TON,T,500 OTE,%Q0.0"
    old = {"format": "plcyard", "version": 1, "profile": "s7", "tags": {"D": {"type": "IEC_TIMER"}, "N": {"type": "Int"}},
           "programs": [{"number": 2, "rungs": [{"text": "CMP==,N,3 TON,D,T#1s MOVE,5,N"}]}]}
    prog = plcy.loads(json.dumps(old))
    assert rsl.rung_text(prog.main.rungs[0].body) == "EQU,N,3 TON,D,T#1s MOV,5,N" and prog.tags["D"]["type"] == "TIMER"
