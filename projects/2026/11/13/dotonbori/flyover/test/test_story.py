import unittest

from build_story import parse_dialogue, split_text, speech_text


class ScriptTests(unittest.TestCase):
    def test_splits_long_dialogue_without_losing_words(self):
        text = '道頓堀は江戸時代から劇場街として栄え、いまは観光客が集まる場所です。水面に光が映ります。'
        chunks = split_text(text, 25)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(chunk) <= 25 for chunk in chunks))

    def test_reading_excludes_references_and_preserves_speaker_and_scene(self):
        source = '【導入：川】\n**ずんだもん：** 今日は大阪なのだ。[1]\n【場面2：橋】\n**四国めたん：** 橋の話よ。[3][4]'
        result = parse_dialogue(source)
        self.assertEqual([(r['section'], r['voice'], r['text']) for r in result], [
            (0, 'a', '今日は大阪なのだ。'), (2, 'b', '橋の話よ。')])

    def test_empty_and_long_text_are_handled(self):
        self.assertEqual(split_text(''), [])
        self.assertEqual(''.join(split_text('あ' * 81, 30)), 'あ' * 81)
        self.assertTrue(all(len(x) <= 30 for x in split_text('あ' * 81, 30)))

    def test_punctuation_stays_with_previous_subtitle(self):
        chunks = split_text('あ' * 42 + '、続きを話すのだ。', 42)
        self.assertFalse(chunks[1].startswith('、'))
        self.assertEqual(''.join(chunks), 'あ' * 42 + '、続きを話すのだ。')

    def test_special_place_and_disaster_readings_are_explicit(self):
        actual = speech_text('明暦の大火、両国橋と両国、柳橋、高潮の防潮堤、中ふ頭、咲洲。')
        self.assertEqual(actual, 'めいれきのたいか、りょうごくばしとりょうごく、やなぎばし、たかしおのぼうちょうてい、なかふとう、さきしま。')

    def test_contextual_readings_remain_clear(self):
        actual = speech_text('栄えた両岸。橋の上や川岸。汐留川と数寄屋橋。')
        self.assertEqual(actual, 'さかえたりょうがん。はしのうえやかわぎし。シオドメガワとスキヤバシ。')


if __name__ == '__main__':
    unittest.main()
