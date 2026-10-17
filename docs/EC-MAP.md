# Minisforum MS-S1 MAX — Embedded Controller map

Reverse-engineered on a Minisforum MS-S1 MAX (Ryzen AI Max+ 395), Fedora,
kernel 7.1.x. All offsets are in the 0x00–0xFF EC RAM space accessed through
`/dev/strixec`.

> This board is **not** a Sixunited AXB35-02: its EC layout differs (temperature
> is at 0x09, not 0x70; 0x21/0x23/0x25 are curve-table bytes, not fan-mode
> registers; no readable RPM at 0x35–0x38).

## Known registers

| Offset | Meaning                                  | Notes                          |
|--------|------------------------------------------|--------------------------------|
| `0x09` | CPU temperature (°C), tracks `Tctl`      | Read-only; matches `k10temp`   |
| `0x10` | **Fan 1 curve table** (base)             | 8 × 3-byte records             |
| `0x30` | **Fan 2 curve table** (base)             | identical structure            |

No readable fan tachometer (RPM) was found, and no live "manual duty" register:
under load only `0x09` changes. Fan speed is governed entirely by the curve
tables, which the firmware reads **live**.

## Fan-curve table format

Confirmed by James's alignment experiment (2026-10-16, `plan-hwmon.md`, Phase 0
step 7). Each fan table is **8 records of 3 bytes** (fan 1 `0x10`–`0x27`, fan 2
`0x30`–`0x47`):

```
record k (k = 0..7), base = 0x10 (fan 1) / 0x30 (fan 2):
  base + 3*k + 0 : value for the band (lower, upper]  (raw; see the scale below)
  base + 3*k + 1 : upper temperature of the band (°C)
  base + 3*k + 2 : lower temperature of the band (°C)
```

Record 0 covers everything up to its upper bound, so below the first temperature
the fans get record 0's value. Stock uses 0 there, which stops the fans below
25 °C. The last record's value holds above its upper bound.

> The earlier model (7 records from `0x11`, `[upper, lower, value]`) was off by
> one byte: each value was written into the band above. Its claim that `0x26`–
> `0x28` are not writable was also wrong: `0x26`/`0x27` are record 7's upper and
> lower. `0x28`/`0x48` are volatile (firmware-updated) and are not curve bytes.

### Record 7 is the protection band (decision)

Record 7 (`0x25`–`0x27`, stock `40 / 95 / 90`) is treated as the firmware's own
protection band. The evidence is indirect: the Minisforum UM790 driver never
writes this record and reports a hard override to 100 % at ≥ 94 °C, and no
other source describes a curve row above 90 °C. The rules `strixec-setcurve`
follows:

- its bounds stay at the stock 90–95 °C;
- its value is never lowered below the stock 40; it takes the profile's last
  duty when that is higher;
- every profile ends at 90 °C or below, so record 6 stops where record 7 starts.

Open: James's check on `0x25`–`0x27` (plan-hwmon.md, Phase 10 H4) can confirm or
change this. If record 7 turns out not to be a protection band, the rule can be
relaxed; until then it stays.

### Duty scale

The raw value that means full speed is the fan scale. Default `100`, stored in
`/etc/strixec/fan-scale`. Set with `strixec-setcurve set-scale N`.

James's measurements put the knee at **48**: the fans stop getting faster above
it. A rotation tone measured at each step gives about 98 RPM per unit, so the
value is RPM/100 and 48 is about 4700 RPM. This is strong evidence but not a
tachometer reading. Until it is confirmed, `set-scale 48` is the tested option.

The fans were run down to value 9 without stalling; stall from standstill is not
tested. `strixec-setcurve` never writes a non-zero duty below 9.

`strixec-setcurve test P S` holds P % of full speed for S seconds and then
restores the previous table.

### Factory (stock) curve

Records as `value (upper, lower]`, from `ec-stock.txt` in James's experiments:

| Band, °C | ≤ 25 | 25–45 | 45–60 | 60–72 | 72–83 | 83–88 | 88–93 | 93–95 (lower 90) |
|---|---|---|---|---|---|---|---|---|
| Value | 0 | 16 | 18 | 25 | 29 | 34 | 36 | 40 |
| % of 48 | 0 | 33 | 38 | 52 | 60 | 71 | 75 | 83 |

The stock curve reaches 40 of 48 (83 %) near 93 °C, which is why the APU
throttles under sustained load.

## Platform notes (Fedora + Secure Boot)

- `ec_sys` is unavailable (`# CONFIG_ACPI_EC_DEBUGFS is not set`). The exported
  symbols `ec_read`/`ec_write`/`ec_transaction` **are** available, so a small
  out-of-tree module can access the EC without patching the kernel.
- Secure Boot enables kernel lockdown (`integrity`), which blocks
  `/sys/kernel/debug/ec/ec0/io`. A **misc char device** (`/dev/strixec`) is not
  affected.
- SELinux (enforcing) denies `module_load` for a `.ko` in `/opt` (`usr_t`) from
  a service context. The module is installed into
  `/lib/modules/<krel>/extra/` (`modules_object_t`) and loaded with `modprobe`.

## Sources

- Alignment, knee, rotation tone and the minimum speed: James's experiments and
  `plan-hwmon.md` (2026-10-11 to 10-17).
- Value-first layout and the protection row: [malwareslayer/minisforum-platform](https://github.com/malwareslayer/minisforum-platform)
  (UM790 driver, `src/minisforum_hwmon.c`).
- Board check and minimum speed: [ibnbajja/ec-su_axb35-linux](https://github.com/ibnbajja/ec-su_axb35-linux).
