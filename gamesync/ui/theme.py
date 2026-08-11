"""Colour tokens and the application stylesheet.

Qt stylesheets have no variables, so the palette lives in Python and the sheet
is formatted against it. Both themes use the same token names, which keeps the
widget code free of theme conditionals.
"""

from __future__ import annotations

DARK = {
    "bg": "#0f1115",
    "surface": "#171a21",
    "surface_alt": "#1d212a",
    "surface_hover": "#232833",
    "border": "#2a3040",
    "border_strong": "#3a4356",
    "text": "#e7eaf0",
    "text_dim": "#98a1b3",
    "text_faint": "#6b7488",
    "accent": "#6366f1",
    "accent_hover": "#7c7ff5",
    "accent_press": "#5457d6",
    "accent_soft": "#1e2039",
    "success": "#34d399",
    "success_soft": "#10291f",
    "warn": "#fbbf24",
    "warn_soft": "#2b2211",
    "danger": "#f87171",
    "danger_soft": "#2d1717",
    "shadow": "rgba(0, 0, 0, 0.45)",
}

LIGHT = {
    "bg": "#f5f6f8",
    "surface": "#ffffff",
    "surface_alt": "#f0f2f5",
    "surface_hover": "#e8ebf0",
    "border": "#dfe3ea",
    "border_strong": "#c3cad6",
    "text": "#161922",
    "text_dim": "#5b6474",
    "text_faint": "#8a93a3",
    "accent": "#5457d6",
    "accent_hover": "#6366f1",
    "accent_press": "#4245b8",
    "accent_soft": "#ecedfc",
    "success": "#0f9d6e",
    "success_soft": "#e4f7f0",
    "warn": "#b45309",
    "warn_soft": "#fdf3e2",
    "danger": "#d0342c",
    "danger_soft": "#fdeceb",
    "shadow": "rgba(15, 20, 35, 0.10)",
}

FONT_STACK = (
    '"Inter", "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", '
    '"Ubuntu", "Cantarell", "Noto Sans", sans-serif'
)

MONO_STACK = (
    '"JetBrains Mono", "SF Mono", "Cascadia Mono", "Consolas", '
    '"DejaVu Sans Mono", monospace'
)


def _check_svg(color: str = "#ffffff") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 12 12"><path d="M2.4 6.3 L4.8 8.7 L9.6 3.3" fill="none" '
        f'stroke="{color}" stroke-width="1.9" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )


def _chevron_svg(color: str, up: bool = False) -> str:
    path = "M2.2 6.2 L5 3.4 L7.8 6.2" if up else "M2.2 3.8 L5 6.6 L7.8 3.8"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
        f'viewBox="0 0 10 10"><path d="{path}" fill="none" '
        f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )


_icon_cache: dict[str, str] = {}


def _icon_url(name: str, svg: str) -> str:
    """Write an SVG to the app data dir once and return its path for url().

    Qt stylesheets cannot draw a glyph, do not accept data: URIs, and ignore
    the CSS border-triangle trick — an arrow or tick has to be a real image.
    If the SVG image plugin is missing, callers fall back to no image.
    """
    if name in _icon_cache:
        return _icon_cache[name]

    try:
        from PySide6.QtGui import QImage

        from ..paths import data_dir

        icon_dir = data_dir() / "icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        path = icon_dir / f"{name}.svg"
        if not path.exists() or path.read_text(encoding="utf-8") != svg:
            path.write_text(svg, encoding="utf-8")

        _icon_cache[name] = "" if QImage(str(path)).isNull() else path.as_posix()
    except Exception:
        _icon_cache[name] = ""
    return _icon_cache[name]


def palette(theme: str) -> dict[str, str]:
    return LIGHT if theme == "light" else DARK


def stylesheet(theme: str) -> str:
    c = palette(theme)
    suffix = "light" if theme == "light" else "dark"

    check = _icon_url("check", _check_svg())
    chevron = _icon_url(f"chevron-{suffix}", _chevron_svg(c["text_dim"]))
    chevron_hover = _icon_url(f"chevron-hover-{suffix}", _chevron_svg(c["text"]))
    chevron_up = _icon_url(f"chevron-up-{suffix}", _chevron_svg(c["text_dim"], up=True))

    return _SHEET % {
        **c,
        "font": FONT_STACK,
        "mono": MONO_STACK,
        "check_image": f"image: url({check});" if check else "image: none;",
        "chevron_image": f"image: url({chevron});" if chevron else "image: none;",
        "chevron_hover_image": (
            f"image: url({chevron_hover});" if chevron_hover else "image: none;"
        ),
        "chevron_up_image": (
            f"image: url({chevron_up});" if chevron_up else "image: none;"
        ),
    }


_SHEET = """
* {
    font-family: %(font)s;
    font-size: 13px;
    color: %(text)s;
    outline: none;
}

QWidget#Root, QMainWindow, QDialog {
    background: %(bg)s;
}

/* ---- sidebar ---- */

QWidget#Sidebar {
    background: %(surface)s;
    border-right: 1px solid %(border)s;
}

QLabel#BrandTitle {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.2px;
}

QLabel#BrandSub {
    color: %(text_faint)s;
    font-size: 11px;
}

QPushButton#NavItem {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    color: %(text_dim)s;
    font-weight: 500;
}
QPushButton#NavItem:hover {
    background: %(surface_hover)s;
    color: %(text)s;
}
QPushButton#NavItem:checked {
    background: %(accent_soft)s;
    color: %(accent)s;
    font-weight: 600;
}

QWidget#AccountChip {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}

/* ---- headings ---- */

QLabel#PageTitle {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.4px;
}
QLabel#PageSubtitle {
    color: %(text_dim)s;
    font-size: 13px;
}
QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 650;
}
QLabel#Hint {
    color: %(text_faint)s;
    font-size: 12px;
}
QLabel#Dim {
    color: %(text_dim)s;
}
QLabel#Mono {
    font-family: %(mono)s;
    color: %(text_dim)s;
    font-size: 12px;
}

/* ---- cards ---- */

QFrame#Card, QWidget#Card {
    background: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 12px;
}
QFrame#Card:hover {
    border-color: %(border_strong)s;
}
QFrame#InsetCard {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}

/* ---- buttons ---- */

QPushButton {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 550;
    color: %(text)s;
}
QPushButton:hover { background: %(surface_hover)s; }
QPushButton:pressed { background: %(border)s; }
QPushButton:disabled { color: %(text_faint)s; background: %(surface_alt)s; border-color: %(border)s; }

QPushButton#Primary {
    background: %(accent)s;
    border: 1px solid %(accent)s;
    color: #ffffff;
}
QPushButton#Primary:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton#Primary:pressed { background: %(accent_press)s; }
QPushButton#Primary:disabled { background: %(border)s; border-color: %(border)s; color: %(text_faint)s; }

QPushButton#Ghost {
    background: transparent;
    border: 1px solid transparent;
    color: %(text_dim)s;
    padding: 6px 10px;
}
QPushButton#Ghost:hover { background: %(surface_hover)s; color: %(text)s; }

QPushButton#Danger {
    background: transparent;
    border: 1px solid %(border_strong)s;
    color: %(danger)s;
}
QPushButton#Danger:hover { background: %(danger_soft)s; border-color: %(danger)s; }

QPushButton#LinkButton {
    background: transparent;
    border: none;
    color: %(accent)s;
    padding: 2px 0;
    text-align: left;
    font-weight: 550;
}
QPushButton#LinkButton:hover { color: %(accent_hover)s; }

/* ---- inputs ---- */

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: %(accent)s;
    selection-color: #ffffff;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: %(accent)s;
}
QLineEdit:disabled, QSpinBox:disabled { color: %(text_faint)s; }
QLineEdit[echoMode="2"] { font-family: %(mono)s; letter-spacing: 1px; }

QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow {
    %(chevron_image)s
    width: 10px; height: 10px;
    margin-right: 9px;
}
QComboBox::down-arrow:hover { %(chevron_hover_image)s }
QComboBox QAbstractItemView {
    background: %(surface)s;
    border: 1px solid %(border_strong)s;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
}

QSpinBox::up-button, QSpinBox::down-button {
    width: 18px; border: none; background: transparent;
}
QSpinBox::up-arrow { %(chevron_up_image)s width: 10px; height: 10px; }
QSpinBox::down-arrow { %(chevron_image)s width: 10px; height: 10px; }

/* ---- lists ---- */

QListWidget, QTreeWidget {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    padding: 4px;
}
QListWidget::item, QTreeWidget::item {
    padding: 7px 8px;
    border-radius: 6px;
    color: %(text)s;
}
QListWidget::item:hover { background: %(surface_hover)s; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}

/* ---- misc ---- */

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 17px; height: 17px;
    border: 1px solid %(border_strong)s;
    border-radius: 5px;
    background: %(surface_alt)s;
}
QCheckBox::indicator:checked {
    background: %(accent)s;
    border-color: %(accent)s;
    %(check_image)s
}
QCheckBox::indicator:hover { border-color: %(accent)s; }

QProgressBar {
    background: %(surface_alt)s;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: %(border_strong)s; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: %(text_faint)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: %(border_strong)s; border-radius: 5px; min-width: 30px;
}

QFrame#Divider { background: %(border)s; max-height: 1px; border: none; }

QToolTip {
    background: %(surface)s;
    color: %(text)s;
    border: 1px solid %(border_strong)s;
    border-radius: 6px;
    padding: 5px 8px;
}

QMenu {
    background: %(surface)s;
    border: 1px solid %(border_strong)s;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: %(accent_soft)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 6px; }
"""
