import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import entry


class MigrationTests(unittest.TestCase):
    def test_import_copies_only_known_data_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'old'; target=root/'new'; source.mkdir(); target.mkdir()
            (source/'progressi.json').write_text('{"days":{"2026-11-11":60}}',encoding='utf-8')
            (source/'sessioni.json').write_text('{"sessions":[]}',encoding='utf-8')
            (source/'credenziali.json').write_text('{"encrypted":"sample"}',encoding='utf-8')
            (source/'unrelated.txt').write_text('not imported',encoding='utf-8')
            (target/'progressi.json').write_text('{"existing":true}',encoding='utf-8')
            copied=entry.migrate_legacy(source,target)
            self.assertEqual(set(copied), {'sessioni.json','credenziali.json'})
            self.assertTrue(json.loads((target/'progressi.json').read_text())['existing'])
            self.assertTrue((source/'credenziali.json').exists())
            self.assertFalse((target/'unrelated.txt').exists())
            self.assertEqual(entry.migrate_legacy(source,target),[])

    def test_interrupted_import_does_not_leave_partial_file_or_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'old'; target=root/'new'; source.mkdir()
            (source/'progressi.json').write_text('original',encoding='utf-8')
            with patch.object(entry.shutil,'copyfileobj',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError): entry.migrate_legacy(source,target)
            self.assertEqual((source/'progressi.json').read_text(),'original')
            self.assertFalse((target/'progressi.json').exists())
            self.assertFalse((target/'migrazione.json').exists())
            self.assertFalse(list(target.glob('*.tmp')))
            self.assertEqual(entry.migrate_legacy(source,target),['progressi.json'])


if __name__ == '__main__':
    unittest.main()
