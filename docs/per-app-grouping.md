# Per-app grouping for the RAM hoarders view

Status: proposal, not implemented. Measured on `dex` (31 GiB, 369 processes,
122 owned by the user) on 6 September 2026.

## What is wrong today

`hoarders()` (`ram_pulse.py:113`) returns a flat list of processes sorted by
`VmRSS`, and `Panel.qml:232` pages through it eight at a time. One application
therefore occupies several rows. A live capture of the current list:

```
01  voxtype   · 1705      1003.0 MiB
02  quickshell · 1934221   981.1 MiB
03  grok      · 1060239    771.5 MiB
04  brave     · 18496      766.1 MiB
05  grok      · 1136228    752.8 MiB
06  brave     · 18111      541.0 MiB
07  claude    · 1448258    474.1 MiB
08  claude    · 1112044    443.0 MiB
```

Three applications take six of the eight rows, and the reader has no way to
answer "how much is Brave costing me" without adding numbers that must not be
added.

## Why the numbers must not be added

`VmRSS` counts every resident page in every process that maps it. A browser's
helpers share their executable, their fonts and large parts of their heap
allocator with the parent, so summing RSS across a process family overstates
the total, sometimes by more than a factor of two. `Panel.qml:260` already says
this in the footer, and the footer is correct.

The measure that does sum is PSS, the proportional set size, where each shared
page is divided by the number of processes mapping it. `hoarders()` already
reads it, at `ram_pulse.py:128`, but only for the 24 rows it is about to
return, and the UI only shows it when a row has no window to focus.

Grouping therefore has to be a collector change, not a UI change: the group
total has to be a sum of PSS, and PSS has to be available for every member of
every group shown, not just for the top 24 processes overall.

## What the grouping key should be

Three candidates, tested against the live process table.

**Process name is too coarse.** Two `claude` processes above are unrelated
sessions in different terminals. Merging them by name would invent a
relationship that does not exist.

**The systemd cgroup is close but not exact.** Reading `/proc/<pid>/cgroup`
gives a per-launch scope:

```
   553.9 MiB  brave      app-Hyprland-brave\x2damd-97f4342a.scope
   259.0 MiB  brave      app-Hyprland-brave\x2damd-97f4342a.scope
   257.5 MiB  brave      app-Hyprland-brave\x2damd-97f4342a.scope
   548.2 MiB  brave      app-org.chromium.Chromium-18111.scope
   842.7 MiB  grok       app-Hyprland-xdg\x2dterminal\x2dexec-bf02fda7.scope
   766.8 MiB  grok       app-Hyprland-xdg\x2dterminal\x2dexec-b3b7b5c9.scope
```

Three of the four Brave processes collapse correctly. The fourth was launched
another way and sits in its own scope, so cgroup grouping would show two Brave
groups. The two `grok` terminals land in separate scopes, which is right.

**The resolved window is the best key for this view.** `window_for()`
(`ram_pulse.py:65`) already walks the parent chain to the Hyprland client that
owns a process, which is why browser helpers already navigate to their browser
window today. Every row in this list exists to be clicked, and clicking focuses
a window, so one row per focusable window is exactly the grouping the view
wants.

Recommended key, in order:

1. the address of the window `target_for()` resolves for the process,
2. otherwise the systemd cgroup scope leaf,
3. otherwise the process itself, ungrouped, as today.

Herdr and tmux panes already resolve through the same function, so a pane's
processes group under the pane rather than under the terminal emulator.

## What it costs

The objection to grouping has always been the price of PSS. Measured, it is
smaller than assumed. Times are for one pass over the whole process table:

| read | cost | notes |
|---|---|---|
| `status` for all 369 pids | 11.3 ms | what the collector already pays |
| `cgroup` for all 369 pids | 8.1 ms | the fallback grouping key |
| `smaps_rollup` for the top 24 by RSS | 95.8 ms | what the collector already pays |
| `smaps_rollup` for the top 40 by RSS | 120.3 ms | enough to fill eight groups |
| `smaps_rollup` for every readable pid | 139.9 ms | 114 of 369 are readable |

Going from PSS for the top 24 processes to PSS for every process the user owns
costs **about 45 ms more, once every nine seconds** — roughly half a percent of
one core, inside a background daemon that already sleeps most of its cycle
(`ram_pulse.py:210`). That is affordable, and it removes the need for any
staged or partial scheme.

One caveat that is not visible in the timings: reading `smaps_rollup` takes the
target's `mmap_lock`, so it contends with a process that is actively mapping or
unmapping memory. For a busy browser this is short but real. Reading every nine
seconds rather than every cycle keeps it well clear of anything noticeable.

## Where PSS is unavailable

Only 114 of 369 processes are readable by this user; the rest belong to other
users, mostly root. `smaps_rollup` returns nothing for those, so a group that
contains one has no honest total. The existing code already models this: `pss`
is `None` when the read fails, and the UI already prints "unavailable". A
group in that state must show its RSS with the shared-page caveat rather than a
sum, and must not be ranked against groups that have a real PSS total.

## Sketch of the change

In `ram_pulse.py`:

- `hoarders()` reads PSS for every owned process, not the top 24, and keeps
  `rss`, `swap` and `pss` per process as it does now.
- A new grouping pass keys each process by the rule above, and emits one entry
  per group: the leader's name and target, the member count, the summed PSS,
  the summed swap, and the largest single RSS in the group for the bar width.
- Groups are ranked by summed PSS. Groups with any unreadable member are ranked
  by RSS and flagged.
- The flat list stays in the payload so the change is reversible from the UI.

In `Panel.qml`:

- The row gains a member count ("Brave · 4 processes") and shows the group's
  PSS as the headline number, with RSS available on the row.
- A toggle switches between grouped and flat. The footer text at `Panel.qml:260`
  changes when grouped: summed PSS may be added together, which is the whole
  point of the change.

## Open question for the author

Grouping by window means an application with two windows shows as two rows.
For Brave that is probably right — two windows are two things to click. For a
single application spread over many windows it may not be. The alternative is
to group by cgroup scope first and fall back to the window, which merges
windows of one launch but splits differently-launched instances of one app.
Both are defensible; this needs a decision before implementation.
