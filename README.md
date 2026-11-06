<img src="https://raw.githubusercontent.com/stfngrt/t3rig/main/assets/icon.svg" width="64" height="64" alt="">

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
uv tool install 't3rig[serve]'   # with the status page, which `t3rig run` needs
t3rig --version
```

`uv tool install t3rig` installs it without the status page (`run` and `serve`). It needs Python
3.13; add `--python 3.13` if uv picks an older one. To work on t3rig itself, clone the repository
and use `uv run t3rig` there.

## Quick start

With a rig spec, such as [`examples/two-seat/rig.yaml`](https://github.com/stfngrt/t3rig/blob/main/examples/two-seat/rig.yaml):

```sh
t3rig validate rig.yaml               # check the spec; starts nothing
t3rig run rig.yaml                    # start the seats and keep them going
t3rig send rig.yaml dev.impl "Hello"  # in another terminal
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

- [`docs/development.md`](https://github.com/stfngrt/t3rig/blob/main/docs/development.md): the checks to run, the docs build, and how the self
  rig works
- [`docs/glossary.md`](https://github.com/stfngrt/t3rig/blob/main/docs/glossary.md): the project's terms
- [`docs/adr/`](https://github.com/stfngrt/t3rig/blob/main/docs/adr/index.md): decisions already made
