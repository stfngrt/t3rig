# Getting started

t3rig runs [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes). Each {term}`seat` becomes a T3 {term}`thread`.

It requires [uv](https://docs.astral.sh/uv/) and a running T3 Code with the `t3` CLI.

## Install

Run it from a checkout:

```sh
git clone https://github.com/stfngrt/t3rig
cd t3rig
uv run t3rig --version   # `uv sync` includes the serve extra, which `run` and `serve` need
```

Once t3rig is on PyPI, `uv tool install 't3rig[serve]'` will install it as a command, and you'll
run `t3rig` instead of `uv run t3rig`. It isn't published yet.

## Run a rig

```sh
uv run t3rig run examples/two-seat/rig.yaml
```

`run` is the one command to start with. It does what `up` does, starting a T3 {term}`thread` for
each seat that doesn't have one, and then what `serve` does: it runs the {term}`watch` loop and
the {doc}`status page <serve>` at `http://127.0.0.1:8765/`, in the foreground. Ctrl-C stops the
loop and the page and leaves the seats running; `t3rig down` stops the seats.

- Like `up`, it shows the skills it would install and stops, without serving, unless you add
  `--yes` (see {doc}`skills`).
- It takes `serve`'s options: `--port`, `--host`, `--interval` and `--tracker-interval`.
- Only one `run`, `serve` or `watch` works on a rig at a time. A second one exits and says which
  process holds the rig, for example
  `another t3rig run (pid 1234) is already running for this rig`.
- It needs the serve extra, as `serve` does: `uv sync --extra serve` (plain `uv sync` includes it).

## Basic commands

The pieces `run` puts together, and the commands for talking to seats:

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig up examples/two-seat/rig.yaml         # start a thread per seat; safe to re-run
uv run t3rig up examples/skills/rig.yaml --yes     # also install the rig's skills; see Skills
uv run t3rig ps examples/two-seat/rig.yaml         # status, model, mode and links; --json too
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"        # add --wait for the reply
uv run t3rig send examples/two-seat/rig.yaml --pod dev "Hello"       # or --all for every seat
uv run t3rig log examples/two-seat/rig.yaml dev.impl                 # latest messages; --messages N (default 10, at least 1)
uv run t3rig log examples/two-seat/rig.yaml dev.impl --thread <id>   # an earlier thread, such as one `down` archived
```

`validate` checks that t3rig can run the spec. `up` starts a thread for each seat that doesn't have
one, and {doc}`watch` and {doc}`serve` keep the rig going without bringing it up.
See the {doc}`CLI reference <cli>` for every option.

## Messages

Messages carry a `From:`/`To:` header (the {term}`envelope`) unless you pass `--raw`. Seats are told to name themselves with
`--from`, and a send without it says `From: operator` (the {term}`operator`). It's self-declared, so treat it as a label
rather than proof of who sent the message.

## Seat threads

A seat's thread is the one titled `pod-member@rig` (its {term}`session name`), so renaming a thread
disconnects it from its seat.

`ps` and `log` use the newest thread with that title. `down` archives threads, and T3 doesn't list
archived threads, so t3rig can't find a seat's earlier threads by itself. Given a thread id, for
example from a link in an issue comment or a commit's `Rig-Session` trailer, `log --thread <id>`
shows that thread, if T3 still serves it. It refuses a thread whose title isn't the seat's session
name.

Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat is
told to change to it.

## Task threads

A seat named in `per_task` in `rig.t3rig.yaml` (see {doc}`rig-specs`) gets a new
{term}`task thread` per task instead of one long-lived thread. Its title is the session name plus
the task, such as `dev-impl@self #18` or `dev-review@self #18 r2`. `up` doesn't start these seats.
The seat that delegates to them does, one task at a time:

```sh
uv run t3rig send rig.yaml dev.impl --new --task "#18" "Build #18 in .worktrees/18"
uv run t3rig send rig.yaml dev.impl --task "#18" "Fix the review findings"
uv run t3rig send rig.yaml dev.review --new --task "#18 r2" "Review round 2"
uv run t3rig down rig.yaml --task "#18"   # archive every task thread of #18, all rounds
```

- `send --new --task` starts the thread with the seat's brief, which names the task, and the seat's
  model, effort and runtime mode, as `up` would; then it sends the message. It refuses a task that
  already has a live thread, and more issues at once than `max_parallel`.
- `send --task`, `log --task` and `stop --task` reach a live task thread. Without `--task` they use
  the seat's only live task thread, and list them if there are several.
- `ps`, the {doc}`status page <serve>` and {doc}`watch` show and follow each live task thread under
  its seat, and a ping names the task: `dev.impl #18 finished a run`.
