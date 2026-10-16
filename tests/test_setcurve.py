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
        tmp = tempfile.mkdtemp()
        self.sc.DEV = self.dev
        self.sc.STATE = os.path.join(tmp, "profile")
        self.sc.SCALE_FILE = os.path.join(tmp, "fan-scale")   # absent -> default scale 100
        self.snapshot = self._image()
        self.addCleanup(os.unlink, self.dev)

    def _image(self):
        with open(self.dev, "rb") as f:
            return f.read()

    def _quiet(self):
        return mock.patch("builtins.print")

    # --- scale ---------------------------------------------------------------

    def test_default_scale_writes_percent_values_unchanged(self):
        with self._quiet():
            self.sc.apply_profile("silenzioso")
        img = self._image()
        for base in self.sc.FAN_BASES:
            for i, (t, d) in enumerate(self.sc.PROFILES["silenzioso"]):
                self.assertEqual(img[base + 3 * i], t)
                self.assertEqual(img[base + 3 * i + 2], d)

    def test_scale_48_maps_percent_to_raw(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("48\n")
        self.assertEqual(self.sc.get_scale(), 48)
        with self._quiet():
            self.sc.apply_profile("aggressivo")
        img = self._image()
        for i, (t, d) in enumerate(self.sc.PROFILES["aggressivo"]):
            self.assertEqual(img[0x11 + 3 * i + 2], round(d * 48 / 100))
            self.assertTrue(img[0x11 + 3 * i + 2] <= 48)

    def test_stock_is_raw_whatever_the_scale(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("48\n")
        with self._quiet():
            self.sc.apply_profile("stock")
        img = self._image()
        for i, (t, d) in enumerate(self.sc.STOCK):
            self.assertEqual((img[0x11 + 3 * i], img[0x11 + 3 * i + 2]), (t, d))

    def test_bad_scale_file_falls_back_to_default(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("999\n")
        self.assertEqual(self.sc.get_scale(), self.sc.DEFAULT_SCALE)

    def test_set_scale_reapplies_active_profile(self):
        with open(self.sc.STATE, "w") as f:
            f.write("bilanciato\n")
        with self._quiet():
            self.sc.set_scale(48)
        self.assertEqual(open(self.sc.SCALE_FILE).read().strip(), "48")
        img = self._image()
        self.assertEqual(img[0x11 + 2], round(30 * 48 / 100))   # first band of "bilanciato"

    def test_set_scale_rejects_out_of_range(self):
        with self.assertRaises(SystemExit):
            self.sc.set_scale(5)

    # --- profiles and validation ----------------------------------------------

    def test_profiles_fit_the_scale(self):
        for name in self.sc.PROFILES:
            for d in (d for _, d in self.sc.profile_raw(name, 48)):
                self.assertTrue(0 <= d <= 48, (name, d))

    def test_raw_points_validation(self):
        with self.assertRaises(SystemExit):
            self.sc._validate_raw([(40, 1), (30, 2), (50, 3), (60, 4), (70, 5), (80, 6), (90, 7)])
        with self.assertRaises(SystemExit):
            self.sc._validate_raw([(40, 1)])

    def test_parse_points_bad_input_is_a_clean_error(self):
        with self.assertRaises(SystemExit) as cm:
            self.sc.parse_points("55:6,68-10")
        self.assertIn("68-10", str(cm.exception))

    def test_parse_points_ok(self):
        self.assertEqual(self.sc.parse_points("55:6,68:10"), [(55, 6), (68, 10)])

    # --- safety --------------------------------------------------------------

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
                self.sc.apply_profile("aggressivo")
        self.assertEqual(self._image(), self.snapshot, "table must be back to its previous bytes")
        self.assertFalse(os.path.exists(self.sc.STATE), "state must not claim a profile was applied")

    def test_speed_test_holds_then_restores(self):
        seen = {}

        def fake_sleep(secs):
            seen["during"] = self._image()
            seen["secs"] = secs

        with mock.patch.object(self.sc.time, "sleep", side_effect=fake_sleep), self._quiet():
            self.sc.speed_test(50, 5)
        self.assertEqual(seen["secs"], 5)
        self.assertEqual(seen["during"][0x11 + 2], 50)      # 50 % at scale 100 -> raw 50
        self.assertEqual(self._image(), self.snapshot)

    def test_speed_test_restores_even_if_interrupted(self):
        def boom(secs):
            raise KeyboardInterrupt()

        with mock.patch.object(self.sc.time, "sleep", side_effect=boom), self._quiet():
            with self.assertRaises(KeyboardInterrupt):
                self.sc.speed_test(80, 5)
        self.assertEqual(self._image(), self.snapshot)


if __name__ == "__main__":
    unittest.main()
