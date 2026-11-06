# Compared with OpenRig

t3rig runs [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files as T3 Code
{term}`threads <thread>`. OpenRig is a Node daemon with its own CLI, TUI and tmux sessions, so many
differences follow from T3 being the runtime. This page records which gaps t3rig closes, which it
handles differently on purpose, and which are out of scope. It's a map, not a feature-by-feature
audit, and it was last reviewed on 2026-11-06 in
[#6](https://github.com/stfngrt/t3rig/issues/6) against OpenRig v0.7.5.

| Area | OpenRig | t3rig | Decision |
|---|---|---|---|
| Runtime and host | A long-running daemon over tmux/Herdr terminal sessions | T3 threads are the runtime. {doc}`serve` runs the orchestration loop and a status page | Closing: `t3rig run` ([#21](https://github.com/stfngrt/t3rig/issues/21)) |
| Harnesses | Claude Code, Codex, community presets, ACP and A2A agents, hosted members | `claude-code` and `codex` | Later: follows what T3 supports |
| Rig spec coverage | Plugins, subagents, hooks, runtime resources, startup actions, services, continuity policies, bundles | The subset in {doc}`rig-specs`. t3rig-only settings live in `rig.t3rig.yaml` | Later, per feature |
| Instruction delivery | Per-layer `delivery_hint` and managed guidance files | Everything goes in the {term}`brief`, so it can be lost on compaction | Closing: seat memory, `refocus` and `handover` ([#5](https://github.com/stfngrt/t3rig/issues/5)), per-seat skills ([#7](https://github.com/stfngrt/t3rig/issues/7)) |
| Permissions | Fine-grained and custom policies | Four T3 {term}`runtime modes <runtime mode>` ({doc}`permissions`) | Out of scope: T3 owns permissions |
| Edges | Edge types with enforced meaning | Only `delegates_to` has an effect | Later |
| Coordination | A durable queue, inbox and outbox with transactional handoff | GitHub or GitLab issues are the queue, with four labels, `watch` pings, and a worktree and pull request per issue ({doc}`design/planning`) | Done differently |
| Human control | Mission Control verbs with an audit table | The operator talks to the project-manager seat, which records decisions on issues. Adding `rig-queue` is the only approval | Done differently |
| Notifications | ntfy, webhooks, Slack | Pings to seats' T3 threads | Closing: notices through T3 ([#22](https://github.com/stfngrt/t3rig/issues/22)) |
| Workflows | A workflow runtime with packets and lifecycle graphs | The issue flow, described in the roles | Out of scope |
| SDLC tooling | Missions, slices, `rig proof` with judges, planning dial | The planning dial as guidance, pull request review, lessons, vendored skills | Done differently. Proof judges: later |
| Lifecycle | Snapshot, restore, fork, grow, shrink, adopt, reconcile | `up`, `stop`, `down` | Closing: `handover` ([#5](https://github.com/stfngrt/t3rig/issues/5)). Snapshot and fork: out of scope, because T3 owns threads |
| Observability | TUI, web UI, views, transcripts, telemetry, doctor | `ps` (with `watch` health), `log` (also on an earlier thread by id), the {doc}`serve` page, and thread links on every post and commit | Done: traceable sessions and `watch` health ([#18](https://github.com/stfngrt/t3rig/issues/18)). Closing: redesign ([#19](https://github.com/stfngrt/t3rig/issues/19)). Cost per seat: later |
| Distribution | Bundles, a specs registry, an installer | Run from a checkout with `uv` | Closing: `t3rig init` ([#23](https://github.com/stfngrt/t3rig/issues/23)) |
| Multi-host | Cross-host routing and remote actions | One T3 environment | Later: T3 can already link environments |
| Workspaces | A workspace and project catalog | A seat's `cwd` must be inside a T3 project; a worktree per issue | Later |
| Identity | Sender identity with provenance modes | GitHub posts go out under the operator's account with a `🤖 <seat>` line | Closing: a GitHub App ([#24](https://github.com/stfngrt/t3rig/issues/24)) |
