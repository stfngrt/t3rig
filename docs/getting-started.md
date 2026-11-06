# Getting started

t3rig runs [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes). Each {term}`seat` becomes a T3 {term}`thread`.

It requires [uv](https://docs.astral.sh/uv/) and a running T3 Code with the `t3` CLI.

```sh
git clone https://github.com/stfngrt/t3rig
cd t3rig
uv run t3rig --version
```

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
