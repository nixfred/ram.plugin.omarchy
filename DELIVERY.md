# RAM Pulse — OMW-028

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
