"""PLCYard entry point.

    python -m plcyard [program.rsl]
    python -m plcyard --headless program.rsl --ticks 100 [--press I:1/0 ...]
"""

from __future__ import annotations

import argparse
import sys


def headless(args) -> int:
    from .core.address import parse_address
    from .core.processor import Processor
    from . import formats
    from .sims.io_panel import IoPanelModel

    plc = Processor()
    panel = IoPanelModel()
    plc.device = panel
    prog = formats.load(args.program)
    panel.configure_from_symbols(prog.symbols)
    for addr in args.press:
        a = parse_address(addr)
        panel.set_pressed(a.element, a.bit, True)
    problems = plc.download(prog)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 2
    plc.set_mode(Processor.RUN)
    for _ in range(args.ticks):
        plc.tick(10)
    print(f"scans={plc.scan_count} mode={plc.mode}")
    for slot in (2, 4, 6):
        print(f"O:{slot} = {plc.dt.read_slot(0, slot):016b}")
    return 1 if plc.fault else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="plcyard")
    ap.add_argument("program", nargs="?")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument("--press", action="append", default=[], help="input to hold on, e.g. I:1/0")
    ap.add_argument("--theme", choices=("light", "dark"), default="light")
    ap.add_argument("--shot", help="save a screenshot of the window and exit")
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
        from .core.address import parse_address

        def shoot():
            win.download()
            win.panel.mode.set_mode("RUN")
            for addr in args.press:
                a = parse_address(addr)
                win.sim.set_pressed(a.element, a.bit, True)
                win.sim_view.switches[(a.element, a.bit)].pressed = True
            QTimer.singleShot(600, lambda: (win.grab().save(args.shot), app.quit()))

        QTimer.singleShot(200, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
