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
    assert st["machine"]["trend"] and st["machine"]["level"] > 20      # the tank loop fills the tank


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
