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
    edit_chosen = Signal(int, int, int, int)

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
        self.edit_scale = int(appearance.get('scale_percent', 100))
        self.edit_angle = int(appearance.get('rotation_degrees', 0))
        self.edit_action = None
        self.edit_origin = None
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
        factor = self.edit_scale / max(1, self.appearance.get('scale_percent', 100)) if self.mode == 'edit' else 1
        w, h = self.ghost.width()/sx*factor, self.ghost.height()/sy*factor
        x = self.width()/2 - w/2 + self.appearance.get('offset_x', 0)/sx + self.delta.x()
        y = self.height()/2 - h/2 + self.appearance.get('offset_y', 0)/sy + self.delta.y()
        return QRectF(x, y, w, h)

    def paintEvent(self, _event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(8, 15, 22, 110))
        if self.mode in ('move', 'edit') and not self.ghost.isNull():
            rect = self.ghost_rect()
            painter.save()
            if self.mode == 'edit':
                painter.translate(rect.center()); painter.rotate(self.edit_angle - self.appearance.get('rotation_degrees', 0)); painter.translate(-rect.center())
            painter.drawImage(rect, self.ghost)
            painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 193, 153, 205), 2, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect, 10, 10)
            if self.mode == 'edit':
                painter.setBrush(QColor('#ffc4a1')); painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(rect.bottomRight(), 9, 9)
                painter.drawEllipse(QPointF(rect.center().x(), rect.top()-25), 8, 8)
                painter.setPen(QPen(QColor('#ffc4a1'), 2)); painter.drawLine(QPointF(rect.center().x(), rect.top()), QPointF(rect.center().x(), rect.top()-25))
                if abs(rect.center().x()-self.width()/2) < 2: painter.drawLine(QPointF(self.width()/2, 0), QPointF(self.width()/2, self.height()))
                if abs(rect.center().y()-self.height()/2) < 2: painter.drawLine(QPointF(0, self.height()/2), QPointF(self.width(), self.height()/2))
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
        elif self.mode == 'edit':
            title = 'Trascina · angolo: dimensione · maniglia in alto: rotazione'
        else:
            title = 'Trascina l’anteprima del widget nella posizione desiderata'
        painter.drawText(panel.adjusted(18, 12, -18, -44), Qt.AlignmentFlag.AlignVCenter, title)
        painter.setFont(QFont('Segoe UI', 9)); painter.setPen(QColor('#b5c5d0'))
        painter.drawText(panel.adjusted(18, 44, -18, -12), Qt.AlignmentFlag.AlignVCenter,
                         'Conferma: clic qui o Invio · Esc / clic destro: annulla' if self.mode == 'edit' else 'La modifica resta in anteprima. Esc o clic destro per annullare.')

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
        if self.mode == 'edit':
            panel = QRectF(max(12, (self.width()-650)/2), 30, min(650, self.width()-24), 84)
            if panel.contains(point): self.accept_edit(); return
            rect = self.ghost_rect()
            if math.hypot(point.x()-rect.bottomRight().x(), point.y()-rect.bottomRight().y()) < 22:
                self.edit_action = 'resize'
            elif math.hypot(point.x()-rect.center().x(), point.y()-(rect.top()-25)) < 22:
                self.edit_action = 'rotate'
            elif rect.contains(point): self.edit_action = 'move'
            else: self.message = 'Trascina il widget o una maniglia.'; self.update(); return
            self.drag_start = point
            self.edit_origin = (QPointF(self.delta), self.edit_scale, self.edit_angle, rect)
            return
        if self.ghost_rect().contains(point):
            self.drag_start = point; self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            self.message = 'Clicca all’interno del riquadro e trascina.'; self.update()

    def mouseMoveEvent(self, event):
        if self.mode == 'angle' and self.first is not None:
            self.pointer = event.position(); self.update()
        elif self.mode == 'edit' and self.drag_start is not None:
            origin_delta, origin_scale, origin_angle, rect = self.edit_origin
            if self.edit_action == 'move':
                self.delta = origin_delta + event.position() - self.drag_start
                current = self.ghost_rect(); center = current.center()
                if abs(center.x()-self.width()/2) < 12: self.delta.setX(self.delta.x() + self.width()/2-center.x())
                if abs(center.y()-self.height()/2) < 12: self.delta.setY(self.delta.y() + self.height()/2-center.y())
            elif self.edit_action == 'resize':
                start = math.hypot(self.drag_start.x()-rect.center().x(), self.drag_start.y()-rect.center().y())
                now = math.hypot(event.position().x()-rect.center().x(), event.position().y()-rect.center().y())
                self.edit_scale = max(50, min(140, round(origin_scale * now / max(start, 1))))
            elif self.edit_action == 'rotate':
                start = math.atan2(self.drag_start.y()-rect.center().y(), self.drag_start.x()-rect.center().x())
                now = math.atan2(event.position().y()-rect.center().y(), event.position().x()-rect.center().x())
                self.edit_angle = round((origin_angle + math.degrees(now-start) + 180) % 360 - 180)
                if abs(self.edit_angle) < 4: self.edit_angle = 0
            self.update()
        elif self.mode == 'move' and self.drag_start is not None:
            self.delta = event.position() - self.drag_start; self.update()

    def mouseReleaseEvent(self, event):
        if self.mode == 'edit' and event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = None; self.edit_action = None; return
        if self.mode != 'move' or event.button() != Qt.MouseButton.LeftButton or self.drag_start is None:
            return
        delta = event.position() - self.drag_start
        sx, sy = self.ratios()
        x = max(-10000, min(10000, round(self.appearance.get('offset_x', 0) + delta.x()*sx)))
        y = max(-10000, min(10000, round(self.appearance.get('offset_y', 0) + delta.y()*sy)))
        self.position_chosen.emit(x, y); self.close()

    def accept_edit(self):
        sx, sy = self.ratios()
        x = max(-10000, min(10000, round(self.appearance.get('offset_x', 0) + self.delta.x()*sx)))
        y = max(-10000, min(10000, round(self.appearance.get('offset_y', 0) + self.delta.y()*sy)))
        self.edit_chosen.emit(x, y, self.edit_scale, self.edit_angle); self.close()

    def keyPressEvent(self, event):
        if self.mode == 'edit' and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept_edit(); return
        if event.key() == Qt.Key.Key_Escape:
            self.close(); return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
