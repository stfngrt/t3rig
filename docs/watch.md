# Pinging the dispatcher

The {term}`watch` command, `t3rig watch`, keeps a seat's {term}`dispatcher` informed, so nothing
depends on an agent remembering to report back. A seat's dispatcher is the seat with a
`delegates_to` edge to it.

```sh
uv run t3rig watch examples/two-seat/rig.yaml
```

## What it pings

- It sends a {term}`ping` when a seat finishes a {term}`run`, including a failed one, and when a
  seat has a question or approval waiting. Seats that change together share one ping. A seat's reply
  to its first message doesn't count.
- A ping is a short pointer with a one-line excerpt and a link. The dispatcher reads the thread for
  the rest. A run stopped partway says so and shows no excerpt, since it has no result.

## Issue tracker pings

If the rig has a tracker in `rig.t3rig.yaml` (see {doc}`rig-specs`), `watch` also polls its open
issues and pings for two changes, and nothing else:

- An issue gains {term}`rig-queue`: it pings the tracker's `queue_seat`. An issue that already has
  the label when `watch` first sees it, for example after a restart, is pinged once, so queued work
  isn't missed, unless it also has {term}`in-progress`: that work is already under way.
- {term}`needs-answer` is removed from an open issue: it pings the seat named in the `🤖 <seat>`
  signature of the question comment, the newest signed comment when `watch` first saw the label, or
  `queue_seat` if there's none. An issue it never saw with the label gives no ping. When `dev.pm`
  asked the question, it is pinged after removing the label itself, and that ping needs no action.

A ping names the issue by its full URL. `watch` uses `gh` or `glab` with their own login, and never
changes labels or writes comments.

## Failures and alerts

- A failed ping is retried on the next check, and prints an `ALERT` after three failures. A
  {term}`stuck seat` with no dispatcher also prints one, and so does a seat stopped at a usage
  limit, which `watch` recognizes from the wording of its last reply.

## State

It keeps what it has pinged, and the labels it last saw on each tracked issue, in a small file under
`~/.local/state/t3rig/`, so a restart neither repeats old pings nor misses new ones. A crash can
repeat a ping, but not lose one.

## Running it

- It only works while running. It's a foreground command, not a daemon. `t3rig ps` says whether a
  `watch` or `serve` is running for the rig (it holds the rig's lock) and when it last checked, and
  `ps --json` has both as `watch_running` and `watch_last_check`. Both are keyed by the rig file's
  path, so run `ps` on the same `rig.yaml` path that `watch` was started with: another copy of the
  rig, such as one in a git worktree, says `watch` isn't running.
- It polls, every 15 seconds by default (`--interval`), so a ping can lag by that much. The
  tracker is polled every 60 seconds by default (`--tracker-interval`), a guess still to be
  measured against the tracker's rate limits.

## Approvals

A dispatcher can't approve for a seat, and T3's tools don't let an agent do so. A person answers in
T3. When signed in, the ping says what command the seat is waiting on and how to `t3rig stop` it, so
the dispatcher can stop that run and send other instructions instead. Stopping doesn't approve
anything, and the seat can't run the command.
