<img src="assets/icon.svg" width="64" height="64" alt="">

# t3rig

Run [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes), with every seat as a T3 thread. There is no tmux and no daemon.

Status: early, simple version. It has been run on a two-seat Claude rig.

## Usage

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig up examples/two-seat/rig.yaml         # start a thread per seat; safe to re-run
uv run t3rig ps examples/two-seat/rig.yaml         # show status and thread links
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"        # add --wait for the reply
```

A seat's thread is the one titled `pod-member@rig` (OpenRig's seat name), so renaming a thread
disconnects it from its seat. No state is kept outside T3.

## What's supported

- Rig specs at version `0.2`: pods, members, edges and `culture_file`.
- `claude-code` and `codex` seats. A `codex` seat must set `model`.

A spec using anything else is refused with a clear error, including skills and other agent
resources, startup files, services, continuity policies and permission settings.

## Limits

- Edges are only described in each seat's first message, so nothing enforces them.
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
