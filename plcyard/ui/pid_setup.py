"""PID Setup: the members of a PID tag in four tabs (Tuning, Configuration, Alarms, Scaling), as PLC
software shows them. Values are the tag's start values; while the PLC runs the program they are
also written to the running PID at once."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core.plc.memory import START

# (member, label, kind, tooltip): kind is "real", "bool", or a list of choices for a BOOL member
TUNING = [("SP", "Setpoint (SP)", "real", "Setpoint in engineering units"),
          ("SO", "Set output %", "real", "Output used in manual mode; in automatic it shows the output"),
          ("BIAS", "Output bias %", "real", "Feedforward or bias added to the output"),
          ("KP", "Proportional gain (Kp)", "real", ""),
          ("KI", "Integral gain (Ki)", "real", ""),
          ("KD", "Derivative time (Kd)", "real", ""),
          ("MO", "Manual mode", "bool", "Output = set output % (or the tieback operand when there is one)")]
CONFIG = [("PE", "PID equation", ["Independent gains", "Dependent gains"],
           "Independent: Kp, Ki (1/s), Kd (s). Dependent: controller gain Kc, reset Ti (min/repeat), rate Td (min)"),
          ("CA", "Control action", ["E = SP - PV", "E = PV - SP"], "E = PV - SP when more output lowers the PV"),
          ("DOE", "Derivative of", ["PV", "Error"], "PV avoids a kick when the setpoint changes"),
          ("UPD", "Loop update time (s)", "real", "How often the PID computes; 0 = every scan"),
          ("MAXO", "CV high limit %", "real", ""),
          ("MINO", "CV low limit %", "real", ""),
          ("DB", "Deadband", "real", "Around the setpoint, in engineering units: the output holds while the error is inside")]
ALARMS = [("PVH", "PV high", "real", "0 = no alarm"), ("PVL", "PV low", "real", "0 = no alarm"),
          ("PVDB", "PV deadband", "real", ""), ("DVP", "Positive deviation", "real", "PV - SP above this alarms; 0 = none"),
          ("DVN", "Negative deviation", "real", "SP - PV above this alarms; 0 = none"),
          ("DVDB", "Deviation deadband", "real", "")]
SCALING = [("MAXI", "PV unscaled maximum", "real", "Raw value at the top of the range, e.g. 27648; max = min: no scaling"),
           ("MINI", "PV unscaled minimum", "real", ""),
           ("MAXS", "PV engineering units maximum", "real", "e.g. 100 for 0-100 %"),
           ("MINS", "PV engineering units minimum", "real", ""),
           ("MAXCV", "CV maximum (at 100 %)", "real", "Control variable value at 100 % output; max = min: CV in %"),
           ("MINCV", "CV minimum (at 0 %)", "real", "")]
GAIN_LABELS = {False: ("Proportional gain (Kp)", "Integral gain (Ki, 1/s)", "Derivative time (Kd, s)"),
               True: ("Controller gain (Kc)", "Reset time (Ti, min/repeat)", "Rate time (Td, min)")}


def members(program, name: str, memory=None) -> dict:
    """Current values: the running PID when there is one, else the declaration's start values."""
    if memory is not None:
        try:
            return dict(memory.element(name))
        except Exception:
            pass
    out = {k: v for k, v in START["PID"].items()}
    decl = next((d for n, d in program.tags.items() if n.lower() == name.lower()), {})
    out.update({k.upper(): v for k, v in (decl.get("value") or {}).items()})
    return out


class PidSetup(QDialog):
    def __init__(self, parent, program, name: str, memory=None):
        super().__init__(parent)
        self.program, self.name, self.memory = program, name, memory
        self.setWindowTitle(f"PID Setup - {name}")
        self.values = members(program, name, memory)
        self.fields: dict[str, QWidget] = {}
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        for title, rows in (("Tuning", TUNING), ("Configuration", CONFIG), ("Alarms", ALARMS), ("Scaling", SCALING)):
            page = QWidget()
            form = QFormLayout(page)
            for member, label, kind, tip in rows:
                w = self._field(member, kind)
                w.setToolTip(tip)
                lab = QLabel(label)
                lab.setToolTip(tip)
                form.addRow(lab, w)
                if member in ("KP", "KI", "KD"):
                    setattr(self, f"_label_{member}", lab)
            tabs.addTab(page, title)
        lay.addWidget(tabs)
        self.tabs = tabs
        note = QLabel("Applies to the tag's start values" + (" and to the running PID." if memory is not None else "."))
        note.setProperty("muted", "true")
        lay.addWidget(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        lay.addWidget(box)
        self.fields["PE"].currentIndexChanged.connect(self._gain_labels)
        self._gain_labels()

    def _field(self, member: str, kind) -> QWidget:
        v = self.values.get(member, 0.0)
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(v))
        elif isinstance(kind, list):
            w = QComboBox()
            w.addItems(kind)
            w.setCurrentIndex(1 if v else 0)
        else:
            w = QDoubleSpinBox()
            w.setDecimals(4)
            w.setRange(-1e9, 1e9)
            w.setValue(float(v))
        self.fields[member] = w
        return w

    def _gain_labels(self) -> None:
        for member, text in zip(("KP", "KI", "KD"), GAIN_LABELS[self.fields["PE"].currentIndex() == 1]):
            getattr(self, f"_label_{member}").setText(text)

    def result_values(self) -> dict:
        out = {}
        for member, w in self.fields.items():
            if isinstance(w, QCheckBox):
                out[member] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[member] = w.currentIndex() == 1
            else:
                out[member] = w.value()
        return out

    def problem(self, v: dict) -> str:
        if v["MAXO"] < v["MINO"]:
            return "CV high limit is below the low limit"
        if v["UPD"] < 0:
            return "Loop update time cannot be negative"
        return ""

    def apply(self) -> bool:
        v = self.result_values()
        msg = self.problem(v)
        if msg:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "PID Setup", msg)
            return False
        name = next((n for n in self.program.tags if n.lower() == self.name.lower()), None)
        if name is not None:
            decl = self.program.tags[name]
            default = lambda k, val: START["PID"].get(k, False if isinstance(val, bool) else 0.0)
            start = {k: val for k, val in v.items() if val != default(k, val)}   # only what differs
            if start:
                decl["value"] = start
            else:
                decl.pop("value", None)
        if self.memory is not None:
            try:
                self.memory.element(self.name).update(v)
            except Exception:
                pass
        return True

    def accept(self) -> None:
        if self.apply():
            super().accept()
