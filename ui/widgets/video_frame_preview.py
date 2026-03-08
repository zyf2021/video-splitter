from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget


class VideoFramePreviewWidget(QWidget):
    hoverPointChanged = pyqtSignal(int, int)
    hoverLeftImage = pyqtSignal()
    clickedPoint = pyqtSignal(int, int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._pixmap = QPixmap()
        self._draw_rect: Optional[QRect] = None
        self._video_rect: Optional[tuple[int, int, int, int]] = None
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._invalid_overlay = False

    def set_frame_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._recalculate_viewport()
        self.update()

    def set_overlay_rect(self, x: int, y: int, w: int, h: int, invalid: bool = False) -> None:
        self._video_rect = (x, y, w, h)
        self._invalid_overlay = invalid
        self._recalculate_overlay_rect()
        self.update()

    def clear_overlay_rect(self) -> None:
        self._video_rect = None
        self._draw_rect = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recalculate_viewport()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202124"))
        if self._pixmap.isNull():
            painter.setPen(QColor("#9aa0a6"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет кадра для предпросмотра")
            return

        target = self._pixmap_target_rect()
        painter.drawPixmap(target, self._pixmap)

        if self._draw_rect and self._draw_rect.width() > 0 and self._draw_rect.height() > 0:
            fill = QColor(255, 0, 0, 70) if self._invalid_overlay else QColor(80, 170, 255, 70)
            stroke = QColor(255, 0, 0) if self._invalid_overlay else QColor(80, 170, 255)
            painter.fillRect(self._draw_rect, fill)
            pen = QPen(stroke)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self._draw_rect)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = self._to_video_point(event.position().toPoint())
        if pos is None:
            self.hoverLeftImage.emit()
            return
        self.hoverPointChanged.emit(pos.x(), pos.y())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._to_video_point(event.position().toPoint())
        if pos is None:
            return
        self.clickedPoint.emit(pos.x(), pos.y())

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.hoverLeftImage.emit()

    def _pixmap_target_rect(self) -> QRect:
        if self._pixmap.isNull():
            return QRect()
        w = int(round(self._pixmap.width() * self._scale))
        h = int(round(self._pixmap.height() * self._scale))
        return QRect(int(round(self._offset_x)), int(round(self._offset_y)), w, h)

    def _recalculate_viewport(self) -> None:
        if self._pixmap.isNull():
            self._scale = 1.0
            self._offset_x = 0.0
            self._offset_y = 0.0
            return
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        scale_w = avail_w / self._pixmap.width()
        scale_h = avail_h / self._pixmap.height()
        self._scale = min(scale_w, scale_h)
        draw_w = self._pixmap.width() * self._scale
        draw_h = self._pixmap.height() * self._scale
        self._offset_x = (avail_w - draw_w) / 2
        self._offset_y = (avail_h - draw_h) / 2
        self._recalculate_overlay_rect()

    def _recalculate_overlay_rect(self) -> None:
        if self._video_rect is None:
            self._draw_rect = None
            return
        x, y, w, h = self._video_rect
        self._draw_rect = QRect(
            int(round(self._offset_x + x * self._scale)),
            int(round(self._offset_y + y * self._scale)),
            max(1, int(round(w * self._scale))),
            max(1, int(round(h * self._scale))),
        )

    def _to_video_point(self, widget_point: QPoint) -> Optional[QPoint]:
        if self._pixmap.isNull() or self._scale <= 0:
            return None
        local_x = widget_point.x() - self._offset_x
        local_y = widget_point.y() - self._offset_y
        draw_w = self._pixmap.width() * self._scale
        draw_h = self._pixmap.height() * self._scale
        if local_x < 0 or local_y < 0 or local_x > draw_w or local_y > draw_h:
            return None

        x_video = int(local_x / self._scale)
        y_video = int(local_y / self._scale)
        x_video = max(0, min(self._pixmap.width() - 1, x_video))
        y_video = max(0, min(self._pixmap.height() - 1, y_video))
        return QPoint(x_video, y_video)
