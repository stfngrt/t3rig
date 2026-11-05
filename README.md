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
uv run t3rig log examples/two-seat/rig.yaml dev.impl                 # latest messages; --messages N (default 10)
```

Messages carry a `From:`/`To:` header unless you pass `--raw`. Seats are told to name themselves with
`--from`. It's self-declared, so treat it as a label rather than proof of who sent the message.

### Permissions and stopping

Seats with a `permission_policy` or `effort`, and `t3rig down`, use T3's `/mcp` tools, which need a
sign-in. Other seats use the `t3` CLI and need none, but run in T3's default mode, which may be full
access.

```sh
uv run t3rig login --access auto                    # seats can't launch above this level
uv run t3rig up examples/restricted/rig.yaml        # lead at auto, review at approval-required
uv run t3rig down examples/restricted/rig.yaml      # interrupt and archive; add --seat pod.member
```

| `permission_policy` | T3 mode | Roughly |
|---|---|---|
| `builtin:locked` | `approval-required` | Anything that changes something waits for a person |
| `builtin:standard` | `auto-accept-edits` | File edits run; other commands can wait |
| `builtin:open`, `builtin:auto` | `auto` | Runs on its own, with T3's own checks |
| `builtin:yolo` | `full-access` | Runs anything |

This is an approximation: OpenRig's policies are finer-grained rules and T3 has four modes, so custom
policy files are refused. A member's policy overrides the rig's. Each seat launches idle, and its first
message is sent only after T3 confirms its mode, provider, model and effort. A mismatch is archived.

The credential is kept in `~/.config/t3rig/credentials.json`, readable only by you, for 30 days. Stop
`watch` before `down`, or its pings to the archived dispatcher will fail.

Modes aren't a security boundary. They make a seat ask before acting, but `locked` seats still run
read-only commands, and a seat allowed to run shell commands could use your `t3` CLI or credential.
Restricted seats also have to ask before running `t3rig send`, so `watch` is how they report back.

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
- A failed ping is retried on the next check, and prints an `ALERT` after three failures. A stuck
  seat with no dispatcher also prints one, and so does a seat stopped at a usage limit, which `watch`
  recognizes from the wording of its last reply.
- It keeps what it has pinged in a small file under `~/.local/state/t3rig/`, so a restart neither
  repeats old pings nor misses new ones. A crash can repeat a ping, but not lose one.
- It only works while running. It's a foreground command, not a daemon.
- It polls, every 15 seconds by default (`--interval`), so a ping can lag by that much.
- A dispatcher can see that a seat is waiting but can't answer for it. A person answers in T3.
  T3's tools let an agent answer questions, but not approve permission requests.

A seat's thread is the one titled `pod-member@rig` (OpenRig's seat name), so renaming a thread
disconnects it from its seat.

## What's supported

- Rig specs at version `0.2`: pods, members, edges, `culture_file` and `startup.files` at the rig,
  pod and member levels.
- Agent specs: `startup.files`, `uses.guidance`, `imports`, and `model` from `defaults` or a
  profile's `preferences`. The model used is the member's, then the profile's, then the agent's.
  As in OpenRig, imports only add resources for `uses` to select, and can't import further specs.
- `claude-code` and `codex` seats. A `codex` seat needs a model.

A spec using anything else is refused with a clear error, including skills, plugins, startup actions,
custom permission policies, services and continuity policies.

Unlike OpenRig, all instructions go in the seat's first message, in OpenRig's layer order, whatever
their `delivery_hint`. Nothing is written to the repo, so a long-running seat can lose them when its
conversation is compacted.

## Limits

- `delegates_to` edges decide who `watch` pings. Otherwise edges are only described in each seat's
  first message, so nothing enforces them. `delegates_to` cycles are refused.
- Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat
  is told to change to it.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run t3rig --version
uv run pytest
uv run ruff check .
```
