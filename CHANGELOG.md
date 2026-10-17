# Changelog

## 1.2.0

### Fixed
- The module's read and write loops now advance the file position per byte, so a
  retried partial transfer lands on the right EC register. Reported by James.
- The fan table is written at `0x10`/`0x30` as 8 records `[value, upper, lower]`.
  The previous writer ran every profile one band late and left record 0 at 0,
  so the fans stopped below the first temperature. Found by James's alignment
  experiment.
- `setcurve` rolls back the table if a write fails part-way.
- A 0 % duty is refused unless `--allow-off`.
- The GUI no longer blocks while `pkexec` waits, and times out after 120 s.
- The GUI status line keeps the result of the last action.

### Changed
- Writes are refused unless the DMI product name contains `MS-S1`. Use `--force`
  to override.
- Record 7 is the protection band: its bounds stay at 90–95 °C, its value is
  never lowered, and every profile ends at 90 °C or below.
- The fan scale is a runtime setting (`set-scale`), default 100. The 48 knee
  is the working hypothesis.
- `install.sh` restarts the services, so an upgrade reapplies the curve.
- GUI: a new theme for light and dark, with a settings menu for the scale and a
  speed test.

### Added
- `setcurve test P S` holds a fixed speed and restores the table afterwards.
- Tests: `tests/` (setcurve and GUI, headless) and `module/tests/run.sh`.

### Credits
See the Credits section in the README.
