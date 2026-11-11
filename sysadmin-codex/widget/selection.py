"""Selezione temporanea su uno schermo; non modifica il widget applicato."""
import math
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QCursor, QImage, QFont
from PySide6.QtWidgets import QWidget


def angle_degrees(first, second):
    dx, dy = second[0]-first[0], second[1]-first[1]
    if math.hypot(dx, dy) < 4:
        raise ValueError('Scegli un secondo punto diverso dal primo.')
    return round(math.degrees(math.atan2(dy, dx)))


def screen_for_monitor(screens, monitor):
    """Associa il monitor fisico Windows allo schermo Qt più coerente."""
    if not screens:
        raise RuntimeError('Nessuno schermo disponibile.')
    left, top, right, bottom = monitor['rect']
    def score(screen):
        geom = screen.geometry(); ratio = screen.devicePixelRatio()
        return (abs(geom.x()-left) + abs(geom.y()-top) +
                abs(geom.width()*ratio-(right-left)) + abs(geom.height()*ratio-(bottom-top)))
    return min(screens, key=score)


class DesktopSelection(QWidget):
    angle_chosen = Signal(int)
    position_chosen = Signal(int, int)
    finished = Signal()

    def __init__(self, screen, mode, monitor_rect, appearance, ghost=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor if mode == 'angle' else Qt.CursorShape.OpenHandCursor))
        self.screen, self.mode, self.monitor_rect, self.appearance = screen, mode, monitor_rect, dict(appearance)
        self.first = None
        self.pointer = None
        self.drag_start = None
        self.delta = QPointF(0, 0)
        self.message = ''
        self.ghost = ghost or QImage()
        self.setGeometry(screen.geometry())

    def show_selection(self):
        self.winId()
        if self.windowHandle(): self.windowHandle().setScreen(self.screen)
        self.setGeometry(self.screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def ratios(self):
        left, top, right, bottom = self.monitor_rect
        return (right-left)/max(1, self.width()), (bottom-top)/max(1, self.height())

    def ghost_rect(self):
        sx, sy = self.ratios()
        w, h = self.ghost.width()/sx, self.ghost.height()/sy
        x = self.width()/2 - w/2 + self.appearance.get('offset_x', 0)/sx + self.delta.x()
        y = self.height()/2 - h/2 + self.appearance.get('offset_y', 0)/sy + self.delta.y()
        return QRectF(x, y, w, h)

    def paintEvent(self, _event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(8, 15, 22, 110))
        if self.mode == 'move' and not self.ghost.isNull():
            rect = self.ghost_rect()
            painter.drawImage(rect, self.ghost)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 193, 153, 205), 2, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect, 10, 10)
        if self.mode == 'angle' and self.first is not None:
            painter.setPen(QPen(QColor('#ffc4a1'), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            end = self.pointer or self.first
            painter.drawLine(self.first, end)
            painter.setBrush(QColor('#ffc4a1')); painter.drawEllipse(self.first, 7, 7)
        painter.setPen(Qt.PenStyle.NoPen)
        panel = QRectF(max(12, (self.width()-650)/2), 30, min(650, self.width()-24), 84)
        painter.setBrush(QColor(20, 32, 42, 235)); painter.drawRoundedRect(panel, 14, 14)
        painter.setFont(QFont('Segoe UI', 11, QFont.Weight.DemiBold)); painter.setPen(QColor('#f4f6f7'))
        if self.message:
            title = self.message
        elif self.mode == 'angle':
            title = 'Scegli il secondo punto' if self.first else 'Scegli il primo punto della linea'
        else:
            title = 'Trascina l’anteprima del widget nella posizione desiderata'
        painter.drawText(panel.adjusted(18, 12, -18, -44), Qt.AlignmentFlag.AlignVCenter, title)
        painter.setFont(QFont('Segoe UI', 9)); painter.setPen(QColor('#b5c5d0'))
        painter.drawText(panel.adjusted(18, 44, -18, -12), Qt.AlignmentFlag.AlignVCenter,
                         'La modifica resta in anteprima. Esc o clic destro per annullare.')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close(); return
        if event.button() != Qt.MouseButton.LeftButton: return
        point = event.position()
        if self.mode == 'angle':
            if self.first is None:
                self.first = point; self.message = ''; self.update(); return
            try:
                angle = angle_degrees((self.first.x(), self.first.y()), (point.x(), point.y()))
            except ValueError as error:
                self.message = str(error); self.update(); return
            self.angle_chosen.emit(angle); self.close(); return
        if self.ghost_rect().contains(point):
            self.drag_start = point; self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            self.message = 'Clicca all’interno del riquadro e trascina.'; self.update()

    def mouseMoveEvent(self, event):
        if self.mode == 'angle' and self.first is not None:
            self.pointer = event.position(); self.update()
        elif self.mode == 'move' and self.drag_start is not None:
            self.delta = event.position() - self.drag_start; self.update()

    def mouseReleaseEvent(self, event):
        if self.mode != 'move' or event.button() != Qt.MouseButton.LeftButton or self.drag_start is None:
            return
        delta = event.position() - self.drag_start
        sx, sy = self.ratios()
        x = max(-10000, min(10000, round(self.appearance.get('offset_x', 0) + delta.x()*sx)))
        y = max(-10000, min(10000, round(self.appearance.get('offset_y', 0) + delta.y()*sy)))
        self.position_chosen.emit(x, y); self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close(); return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
