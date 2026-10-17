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


def record(img, base, k):
    o = base + 3 * k
    return img[o], img[o + 1], img[o + 2]          # (value, upper, lower)


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

    # --- layout (James's alignment experiment) ---------------------------------

    def test_stock_table_decodes_to_james_values(self):
        with self._quiet():
            self.sc.apply_profile("stock")
        img = self._image()
        for base in self.sc.FAN_BASES:
            self.assertEqual([record(img, base, k) for k in range(8)], self.sc.STOCK)
        self.assertEqual(record(img, 0x10, 7), (40, 95, 90))   # record 7 at 0x25..0x27

    def test_record_zero_is_never_zero_for_a_profile(self):
        for name in self.sc.PROFILES:
            for scale in (48, 100):
                recs = self.sc.points_to_records(self.sc.profile_raw(name, scale))
                self.assertGreater(recs[0][0], 0, (name, scale))

    def test_profile_records_sit_at_0x10_and_0x30(self):
        with self._quiet():
            self.sc.apply_profile("silenzioso")
        img = self._image()
        recs = self.sc.points_to_records(self.sc.profile_raw("silenzioso", 100))
        for base in self.sc.FAN_BASES:
            self.assertEqual([record(img, base, k) for k in range(8)], recs)

    def test_below_first_temperature_gets_a_running_speed(self):
        with self._quiet():
            self.sc.apply_profile("ultrasilenzioso")
        img = self._image()
        value, upper, lower = record(img, 0x10, 0)
        self.assertEqual((lower, upper), (0, 55))
        self.assertGreaterEqual(value, self.sc.MIN_RAW)

    # --- scale ---------------------------------------------------------------

    def test_scale_48_maps_percent_to_raw(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("48\n")
        self.assertEqual(self.sc.get_scale(), 48)
        with self._quiet():
            self.sc.apply_profile("aggressivo")
        img = self._image()
        for i, (t, d) in enumerate(self.sc.PROFILES["aggressivo"]):
            value = record(img, 0x10, i)[0]
            self.assertEqual(value, max(self.sc.MIN_RAW, round(d * 48 / 100)))
            self.assertLessEqual(value, 48)

    def test_stock_is_raw_whatever_the_scale(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("48\n")
        with self._quiet():
            self.sc.apply_profile("stock")
        img = self._image()
        self.assertEqual(record(img, 0x10, 1), (16, 45, 25))

    def test_bad_scale_file_falls_back_to_default(self):
        with open(self.sc.SCALE_FILE, "w") as f:
            f.write("999\n")
        self.assertEqual(self.sc.get_scale(), self.sc.DEFAULT_SCALE)

    def test_set_scale_reapplies_active_profile(self):
        with open(self.sc.STATE, "w") as f:
            f.write("bilanciato\n")
        with self._quiet():
            self.sc.set_scale(48)
        with open(self.sc.SCALE_FILE) as f:
            self.assertEqual(f.read().strip(), "48")
        self.assertEqual(record(self._image(), 0x10, 0)[0], round(30 * 48 / 100))

    def test_set_scale_rejects_out_of_range(self):
        with self.assertRaises(SystemExit):
            self.sc.set_scale(5)

    # --- profiles and validation ----------------------------------------------

    def test_profiles_fit_the_scale(self):
        for name in self.sc.PROFILES:
            for _, d in self.sc.profile_raw(name, 48):
                self.assertTrue(0 <= d <= 48, (name, d))

    def test_small_duty_is_raised_to_the_tested_minimum(self):
        self.assertEqual(self.sc.to_raw_points([(50, 1)], 100), [(50, self.sc.MIN_RAW)])
        self.assertEqual(self.sc.to_raw_points([(50, 0)], 100), [(50, 0)])

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
        self.assertEqual(record(seen["during"], 0x10, 0)[0], 50)        # 50 % at scale 100 -> raw 50
        self.assertEqual(record(seen["during"], 0x10, 7)[0], 50)        # flat: last record too
        self.assertEqual(self._image(), self.snapshot)

    def test_speed_test_restores_even_if_interrupted(self):
        def boom(secs):
            raise KeyboardInterrupt()

        with mock.patch.object(self.sc.time, "sleep", side_effect=boom), self._quiet():
            with self.assertRaises(KeyboardInterrupt):
                self.sc.speed_test(80, 5)
        self.assertEqual(self._image(), self.snapshot)


class GuardTest(unittest.TestCase):
    """Board guard and zero-duty refusal, on the command line."""

    setUp = SetcurveTest.setUp
    _image = SetcurveTest._image
    _quiet = SetcurveTest._quiet

    def _dmi(self, product, board=""):
        files = {"/sys/class/dmi/id/product_name": product + "\n",
                 "/sys/class/dmi/id/board_name": board + "\n"}

        def fake_open(path, *a, **k):
            if path in files:
                import io
                return io.StringIO(files[path])
            raise OSError(2, "no such file")
        return mock.patch.object(self.sc, "open", side_effect=fake_open, create=True)

    def test_board_check_accepts_ms_s1(self):
        with self._dmi("MS-S1 MAX"):
            self.sc.board_check(force=False)              # no exception

    def test_board_check_refuses_other_boards(self):
        with self._dmi("UM790 Pro", "F7BSC"):
            with self.assertRaises(SystemExit) as cm:
                self.sc.board_check(force=False)
        self.assertIn("--force", str(cm.exception))

    def test_board_check_refuses_when_dmi_unreadable(self):
        with self._dmi("", ""):
            with self.assertRaises(SystemExit):
                self.sc.board_check(force=False)

    def test_force_bypasses_board_check(self):
        with self._dmi("UM790 Pro"):
            self.sc.board_check(force=True)

    def _run(self, *argv):
        with mock.patch.object(self.sc.sys, "argv", ["strixec-setcurve"] + list(argv)), self._quiet():
            return self.sc.main()

    def test_custom_zero_duty_refused_without_allow_off(self):
        with self._dmi("MS-S1 MAX"):
            with self.assertRaises(SystemExit) as cm:
                self._run("custom", "40:0,50:10,60:20,70:30,80:40,90:50,97:60")
        self.assertIn("--allow-off", str(cm.exception))

    def test_test_zero_percent_refused_without_allow_off(self):
        with self._dmi("MS-S1 MAX"):
            with self.assertRaises(SystemExit):
                self._run("test", "0", "5")

    def test_write_refused_on_unknown_board(self):
        with self._dmi("UM790 Pro"):
            with self.assertRaises(SystemExit) as cm:
                self._run("silenzioso")
        self.assertIn("MS-S1", str(cm.exception))
        self.assertEqual(self._image(), self.snapshot)            # nothing written

    def test_reads_do_not_need_the_board(self):
        with self._dmi("UM790 Pro"):
            self._run("dump-profiles")                            # no exception


if __name__ == "__main__":
    unittest.main()
