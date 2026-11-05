import unittest
from timeline import physical_time,design_source_frame


class TimelineTests(unittest.TestCase):
    def test_design_chapters_hold_without_crossing_into_next_chapter(self):
        self.assertEqual(design_source_frame(96),96)
        self.assertEqual(design_source_frame(144),96)
        self.assertEqual(design_source_frame(145),97)
        self.assertEqual(design_source_frame(576),384)

    def test_physical_clock_is_continuous_at_playback_transitions(self):
        apex=2.6022575557044076
        for boundary in (1.5,5.5,11.5):
            before=physical_time(boundary-1e-8,apex)[0]
            after=physical_time(boundary+1e-8,apex)[0]
            self.assertLess(abs(after-before),1e-7)
        self.assertEqual(physical_time(14,apex),(apex,0))


if __name__=="__main__":unittest.main()
