<img src="assets/icon.svg" width="64" height="64" alt="">

# t3rig

Run [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes), with every seat as a T3 thread. There is no tmux and no daemon.

Status: early, simple version. It has been run on a two-seat Claude rig.

## Usage

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig up examples/two-seat/rig.yaml         # start a thread per seat; safe to re-run
uv run t3rig ps examples/two-seat/rig.yaml         # status, model, mode and links; --json too
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"        # add --wait for the reply
uv run t3rig send examples/two-seat/rig.yaml --pod dev "Hello"       # or --all for every seat
```

Messages carry a `From:`/`To:` header unless you pass `--raw`. Seats are told to name themselves with
`--from`. It's self-declared, so treat it as a label rather than proof of who sent the message.

### Pinging the dispatcher

`t3rig watch` keeps a seat's dispatcher informed, so nothing depends on an agent remembering to
report back. A seat's dispatcher is the seat with a `delegates_to` edge to it.

```sh
uv run t3rig watch examples/two-seat/rig.yaml
```

- It pings when a seat finishes a run, including a failed one, and when a seat has a question or
  approval waiting. Seats that change together share one ping. A seat's reply to its first message
  doesn't count.
- A ping is a short pointer with a one-line excerpt and a link. The dispatcher reads the thread for
  the rest.
- A failed ping is retried on the next check, and prints an `ALERT` after three failures. So does a
  stuck seat with no dispatcher.
- It keeps what it has pinged in a small file under `~/.local/state/t3rig/`, so a restart neither
  repeats old pings nor misses new ones. A crash can repeat a ping, but not lose one.
- It only works while running. It's a foreground command, not a daemon.
- It polls, every 15 seconds by default (`--interval`), so a ping can lag by that much.
- A dispatcher can see that a seat is waiting but can't answer for it. A person answers in T3.

A seat's thread is the one titled `pod-member@rig` (OpenRig's seat name), so renaming a thread
disconnects it from its seat.

## What's supported

- Rig specs at version `0.2`: pods, members, edges and `culture_file`.
- `claude-code` and `codex` seats. A `codex` seat must set `model`.

A spec using anything else is refused with a clear error, including skills and other agent
resources, startup files, services, continuity policies and permission settings.

## Limits

- `delegates_to` edges decide who `watch` pings. Otherwise edges are only described in each seat's
  first message, so nothing enforces them. `delegates_to` cycles are refused.
- Threads run in T3's default runtime mode, which may be full access. A rig's permission settings
  aren't supported.
- Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat
  is told to change to it.
- There's no `down` yet, because the `t3` CLI can't archive threads. Archive them in T3 instead; the
  next `up` starts those seats fresh.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run t3rig --version
uv run pytest
uv run ruff check .
```
