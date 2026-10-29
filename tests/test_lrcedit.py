import unittest

from undertone.lrcedit import format_lrc, shift_lines, set_line_time, mark_next


LINES = [(1.0, "first", None), (5.0, "second", None), (9.0, "third", None)]


class FormatLrc(unittest.TestCase):
    def test_writes_standard_timestamps(self):
        self.assertEqual(format_lrc(LINES), "[00:01.00] first\n[00:05.00] second\n[00:09.00] third\n")

    def test_keeps_word_tags_for_enhanced_lines(self):
        lines = [(1.0, "a b", [(1.0, "a"), (1.5, "b")])]
        self.assertEqual(format_lrc(lines), "[00:01.00] <00:01.00> a <00:01.50> b\n")

    def test_round_trips_through_the_parser(self):
        from undertone.lyrics import parse_enhanced_lrc
        self.assertEqual(parse_enhanced_lrc(format_lrc(LINES)), LINES)


class Edits(unittest.TestCase):
    def test_shift_moves_every_line_and_clamps_at_zero(self):
        out = shift_lines(LINES, -1500)
        self.assertEqual([t for t, _, _ in out], [0.0, 3.5, 7.5])

    def test_set_line_time_changes_one_line_and_keeps_order(self):
        out = set_line_time(LINES, 1, 7.25)
        self.assertEqual(out[1][0], 7.25)
        self.assertEqual([l[1] for l in out], ["first", "second", "third"])

    def test_mark_next_stamps_the_first_unmarked_line(self):
        lines = [(1.0, "first", None), (None, "second", None), (None, "third", None)]
        out, idx = mark_next(lines, 4.2)
        self.assertEqual((idx, out[1][0]), (1, 4.2))
        out, idx = mark_next(out, 8.0)
        self.assertEqual((idx, out[2][0]), (2, 8.0))
        out, idx = mark_next(out, 9.0)
        self.assertEqual(idx, -1)  # nothing left to mark
