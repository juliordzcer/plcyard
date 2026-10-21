"""UI regression tests for docs/testing/bugs.md (data table input)."""

import pytest

from plcyard.core.datatable import DataTable
from plcyard.ui.datatable_view import TableModel


@pytest.fixture
def model(qapp):
    return TableModel(DataTable())


def test_bug005_bit_cells_accept_only_0_or_1(model):
    model.file_no, model.radix = 7, "Binary"
    assert model.setData(model.index(0, 0), "2") is False
    assert model.setData(model.index(0, 0), "1") is True


@pytest.mark.parametrize("radix,text", [("Hex/BCD", "12345"), ("Decimal", "40000"), ("Decimal", "-32769"),
                                        ("Octal", "200000")])
def test_bug006_word_cells_reject_out_of_range(model, radix, text):
    model.file_no, model.radix = 7, radix
    assert model.setData(model.index(0, 0), text) is False
    assert model.dt.read_word("N7:0") == 0


def test_bug006_float_cells_reject_out_of_range(model):
    model.file_no, model.radix = 8, "Decimal"
    assert model.setData(model.index(0, 0), "1e40") is False
    assert model.setData(model.index(0, 0), "-2.5") is True
