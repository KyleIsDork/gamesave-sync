#!/usr/bin/env python3
"""Render the application icon.

Run this to regenerate assets/ after changing the design:

    python packaging/make_icon.py

Produces PNGs at the sizes AppImage, Windows and macOS want, plus a .ico.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

ACCENT_TOP = "#7c7ff5"
ACCENT_BOTTOM = "#4f46e5"
FOREGROUND = "#ffffff"

SIZES = [16, 32, 48, 64, 128, 256, 512]


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size / 256.0  # design is authored at 256px

    # Rounded-square background with a vertical gradient.
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    gradient.setColorAt(0.0, QColor(ACCENT_TOP))
    gradient.setColorAt(1.0, QColor(ACCENT_BOTTOM))
    background = QPainterPath()
    background.addRoundedRect(QRectF(0, 0, size, size), 58 * s, 58 * s)
    painter.fillPath(background, QBrush(gradient))

    # A floppy disk: the universal "save" mark, still legible at 16px.
    white = QColor(FOREGROUND)
    body = QPainterPath()
    corner_cut = 34 * s
    left, top, right, bottom = 58 * s, 58 * s, 198 * s, 198 * s
    radius = 10 * s

    body.moveTo(left + radius, top)
    body.lineTo(right - corner_cut, top)
    body.lineTo(right, top + corner_cut)
    body.lineTo(right, bottom - radius)
    body.quadTo(right, bottom, right - radius, bottom)
    body.lineTo(left + radius, bottom)
    body.quadTo(left, bottom, left, bottom - radius)
    body.lineTo(left, top + radius)
    body.quadTo(left, top, left + radius, top)
    body.closeSubpath()
    painter.fillPath(body, white)

    # Cut the shutter and label back out by refilling them with the *same*
    # gradient brush. Because the gradient is defined over the whole image,
    # this reproduces the background exactly at those positions — cleaner than
    # a composition mode, which would punch through the background too.
    shutter = QPainterPath()
    shutter.addRoundedRect(QRectF(98 * s, 58 * s, 54 * s, 48 * s), 4 * s, 4 * s)
    painter.fillPath(shutter, QBrush(gradient))

    label = QPainterPath()
    label.addRoundedRect(QRectF(84 * s, 132 * s, 88 * s, 66 * s), 7 * s, 7 * s)
    painter.fillPath(label, QBrush(gradient))

    # Two lines on the label, so the mark still reads as a disk at small sizes.
    for index in range(2):
        line = QPainterPath()
        line.addRoundedRect(
            QRectF(100 * s, (150 + index * 22) * s, 56 * s, 10 * s), 5 * s, 5 * s
        )
        painter.fillPath(line, white)

    painter.end()
    return image


def main() -> int:
    QApplication(sys.argv)  # QPainter/QImage need an application instance

    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)

    images = {}
    for size in SIZES:
        image = render(size)
        images[size] = image
        image.save(str(assets / f"icon-{size}.png"))

    # Canonical icon used by the README, the .desktop entry and the AppImage.
    images[256].save(str(assets / "icon.png"))

    # Windows .ico — Qt writes a multi-size ICO from the largest image it gets,
    # so write the 256px one and let Qt downscale.
    images[256].save(str(assets / "icon.ico"))

    print(f"wrote {len(SIZES) + 2} files to {assets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
