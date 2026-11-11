"""Launcher del widget: impostazioni guidate e modifiche grafiche esplicite."""
import ctypes
import datetime as dt
import io
import math
import runpy
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from PySide6.QtCore import Qt, Signal, QObject, QThreadPool, QRunnable, QUrl, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QDesktopServices, QFont, QImage
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QListWidget, QListWidgetItem, QScrollArea,
    QSlider, QSpinBox, QComboBox, QCheckBox, QColorDialog, QLineEdit, QDialog, QGridLayout,
    QDialogButtonBox, QFormLayout, QMessageBox, QFileDialog, QInputDialog)
import credentials
import displays
import google_oauth
import model
import providers
import selection
import paths

SOURCES = {'Obiettivo personale': 'personal', 'GitHub': 'github',
           **{name: key for key, (name, _) in providers.SERVICES.items()}}
BASE = paths.RESOURCES
PRESETS = model.HERE / 'preset-aspetto.json'
DEFAULT_APPEARANCE = {'scale_percent': 100, 'opacity_percent': 100, 'accent': '#ffae85',
                      'rotation_degrees': 0, 'offset_x': 0, 'offset_y': 0,
                      'monitor': '', 'manual_timer_enabled': True}

STYLE = """
QWidget { background:#101923; color:#e9eef2; font-family:'Segoe UI'; font-size:13px; }
QFrame#sidebar { background:#121d28; border-right:1px solid #2a3844; }
QFrame#card { background:#1a2733; border:1px solid #30404c; border-radius:16px; }
QFrame#card QLabel, QFrame#card QCheckBox { background:transparent; }
QLabel#eyebrow { color:#f1aa85; font-size:11px; font-weight:700; letter-spacing:2px; }
QLabel#heading { color:#f5f7f8; font-size:28px; font-weight:700; }
QLabel#section { color:#f2f5f6; font-size:17px; font-weight:650; }
QLabel#muted { color:#a4b5c2; font-size:12px; }
QLabel#status { color:#b7c9d2; font-size:12px; }
QPushButton { background:#293b49; border:1px solid #405361; border-radius:9px; padding:9px 14px; font-weight:600; }
QPushButton:hover { background:#364b5a; border-color:#68808d; }
QPushButton:pressed { background:#233440; }
QPushButton:disabled { color:#627581; background:#202e39; border-color:#30404a; }
QPushButton#primary { background:#efa77f; color:#1c2025; border:none; }
QPushButton#primary:hover { background:#ffc6a6; }
QPushButton#navigation { text-align:left; background:transparent; color:#aabac4; border:0; padding:13px 16px; }
QPushButton#navigation:checked { background:#2a3c48; color:#ffffff; border-left:3px solid #f0aa84; }
QPushButton#navigation:hover { background:#223340; color:white; }
QListWidget { background:#14212b; border:1px solid #334550; border-radius:10px; padding:4px; outline:0; }
QListWidget::item { padding:12px; border-radius:7px; color:#c3d0d7; }
QListWidget::item:selected { background:#354c59; color:white; }
QLineEdit, QComboBox, QSpinBox { background:#14222c; border:1px solid #40515d; border-radius:8px; padding:8px; selection-background-color:#5a7786; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #eea680; }
QComboBox QAbstractItemView { background:#1c2b36; color:#f2f5f5; selection-background-color:#405766; }
QSlider::groove:horizontal { height:5px; border-radius:2px; background:#3b505d; }
QSlider::sub-page:horizontal { background:#edaa86; border-radius:2px; }
QSlider::handle:horizontal { width:16px; margin:-7px 0; border-radius:8px; background:#ffd0b5; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:4px; border:1px solid #70828d; background:#14222c; }
QCheckBox::indicator:checked { background:#eea881; border-color:#eea881; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { width:8px; background:transparent; }
QScrollBar::handle:vertical { background:#4c606c; border-radius:4px; min-height:25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""


def label(text, role=None, wrap=False):
    item = QLabel(text)
    if role: item.setObjectName(role)
    item.setWordWrap(wrap)
    return item


def button(text, action, primary=False):
    item = QPushButton(text)
    if primary: item.setObjectName('primary')
    item.clicked.connect(action)
    return item


def card():
    box = QFrame()
    box.setObjectName('card')
    layout = QVBoxLayout(box)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(10)
    return box, layout


def notify_widget():
    """Invia la richiesta di ridisegno solo dopo il salvataggio esplicito."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.PostMessageW.restype = ctypes.c_int
    hwnd = user32.FindWindowW(None, 'Training Desktop Graphic')
    return bool(hwnd and user32.PostMessageW(hwnd, 0x800E, 0, 0))


class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, task, on_done, on_error):
        super().__init__()
        self.task = task
        self.signals = WorkerSignals()
        self.signals.done.connect(on_done)
        self.signals.failed.connect(on_error)

    def run(self):
        try:
            result = self.task()
        except Exception as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.done.emit(result)


class Preview(QWidget):
    """Anteprima simbolica locale: non modifica configurazione né desktop."""
    def __init__(self):
        super().__init__()
        self.appearance = dict(DEFAULT_APPEARANCE)
        self.setMinimumHeight(180)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#172633'))
        painter.drawRoundedRect(bounds, 13, 13)
        painter.save()
        painter.translate(bounds.center().x() + self.appearance.get('offset_x', 0)*self.width()/3840,
                          bounds.center().y() + self.appearance.get('offset_y', 0)*self.height()/2160)
        painter.rotate(self.appearance.get('rotation_degrees', 0))
        scale = min(self.width()/820, self.height()/270) * self.appearance.get('scale_percent', 100)/100
        painter.scale(scale, scale)
        factor = self.appearance.get('opacity_percent', 100)/100
        muted = QColor(96, 116, 129, min(255, round(115*factor)))
        accent = QColor(self.appearance.get('accent', '#ffae85'))
        accent.setAlpha(min(255, round(175*factor)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(muted, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(QRectF(-310, -58, 116, 116))
        painter.setPen(QPen(accent, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(-310, -58, 116, 116), 90*16, -82*16)
        painter.setPen(Qt.PenStyle.NoPen)
        for col in range(24):
            for row in range(7):
                painter.setBrush(accent if (col*7+row)%19 in (0, 1, 2) else muted)
                painter.drawRoundedRect(QRectF(-156+col*19, -62+row*19, 14, 14), 3, 3)
        painter.restore()


class GoalDialog(QDialog):
    def __init__(self, parent, goal=None):
        super().__init__(parent)
        self.setWindowTitle('Modifica obiettivo' if goal else 'Nuovo obiettivo')
        self.setMinimumWidth(420)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(label('Un obiettivo alla volta', 'section'))
        outer.addWidget(label('Scegli se misurare il tempo oppure segnare una volta al giorno.', 'muted', True))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.name = QLineEdit(goal['name'] if goal else '')
        self.name.setPlaceholderText('Es. Studio, lettura, movimento')
        self.kind = QComboBox()
        self.kind.addItem('Cronometro', 'timer')
        self.kind.addItem('Da spuntare ogni giorno', 'check')
        self.target = QSpinBox()
        self.target.setRange(1, 10080)
        self.target.setValue(goal['weekly_target'] if goal else 420)
        self.kind.setCurrentIndex(1 if goal and goal['kind'] == 'check' else 0)
        self.kind.setEnabled(goal is None)
        self.kind.currentIndexChanged.connect(self.update_unit)
        self.update_unit()
        form.addRow('Nome', self.name)
        form.addRow('Come lo misuri', self.kind)
        form.addRow('Obiettivo settimanale', self.target)
        outer.addLayout(form)
        outer.addSpacing(12)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        actions.button(QDialogButtonBox.StandardButton.Save).setText('Salva obiettivo')
        actions.accepted.connect(self.validate)
        actions.rejected.connect(self.reject)
        outer.addWidget(actions)

    def update_unit(self):
        check = self.kind.currentData() == 'check'
        self.target.setMaximum(7 if check else 10080)
        self.target.setSuffix(' giorni' if check else ' min')
        if check and self.target.value() > 7: self.target.setValue(7)

    def validate(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, 'Nome mancante', 'Inserisci un nome per riconoscere l’obiettivo.')
            return
        self.accept()


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Progressi · Centro di controllo')
        self.resize(1160, 790)
        self.setMinimumSize(900, 690)
        self.setStyleSheet(STYLE)
        self.cfg = model.config()
        self.jobs = set()
        self.draft = {**DEFAULT_APPEARANCE, **self.cfg.get('appearance', {})}
        self.applied = dict(self.draft)
        self.build()

    def build(self):
        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar); side.setContentsMargins(18, 32, 18, 24); side.setSpacing(8)
        side.addWidget(label('PROGRESSI', 'eyebrow'))
        title = QLabel('Il tuo spazio'); title.setFont(QFont('Segoe UI', 18, QFont.Weight.DemiBold)); side.addWidget(title)
        side.addWidget(label('Centro di controllo', 'muted'))
        side.addSpacing(32)
        self.nav = []
        self.stack = QStackedWidget()
        for index, text in enumerate(('Obiettivi', 'Aspetto', 'Integrazioni')):
            nav = QPushButton(text); nav.setObjectName('navigation'); nav.setCheckable(True)
            nav.clicked.connect(lambda _checked=False, i=index: self.navigate(i))
            side.addWidget(nav); self.nav.append(nav)
        side.addStretch(1)
        side.addWidget(label('I dati personali rimangono\nsu questo PC.', 'muted'))
        row.addWidget(sidebar)
        content = QWidget()
        content_layout = QVBoxLayout(content); content_layout.setContentsMargins(30, 28, 30, 20); content_layout.setSpacing(10)
        self.page_kicker = label('IL TUO PERCORSO', 'eyebrow')
        self.page_title = label('', 'heading')
        self.page_subtitle = label('', 'muted', True)
        content_layout.addWidget(self.page_kicker); content_layout.addWidget(self.page_title); content_layout.addWidget(self.page_subtitle)
        content_layout.addSpacing(8)
        for builder in (self.build_goals, self.build_appearance, self.build_integrations):
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(0, 2, 8, 5); layout.setSpacing(14)
            builder(layout)
            layout.addStretch(1)
            scroll.setWidget(body)
            self.stack.addWidget(scroll)
        content_layout.addWidget(self.stack, 1)
        content_layout.addWidget(self.appearance_actions)
        self.status = label('Pronto. Le impostazioni sono salvate su questo PC.', 'status')
        content_layout.addWidget(self.status)
        row.addWidget(content, 1)
        self.navigate(0)

    def navigate(self, index):
        pages = [('I tuoi obiettivi', 'Scegli cosa seguire e come registrare i tuoi progressi.'),
                 ('Aspetto del widget', 'Personalizza la grafica sul desktop. Le modifiche si applicano solo quando lo decidi tu.'),
                 ('Integrazioni', 'Scegli una fonte per la griglia annuale e collega i servizi che usi.')]
        self.stack.setCurrentIndex(index)
        self.appearance_actions.setVisible(index == 1)
        for i, nav in enumerate(self.nav): nav.setChecked(i == index)
        self.page_title.setText(pages[index][0]); self.page_subtitle.setText(pages[index][1])

    def set_status(self, text):
        self.status.setText(text)

    def update_config(self, update, message):
        cfg = model.config()
        cfg.update(update)
        model.save(model.CONFIG, cfg)
        self.cfg = cfg
        self.set_status(message)

    def build_goals(self, layout):
        panel, body = card()
        top = QVBoxLayout(); top.addWidget(label('Obiettivi da seguire', 'section'))
        top.addWidget(button('+ Nuovo obiettivo', self.add_goal, True), alignment=Qt.AlignmentFlag.AlignLeft); body.addLayout(top)
        body.addWidget(label('Seleziona un obiettivo; il cerchio sul desktop mostra quello attivo.', 'muted', True))
        self.goal_list = QListWidget(); self.goal_list.setMinimumHeight(160); self.goal_list.setMaximumHeight(240)
        body.addWidget(self.goal_list)
        for group in [[('Mostra nel widget', self.choose_goal), ('Avvia / Ferma', self.toggle_goal)],
                      [('Segna oggi', self.check_goal), ('Modifica', self.edit_goal)], [('Rimuovi', self.remove_goal)]]:
            actions = QHBoxLayout()
            for text, action in group: actions.addWidget(button(text, action))
            actions.addStretch(1); body.addLayout(actions)
        layout.addWidget(panel)
        help_panel, help_body = card()
        help_body.addWidget(label('Come funziona', 'section'))
        help_body.addWidget(label('1  Crea un cronometro o un’attività da spuntare.\n2  Selezionala e scegli “Mostra nel widget”.\n3  Usa il pulsante nel cerchio per avviare, fermare o segnare oggi.', 'muted', True))
        layout.addWidget(help_panel)
        self.refresh_goals()

    def selected_goal(self):
        item = self.goal_list.currentItem()
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((g for g in model.config()['goals'] if g['id'] == identifier), None)

    def refresh_goals(self, selection=None):
        self.cfg = model.config()
        selected = selection or self.cfg.get('selected')
        self.goal_list.clear()
        for goal in self.cfg['goals']:
            active = '  ·  SUL DESKTOP' if goal['id'] == self.cfg.get('selected') else ''
            kind = 'Cronometro' if goal['kind'] == 'timer' else 'Da spuntare'
            target = f"{goal['weekly_target']} min" if goal['kind'] == 'timer' else f"{goal['weekly_target']} giorni"
            item = QListWidgetItem(f"{goal['name']}     {kind}  ·  {target} / settimana{active}")
            item.setData(Qt.ItemDataRole.UserRole, goal['id']); self.goal_list.addItem(item)
            if goal['id'] == selected: self.goal_list.setCurrentItem(item)

    def add_goal(self):
        dialog = GoalDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        goal = model.new_goal(dialog.name.text(), dialog.kind.currentData(), dialog.target.value())
        cfg = model.config(); cfg['goals'].append(goal)
        self.update_config({'goals': cfg['goals']}, 'Obiettivo aggiunto. Seleziona “Mostra nel widget” per usarlo sul desktop.')
        self.refresh_goals(goal['id'])

    def edit_goal(self):
        goal = self.selected_goal()
        if not goal: return
        dialog = GoalDialog(self, goal)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        cfg = model.config()
        for item in cfg['goals']:
            if item['id'] == goal['id']:
                item['name'], item['weekly_target'] = dialog.name.text().strip(), dialog.target.value()
        self.update_config({'goals': cfg['goals']}, 'Obiettivo aggiornato.')
        notify_widget(); self.refresh_goals(goal['id'])

    def remove_goal(self):
        goal = self.selected_goal()
        if not goal: return
        if goal['id'] == 'training':
            QMessageBox.information(self, 'Formazione Linux', 'L’obiettivo della formazione viene conservato.'); return
        if model.active(goal['id']):
            QMessageBox.information(self, 'Cronometro attivo', 'Ferma il cronometro prima di rimuovere questo obiettivo.'); return
        if QMessageBox.question(self, 'Rimuovere l’obiettivo?', 'L’obiettivo sarà rimosso dalla lista. Lo storico locale rimarrà conservato.') != QMessageBox.StandardButton.Yes: return
        cfg = model.config(); cfg['goals'] = [g for g in cfg['goals'] if g['id'] != goal['id']]
        selected = 'training' if cfg.get('selected') == goal['id'] else cfg.get('selected')
        self.update_config({'goals': cfg['goals'], 'selected': selected}, 'Obiettivo rimosso dalla lista.')
        notify_widget(); self.refresh_goals(selected)

    def choose_goal(self):
        goal = self.selected_goal()
        if goal:
            self.update_config({'selected': goal['id']}, f"{goal['name']} è mostrato nel widget.")
            notify_widget(); self.refresh_goals(goal['id'])

    def toggle_goal(self):
        goal = self.selected_goal()
        if not goal or goal['kind'] != 'timer':
            QMessageBox.information(self, 'Cronometro', 'Seleziona un obiettivo di tipo cronometro.'); return
        try:
            model.toggle_timer(goal['id'])
            self.set_status('Cronometro avviato.' if model.active(goal['id']) else 'Cronometro fermato e tempo salvato.')
            notify_widget()
        except Exception as error: QMessageBox.warning(self, 'Cronometro', str(error))

    def check_goal(self):
        goal = self.selected_goal()
        if not goal or goal['kind'] != 'check':
            QMessageBox.information(self, 'Attività', 'Seleziona un obiettivo da spuntare.'); return
        try:
            model.toggle_check(goal['id']); self.set_status('Stato di oggi aggiornato.'); notify_widget()
        except Exception as error: QMessageBox.warning(self, 'Attività', str(error))

    def make_slider(self, name, key, low, high, suffix, parent):
        row = QVBoxLayout(); row.setSpacing(4)
        top = QHBoxLayout(); top.addWidget(label(name)); value = label('', 'muted'); top.addStretch(1); top.addWidget(value)
        row.addLayout(top)
        slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(low, high); slider.setValue(int(self.draft[key]))
        def change(number):
            self.draft[key] = number; value.setText(f'{number}{suffix}'); self.update_preview()
        slider.valueChanged.connect(change); value.setText(f'{slider.value()}{suffix}')
        self.slider_value_labels[key] = (value, suffix)
        row.addWidget(slider); parent.addLayout(row)
        return slider

    def build_appearance(self, layout):
        self.slider_value_labels = {}
        preview_card, preview_body = card()
        line = QHBoxLayout(); line.addWidget(label('Anteprima', 'section')); line.addStretch(1)
        line.addWidget(label('esempio · non modifica il desktop', 'muted')); preview_body.addLayout(line)
        self.preview = Preview(); preview_body.addWidget(self.preview); layout.addWidget(preview_card)
        panel, body = card()
        body.addWidget(label('Personalizza il desktop', 'section'))
        self.size_slider = self.make_slider('Dimensione', 'scale_percent', 50, 140, '%', body)
        self.opacity_slider = self.make_slider('Intensità e trasparenza', 'opacity_percent', 20, 150, '%', body)
        self.rotation_slider = self.make_slider('Inclinazione', 'rotation_degrees', -180, 180, '°', body)
        angle_row = QVBoxLayout()
        angle_row.addWidget(button('Scegli due punti · Sperimentale', self.select_angle))
        angle_row.addWidget(label('Il primo e il secondo punto definiscono la direzione della linea.', 'muted', True))
        body.addLayout(angle_row)
        settings = QGridLayout(); settings.setHorizontalSpacing(12); settings.setVerticalSpacing(10)
        color_col = QVBoxLayout(); color_col.addWidget(label('Colore attività', 'muted'))
        self.color_button = button('Scegli colore', self.choose_color); color_col.addWidget(self.color_button); settings.addLayout(color_col, 0, 0)
        monitor_col = QVBoxLayout(); monitor_col.addWidget(label('Schermo · multi-monitor sperimentale', 'muted', True))
        self.monitor_combo = QComboBox()
        self.monitor_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.monitor_combo.setMinimumContentsLength(10)
        monitors = displays.all_monitors()
        configured = self.draft.get('monitor', '')
        for idx, monitor in enumerate(monitors):
            r = monitor['rect']; desc = f"Schermo {idx+1} · {r[2]-r[0]}×{r[3]-r[1]}" + (' · principale' if monitor['primary'] else '')
            self.monitor_combo.addItem(desc, monitor['id'])
            if monitor['id'] == configured or not configured and monitor['primary']: self.monitor_combo.setCurrentIndex(idx)
        self.monitor_combo.currentIndexChanged.connect(self.monitor_changed)
        self.monitor_combo.setMinimumWidth(0)
        monitor_col.addWidget(self.monitor_combo); settings.addLayout(monitor_col, 0, 1)
        for index, (label_text, key) in enumerate([('Spostamento X', 'offset_x'), ('Spostamento Y', 'offset_y')]):
            col = QVBoxLayout(); col.addWidget(label(label_text, 'muted'))
            spin = QSpinBox(); spin.setRange(-10000, 10000); spin.setSingleStep(25); spin.setSuffix(' px'); spin.setValue(self.draft[key])
            spin.valueChanged.connect(lambda val, k=key: self.change_draft(k, val))
            col.addWidget(spin); settings.addLayout(col, 1, index)
            if key == 'offset_x': self.offset_x = spin
            else: self.offset_y = spin
        body.addLayout(settings)
        body.addWidget(label('Gli spostamenti sono relativi al centro dello schermo: X positivo va a destra, Y positivo verso il basso.', 'muted', True))
        drag_row = QVBoxLayout()
        drag_row.addWidget(button('Trascina anteprima · Sperimentale', self.drag_preview))
        drag_row.addWidget(label('Il clic si sblocca solo durante il trascinamento.', 'muted', True))
        body.addLayout(drag_row)
        self.manual = QCheckBox('Abilita il timer manuale nel cerchio')
        self.manual.setChecked(self.draft.get('manual_timer_enabled', True))
        self.manual.toggled.connect(lambda value: self.change_draft('manual_timer_enabled', value))
        body.addWidget(self.manual)
        body.addWidget(label('Se disattivato, il pulsante del cronometro scompare. Un timer già avviato continua fino a quando lo fermi.', 'muted', True))
        self.appearance_actions = QWidget()
        action_row = QHBoxLayout(self.appearance_actions)
        action_row.setContentsMargins(0, 8, 0, 0)
        self.apply_button = button('Applica al desktop', self.apply_appearance, True)
        self.reset_button = button('Annulla modifiche', self.reset_draft)
        action_row.addWidget(self.apply_button); action_row.addWidget(self.reset_button); action_row.addStretch(1)
        self.draft_status = label('', 'muted'); action_row.addWidget(self.draft_status)
        layout.addWidget(panel)
        presets_card, presets = card()
        presets.addWidget(label('Preset di aspetto · Sperimentale', 'section'))
        presets.addWidget(label('Salva una combinazione di schermo, posizione, inclinazione e stile. Caricarla non modifica il desktop finché non premi Applica.', 'muted', True))
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(button('Carica', self.load_preset))
        presets.addLayout(preset_row)
        preset_actions = QHBoxLayout()
        preset_actions.addWidget(button('Salva preset', self.save_preset))
        preset_actions.addWidget(button('Elimina', self.delete_preset))
        preset_actions.addStretch(1); presets.addLayout(preset_actions); layout.addWidget(presets_card)
        self.refresh_presets()
        self.update_preview()

    def change_draft(self, key, value):
        self.draft[key] = value
        self.update_preview()

    def monitor_changed(self):
        self.change_draft('monitor', self.monitor_combo.currentData() or '')

    def update_preview(self):
        if not hasattr(self, 'preview'): return
        self.preview.appearance = dict(self.draft); self.preview.update()
        if hasattr(self, 'draft_status'):
            changed = self.draft != self.applied
            self.draft_status.setText('Modifiche non applicate' if changed else 'Nessuna modifica in sospeso')
            self.apply_button.setEnabled(changed); self.reset_button.setEnabled(changed)
        if hasattr(self, 'color_button'):
            self.color_button.setText(self.draft['accent'].upper())

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.draft['accent']), self, 'Colore del widget')
        if color.isValid(): self.change_draft('accent', color.name())

    def reset_draft(self):
        self.draft = dict(self.applied)
        self.show_draft_values()

    def show_draft_values(self):
        for control, key in [(self.size_slider, 'scale_percent'), (self.opacity_slider, 'opacity_percent'),
                             (self.rotation_slider, 'rotation_degrees'), (self.offset_x, 'offset_x'), (self.offset_y, 'offset_y')]:
            control.blockSignals(True); control.setValue(self.draft[key]); control.blockSignals(False)
            if key in self.slider_value_labels:
                text_label, suffix = self.slider_value_labels[key]
                text_label.setText(f'{control.value()}{suffix}')
        self.manual.blockSignals(True); self.manual.setChecked(self.draft['manual_timer_enabled']); self.manual.blockSignals(False)
        index = self.monitor_combo.findData(self.draft['monitor'])
        if index < 0:
            monitors = displays.all_monitors(); primary = displays.choose(monitors, '')
            index = self.monitor_combo.findData(primary['id'])
        self.monitor_combo.blockSignals(True); self.monitor_combo.setCurrentIndex(max(0, index)); self.monitor_combo.blockSignals(False)
        self.update_preview()

    def target_screen(self):
        monitors = displays.all_monitors()
        identifier = self.draft.get('monitor') or self.monitor_combo.currentData() or ''
        monitor = displays.choose(monitors, identifier)
        return selection.screen_for_monitor(QApplication.screens(), monitor), monitor

    def begin_selection(self, mode, ghost=None):
        overlay = None
        try:
            screen, monitor = self.target_screen()
            overlay = selection.DesktopSelection(screen, mode, monitor['rect'], self.draft, ghost)
            self.selection_overlay = overlay
            overlay.angle_chosen.connect(self.angle_from_points)
            overlay.position_chosen.connect(self.position_from_drag)
            overlay.finished.connect(self.selection_finished)
            self.hide()
            overlay.show_selection()
        except Exception as error:
            if overlay is not None:
                overlay.close()
                self.selection_overlay = None
            self.showNormal()
            QMessageBox.warning(self, 'Selezione sul desktop', str(error))

    def select_angle(self):
        self.begin_selection('angle')

    def drag_preview(self):
        try:
            cfg = model.config()
            cfg['appearance'] = dict(self.draft)
            import desktop
            image = desktop.create_image(config_override=cfg)
            buffer = io.BytesIO(); image.save(buffer, format='PNG')
            ghost = QImage.fromData(buffer.getvalue(), 'PNG')
            if ghost.isNull(): raise ValueError('Impossibile creare l’anteprima del widget.')
            self.begin_selection('move', ghost)
        except Exception as error:
            QMessageBox.warning(self, 'Anteprima', str(error))

    def selection_finished(self):
        self.showNormal(); self.raise_(); self.activateWindow()
        self.selection_overlay = None

    def angle_from_points(self, angle):
        self.rotation_slider.setValue(angle)
        self.set_status(f'Inclinazione {angle}° in anteprima. Premi Applica al desktop per confermare.')

    def position_from_drag(self, x, y):
        self.offset_x.setValue(x); self.offset_y.setValue(y)
        self.set_status('Posizione aggiornata in anteprima. Premi Applica al desktop per confermare.')

    def read_presets(self):
        data = model.read(PRESETS, {'version': 1, 'presets': {}})
        return data if isinstance(data, dict) and isinstance(data.get('presets'), dict) else {'version': 1, 'presets': {}}

    def refresh_presets(self, selected=None):
        names = sorted(self.read_presets()['presets'], key=str.casefold)
        self.preset_combo.clear(); self.preset_combo.addItem('Seleziona un preset', None)
        for name in names: self.preset_combo.addItem(name, name)
        index = self.preset_combo.findData(selected)
        self.preset_combo.setCurrentIndex(max(0, index))

    def save_preset(self):
        name, ok = QInputDialog.getText(self, 'Salva preset', 'Nome del preset:')
        name = name.strip()
        if not ok: return
        if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
            QMessageBox.warning(self, 'Nome non valido', 'Scegli un nome tra 1 e 80 caratteri, senza caratteri di controllo.'); return
        data = self.read_presets()
        if name in data['presets'] and QMessageBox.question(self, 'Sostituire il preset?', f'Esiste già un preset chiamato “{name}”. Vuoi sostituirlo?') != QMessageBox.StandardButton.Yes:
            return
        data['presets'][name] = dict(self.draft)
        model.save(PRESETS, data); self.refresh_presets(name)
        self.set_status(f'Preset “{name}” salvato. Il desktop non è stato modificato.')

    def load_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            QMessageBox.information(self, 'Preset', 'Seleziona un preset da caricare.'); return
        saved = self.read_presets()['presets'].get(name)
        if not isinstance(saved, dict):
            QMessageBox.warning(self, 'Preset', 'Il preset non è più disponibile.'); return
        self.draft = {**DEFAULT_APPEARANCE, **saved}
        self.show_draft_values()
        self.set_status(f'Preset “{name}” caricato in anteprima. Premi Applica al desktop per confermare.')

    def delete_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            QMessageBox.information(self, 'Preset', 'Seleziona un preset da eliminare.'); return
        if QMessageBox.question(self, 'Eliminare il preset?', f'Eliminare il preset “{name}”?') != QMessageBox.StandardButton.Yes: return
        data = self.read_presets(); data['presets'].pop(name, None)
        model.save(PRESETS, data); self.refresh_presets()
        self.set_status('Preset eliminato. L’aspetto applicato non è cambiato.')

    def apply_appearance(self):
        self.update_config({'appearance': dict(self.draft)}, 'Aspetto applicato al desktop.')
        self.applied = dict(self.draft)
        if not notify_widget(): self.set_status('Aspetto salvato: sarà visibile al prossimo avvio del widget.')
        self.update_preview()

    def build_integrations(self, layout):
        panel, body = card()
        body.addWidget(label('La tua griglia annuale', 'section'))
        body.addWidget(label('La griglia mensile resta legata all’obiettivo personale. Scegli quale fonte usare per l’anno.', 'muted', True))
        row = QHBoxLayout(); row.addWidget(label('Fonte'))
        self.source = QComboBox()
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(10)
        for text, key in SOURCES.items(): self.source.addItem(text, key)
        cfg = model.config(); selected = cfg.get('annual_source', cfg.get('github', {}).get('year_mode', 'personal'))
        self.source.setCurrentIndex(max(0, self.source.findData(selected)))
        row.addWidget(self.source, 1); row.addWidget(button('Usa questa fonte', self.save_source)); body.addLayout(row); layout.addWidget(panel)
        github, git = card(); git.addWidget(label('GitHub · Sperimentale', 'section'))
        git.addWidget(label('Mostra i contributi visibili pubblicamente. Non serve un token; il formato della pagina potrebbe cambiare.', 'muted', True))
        row = QHBoxLayout(); self.github_user = QLineEdit(cfg.get('github', {}).get('username', '')); self.github_user.setPlaceholderText('Nome utente GitHub')
        self.github_enabled = QCheckBox('Abilita GitHub'); self.github_enabled.setChecked(cfg.get('github', {}).get('enabled', False))
        row.addWidget(self.github_user, 1); row.addWidget(self.github_enabled); git.addLayout(row)
        last = providers.github_cached(self.github_user.text())
        self.github_status = label('Ultimo aggiornamento: '+last['fetched_at'] if last else 'Non ancora sincronizzato.', 'muted', True)
        git.addWidget(self.github_status)
        row = QHBoxLayout(); row.addWidget(button('Salva GitHub', self.save_github)); row.addWidget(button('Sincronizza ora', self.sync_github, True)); row.addStretch(1); git.addLayout(row)
        layout.addWidget(github)
        other, other_body = card(); other_body.addWidget(label('Altri servizi · Sperimentali', 'section'))
        other_body.addWidget(label('Google Calendar, Outlook Calendar, Todoist, Notion e Strava. Verificati con dati simulati; non ancora con account reali.', 'muted', True))
        row = QHBoxLayout(); self.service = QComboBox()
        self.service.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.service.setMinimumContentsLength(10)
        for key, (name, _) in providers.SERVICES.items(): self.service.addItem(name, key)
        row.addWidget(self.service, 1); row.addWidget(button('Configura servizio', self.external_dialog)); other_body.addLayout(row)
        layout.addWidget(other)

    def save_source(self):
        source = self.source.currentData(); cfg = model.config()
        if source == 'github' and not cfg.get('github', {}).get('enabled'):
            QMessageBox.information(self, 'GitHub non attivo', 'Abilita e salva GitHub prima di scegliere questa fonte.'); return
        if source in providers.SERVICES and providers.external_cached(source, options=cfg.get('integrations', {}).get(source, {})) is None:
            QMessageBox.information(self, 'Collega prima il servizio', 'Configura e sincronizza il servizio prima di mostrarlo nella griglia.'); return
        self.update_config({'annual_source': source}, 'Fonte della griglia annuale aggiornata.'); notify_widget()

    def save_github(self):
        name, enabled = self.github_user.text().strip(), self.github_enabled.isChecked()
        if enabled and not providers.USERNAME.fullmatch(name):
            QMessageBox.warning(self, 'Nome non valido', 'Inserisci un nome utente GitHub valido.'); return False
        cfg = model.config(); git = dict(cfg.get('github', {})); git.update({'username': name, 'enabled': enabled})
        self.update_config({'github': git}, 'Impostazioni GitHub salvate.'); notify_widget()
        return True

    def start_job(self, func, success, error):
        job = Worker(func, success, error); self.jobs.add(job)
        job.signals.done.connect(lambda _value, item=job: self.jobs.discard(item))
        job.signals.failed.connect(lambda _value, item=job: self.jobs.discard(item))
        QThreadPool.globalInstance().start(job)

    def sync_github(self):
        if not self.save_github() or not self.github_enabled.isChecked(): return
        username = self.github_user.text().strip(); self.github_status.setText('Sincronizzazione in corso…')
        def success(result):
            self.github_status.setText(f"Aggiornato: {result['fetched_at']} · {len(result['levels'])} giorni.")
            self.set_status('GitHub aggiornato.'); notify_widget()
        self.start_job(lambda: providers.github_fetch(username), success, lambda error: self.github_status.setText(f'Non sincronizzato: {error}'))

    def external_dialog(self):
        key = self.service.currentData()
        dialog = IntegrationDialog(self, key)
        dialog.exec()


class IntegrationDialog(QDialog):
    def __init__(self, parent, key):
        super().__init__(parent)
        self.key = key
        self.setWindowTitle(providers.SERVICES[key][0]); self.setMinimumWidth(600)
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 24, 24, 24); outer.setSpacing(12)
        outer.addWidget(label(providers.SERVICES[key][0] + ' · Sperimentale', 'section'))
        descriptions = {
            'google': 'Conta gli eventi, anche futuri. Collega Google con un client OAuth desktop oppure inserisci un token in sola lettura.',
            'outlook': 'Conta gli eventi, anche futuri. Serve un token Microsoft Graph con Calendars.ReadBasic.',
            'todoist': 'Conta i task completati per giorno. Serve un token Todoist.',
            'notion': 'Conta le pagine con una data nella proprietà indicata; la data non implica necessariamente completamento.',
            'strava': 'Conta le attività disponibili al token. Serve il permesso activity:read; il token può scadere.'}
        outer.addWidget(label(descriptions[key], 'muted', True))
        cfg = model.config(); options = cfg.get('integrations', {}).get(key, {})
        form = QFormLayout(); form.setVerticalSpacing(14)
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('Lascia vuoto per mantenere la credenziale salvata')
        form.addRow('Token', self.token)
        self.identifier = QLineEdit(options.get('data_source_id', options.get('calendar_id', '')))
        self.prop = QLineEdit(options.get('date_property', ''))
        if key == 'google':
            self.identifier.setPlaceholderText('primary')
            form.addRow('ID calendario', self.identifier)
        elif key == 'notion':
            form.addRow('ID data source', self.identifier)
            form.addRow('Proprietà data', self.prop)
        outer.addLayout(form)
        outer.addWidget(label('Non scrivere credenziali in chat. Se salvate qui, sono protette per il tuo utente Windows.', 'muted', True))
        cache = providers.external_cached(key, options=options)
        self.info = label('Ultima sincronizzazione: '+cache['fetched_at'] if cache else 'Nessuna sincronizzazione riuscita per questa connessione.', 'muted', True)
        outer.addWidget(self.info)
        row = QHBoxLayout(); row.addWidget(button('Salva e sincronizza', self.sync, True))
        if key == 'google':
            row.addWidget(button('Accedi con Google', self.google_login))
            row.addWidget(button('Guida', self.open_guide))
        row.addWidget(button('Scollega', self.disconnect)); row.addStretch(1); outer.addLayout(row)
        outer.addWidget(button('Chiudi', self.accept))
        self.jobs = set()

    def start_job(self, func, success):
        job = Worker(func, success, lambda error: self.info.setText('Operazione non riuscita: ' + error))
        self.jobs.add(job)
        job.signals.done.connect(lambda _v, item=job: self.jobs.discard(item))
        job.signals.failed.connect(lambda _v, item=job: self.jobs.discard(item))
        QThreadPool.globalInstance().start(job)

    def sync(self):
        key = self.key; secret = self.token.text().strip(); cfg = model.config()
        old = cfg.get('integrations', {}).get(key, {})
        try:
            if secret:
                credentials.put(key, secret)
                if key == 'google': credentials.delete('google_oauth')
                self.token.clear()
            has_oauth = key == 'google' and bool(credentials.get('google_oauth'))
            if not has_oauth and not credentials.get(key): raise ValueError('Inserisci una credenziale o usa l’accesso Google.')
            options = {'calendar_id': self.identifier.text().strip() or 'primary'} if key == 'google' else (
                {'data_source_id': self.identifier.text().strip(), 'date_property': self.prop.text().strip()} if key == 'notion' else {})
            options['connection_id'] = uuid.uuid4().hex if secret else old.get('connection_id', uuid.uuid4().hex)
            cfg.setdefault('integrations', {})[key] = options; model.save(model.CONFIG, cfg)
        except Exception as error:
            QMessageBox.warning(self, 'Configurazione', str(error)); return
        self.info.setText('Sincronizzazione in corso…')
        def task():
            token = google_oauth.access_token() if has_oauth else credentials.get(key)
            return providers.external_fetch(key, token, options)
        def success(data):
            self.info.setText(f"Sincronizzato: {sum(data['counts'].values())} elementi nell’anno. Ora puoi scegliere questa fonte.")
            notify_widget()
        self.start_job(task, success)

    def disconnect(self):
        key = self.key; credentials.delete(key)
        if key == 'google': credentials.delete('google_oauth')
        cfg = model.config(); cfg.get('integrations', {}).pop(key, None)
        if cfg.get('annual_source') == key: cfg['annual_source'] = 'personal'
        model.save(model.CONFIG, cfg); self.info.setText('Credenziale rimossa. La cache aggregata è conservata.'); notify_widget()

    def google_login(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Seleziona il client OAuth desktop Google', '', 'File JSON (*.json)')
        if not path: return
        self.info.setText('Completa l’autorizzazione nel browser, poi torna qui.')
        def task():
            google_oauth.connect(path)
            cfg = model.config(); cfg.setdefault('integrations', {}).setdefault('google', {})['connection_id'] = uuid.uuid4().hex
            model.save(model.CONFIG, cfg)
        self.start_job(task, lambda _v: self.info.setText('Google collegato. Premi “Salva e sincronizza”.'))

    def open_guide(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE / 'GOOGLE-CALENDAR.md')))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Launcher(); window.show()
    sys.exit(app.exec())
