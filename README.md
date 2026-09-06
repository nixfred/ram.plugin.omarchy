# RAM Pulse

An animated, glowing memory chip for the Omarchy top bar. Dark red → yellow at 50% available → green with ample headroom. Left-click opens the dashboard; right-click offers four saved readouts: percentage available, percentage used, amount used, amount available. All memory readouts use one decimal and explicit GiB/MiB units.

The dashboard includes:

- Animated liquid chip and orbiting charge, available headroom, used RAM, reusable cache, memory pressure (PSI).
- Continuous 1-hour, 24-hour and 7-day RAM/swap history, peak envelope and hover readings. Missing history is left blank; shutdowns and recording gaps break the trace.
- Swap devices, swap traffic, zram logical allocation versus real physical cost, and compression efficiency.
- Top 24 RAM hoarders, eight per page, grouped by app or listed per process. **By app** puts one row per window or service — a browser's 16 processes become one row, a terminal's agent, shell and helpers become one — totalled by proportional set size, the one figure that may be summed. **By process** is the flat resident-memory list. Click to focus the existing app or attached Herdr/tmux pane. Exact Boomux terminal titles can resolve an existing terminal too. Background processes report details. Browser children focus their browser window, not an individual tab.
- Memory lab with dirty/writeback pages, anonymous and shared memory, kernel slab, page tables, unevictable memory, major faults and committed virtual memory.
- Asynchronous **Flush pending writes**, limited to once a minute, with before/after dirty and available readings. This uses unprivileged `sync`; it saves dirty data without discarding cache or promising recovered memory. Storage work can briefly increase while it runs.

There are no process termination, session termination, forced cache eviction, swap reset, or privileged tuning actions. Processes and window identities are revalidated on every focus click. Session routing uses argument arrays and validated IDs, never interpolated shell commands. No process command lines or credentials are saved.

## Install

Requires an existing Omarchy Quickshell desktop, Python 3, systemd user services and Hyprland. No additional Python packages.

```sh
python3 install.py
```

Installs under `~/.config/omarchy/plugins/nixfred.ram-pulse`, appends to the far-right bar, and enables `ram-pulse.service` for the graphical session. Existing files and bar layout are backed up under `~/.local/state/omarchy/backups/ram-pulse-TIMESTAMP/`.

The recorder runs independently of the shell/popup: metrics every 3 seconds, processes every 9 seconds, history every 15 seconds. SQLite retains seven days (up to 40,320 samples), downsampled to ~240 points per displayed range; per-bucket peaks are retained. State is private (`0700` directory / `0600` files) in `$XDG_STATE_HOME/ram-pulse` or `~/.local/state/ram-pulse`. History stores aggregate metrics only. The latest snapshot contains process names/PIDs/window titles and is replaced, not logged. Closed panels stop their large animations.

## Controls and diagnosis

```sh
omarchy-shell nixfred.ram-pulse open
omarchy-shell nixfred.ram-pulse modes
omarchy-shell nixfred.ram-pulse status
omarchy-shell nixfred.ram-pulse grouping true
systemctl --user status ram-pulse.service
journalctl --user -u ram-pulse.service
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

Left/right arrows change dashboard tabs. Escape closes. Keys 1–4 select modes in the right-click picker. Inline bar setting `animated: false` disables chip animations; `groupByApp: false` opens RAM hoarders as a flat process list. Chip and graph repaints are coalesced onto a 10Hz tick and stop entirely while off screen.

Disable with `omarchy plugin disable nixfred.ram-pulse` and `systemctl --user disable --now ram-pulse.service`. This stops only this plugin's telemetry service; historical data stays available. Restore the timestamped `shell.json` backup only if you also intend to restore that earlier layout.

## Accounting

Used RAM is `MemTotal − MemAvailable`, consistent with modern Linux headroom accounting. Cache and kernel categories overlap; they are not additive partitions. RSS can double-count shared pages across processes and is never summed. Group totals are proportional set size (PSS), which divides each shared page between the processes mapping it and may be added; a group with a member whose PSS is unreadable, such as a root command in one of your own terminals, shows its largest resident process instead, marked *resident*. A cgroup running more than five distinct programs is a desktop session, not an application, and its processes stay individual. Process swap omits some shared swap. zram's physical allocation is already in used physical RAM. Committed virtual memory is not resident RAM.

References: [Linux /proc memory fields](https://docs.kernel.org/filesystems/proc.html), [kernel cache-reclaim guidance](https://kernel.org/doc/html/latest/admin-guide/sysctl/vm.html), [PSI](https://docs.kernel.org/accounting/psi.html), [zram](https://docs.kernel.org/admin-guide/blockdev/zram.html).
