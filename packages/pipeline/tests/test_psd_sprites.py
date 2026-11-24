import importlib
import sys
import types
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

fake_psd_tools = types.ModuleType('psd_tools')
fake_psd_tools.PSDImage = object
sys.modules.setdefault('psd_tools', fake_psd_tools)

from support import import_pipeline

psd_sprites = import_pipeline('narration.psd_sprites')


class Node:
    def __init__(self, name, children=(), *, group=True, visible=True):
        self.name = name
        self.children = list(children)
        self.group = group
        self.visible = visible

    def __iter__(self):
        return iter(self.children)

    def is_group(self):
        return self.group


class PsdSpriteSelectionTests(unittest.TestCase):
    def setUp(self):
        self.pupil_a = Node('*正面', group=False)
        self.pupil_b = Node('*横', group=False)
        self.pupils = Node('*黒目', [self.pupil_a, self.pupil_b])
        self.eye_open = Node('*目セット', [self.pupils])
        self.eye_closed = Node('*閉じ目')
        self.eyes = Node('目', [self.eye_open, self.eye_closed])
        self.sweat = Node('汗', group=False, visible=False)
        self.symbols = Node('記号など', [self.sweat])
        self.psd = Node('root', [self.eyes, self.symbols])

    def test_bare_removes_psdtool_prefix_and_whitespace(self):
        self.assertEqual(psd_sprites.bare(' *! 名前 '), '名前')

    def test_find_walks_group_paths_and_rejects_missing_groups(self):
        self.assertIs(psd_sprites.find(self.psd, '目/目セット/黒目'), self.pupils)
        self.assertIs(psd_sprites.find(self.psd, '/'), self.psd)
        with self.assertRaisesRegex(KeyError, 'no group'):
            psd_sprites.find(self.psd, '目/存在しない')

    def test_choose_shows_one_starred_sibling(self):
        psd_sprites.choose(self.eyes, '閉じ目')
        self.assertFalse(self.eye_open.visible)
        self.assertTrue(self.eye_closed.visible)
        with self.assertRaisesRegex(KeyError, 'not a choice'):
            psd_sprites.choose(self.eyes, '不明')

    def test_toggle_changes_layer_and_rejects_unknown_layer(self):
        psd_sprites.toggle(self.psd, '記号など/汗', True)
        self.assertTrue(self.sweat.visible)
        with self.assertRaisesRegex(KeyError, 'no layer'):
            psd_sprites.toggle(self.psd, '記号など/涙', True)

    def test_apply_combines_selection_and_visibility_changes(self):
        psd_sprites.apply(self.psd, {'目': '閉じ目'}, on=['記号など/汗'])
        self.assertTrue(self.eye_closed.visible)
        self.assertFalse(self.eye_open.visible)
        self.assertTrue(self.sweat.visible)
        psd_sprites.apply(self.psd, {}, off=['記号など/汗'])
        self.assertFalse(self.sweat.visible)

    def test_render_opens_fresh_psd_for_each_variant_and_writes_sheet(self):
        class FakeRenderedImage:
            size = (100, 200)

            def crop(self, box):
                self.crop_box = box
                return self

            def resize(self, size, method):
                self.size = size
                return self

            def save(self, path):
                Path(path).write_bytes(b'image')

        class FakePsd:
            def composite(self, force=False):
                self.force = force
                return FakeRenderedImage()

        class FakeSheet(FakeRenderedImage):
            def alpha_composite(self, image, position):
                pass

        cfg = {
            'crop': [0, 0, 100, 200], 'width': 50, 'blink': {},
            'faces': {'normal': {'mouth_open': 'open', 'mouth_closed': 'closed'}},
        }
        with TemporaryDirectory() as temp, \
             patch.object(psd_sprites, 'PSDImage') as psd_api, \
             patch.object(psd_sprites, 'apply'), \
             patch.object(psd_sprites.Image, 'new', return_value=FakeSheet()):
            psd_api.open.side_effect = lambda _: FakePsd()
            names = psd_sprites.render('character.psd', cfg, temp)
            self.assertEqual(names, ['normal_o_o.png', 'normal_o_c.png', 'normal_c_o.png', 'normal_c_c.png'])
            self.assertEqual(psd_api.open.call_count, 4)
            self.assertTrue((Path(temp) / 'sheet.png').is_file())

    def test_render_rejects_config_without_faces(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'faces'):
                psd_sprites.render('character.psd', {'crop': [0, 0, 10, 10], 'faces': {}}, temp)


if __name__ == '__main__':
    unittest.main()
