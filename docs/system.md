# System notes
- tuned profile: `balanced`. The previous `powersave` profile pinned the CPU near 450 MHz with turbo off and made video decode lag. Revert: `sudo tuned-adm profile powersave`.
- Helium (AppImage) launcher adds VA-API decode flags: `--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL,VaapiVideoDecoder,VaapiIgnoreDriverChecks`.
- udev rules in `system/` use `TAG+="uaccess"` so the logged-in user gets ACLs without joining the `input` group.
- TeX Live: `dnf install --exclude=kf6-kmime texlive-scheme-medium latexmk` (the default transaction conflicts with the installed kmime locale files).
- Package list: `packages/dnf-userinstalled.txt` is everything dnf marks user-installed, including the base comps; trim it before reinstalling.
- ydotool: needs `sudo dnf install ydotool` plus the uinput udev rule; the daemon runs as the user service `ydotoold` (socket in `$XDG_RUNTIME_DIR/.ydotool_socket`, which `holdtalk` points `YDOTOOL_SOCKET` at).
- tuned `balanced` sets turbo on and `balance_performance` energy preference; verify with `cat /sys/devices/system/cpu/intel_pstate/no_turbo` (0) and `.../cpu0/cpufreq/energy_performance_preference`.

## Clock after sleep (dual boot)
Windows keeps the hardware clock in local time, so this machine does too (`timedatectl` shows "RTC in local TZ: yes"). On resume the kernel read that clock as UTC, shifting the system clock by +5:30 in India. `system/usr/lib/systemd/system-sleep/clock-fix` (install as root, mode 755, to `/usr/lib/systemd/system-sleep/`) re-reads the hardware clock as local time after every resume and then asks chrony to confirm it. Idle sleep is set in `powerdevilrc` (suspend after 3600 s on AC and battery); hibernation is not possible because the only swap is zram.
