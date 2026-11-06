<img src="assets/icon.svg" width="64" height="64" alt="">

# t3rig

Run [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes), with every seat as a T3 thread. There is no tmux and no daemon:
`t3rig run` starts a thread per seat and keeps the rig going, pinging a seat's dispatcher when work
finishes and serving a status page; `send`, `log` and `ps` talk to the seats.

Status: early, simple version. It has been run on a two-seat Claude rig.

**Documentation: <https://stfngrt.github.io/t3rig/>**

## Install

Requires [uv](https://docs.astral.sh/uv/) and a running T3 Code with the `t3` CLI.

```sh
git clone https://github.com/stfngrt/t3rig
cd t3rig
uv run t3rig --version
```

## Quick start

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig run examples/two-seat/rig.yaml        # start the seats and keep them going
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"   # in another terminal
```

## Docs

- [Getting started](https://stfngrt.github.io/t3rig/getting-started.html)
- [Rig specs](https://stfngrt.github.io/t3rig/rig-specs.html): what's supported, and `rig.t3rig.yaml`
- [Permissions and stopping](https://stfngrt.github.io/t3rig/permissions.html)
- [Pinging the dispatcher](https://stfngrt.github.io/t3rig/watch.html) (`watch`)
- [Status page](https://stfngrt.github.io/t3rig/serve.html) (`serve`)
- [Skills](https://stfngrt.github.io/t3rig/skills.html)
- [Limits](https://stfngrt.github.io/t3rig/limits.html)
- [CLI reference](https://stfngrt.github.io/t3rig/cli.html)
- [Development](https://stfngrt.github.io/t3rig/development.html): checks, the docs build and the
  self rig

## Working on t3rig

`rigs/self` develops t3rig with t3rig. Its seats, and anyone changing the code, should read these
in the repo:

- [`docs/development.md`](docs/development.md): the checks to run, the docs build, and how the self
  rig works
- [`docs/glossary.md`](docs/glossary.md): the project's terms
- [`docs/adr/`](docs/adr/index.md): decisions already made
