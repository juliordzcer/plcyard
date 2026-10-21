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
    assert back.profile == prog.profile and plcy.dumps(back) == plcy.dumps(prog)
    if prog.profile == "slc500":
        assert rsl.dumps(back) == rsl.dumps(prog)
    assert Processor().download(back) == []


def test_file_is_readable_json_with_rung_text(tmp_path):
    prog = rsl.load(labs.SAMPLES / "start-stop.rsl")
    doc = json.loads(plcy.dumps(prog))
    assert doc["format"] == "plcyard" and doc["version"] == 1 and doc["profile"] == "slc500"
    main = next(p for p in doc["programs"] if p["number"] == 2)
    assert main["language"] == "LD" and main["rungs"][0]["text"].startswith("XIC,I:1/1")


def test_unicode_is_kept(tmp_path):
    prog = rsl.load(labs.SAMPLES / "start-stop.rsl")
    prog.main.rungs[0].comment = "Válvula 🚀 ✓"
    assert formats.save(prog, tmp_path / "x.plcy") == []
    assert formats.load(tmp_path / "x.plcy").main.rungs[0].comment == "Válvula 🚀 ✓"


@pytest.mark.parametrize("text,msg", [
    ("not json", "not a PLCYard project"),
    ('{"format": "other"}', "not a PLCYard project"),
    ('{"format": "plcyard", "version": 99}', "newer PLCYard"),
    ('{"format": "plcyard", "version": 1, "profile": "s5"}', "unknown controller profile"),
    ('{"format": "plcyard", "version": 1, "programs": []}', "no main program"),
    ('{"format": "plcyard", "version": 1, "programs": [{"number": 2, "language": "FBD"}]}', "not supported yet"),
    ('{"format": "plcyard", "version": 1, "programs": [{"number": 2, "rungs": [{"text": "BST,1 XIC,I:1/0"}]}]}',
     "branch not closed"),
])
def test_bad_files_are_reported(text, msg):
    with pytest.raises(plcy.PlcyError, match=msg):
        plcy.loads(text)


def test_rsl_refuses_other_controllers():
    prog = rsl.load(labs.SAMPLES / "start-stop.rsl")
    prog.profile = "logix"
    with pytest.raises(rsl.RslError, match="SLC 500 ladder only"):
        rsl.dumps(prog)
