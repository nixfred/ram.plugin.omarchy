# RAM Pulse — PURIFY: what changed and why

Status: implemented as a 4-commit stack on `origin/main`.
Goal: make RAM Pulse smaller, clearer, and cheaper to maintain **without
reducing useful behavior**. Feature work is out of scope; the only behavior
removed on purpose is redundant identity UI (About links) and fields nobody
reads.

Non-goals: no new collectors, no new tabs, no Repository/DTO/DI/event-bus
layers, no tab componentization. One Python file stays the default.

## The contract Rule

`snapshot.json` contains **display state**. `focus()` derives **operational
state** fresh on every click (`ram_pulse.py:144-153`). Nothing the panel only
displays is allowed to carry credentials, PIDs' parents, socket paths, or
window-manager IDs into the persisted snapshot.

## A — Narrow the runtime contract (`ram_pulse.py`, `tests/test_ram_pulse.py`)

Why: the snapshot carried 60 meminfo keys, four `vm` keys, and per-row /
per-target internals the QML never renders. Every extra persisted key is disk,
parse time, and a privacy surface.

What:

- `details` is now exactly `AnonPages, Shmem, Slab, PageTables, Unevictable,
  Committed_AS` — the six fields the Memory Lab renders.
- `vm` (`pswpin, pswpout, pgmajfault`) is still collected for swap/fault
  rates but is **excluded from the published snapshot**; `oom_kill`
  collection is dropped.
- `swaps` rows keep `name, total, used, priority` (`type` dropped);
  `zram` keeps `original, physical` (`compressed` dropped).
- New `public_row()` / `public_target()` strip `owned, ppid` from rows and
  `socket, client, workspace-id, tab-id` from focus targets. Retained target
  shape is `address, title, workspace, host{kind, pane}`; `focus()` still
  re-resolves the live window/pane, so clicks keep working.
- New `HISTORY_RANGES = (3600, 86400, 604800)` (`ram_pulse.py:197`) is the
  single Python source for history ranges, matching `Model.js` `RANGES`.
- `record()` names its columns explicitly (including `total` for existing
  databases) and caches `boot_id` only when the read is non-empty, so a
  transient read failure retries instead of pinning an empty value.

Measured here: metrics-only snapshot 2162 → 897 bytes (-58%);
`details` 60 → 6 keys; `swaps` 5 → 4; `zram` 3 → 2; rows 9 → 7.

## B — Pure UI model, fewer test files (`Model.js`, `tests/test_model.cjs`)

Why: `Panel.qml` duplicated pure formatting/pagination logic inline, and three
test files asserted on QML text with regexes instead of testing the logic.
Logic in QML cannot be unit-tested; logic in `Model.js` can.

What:

- `Model.js` owns `PAGE_SIZE = 8`, `RANGES` + `validRange()`, `totalOf()`,
  `kindOf()`, `pageCount()`, `clampPage()`, `targetLabel()`,
  `recorderStatus()` (`Model.js:137-155`).
- Deleted `tests/test_accounting.cjs`, `tests/test_pagination.cjs`,
  `tests/test_panel_status.cjs`; their assertions moved into
  `tests/test_model.cjs`, including exact-multiple pagination (`16 → 2`,
  `24` cases), LIVE footer guards, and Panel-to-Model wiring asserts so the
  QML cannot silently stop calling the model.

## C — QML purification (`Panel.qml`, `MemoryChip.qml`)

Why: duplicated constants and local primitives drift; the panel had two
sources of truth for tabs, page size, and ranges.

What:

- `Panel.qml` calls `Model.PAGE_SIZE`, `Model.RANGES` / `validRange()`,
  `Model.totalOf()`, `Model.targetLabel()`, `Model.recorderStatus()`,
  `Model.clampPage()`; `range` initializes from `Model.RANGES[0].seconds`
  (`Panel.qml:52`); tabs live in `root.tabs` / `root.lastTab`.
- Local divider markup replaced with the shell's `PanelSeparator{}`.
- Native `Button` evaluated and **rejected**: the tint-following accent
  styling needs per-use adapters, so `native replacement + adapters < local
  code` fails. Documented here so nobody re-tries it blind.
- `MemoryChip.qml` history comments purged; the coalesced/invisible
  invariant is kept.

Net: `Panel.qml` 444 → 405 lines.

## D — Repository and installer footprint (`DELIVERY.md`, `README.md`, `install.py`)

Why: ship less, install less.

What:

- Deleted `DELIVERY.md` (60 lines, internal handoff note, not user docs).
- `README.md` tightened (redundant About URLs / global footer removed).
- `install.py` no longer ships `README.md` in `FILES` and `update_layout()`
  collapsed from two loops to one; `tests/test_install.py` asserts the
  single-source tabs and the no-README payload.

Measured here: install payload 78252 → 76484 bytes; repo archive
194560 → 174080 bytes (-10.5%).

## Footprint (this stack, `origin/main` → tip)

| metric | before | after |
|---|---|---|
| production LOC (8 shipped files) | 1497 | 1489 |
| tests LOC (`tests/`) | 1197 | 1146 |
| install payload (7 shipped files) | 78252 B | 76484 B |
| repo archive (`git archive`) | 194560 B | 174080 B |
| snapshot metrics-only | 2162 B | 897 B |

Production LOC moves only -8 because `ram_pulse.py` grows (+26, explicit
`public_*` constructors) while `Panel.qml` shrinks (-39). The win is in
persisted keys, payload bytes, and deleted files, not raw line count.

## Behavior preservation (how to check)

- `python3 -m unittest discover -s tests` → 68 pass.
- `node --test tests/*.cjs` → 25 pass.
- `omarchy plugin validate .` → exit 0.
- Snapshot contract: `details` is exactly the six lab fields, `vm` excluded
  from publish, `swaps`/`zram`/rows/targets carry only the shapes above.
- Mutation spot-checks: restoring `vm`/`socket` to the snapshot, breaking
  `targetLabel`, or dropping `lastTab` fails the suite.
- Preserved: `prepare_state()`, `inspect_state()`, atomic publication,
  PID/start revalidation, argv-only subprocesses, failure isolation, SQLite
  parameterization, privacy (`0700`/`0600`), `Restart=on-failure`.

## Relationship to other PRs

This stack is rebased on `origin/main` and is independent of the still-open
fix PRs (#11–#14, #16). It neither includes nor requires them; where both
touch one file (e.g. `ram_pulse.py`, `Panel.qml`, `install.py`) the maintainer
should expect ordinary merge conflicts, all small and mechanical.
