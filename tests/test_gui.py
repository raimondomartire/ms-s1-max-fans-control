"""
Headless tests for bin/strixec-gui (needs PySide6; skipped if missing).
Run: python3 -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(HERE, "..", "bin", "strixec-gui")
SC = os.path.join(HERE, "..", "bin", "strixec-setcurve")

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.sc = load(SC, "setcurve_for_gui")
        self.gui = load(GUI, "strixec_gui")
        self.gui.CONFIG = os.path.join(tempfile.mkdtemp(), "gui.json")
        self.gui.STATE = os.path.join(tempfile.mkdtemp(), "profile")
        profiles = json.dumps(self.sc.PROFILES)
        patcher = mock.patch.object(self.gui.subprocess, "check_output", return_value=profiles)
        patcher.start(); self.addCleanup(patcher.stop)
        self.real_read_temp = self.gui.read_temp
        patcher = mock.patch.object(self.gui, "read_temp", return_value=60.0)
        self.read_temp = patcher.start(); self.addCleanup(patcher.stop)
        self.win = self.gui.MainWin()
        self.addCleanup(self.win.close)

    def test_profiles_loaded(self):
        self.assertGreaterEqual(self.win.combo.count(), 5)

    def test_edit_does_not_reread_sensors(self):
        self.read_temp.reset_mock()
        for _ in range(50):
            self.win.on_edit()
        self.assertEqual(self.read_temp.call_count, 0)
        self.assertTrue(self.win.custom)

    def test_apply_message_survives_refresh(self):
        self.win.pending = "silenzioso"
        self.win.on_applied_result = None
        self.win.msg_lbl.setText("")
        self.win.proc = mock.Mock()
        self.win.proc.readAllStandardError.return_value = b""
        self.win.on_applied(0, 0)
        self.win.refresh(); self.win.refresh()
        self.assertIn("silenzioso", self.win.msg_lbl.text())

    def test_cancelled_authorization_message(self):
        self.win.proc = mock.Mock()
        self.win.proc.readAllStandardError.return_value = b""
        self.win.pending = "silenzioso"
        self.win.on_applied(126, 0)
        self.assertTrue(any(w in self.win.msg_lbl.text().lower() for w in ("annullat", "cancel")),
                        self.win.msg_lbl.text())
        self.assertTrue(self.win.apply_btn.isEnabled())
        self.assertTrue(self.win.combo.isEnabled())

    def test_apply_runs_async_and_locks_controls(self):
        started = {}

        class FakeProc:
            def __init__(self, parent=None):
                self.finished = mock.Mock(); self.finished.connect = lambda f: started.setdefault("cb", f)
            def start(self, prog, args):
                started["cmd"] = [prog] + args
            def deleteLater(self):
                pass
            def readAllStandardError(self):
                return b""

        with mock.patch.object(self.gui, "QProcess", FakeProc):
            self.win.on_apply()
        self.assertEqual(started["cmd"][0], "pkexec")
        self.assertFalse(self.win.apply_btn.isEnabled())
        self.assertFalse(self.win.combo.isEnabled())
        self.win.on_apply()           # second click while busy must not start another run
        self.assertEqual(started["cmd"][0], "pkexec")
        started["cb"](0, 0)
        self.assertTrue(self.win.apply_btn.isEnabled())

    def test_temperature_is_cpu_tctl_only(self):
        from unittest import mock as m
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        def hw(name, labels):
            d = os.path.join(root, name); os.makedirs(d)
            def put(fname, text):
                with open(os.path.join(d, fname), "w") as f:
                    f.write(text)
            put("name", name + "\n")
            for i, (lab, val) in enumerate(labels, 1):
                put("temp%d_label" % i, lab + "\n")
                put("temp%d_input" % i, "%d\n" % val)
            return d
        hw("k10temp", [("Tctl", 71000), ("Tccd1", 80000)])
        hw("amdgpu", [("edge", 90000)])
        real_glob = self.gui.glob.glob
        with m.patch.object(self.gui.glob, "glob",
                            side_effect=lambda pat: real_glob(os.path.join(root, "*")) if pat.startswith("/sys/class/hwmon") else real_glob(pat)):
            self.assertEqual(self.real_read_temp(), 71.0)


if __name__ == "__main__":
    unittest.main()
