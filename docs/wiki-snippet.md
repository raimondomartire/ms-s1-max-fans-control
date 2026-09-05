<!-- Draft to add to kyuz0/strixhalo-homelab : Hardware/PCs/Minisforum_MS-S1_MAX.md
     NOT published yet — requires the repo to be public first. -->

## Fan control (Linux)

The stock fan curve is conservative (~40% duty only at 93 °C), so under sustained
CPU/GPU load the APU reaches Tjmax and throttles. The MS-S1 MAX exposes no
standard Linux fan control (no hwmon PWM, no tachometer, no ACPI fan object),
and on Fedora `ec_sys` is unavailable while Secure Boot lockdown blocks debugfs.

Open-source tool for this board:
**[ms-s1-max-fans-control](https://github.com/raimondomartire/ms-s1-max-fans-control)**
— a small signed kernel module exposes the EC as `/dev/strixec` (works under
Secure Boot + SELinux), with CLI/GUI fan-curve profiles and systemd persistence.

Reverse-engineered EC map: CPU temperature at `0x09`; fan-curve tables at `0x11`
(fan 1) and `0x31` (fan 2), 8 × 3-byte records `[temp, hysteresis, duty%]`, read
live by the firmware. Note: this board is **not** a Sixunited AXB35-02 (different
EC layout). Full details in the repo's `docs/EC-MAP.md`.
