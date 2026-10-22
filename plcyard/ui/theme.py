"""Design tokens -> QPalette + QSS. Widgets read colours by role, never hex."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).parent / "assets"

_tokens: dict = {}
_mode = "light"


def load(mode: str = "light") -> dict:
    global _tokens, _mode
    _mode = mode
    _tokens = json.loads((ASSETS / f"tokens.{mode}.json").read_text(encoding="utf-8"))
    return _tokens


def mode() -> str:
    return _mode


def color(role: str) -> QColor:
    if not _tokens:
        load(_mode)
    return QColor(_tokens["color"][role])


def hexc(role: str) -> str:
    return color(role).name()


def size(name: str) -> int:
    return _tokens["type"][name]["size"]


def layout(name: str) -> int:
    return _tokens["layout"][name]


def radius(name: str) -> int:
    return _tokens["radius"][name]


def font(kind: str = "sans", type_name: str = "base") -> QFont:
    families = [f.strip() for f in _tokens["font"][kind].split(",")]
    f = QFont()
    f.setFamilies(families)
    t = _tokens["type"][type_name]
    f.setPixelSize(t["size"])
    f.setWeight(QFont.Weight(t["weight"]))
    return f


def palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: "surface", QPalette.WindowText: "text",
        QPalette.Base: "bg", QPalette.AlternateBase: "surface",
        QPalette.Text: "text", QPalette.Button: "surface",
        QPalette.ButtonText: "text", QPalette.Highlight: "accent",
        QPalette.HighlightedText: "on-accent", QPalette.ToolTipBase: "surface-2",
        QPalette.ToolTipText: "text", QPalette.PlaceholderText: "text-muted",
        QPalette.Link: "accent", QPalette.Mid: "border",
    }
    for qrole, token in roles.items():
        p.setColor(qrole, color(token))
    p.setColor(QPalette.Disabled, QPalette.Text, color("text-muted"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, color("text-muted"))
    return p


def stylesheet() -> str:
    c = hexc
    r = radius
    return f"""
QWidget {{ color: {c('text')}; }}
QMainWindow, QDialog {{ background: {c('surface')}; }}
QToolTip {{ background: {c('surface-2')}; color: {c('text')}; border: 1px solid {c('border')}; padding: 4px 6px; }}
QPushButton {{
  background: {c('surface')}; color: {c('text')}; border: 1px solid {c('border')};
  border-radius: {r('sm')}px; padding: 0 12px; min-height: 30px; font-weight: 500;
}}
QPushButton:hover {{ background: {c('surface-2')}; }}
QPushButton:pressed {{ background: {c('border')}; }}
QPushButton:focus {{ border: 2px solid {c('accent')}; }}
QPushButton:disabled {{ color: {c('text-muted')}; }}
QPushButton:checked {{ background: {c('accent-soft')}; border: 2px solid {c('accent')}; font-weight: 600; }}
QPushButton[variant="primary"] {{ background: {c('accent')}; color: {c('on-accent')}; border-color: {c('accent')}; }}
QPushButton[variant="danger"] {{ background: {c('danger')}; color: {c('on-danger')}; border-color: {c('danger')}; }}
QPushButton[variant="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {c('surface-2')}; }}
QToolButton {{
  background: transparent; border: 1px solid transparent; border-radius: {r('sm')}px;
  padding: 2px 6px; min-height: 26px;
}}
QToolButton:hover {{ background: {c('surface-2')}; border-color: {c('border')}; }}
QToolButton:checked {{ background: {c('accent-soft')}; border-color: {c('accent')}; }}
QToolButton:focus {{ border: 2px solid {c('accent')}; }}
QLineEdit, QComboBox, QSpinBox {{
  background: {c('bg')}; border: 1px solid {c('border-input')}; border-radius: {r('sm')}px;
  padding: 3px 6px; min-height: 24px; selection-background-color: {c('accent')};
  selection-color: {c('on-accent')};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {c('accent')}; }}
QLineEdit[invalid="true"] {{ border: 2px solid {c('danger')}; }}
QTabBar::tab {{
  background: transparent; color: {c('text-muted')}; padding: 4px 12px; border: none;
  border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {c('text')}; border-bottom: 2px solid {c('accent')}; }}
QTabBar::tab:hover {{ color: {c('text')}; }}
QHeaderView::section {{ background: {c('surface')}; color: {c('text-muted')}; border: none;
  border-bottom: 1px solid {c('border')}; padding: 4px; }}
QTableView {{ background: {c('bg')}; gridline-color: {c('border')}; border: 1px solid {c('border')}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c('border')}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c('accent')}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c('bg')}; border: 2px solid {c('accent')};
  width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}
QSplitter::handle {{ background: {c('border')}; }}
QStatusBar {{ background: {c('surface')}; color: {c('text-muted')}; border-top: 1px solid {c('border')}; }}
QMenu {{ background: {c('bg')}; border: 1px solid {c('border')}; padding: 4px; }}
QMenu::item {{ padding: 4px 20px; border-radius: {r('sm')}px; }}
QMenu::item:selected {{ background: {c('accent-soft')}; }}
QLabel[muted="true"] {{ color: {c('text-muted')}; }}
QLabel[status="success"], QToolButton[status="success"] {{ color: {c('success')}; font-weight: 600; }}
QLabel[status="warning"], QToolButton[status="warning"] {{ color: {c('warning')}; font-weight: 600; }}
QLabel[status="danger"], QToolButton[status="danger"] {{ color: {c('danger')}; font-weight: 600; }}
"""


_fonts_loaded = False


def load_fonts() -> None:
    """Bundled OFL fonts: Inter (UI) and JetBrains Mono (addresses, values)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    for ttf in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))
    _fonts_loaded = True


def apply(app: QApplication, mode_name: str = "light") -> None:
    load_fonts()
    load(mode_name)
    app.setPalette(palette())
    app.setFont(font("sans", "base"))
    app.setStyleSheet(stylesheet())
