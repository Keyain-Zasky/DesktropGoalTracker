import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
import model
import displays
import selection


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.module = runpy.run_path(str(Path(__file__).with_name('launcher.pyw')))
        cls.desktop = runpy.run_path(str(Path(__file__).with_name('desktop.pyw')))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'config.json'
        self.patch_config = patch.object(model, 'CONFIG', self.path)
        self.patch_config.start()
        self.monitors = [{'id':'display-1', 'rect':(0,0,3840,2160), 'primary':True},
                         {'id':'display-2', 'rect':(-2560,0,0,1440), 'primary':False}]
        self.patch_monitors = patch.object(displays, 'all_monitors', return_value=self.monitors)
        self.patch_monitors.start()
        model.save(model.CONFIG, model.config())
        self.win = self.module['Launcher']()

    def tearDown(self):
        self.win.close()
        self.patch_monitors.stop(); self.patch_config.stop(); self.temp.cleanup()

    def test_appearance_draft_only_written_on_apply(self):
        before = model.config()['appearance'].copy()
        self.win.size_slider.setValue(75)
        self.win.rotation_slider.setValue(35)
        self.win.offset_x.setValue(125)
        self.win.monitor_combo.setCurrentIndex(1)
        self.win.manual.setChecked(False)
        self.win.opacity_slider.setValue(55)
        self.win.theme_combo.setCurrentIndex(1)
        self.win.shadow_check.setChecked(True)
        self.assertEqual(model.config()['appearance'], before)
        # Salvataggi in altre sezioni non devono includere l'anteprima.
        self.win.update_config({'selected': 'training'}, 'ok')
        self.assertEqual(model.config()['appearance'], before)
        notice = Mock(return_value=True)
        with patch.dict(self.module['Launcher'].apply_appearance.__globals__, {'notify_widget': notice}):
            self.win.apply_appearance()
        notice.assert_called_once_with()
        actual = model.config()['appearance']
        self.assertEqual(actual['scale_percent'], 75)
        self.assertEqual(actual['rotation_degrees'], 35)
        self.assertEqual(actual['offset_x'], 125)
        self.assertEqual(actual['monitor'], 'display-2')
        self.assertFalse(actual['manual_timer_enabled'])
        self.assertEqual(actual['opacity_percent'], 55)
        self.assertEqual(actual['theme'], 'light')
        self.assertTrue(actual['shadow_enabled'])

    def test_discard_restores_draft_without_writing(self):
        before = model.config()['appearance'].copy()
        self.win.rotation_slider.setValue(-50)
        self.win.manual.setChecked(False)
        self.win.reset_draft()
        self.assertEqual(model.config()['appearance'], before)
        self.assertEqual(self.win.rotation_slider.value(), 0)
        self.assertEqual(self.win.slider_value_labels['rotation_degrees'][0].text(), '0°')
        self.assertTrue(self.win.manual.isChecked())

    def test_rotated_layout_and_manual_button(self):
        layout = self.desktop['layout']
        appearance = {'scale_percent':100, 'rotation_degrees':0, 'offset_x':0, 'offset_y':0}
        x, y, bx, by, size = layout((2650,450), (0,0,3840,2160), appearance)
        self.assertEqual((x,y,bx,by,size), (595,855,735,1030,100))
        appearance.update(rotation_degrees=90, offset_x=100, offset_y=-50)
        x, y, bx, by, size = layout((450,2650), (-2560,0,0,1440), appearance)
        self.assertEqual((x,y), (-1280-225+100, 720-1325-50))
        self.assertEqual((bx+size//2, by+size//2), (x+225, y+1325-1135))
        enabled = self.desktop['button_enabled']
        self.assertFalse(enabled({'manual_timer_enabled':False}, {'kind':'timer'}))
        self.assertTrue(enabled({'manual_timer_enabled':False}, {'kind':'check'}))

    def test_rotation_changes_rendered_bounds(self):
        desktop = self.desktop
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.multiple(model, CONFIG=root/'config.json', ENTRIES=root/'entries.json',
                                TRAINING=root/'training.json', TRAINING_SESSIONS=root/'sessions.json',
                                TRAINING_ACTIVE=root/'active.json'):
                cfg = model.config()
                cfg['appearance'].update({'scale_percent':100, 'rotation_degrees':90})
                model.save(model.CONFIG, cfg)
                image = desktop['create_image']()
                self.assertEqual(image.size, (450, 2650))

    def test_two_points_change_draft_not_applied(self):
        original = model.config()['appearance'].copy()
        self.win.angle_from_points(selection.angle_degrees((10, 10), (110, 110)))
        self.assertEqual(self.win.rotation_slider.value(), 45)
        self.assertEqual(model.config()['appearance'], original)
        self.assertEqual(selection.angle_degrees((100, 100), (0, 100)), 180)
        self.assertEqual(selection.angle_degrees((0, 100), (100, 0)), -45)
        with self.assertRaises(ValueError): selection.angle_degrees((10,10), (11,11))

    def test_two_point_overlay_and_cancel(self):
        screen = self.app.primaryScreen()
        rect = screen.geometry()
        overlay = selection.DesktopSelection(screen, 'angle', (0, 0, rect.width(), rect.height()), {})
        results = []; finished = []
        overlay.angle_chosen.connect(results.append)
        overlay.finished.connect(lambda: finished.append(True))
        overlay.show(); self.app.processEvents()
        QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(120, 120))
        self.assertEqual(results, [45]); self.assertEqual(finished, [True])
        second = selection.DesktopSelection(screen, 'angle', (0, 0, rect.width(), rect.height()), {})
        cancelled = []; second.angle_chosen.connect(cancelled.append)
        second.show(); self.app.processEvents()
        QTest.keyClick(second, Qt.Key.Key_Escape)
        self.assertEqual(cancelled, [])

    def test_angle_overlay_rejects_same_point_and_right_click_cancels(self):
        screen = self.app.primaryScreen(); rect = screen.geometry()
        overlay = selection.DesktopSelection(screen, 'angle', (0, 0, rect.width(), rect.height()), {})
        results = []; finished = []
        overlay.angle_chosen.connect(results.append)
        overlay.finished.connect(lambda: finished.append(True))
        overlay.show(); self.app.processEvents()
        QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
        QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(41, 41))
        self.assertEqual(results, [])
        self.assertIn('secondo punto', overlay.message)
        QTest.mouseClick(overlay, Qt.MouseButton.RightButton, pos=QPoint(41, 41))
        self.assertEqual(results, []); self.assertEqual(finished, [True])

    def test_drag_updates_only_draft_with_physical_scaling(self):
        original = model.config()['appearance'].copy()
        screen = self.app.primaryScreen(); rect = screen.geometry()
        image = QImage(200, 80, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.white)
        overlay = selection.DesktopSelection(screen, 'move', (0, 0, rect.width()*2, rect.height()*2), {}, image)
        results = []; overlay.position_chosen.connect(lambda x,y: results.append((x,y)))
        overlay.show(); self.app.processEvents()
        start = overlay.ghost_rect().center().toPoint()
        end = start + QPoint(40, 20)
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(overlay, end)
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(results, [(80,40)])
        self.win.position_from_drag(*results[0])
        self.assertEqual((self.win.offset_x.value(), self.win.offset_y.value()), (80,40))
        self.assertEqual(model.config()['appearance'], original)

    def test_mouse_editor_moves_resizes_and_confirms_draft(self):
        original = model.config()['appearance'].copy()
        screen = self.app.primaryScreen(); rect = screen.geometry()
        image = QImage(200, 80, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.white)
        overlay = selection.DesktopSelection(screen, 'edit', (0, 0, rect.width(), rect.height()), {'scale_percent': 100}, image)
        results = []; overlay.edit_chosen.connect(lambda *v: results.append(v))
        overlay.show(); self.app.processEvents()
        start = overlay.ghost_rect().center().toPoint(); end = start + QPoint(45, 20)
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(overlay, end); QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=end)
        corner = overlay.ghost_rect().bottomRight().toPoint()
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=corner)
        QTest.mouseMove(overlay, corner + QPoint(30, 12)); QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=corner + QPoint(30, 12))
        QTest.keyClick(overlay, Qt.Key.Key_Return)
        self.assertEqual(len(results), 1); self.assertEqual(results[0][:2], (45,20))
        self.assertGreater(results[0][2], 100)
        self.win.appearance_from_editor(*results[0])
        self.assertEqual(model.config()['appearance'], original)

    def test_multiple_presets_do_not_apply_until_button(self):
        path = Path(self.temp.name)/'presets.json'
        namespace = self.module['Launcher'].read_presets.__globals__
        original = model.config()['appearance'].copy()
        with patch.dict(namespace, {'PRESETS': path}), \
             patch('PySide6.QtWidgets.QInputDialog.getText', side_effect=[('Studio', True), ('Sera', True)]):
            self.win.rotation_slider.setValue(20); self.win.save_preset()
            self.win.rotation_slider.setValue(-15); self.win.save_preset()
            self.assertEqual(set(model.read(path, {})['presets']), {'Studio','Sera'})
            self.win.preset_combo.setCurrentIndex(self.win.preset_combo.findData('Studio'))
            self.win.load_preset()
            self.assertEqual(self.win.rotation_slider.value(), 20)
            self.assertEqual(self.win.slider_value_labels['rotation_degrees'][0].text(), '20°')
            self.assertEqual(model.config()['appearance'], original)

    def test_experimental_features_are_identified_in_ui(self):
        texts = [item.text() for item in self.win.findChildren(QLabel)]
        texts += [item.text() for item in self.win.findChildren(QPushButton)]
        self.assertTrue(any('GitHub' in text and 'Sperimentale' in text for text in texts))
        self.assertTrue(any('Altri servizi' in text and 'Sperimentali' in text for text in texts))
        self.assertTrue(any('due punti' in text and 'Sperimentale' in text for text in texts))
        self.assertTrue(any('Trascina' in text and 'Sperimentale' in text for text in texts))
        self.assertTrue(any('Preset' in text and 'Sperimentale' in text for text in texts))

    def test_selection_setup_failure_preserves_saved_appearance(self):
        original = model.config()['appearance'].copy()
        with patch.object(self.win, 'target_screen', side_effect=RuntimeError('test failure')), \
             patch.object(self.module['QMessageBox'], 'warning') as warning:
            self.win.begin_selection('angle')
        warning.assert_called_once()
        self.assertEqual(model.config()['appearance'], original)

    def test_narrow_window_does_not_require_horizontal_scrolling(self):
        self.win.resize(900, 690)
        self.win.show()
        for page in range(3):
            self.win.navigate(page); self.app.processEvents()
            with self.subTest(page=page):
                self.assertLessEqual(self.win.stack.currentWidget().horizontalScrollBar().maximum(), 2)


if __name__ == '__main__':
    unittest.main()
