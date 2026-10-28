import os
import unittest
from unittest import mock

from undertone.idle import idle_seconds, Screensaver


class IdleSeconds(unittest.TestCase):
    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"UNDERTONE_FAKE_IDLE": "123.5"}):
            self.assertEqual(idle_seconds(), 123.5)

    def test_returns_a_non_negative_number_or_zero_on_failure(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UNDERTONE_FAKE_IDLE", None)
            self.assertGreaterEqual(idle_seconds(), 0.0)


class ScreensaverState(unittest.TestCase):
    def test_raises_after_threshold_and_lowers_on_activity(self):
        events = []
        ss = Screensaver(idle_minutes=10, on_change=lambda on: events.append(on))
        ss.update(idle=0)
        ss.update(idle=599)
        self.assertEqual(events, [])
        ss.update(idle=601)
        self.assertEqual(events, [True])
        ss.update(idle=700)          # still idle: no repeat
        self.assertEqual(events, [True])
        ss.update(idle=1)            # activity
        self.assertEqual(events, [True, False])

    def test_disabled_never_fires(self):
        events = []
        ss = Screensaver(idle_minutes=0, on_change=lambda on: events.append(on))
        ss.update(idle=99999)
        self.assertEqual(events, [])
