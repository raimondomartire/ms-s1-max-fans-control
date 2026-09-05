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
| `0x11` | **Fan 1 curve table** (base)             | 8 × 3-byte records             |
| `0x31` | **Fan 2 curve table** (base)             | identical structure            |

No readable fan tachometer (RPM) was found, and no live "manual duty" register:
under load only `0x09` changes. Fan speed is governed entirely by the curve
tables, which the firmware reads **live**.

## Fan-curve table format

Each fan table is **7 records of 3 bytes** (fan1 `0x11`–`0x25`, fan2
`0x31`–`0x45`):

```
record i (i = 0..6), base = 0x11 (fan1) / 0x31 (fan2):
  base + 3*i + 0 : upper temperature of the band (°C)
  base + 3*i + 1 : lower bound / hysteresis (°C) = previous record's upper temp
  base + 3*i + 2 : duty (%) for the band (lower, upper]
```

A record's duty applies for temperatures up to its `upper` value (and above the
previous record's `upper`). Above the last record's temperature the firmware
holds the last band's duty, so the last duty should be 100 %.

> Offsets `0x26`/`0x27`/`0x28` (and `0x46`–`0x48`) are **not** part of the
> writable curve table: `0x28`/`0x48` are volatile (firmware-updated) and must
> not be used as curve bytes.

`duty` is a linear percentage `0..100` (100 = maximum; verified: forcing high
duty under load dropped the APU temperature by ~8 °C and audibly spun the fans
up). This tool writes only the **temperature** and **duty** columns.

### Factory (stock) curve

```
25°C→16%  45°C→18%  60°C→25%  72°C→29%  83°C→34%  88°C→36%  93°C→40%  98°C→(max)
```

The stock curve reaches only ~40 % near 93 °C, which is why the APU throttles
under sustained load.

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
