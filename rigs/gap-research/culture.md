# Gap research team

Goal: find the feature gap between t3rig (this repo) and OpenRig
(read-only checkout at /home/dev/dev/projects/openrig).

## Rules

- This is research. Do not edit either repo, create threads, or run `rig` or `t3rig up`.
- Write only under /tmp/t3rig-gap/.
- Base claims on code or docs you read, and cite `path:line`. Mark anything you couldn't confirm
  as unverified. Don't pad: say so when a feature is small or doesn't matter.
- Don't use `--wait` when messaging another seat. Finish your turn and let replies arrive.

## Roles

- research.lead: hands out work, combines the reports, and writes the final report.
- research.spec: the rig and agent spec formats. What OpenRig accepts and t3rig refuses or ignores.
- research.runtime: seat lifecycle, restore and continuity, compaction, handover, permissions,
  activity and attention tracking, startup and skill placement.
- research.surfaces: agent coordination (chatrooms, queues, `rig_*` MCP tools, workflows), the
  CLI command set, TUI and UI, Slack, services, snapshots, multi-host.

## For every gap, record

- What OpenRig does, and what t3rig does today.
- T3 coverage: does T3 Code already provide it natively (`t3 --help`, its MCP tools)? Answer
  yes, partly, no or unverified.
- Value to someone running agent teams in T3: high, medium or low.
- Effort for t3rig in Python: small, medium or large.
- A recommendation: build, use T3's version, or skip.
