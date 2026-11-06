# Rig specs

## What's supported

- Rig specs with any non-empty string `version`: {term}`pods <pod>`, {term}`members <member>`, {term}`edges <edge>`, a {term}`culture file` and
  `startup.files` at the rig, pod and member levels.
- {term}`Agent specs <agent spec>`: {term}`startup files <startup file>`, `resources.skills` with {term}`uses` for skills and {term}`guidance`, {term}`imports <import>`,
  and `model` from `defaults` or a {term}`profile`'s `preferences`. The model used is the member's, then the
  profile's, then the agent's. As in OpenRig, imports only add resources for `uses` to select, and
  can't import further specs.
- `claude-code` and `codex` seats. A `codex` seat needs a model.

A spec using anything else is refused with a clear error, including plugins, subagents, hooks and
runtime resources, startup actions, custom permission policies, services and continuity policies.

## t3rig's settings

`rig.yaml` stays exactly OpenRig's format. t3rig's own settings go in an optional
`rig.t3rig.yaml` next to it, which `t3rig validate` checks with the rig:

```yaml
tracker:
  kind: github        # or gitlab
  repo: stfngrt/t3rig
  queue_seat: dev.lead
review_rounds: 2      # an issue can override this with a "Review rounds: N" line
```

- `tracker` is the issue tracker {doc}`watch` polls: `kind` picks `gh` or `glab`, `repo` is the
  repository or project, and `queue_seat` is the seat pinged when an issue is queued. It must be one
  of the rig's seats.
- `review_rounds`, a positive integer and 2 by default, is how many review rounds a change gets.
  t3rig only checks it; the seats' instructions use it.

## How instructions are delivered

Unlike OpenRig, all instructions go in the seat's {term}`brief`, in OpenRig's {term}`layer order`, whatever
their {term}`delivery hint`, except skills, which are installed (see {doc}`skills`). Instructions are never
written to the repo, so a long-running seat can lose them when its conversation is compacted.

## Edges

`delegates_to` {term}`edges <edge>` decide who {doc}`watch` pings, and `delegates_to` cycles are refused. Otherwise
edges are only described in each seat's first message, so nothing enforces them.

See `examples/` in the repository for working specs.
