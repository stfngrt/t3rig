# Triage labels

The vendored skills speak in terms of Matt Pocock's five triage roles. This file maps the ones they
use onto this repo's labels (`rigs/self/agents/*/skills/`; the `triage` skill itself isn't installed,
because its state machine would add labels this rig doesn't use).

| Role in the skills | Label in this repo | Meaning |
| --- | --- | --- |
| `ready-for-agent` | `needs-approval` | A ticket or spec `dev.pm` has finished and the operator hasn't approved. It does not reach `dev.lead` until the operator, or `dev.pm` on their word, adds `rig-queue` |
| `needs-info` | `needs-answer` | A seat is waiting on the operator's answer to a question in a comment |
| `needs-triage`, `ready-for-human` | none | Not used |
| `wontfix` | `wontfix` (the GitHub default) | Used only when closing without action, with a comment |

When a skill mentions a role (for example "apply the AFK-ready triage label"), use the label from
this table.

## Labels that drive the rig

| Label | Added by | Meaning |
| --- | --- | --- |
| `needs-approval` | `dev.pm` | Finished; waiting for the operator |
| `rig-queue` | the operator, or `dev.pm` on their word | Approved; `dev.lead` takes these in the order of the project board (see `issue-tracker.md`) |
| `in-progress` | `dev.lead` | Being worked on |
| `needs-answer` | `dev.pm` or `dev.lead` | Has questions for the operator, including why the lead couldn't finish; stays open until answered. The operator answers with `dev.pm`, which writes the answers on the issue and removes it |
| `wayfinder:map`, `wayfinder:<type>` | `dev.pm` | A wayfinder map or one of its decision tickets; never `rig-queue` |

These four (`needs-approval`, `rig-queue`, `in-progress`, `needs-answer`) are the whole state set;
there is no `blocked` label. Adding `rig-queue` is the only approval.

`needs-approval` is never removed by `dev.pm`. `rig-queue` wins: when `dev.lead` takes a `rig-queue`
issue, it removes `needs-approval` in the same edit that adds `in-progress`.

`t3rig watch` pings `dev.lead` when an issue gains `rig-queue`, and the seat that asked when
`needs-answer` is removed (see `docs/design/planning.md`). An answered lead question resumes without
`rig-queue`: `dev.lead` adds `in-progress` back and continues the issue.

## Who closes issues

`dev.lead` closes, with a short comment saying why:

- finished code work, when its pull request merges;
- design and research issues once the operator's decision is recorded, linking the follow-up ticket
  if there is one;
- parent issues once all their children are closed and nothing in them is left;
- denied or canceled work, once `dev.pm` has recorded that decision on the issue.

The operator may close anything themselves. `dev.pm` records answers and decisions and removes
`needs-answer`; it closes an issue only when the operator asks it to.
