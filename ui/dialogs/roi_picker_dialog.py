from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QHBoxLayout


class _RoiCanvas(QLabel):
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self._pixmap = pixmap
        self._start = QPoint()
        self._end = QPoint()
        self._rect = QRect()
        self.setPixmap(self._pixmap)
        self.setFixedSize(self._pixmap.size())

    @property
    def rect_pixels(self) -> tuple[int, int, int, int]:
        r = self._rect.normalized()
        return r.x(), r.y(), r.width(), r.height()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self._rect = QRect(self._start, self._end)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._end = event.position().toPoint()
            self._rect = QRect(self._start, self._end)
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._end = event.position().toPoint()
            self._rect = QRect(self._start, self._end)
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._rect.isNull():
            return
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.drawRect(self._rect.normalized())


class RoiPickerDialog(QDialog):
    def __init__(self, frame_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Выбор ROI")
        pixmap = QPixmap(frame_path)
        if pixmap.isNull():
            raise ValueError("Не удалось загрузить превью кадра")

        self.canvas = _RoiCanvas(pixmap)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_roi(self) -> tuple[int, int, int, int]:
        return self.canvas.rect_pixels
