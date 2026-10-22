"""PLCYard entry point.

    python -m plcyard [program.plcy]
    python -m plcyard --headless program.plcy --ticks 100 [--press %I0.0 ...]
    python -m plcyard program.plcy --shot out.png [--sim silo] [--press %I0.0 ...]
"""

from __future__ import annotations

import argparse
import re
import sys


def input_point(text: str) -> tuple[int, int]:
    """%I0.3 → (slot 1, bit 3), %I1.2 → (slot 1, bit 10): the input card switch behind an address."""
    from .core.plc.memory import INPUT_SLOTS
    m = re.fullmatch(r"%I(\d+)\.([0-7])", text.strip(), re.I)
    for slot, base in INPUT_SLOTS.items():
        if m and base <= int(m[1]) < base + 2:
            return slot, (int(m[1]) - base) * 8 + int(m[2])
    raise SystemExit(f"--press: {text} is not an input switch (use %I0.0 … %I5.7)")


def headless(args) -> int:
    from .core.plc.memory import OUTPUT_SLOTS
    from .core.processor import Processor
    from . import formats
    from .sims.io_panel import IoPanelModel

    plc = Processor()
    panel = IoPanelModel()
    plc.device = panel
    prog = formats.load(args.program)
    panel.configure_from_symbols(prog.symbols)
    for addr in args.press:
        panel.set_pressed(*input_point(addr), True)
    problems = plc.download(prog)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 2
    plc.set_mode(Processor.RUN)
    for _ in range(args.ticks):
        plc.tick(10)
    print(f"scans={plc.scan_count} mode={plc.mode}")
    for base in OUTPUT_SLOTS.values():
        print(f"%QW{base} = {plc.dt.word('Q', base):016b}")
    return 1 if plc.fault else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="plcyard")
    ap.add_argument("program", nargs="?")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument("--press", action="append", default=[], help="input switch to hold on, e.g. %%I0.0")
    ap.add_argument("--sim", help="simulation to show with --shot (io, silo, tank…)")
    ap.add_argument("--theme", choices=("light", "dark"), default="light")
    ap.add_argument("--shot", help="save a screenshot of the window and exit")
    ap.add_argument("--wait", type=int, default=600, help="ms to run before --shot")
    args = ap.parse_args(argv)
    if args.headless:
        if not args.program:
            ap.error("--headless needs a program")
        return headless(args)

    from pathlib import Path

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("PLCYard")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "assets" / "icon.svg")))
    theme.apply(app, args.theme)
    win = MainWindow(args.program)
    win.show()
    if args.shot:
        from PySide6.QtCore import QTimer

        def shoot():
            if args.sim:
                win.select_sim(args.sim)
            win.resize(1440, 900)
            win.download()
            win.panel.mode.set_mode("RUN")
            if args.press and not hasattr(win.sim, "set_pressed"):
                print("--press works with the I/O panel only", file=sys.stderr)
                app.exit(2)
                return
            for addr in args.press:
                slot, bit = input_point(addr)
                win.sim.set_pressed(slot, bit, True)
                win.sim_view.switches[(slot, bit)].pressed = True
            QTimer.singleShot(args.wait, lambda: (win.grab().save(args.shot), app.quit()))

        QTimer.singleShot(200, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
