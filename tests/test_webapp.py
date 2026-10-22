import json
import subprocess
import sys
import zipfile

from plcyard import webbuild
from plcyard.webapp import Session


def lamp(s, bit):
    return json.loads(s.state(800))["io"]["outputs"][0]["points"][bit]["on"]


def test_example_runs_and_lights_the_motor():
    s = Session()
    s.open_example("start-stop")
    s.set_mode("RUN")
    s.press(1, 0, True)
    s.tick(100)
    s.press(1, 0, False)
    s.tick(100)
    st = json.loads(s.state(800))
    assert st["live"] and lamp(s, 0)
    assert st["rungs"][0]["wires"] and any(w[4] for w in st["rungs"][0]["wires"])


def test_write_a_program_with_a_branch_and_undo():
    s = Session()
    assert s.insert("XIC") == ""
    assert s.set_operands(["%I0.0"]) == []
    assert s.add_branch() == ""
    assert s.sel[0] == "leg"
    s.insert("XIC")
    s.set_operands(["Local:2:O.Data.0"])          # either notation is accepted
    s.select(["rung", 0])
    s.insert("OTE")
    s.set_operands(["%Q0.0"])
    assert "BST" in s.save_text() and "%Q0.0" in s.save_text()
    s.set_mode("RUN")
    s.press(1, 0, True)
    s.tick(50)
    s.press(1, 0, False)
    s.tick(50)
    assert lamp(s, 0)                              # sealed in through the branch
    s.undo_step()
    assert "OTE,?" in s.save_text()               # undo takes back the operand, then the coil


def test_exercise_check_and_notation():
    s = Session()
    s.set_notation("B")
    assert any(e["id"] == "02" for e in s.exercises())
    assert "%I0.0" in s.open_exercise("02")["body"]
    assert s.check()["score"].startswith("0/")
    from plcyard import labs
    s.open_text(labs.load_all()[1].solution.read_text(encoding="utf-8"))
    s.lab = labs.load_all()[1]
    assert s.check()["passed"]
    s.set_notation("A")


def test_runs_without_qt(tmp_path):
    code = ("import sys; sys.modules['PySide6'] = None\n"
            "from plcyard.webapp import Session\n"
            "s = Session(); s.open_example('timer-counter'); s.set_mode('RUN'); s.tick(200); s.state(600)\n"
            "s.open_exercise('05'); s.check()")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_build_packs_the_python_and_the_page(tmp_path):
    webbuild.build(tmp_path)
    names = zipfile.ZipFile(tmp_path / "plcyard.zip").namelist()
    assert "plcyard/webapp.py" in names and "plcyard/data/samples/start-stop.plcy" in names
    assert not any("/ui/main_window" in n or "__pycache__" in n for n in names)
    assert (tmp_path / "index.html").exists() and "--energized" in (tmp_path / "tokens.css").read_text()
    version = json.loads((tmp_path / "version.json").read_text())["version"]
    page = (tmp_path / "index.html").read_text()
    assert f'app.js?v={version}' in page and "__VERSION__" not in page
    webbuild.build(tmp_path)                       # same sources, same version
    assert json.loads((tmp_path / "version.json").read_text())["version"] == version


def test_a_new_program_does_not_keep_old_outputs_on():
    s = Session()
    s.open_example("start-stop")
    s.set_mode("RUN")
    s.press(1, 0, True)
    s.tick(100)
    assert lamp(s, 1)                              # Running light of the example
    s.new()
    s.insert("XIC")
    s.set_operands(["%I0.0"])
    s.insert("OTE")
    s.set_operands(["%Q0.0"])
    s.set_mode("RUN")
    s.press(1, 0, True)                            # the new I/O panel starts with every switch open
    s.tick(100)
    assert lamp(s, 0) and not lamp(s, 1)


def test_every_example_runs_on_its_machine():
    from plcyard.webapp import EXAMPLES
    s = Session()
    for key, (_, sim, _) in EXAMPLES.items():
        s.open_example(key)
        s.set_mode("RUN")
        s.sim_action("start", True)
        s.tick(200)
        s.sim_action("start", False)
        s.tick(5000)
        st = json.loads(s.state(800))
        assert st["machine"]["kind"] == sim and not st["problems"] and not st["fault"], key
        if sim == "tank":
            assert st["machine"]["trend"] and st["machine"]["level"] > 20, key   # the tank loop fills the tank


def test_machine_controls_and_exercise_on_its_machine():
    s = Session()
    s.open_example("silo")
    s.sim_action("selector", "C")
    s.sim_action("stop", True)
    assert s.sim.selector == "C" and s.sim.stop_pressed
    s.sim_action("reset")
    assert s.sim.selector == "A" and not s.sim.stop_pressed
    s.set_sim("traffic")
    s.sim_action("park_B", True)
    assert s.sim.cars["B"].parked
    s.set_sim("tank")
    s.sim_action("outlet", 130)
    assert s.sim.outlet == 100.0
    assert {"08", "10", "13"} <= {e["id"] for e in s.exercises()}
    s.open_exercise("10")
    assert s.sim_kind == "traffic"
    from plcyard import labs
    lab = next(x for x in labs.load_all() if x.id == "10")
    s.open_text(lab.solution.read_text(encoding="utf-8"))
    s.lab = lab
    assert s.check()["passed"]


def test_structured_text_program_with_tags():
    s = Session()
    s.new("ST")
    s.set_source("Lamp := %I0.0 AND NOT %I0.1;\n%Q0.0 := Lamp;\nT.TON(IN := Lamp, PT := T#1s);\n")
    st = json.loads(s.state(800))["st"]
    assert st["lines"] and any("Lamp" in p for p in st["problems"])
    assert s.set_tag("", "Lamp", "BOOL", "") == "" and s.set_tag("", "T", "TIMER", "") == ""
    assert s.set_tag("", "Bad", "NOPE", "") and "Bad" not in s.program.tags
    assert json.loads(s.state(800))["st"]["problems"] == []
    s.set_mode("RUN")
    s.press(1, 0, True)
    s.tick(1200)
    st = json.loads(s.state(800))
    assert lamp(s, 0) and any(n == "T" and "DN" in v for n, v in st["st"]["watch"])
    assert s.set_tag("T", "Delay", "TIMER", "a delay") == "" and "Delay" in s.program.tags and "T" not in s.program.tags
    assert "ST" in s.save_text() and s.open_text(s.save_text()) == ""


def test_exercise_in_structured_text():
    s = Session()
    s.open_exercise("02", "ST")
    assert s.language == "ST" and s.sim_kind == "io"
    from plcyard import labs
    lab = next(x for x in labs.load_all() if x.id == "02")
    s.open_text(lab.solutions["ST"].read_text(encoding="utf-8"))
    s.lab = lab
    assert s.check()["passed"]


def test_function_blocks_edit_run_and_undo():
    s = Session()
    s.new("FBD")
    assert s.add_block("OR", 100, 40) == "" and s.add_block("AND", 300, 40) == ""
    assert s.set_block(1, "", {"IN1": "%I0.0", "IN2": "%Q0.0"}) == ""
    assert s.connect(1, "OUT", 2, "IN1") == ""
    assert s.set_block(2, "", {"IN2": "%I0.1", "OUT": "%Q0.0"}) == ""
    s.add_block("TON", 300, 200)
    st = json.loads(s.state(800))
    assert st["fbd"]["problems"]["3"] and st["block"]["kind"] == "TIMER"
    s.delete()
    assert len(s.diagram.blocks) == 2 and s.connect(1, "OUT", 1, "IN1")
    s.set_mode("RUN")
    s.press(1, 1, True)                            # stop not pressed (a normally closed button)
    s.press(1, 0, True)
    s.tick(50)
    s.press(1, 0, False)
    s.tick(50)
    st = json.loads(s.state(800))
    assert lamp(s, 0) and st["fbd"]["blocks"][0]["outputs"][0]["value"] is True
    assert '"FBD"' in s.save_text()
    s.select(["wire", 0])
    s.delete()
    assert not s.diagram.wires
    s.undo_step()
    assert len(s.diagram.wires) == 1


def test_function_block_examples_and_exercise():
    s = Session()
    for key in ("start-stop-fbd", "silo-fbd", "traffic-fbd", "tank-pid-fbd"):
        s.open_example(key)
        assert s.language == "FBD" and not json.loads(s.state(800))["fbd"]["problems"], key
    s.open_exercise("02", "FBD")
    assert s.language == "FBD" and not s.diagram.blocks
    from plcyard import labs
    lab = labs.load_all()[1]
    s.open_text((lab.solution.parent / "02-start-stop.fbd.plcy").read_text(encoding="utf-8"))
    s.lab = lab
    assert s.check()["passed"]


def test_routines_and_block_parameters():
    s = Session()
    assert s.add_routine("Lights", "SBR", "LD") == "" and s.cur == 3
    s.insert("OTE")
    s.set_operands(["%Q0.0"])
    s.open_routine(2)
    s.insert("JSR")
    assert s.set_operands(["Lights"]) == []
    assert s.add_routine("Lights", "SBR", "ST").startswith("Lights is already used")
    assert s.add_routine("Motor", "FB", "ST") == ""
    assert s.set_param("Input", "", "Run", "BOOL") == "" and s.set_param("Output", "", "On", "BOOL") == ""
    assert s.set_param("Input", "", "On", "BOOL").startswith("There is already")
    s.set_source("On := Run;\n")
    assert not json.loads(s.state(800))["st"]["problems"]
    s.set_mode("RUN")
    s.tick(50)
    assert not s.problems and lamp(s, 0)          # main calls Lights, which turns the output on
    assert s.rename_routine(3, "Lamps") == "" and "JSR,Lamps" in s.save_text().replace(" ", "")
    assert s.delete_routine(4) == "" and s.cur == 2 and len(s.routines()) == 2
    s.undo_step()
    assert [r["title"] for r in s.routines()] == ["Main", "Lamps", "Motor"]


def test_examples_with_routines_run():
    s = Session()
    s.open_example("silo-fb")
    s.set_mode("RUN")
    assert not s.problems
    s.open_routine(3)
    s.sim_action("start", True)
    s.tick(300)
    st = json.loads(s.state(800))
    assert st["routine"] == 3 and st["interface"]["rows"] and any(i["on"] for r in st["rungs"] for i in r["instrs"])


def test_every_newer_machine_has_controls_devices_and_a_drawing():
    from plcyard import webmachines
    s = Session()
    for kind in webmachines.SPEC:
        s.set_sim(kind)
        m = json.loads(s.state(800))["machine"]
        assert m["kind"] == kind and m["controls"] and m["devices"]["inputs"] and m["devices"]["outputs"] and m["draw"]
        for c in m["controls"]:
            s.sim_action(c["act"], c.get("max", True) if c["t"] != "button" else None)
        s.tick(100)
        m = json.loads(s.state(800))["machine"]
        assert all(c["value"] for c in m["controls"] if c["t"] in ("check", "hold")), kind
        assert all(c["value"] == c["max"] for c in m["controls"] if c["t"] == "slider"), kind
    s.set_sim("garage")
    s.sim_action("position", 100)                    # not a control: ignored
    assert s.sim.position == 0


def test_input_points_match_the_machines():
    from plcyard import webmachines
    from plcyard.sims import MODELS
    for kind, (controls, ins, *_) in webmachines.SPEC.items():
        m = MODELS[kind][1]()
        for c in controls:
            if c["t"] in ("hold", "check") and not c["act"].startswith(("hall_", "car_", "fault_")):
                before = m.input_words()[1]
                setattr(m, c["act"], not getattr(m, c["act"]))
                changed = before ^ m.input_words()[1]
                setattr(m, c["act"], not getattr(m, c["act"]))
                points = [b for _, b in ins if changed >> b & 1]
                assert changed == 0 or points, (kind, c["act"])


def test_exercises_on_the_newer_machines():
    from plcyard import labs
    s = Session()
    ids = {e["id"] for e in s.exercises()}
    assert {"14", "15", "16"} <= ids
    lab = next(x for x in labs.load_all() if x.id == "15")
    s.open_exercise("15")
    assert json.loads(s.state(800))["machine"]["kind"] == "garage"
    s.open_text(lab.solution.read_text(encoding="utf-8"))
    s.lab = lab
    assert s.check()["passed"]


def test_pickers_and_compact_io_data():
    s = Session()
    ex = s.exercises()
    assert all({"level", "machine", "sim"} <= set(e) for e in ex) and ex[0]["machine"] == "I/O panel"
    langs = {e["key"]: e["language"] for e in s.examples()}
    assert langs["start-stop"] == "LD" and langs["start-stop-st"] == "ST" and langs["tank-pid-fbd"] == "FBD"
    assert s.palette()[0]["items"][0]["shape"] == "contact"
    s.open_exercise("06")
    io = json.loads(s.state(800))["io"]
    used = [p["bit"] for p in io["inputs"][0]["points"] if p["used"]]
    assert used == [0, 1] and io["bcd_used"]          # the exercise's devices and its display
