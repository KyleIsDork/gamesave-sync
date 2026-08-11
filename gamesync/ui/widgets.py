"""Small shared widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import palette


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, inset: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("InsetCard" if inset else "Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class Pill(QLabel):
    """Small status chip. Tone is one of: neutral, success, warn, danger, accent."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None) -> None:
        super().__init__(text, parent)
        self._tone = tone
        self._theme = "dark"
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        font = self.font()
        font.setPointSizeF(max(font.pointSizeF() - 1.0, 7.5))
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        self._restyle()

    def set_state(self, text: str, tone: str) -> None:
        self.setText(text)
        self._tone = tone
        self._restyle()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self._restyle()

    def _restyle(self) -> None:
        c = palette(self._theme)
        mapping = {
            "success": (c["success"], c["success_soft"]),
            "warn": (c["warn"], c["warn_soft"]),
            "danger": (c["danger"], c["danger_soft"]),
            "accent": (c["accent"], c["accent_soft"]),
            "neutral": (c["text_dim"], c["surface_alt"]),
        }
        fg, bg = mapping.get(self._tone, mapping["neutral"])
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 9px;"
            f" padding: 3px 9px; border: none;"
        )


class Spinner(QWidget):
    """Indeterminate activity indicator drawn with QPainter."""

    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._theme = "dark"
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def start(self) -> None:
        self.show()
        if not self._timer.isActive():
            self._timer.start(40)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = palette(self._theme)
        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = painter.pen()
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setColor(QColor(c["border_strong"]))
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        pen.setColor(QColor(c["accent"]))
        painter.setPen(pen)
        painter.drawArc(rect, -self._angle * 16, 100 * 16)


class Toast(QFrame):
    """Transient message that slides in at the bottom of its parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._theme = "dark"
        self._label = QLabel("", self)
        self._label.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.addWidget(self._label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._anim: QPropertyAnimation | None = None
        self.hide()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme

    def show_message(self, text: str, tone: str = "neutral", msec: int = 4200) -> None:
        c = palette(self._theme)
        accents = {
            "success": c["success"],
            "warn": c["warn"],
            "danger": c["danger"],
            "neutral": c["accent"],
        }
        edge = accents.get(tone, c["accent"])
        self.setStyleSheet(
            f"background: {c['surface']}; border: 1px solid {c['border_strong']};"
            f" border-left: 3px solid {edge}; border-radius: 10px;"
        )
        self._label.setText(text)
        self._label.setStyleSheet(f"color: {c['text']}; border: none; background: transparent;")

        self.adjustSize()
        self.setFixedWidth(min(460, max(280, self.parentWidget().width() - 80)))
        self._label.setFixedWidth(self.width() - 28)
        self.adjustSize()
        self._reposition()

        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(msec)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 26
        self.move(max(x, 12), max(y, 12))

    def _fade_out(self) -> None:
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self.hide)
        self._anim.start()


class EmptyState(QWidget):
    action_clicked = Signal()

    def __init__(
        self,
        glyph: str,
        title: str,
        body: str,
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icon = QLabel(glyph)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = icon.font()
        font.setPointSize(34)
        icon.setFont(font)
        icon.setObjectName("Hint")

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading_font = heading.font()
        heading_font.setPointSizeF(heading_font.pointSizeF() + 2)
        heading.setFont(heading_font)

        text = QLabel(body)
        text.setObjectName("Hint")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        text.setMaximumWidth(420)

        layout.addWidget(icon)
        layout.addWidget(heading)
        layout.addWidget(text, alignment=Qt.AlignmentFlag.AlignCenter)

        if action_text:
            button = QPushButton(action_text)
            button.setObjectName("Primary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self.action_clicked.emit)
            layout.addSpacing(6)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)


def hline(*widgets: QWidget, spacing: int = 8, margins: tuple = (0, 0, 0, 0)) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for w in widgets:
        if w is None:
            layout.addStretch(1)
        else:
            layout.addWidget(w)
    return container
