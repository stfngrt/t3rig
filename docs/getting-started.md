# Getting started

t3rig runs [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes). Each {term}`seat` becomes a T3 {term}`thread`.

It requires [uv](https://docs.astral.sh/uv/) and a running T3 Code with the `t3` CLI.

## Basic commands

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig up examples/two-seat/rig.yaml         # start a thread per seat; safe to re-run
uv run t3rig ps examples/two-seat/rig.yaml         # status, model, mode and links; --json too
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"        # add --wait for the reply
uv run t3rig send examples/two-seat/rig.yaml --pod dev "Hello"       # or --all for every seat
uv run t3rig log examples/two-seat/rig.yaml dev.impl                 # latest messages
```

`validate` checks that t3rig can run the spec. `up` starts a thread for each seat that doesn't have one.
See the {doc}`CLI reference <cli>` for every option.

## Messages

Messages carry a `From:`/`To:` header (the {term}`envelope`) unless you pass `--raw`. Seats are told to name themselves with
`--from`, and a send without it says `From: operator` (the {term}`operator`). It's self-declared, so treat it as a label
rather than proof of who sent the message.

## Seat threads

A seat's thread is the one titled `pod-member@rig` (its {term}`session name`), so renaming a thread
disconnects it from its seat.

Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat is
told to change to it.
