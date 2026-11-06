# Changelog

All notable changes to t3rig. Versions follow [Semantic Versioning](https://semver.org/); while
the version is 0.x, a minor version can change behaviour.

## Unreleased

Nothing yet.

## 0.1.0 (not yet released)

The first version, and the first on PyPI. It runs
[OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on [T3
Code](https://t3.codes), with every seat as a T3 thread.

- **Commands:** `validate`, `up`, `run`, `ps`, `send`, `log`, `stop`, `down`, `watch`, `serve` and
  `login`.
- **Rig specs:** OpenRig's pods, members, edges, culture and startup files, and agent specs with
  skills, guidance and imports. Anything outside the supported subset is refused.
  t3rig-only settings live in `rig.t3rig.yaml`.
- **Permissions:** `permission_policy` maps to T3 runtime modes, and seats can set a model and
  effort.
- **Skills:** declared skills are installed into each seat's working folder, with a plan to confirm
  first.
- **watch:** pings a seat's dispatcher when the seat finishes a run or needs input, pings the queue
  seat when an issue is queued or answered on GitHub or GitLab, and sends a notify seat notices
  when the rig needs a person.
- **serve and run:** the watch loop with a live, read-only status page. `run` brings the rig up
  first. One `watch`, `serve` or `run` works on a rig at a time.
- **Packaging:** MIT licensed, installable with `uv tool install 't3rig[serve]'`.
- **Docs:** a Sphinx site at <https://stfngrt.github.io/t3rig/> with a glossary and decision
  records.
