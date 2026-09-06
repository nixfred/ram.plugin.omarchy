# RAM Pulse — OMW-028

Performance and grouping work on `dex`, September 6, 2026, from a report that
RAM Pulse and CPU Pulse together were costing noticeable shell CPU.

The chip drove its canvas from an infinite `NumberAnimation on phase`, so every
repaint landed at display refresh rate, and the `level` and `tint` Behaviors did
the same through each transition regardless of the widget's `animated` setting —
so turning animation off never stopped the repainting. Phase now advances on one
100ms Timer that issues that tick's single paint, the Behaviors are gone, and
neither the chip nor the history graph paints while off screen; both catch up on
becoming visible, so the graph no longer repaints for the samples that land every
15 seconds while the dashboard is closed. The same pattern was found and fixed in
CPU Pulse, Net Pulse and Audio Pulse, which share the chip design. Measured on
`dex` over 45 two-second slices, quickshell's own CPU fell from 97.4% of one core
to a mean of 13.3%; child-process CPU averages a further 6%, lumpy rather than
steady. All 33 bar widgets were then audited: no other plugin carries the
pattern, as nearly every one gates its animations on `opened`, `visible` or a
live condition.

The RAM hoarders view now groups by application. The flat per-PID list gave one
application several rows, and resident sizes cannot be summed because each shared
page is counted in every process mapping it. The collector reads proportional set
size for every process the user owns, groups them by the window `target_for()`
already resolves — every row exists to be clicked, and clicking focuses a window
— falling back to the systemd unit, then to the process. Group totals are summed
PSS, which may legitimately be added; a group with a member whose PSS is
unreadable shows its largest resident process instead, marked *resident*. A
cgroup running more than five distinct programs is treated as a desktop session
rather than an application, which keeps the compositor's own unit from
collapsing 23 unrelated processes into one row; and a process that exits between
its status and its `smaps_rollup` read is dropped rather than costing its group a
total. The view defaults to grouped and keeps a **By process** toggle, persisted
through the same `updateEntryInline` path as the readout modes — verified against
`shell.json` that only this widget's entry gains a key, with the layout and the
other 32 widgets untouched. Median of five warm collector passes: 206ms before,
213ms after. Design, measurements and the two live-only pitfalls are in
`docs/per-app-grouping.md`.

Validation: eighteen Python tests, the JavaScript model checks and five QML
widget tests pass. Both hoarder views, the readout picker and the dashboard were
checked live at 1920×1080 against real telemetry.

Local repair on `dex`, September 5, 2026: the widget and service file were present, but `ram-pulse.service` was disabled and inactive, with no telemetry state directory. Enabled and started the existing user service using `systemctl --user enable --now ram-pulse.service`. The graphical-session enablement now persists across login. Live widget IPC confirmed fresh telemetry, 24 process entries, and three history samples after opening the dashboard; the recorder stayed active with zero restarts. All ten Python tests and the JavaScript model checks passed. Earlier delivery evidence below describes the original installation. The canonical `/home/pi/Omarchy-To-Do-Wish-List.md` was absent on this machine, so no wish-list entry could be updated.

Installed locally on September 5, 2026, at the far right of Omarchy's top bar.

- Source: `/home/pi/Projects/ram.plugin.omarchy`
- Installed plugin: `/home/pi/.config/omarchy/plugins/nixfred.ram-pulse`
- Recorder: `ram-pulse.service`, enabled in the graphical user session
- Local history: `/home/pi/.local/state/ram-pulse/history.sqlite3`
- Pre-install backup: `/home/pi/.local/state/omarchy/backups/ram-pulse-20260905-144520`

Validation: ten Python tests, JavaScript readout/color tests, manifest validation and QML syntax checks pass. Live shell loads without RAM Pulse warnings after fixing a QML property collision. All three tabs and four mode choices were visually checked at 1920×1080. Actual pointer right-click opens the picker; clicking Amount used saved the readout. Actual hoarder click focused the existing Claude Herdr pane and terminal on workspace 1; focus was returned to the prior window. Background process clicks showed proportional-memory details without creating a window.

History retained earlier samples across an Omarchy shell restart and increased from 12 to 13 samples while the popup was closed. No history is fabricated for time before installation. The daemon initially consumed approximately 13 MiB of RAM.

The live Flush pending writes button reduced dirty data from 2.3 MiB to 0.0 MiB; available RAM moved from 2.7 GiB to 2.6 GiB during concurrent workloads. It does not promise recovered RAM. The backend has no termination, cache-drop or swap-reset action; unknown actions are rejected. This test used only unprivileged `sync`.

Screenshots in `evidence/` show the running plugin with real telemetry. Historical graphs will fill in over the next seven days. Source repository: private [nixfred/ram.plugin.omarchy](https://github.com/nixfred/ram.plugin.omarchy), branch `main`. Full-desktop verification screenshots remain local and are excluded from Git.
