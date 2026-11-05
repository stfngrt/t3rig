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

## Failures and alerts

- A failed ping is retried on the next check, and prints an `ALERT` after three failures. A
  {term}`stuck seat` with no dispatcher also prints one, and so does a seat stopped at a usage
  limit, which `watch` recognizes from the wording of its last reply.

## State

It keeps what it has pinged in a small file under `~/.local/state/t3rig/`, so a restart neither
repeats old pings nor misses new ones. A crash can repeat a ping, but not lose one.

## Running it

- It only works while running. It's a foreground command, not a daemon.
- It polls, every 15 seconds by default (`--interval`), so a ping can lag by that much.

## Approvals

A dispatcher can't approve for a seat, and T3's tools don't let an agent do so. A person answers in
T3. When signed in, the ping says what command the seat is waiting on and how to `t3rig stop` it, so
the dispatcher can stop that run and send other instructions instead. Stopping doesn't approve
anything, and the seat can't run the command.
