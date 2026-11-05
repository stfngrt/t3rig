# Rig specs

## What's supported

- Rig specs with any non-empty string `version`: pods, members, edges, `culture_file` and
  `startup.files` at the rig, pod and member levels.
- Agent specs: `startup.files`, `resources.skills` with `uses.skills`, `uses.guidance`, `imports`,
  and `model` from `defaults` or a profile's `preferences`. The model used is the member's, then the
  profile's, then the agent's. As in OpenRig, imports only add resources for `uses` to select, and
  can't import further specs.
- `claude-code` and `codex` seats. A `codex` seat needs a model.

A spec using anything else is refused with a clear error, including plugins, subagents, hooks and
runtime resources, startup actions, custom permission policies, services and continuity policies.

## How instructions are delivered

Unlike OpenRig, all instructions go in the seat's first message, in OpenRig's layer order, whatever
their `delivery_hint`, except skills, which are installed (see {doc}`skills`). Instructions are never
written to the repo, so a long-running seat can lose them when its conversation is compacted.

## Edges

`delegates_to` edges decide who {doc}`watch` pings, and `delegates_to` cycles are refused. Otherwise
edges are only described in each seat's first message, so nothing enforces them.

See `examples/` in the repository for working specs.
