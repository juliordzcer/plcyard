"""The exercise checker: reference solutions pass every check, an empty program fails."""


import pytest

from plcyard import formats, grader, labs
from plcyard.formats import rsl

LABS = labs.load_all()


@pytest.mark.parametrize("lab", LABS, ids=[lab.id for lab in LABS])
def test_reference_solution_passes(lab):
    report = grader.grade(lab, formats.load(lab.solution))
    assert report.error == "" and report.passed, [c for c in report.checks if not c.passed]


@pytest.mark.parametrize("lab", LABS, ids=[lab.id for lab in LABS])
def test_empty_program_fails(lab):
    report = grader.grade(lab, lab.starter())
    assert not report.passed


def test_download_problems_reported_not_raised():
    lab = LABS[0]
    prog = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,? OTE,O:2/0 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    report = grader.grade(lab, prog)
    assert report.error and not report.checks


@pytest.mark.parametrize("lab", LABS, ids=[lab.id for lab in LABS])
def test_empty_program_gets_no_credit(lab):
    """An empty program must not get credit for 'stop works' or 'no spill' when nothing ever ran."""
    report = grader.grade(lab, lab.starter())
    passed = [c.requirement for c in report.checks if c.passed]
    assert passed == []
