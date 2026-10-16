"""
Tests for bin/strixec-setcurve against a plain file standing in for /dev/strixec.
Run: python3 -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SETCURVE = os.path.join(HERE, "..", "bin", "strixec-setcurve")


def load_setcurve():
    loader = importlib.machinery.SourceFileLoader("setcurve", SETCURVE)
    spec = importlib.util.spec_from_loader("setcurve", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SetcurveTest(unittest.TestCase):
    def setUp(self):
        self.sc = load_setcurve()
        fd, self.dev = tempfile.mkstemp()
        os.write(fd, bytes(range(256)))   # distinct starting table, easy to compare
        os.close(fd)
        self.sc.DEV = self.dev
        self.sc.STATE = os.path.join(tempfile.mkdtemp(), "profile")
        self.snapshot = self._image()

    def tearDown(self):
        os.unlink(self.dev)

    def _image(self):
        with open(self.dev, "rb") as f:
            return f.read()

    def test_profile_written_to_both_fans(self):
        with mock.patch("builtins.print"):
            self.sc.apply_profile("silenzioso")
        img = self._image()
        pts = self.sc.PROFILES["silenzioso"]
        for base in self.sc.FAN_BASES:
            for i, (t, d) in enumerate(pts):
                self.assertEqual(img[base + 3 * i], t)
                self.assertEqual(img[base + 3 * i + 2], d)

    def test_failed_write_restores_previous_table(self):
        real_write = self.sc.ec_write
        calls = {"n": 0}

        def failing_write(off, val):
            calls["n"] += 1
            if calls["n"] == 10:            # fail part-way through the first fan
                raise OSError(5, "simulated EC error")
            return real_write(off, val)

        with mock.patch.object(self.sc, "ec_write", side_effect=failing_write):
            with self.assertRaises(SystemExit):
                self.sc.apply_points(self.sc.PROFILES["aggressivo"], "aggressivo")
        self.assertEqual(self._image(), self.snapshot, "table must be back to its previous bytes")
        self.assertFalse(os.path.exists(self.sc.STATE), "state must not claim a profile was applied")

    def test_parse_points_bad_input_is_a_clean_error(self):
        with self.assertRaises(SystemExit) as cm:
            self.sc.parse_points("55:6,68-10")
        self.assertIn("68-10", str(cm.exception))

    def test_profiles_fit_the_raw_scale(self):
        for name, pts in self.sc.PROFILES.items():
            for _, d in pts:
                self.assertTrue(0 <= d <= self.sc.FAN_MAX, (name, d))

    def test_duty_above_scale_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.sc._validate([(t, 49) for t in range(40, 40 + 7 * 5, 5)])

    def test_parse_points_ok(self):
        self.assertEqual(self.sc.parse_points("55:6,68:10"), [(55, 6), (68, 10)])


if __name__ == "__main__":
    unittest.main()
