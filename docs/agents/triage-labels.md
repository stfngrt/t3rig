# Triage labels

The vendored skills speak in terms of Matt Pocock's five triage roles. This file maps the ones they
use onto this repo's labels (`rigs/self/agents/*/skills/`; the `triage` skill itself isn't installed,
because its state machine would add labels this rig doesn't use).

| Role in the skills | Label in this repo | Meaning |
| --- | --- | --- |
| `ready-for-agent` | `needs-approval` | A ticket or spec `dev.pm` has finished and the operator hasn't approved. It does not reach `dev.lead` until the operator adds `rig-queue` |
| `needs-info` | `needs-answer` | `dev.pm` is waiting on the operator's answer to a question in a comment |
| `needs-triage`, `ready-for-human` | none | Not used |
| `wontfix` | `wontfix` (the GitHub default) | Used only when closing without action, with a comment |

When a skill mentions a role (for example "apply the AFK-ready triage label"), use the label from
this table.

## Labels that drive the rig

| Label | Added by | Meaning |
| --- | --- | --- |
| `needs-approval` | `dev.pm` | Finished; waiting for the operator |
| `rig-queue` | the operator only | Approved; `dev.lead` takes these in issue-number order |
| `in-progress` | `dev.lead` | Being worked on |
| `blocked` | `dev.lead` | Couldn't be finished |
| `needs-answer` | `dev.pm` (or `dev.lead`) | Has questions for the operator; stays open until answered. Whoever acts on the answer (the lead or `dev.pm`) removes it |
| `wayfinder:map`, `wayfinder:<type>` | `dev.pm` | A wayfinder map or one of its decision tickets; never `rig-queue` |

`needs-approval` is never removed by `dev.pm`. `rig-queue` wins: when `dev.lead` takes a `rig-queue`
issue, it removes `needs-approval` in the same edit that adds `in-progress`.

`docs/design/planning.md` proposes different meanings for these labels (`needs-approval` there is a
state of the plan-approval machine). The two are to be settled with #3; until then this file is what
the rig follows.
