# Planned, tracked work (proposal for #3)

**Status: proposal. Nothing here is implemented.** Everything marked *Recommendation* is for the
operator to approve or change.

## Goal

Let the lead work from tracked work items instead of one-off briefs, with a person approving at the
points that matter. The tracker (GitHub via `gh`, GitLab via `glab`) stays the source of truth:
there is no local database. The baseline is the manual "Ticket queue" in
`rigs/self/agents/lead/role.md`, which already uses an issue as the work item, labels as state and
comments as the record. This design makes that fixed and checkable.

## (a) What t3rig borrows from OpenRig, and what it leaves out

OpenRig is at https://github.com/mvschwarz/openrig. Citations are `path:line` in that repo.

| Borrowed | From | How t3rig uses it |
|---|---|---|
| Queue states `pending`, `in-progress`, `done`, `blocked`, `failed`, `denied`, `canceled`, `handed-off` | `docs/as-built/architecture/coordination-primitive.md:45-52` | Six become labels or closure: `pending` (`rig-queue`), `in-progress`, `blocked`, `done`, `denied`, `canceled`. `failed` and `handed-off` are left out. |
| Append-only audit of every transition | `coordination-primitive.md:53-54`, `docs/as-built/architecture/mission-control.md:144-151` | Issue comments plus the tracker's timeline. Every state change the lead or a verb makes gets one comment. This is weaker than OpenRig's log: comments can be edited or deleted, and a bare label change has no comment, only a timeline event. |
| A closure reason when an item is done | `coordination-primitive.md:268-294` | A `Closed:` line in the final comment: `done` (OpenRig `no-follow-on`), `denied`, `canceled`. `superseded` and the handoff and escalation reasons are left out. |
| Human verbs `approve`, `deny`, `hold`, `drop`, `resolve`, `answer` | `mission-control.md:88-107` | Comment commands. `route`, `handoff` and `annotate` are left out: the lead assigns work and any comment is an annotation. |
| A verb on a finished item is refused | `mission-control.md:115-116`; notes are still allowed, `coordination-primitive.md:312-314` | A command on a closed issue gets a reply comment and no state change. |
| A human gate must say what it is asking | `coordination-primitive.md:322-324` | `needs-approval` requires the plan or question in the comment above it (OpenRig's `summary`). `evidence_ref` is dropped: the comment is the evidence. |
| Notify a person once | `mission-control.md:190-203`: at most once per item and trigger per daemon run | Different guarantee: `watch` is at least once across restarts (see (e)). |
| Planning dial P0 to P4, chosen per item | `docs/reference/planning-dial.md:3-25,37-45,53-54` | Same rungs; the chosen rung is written in the plan comment. |
| Two locks only, "cut rounds, never checks"; the human records intent, agents plan and build | `docs/reference/sdlc-conventions.md:8-13,323-326,366-377` | `/approve` is the plan-lock. **Departure:** OpenRig's proof-lock (`--scope delivery`) is a human sign-off; here the lead closes after its checks pass, and the closing comment records them. |
| Approval is sign-off, never proof of green; a second approval needs a reason | `sdlc-conventions.md:379-384` | A re-approval after a changed plan needs a new `/approve`; the new plan comment is the reason. |
| Independent review, never by the writers | `docs/reference/wave-sdlc.md:64-70,141-142` | Already how `rigs/self` works (`dev.review`). |

**Left out, and why:**

- Workflow graphs and step trails
  (`docs/as-built/architecture/workflow-runtime.md:19-23,45,258-291`). A fixed label state machine
  covers this use. Revisit if a second kind of workflow appears.
- A queue database with transitions and heartbeat columns (`coordination-primitive.md:45-54`). The
  issue is the record.
- Slice files (`SPEC.md` with `## Intent`, `## Mini-requirements`, `## Proof contract`,
  `sdlc-conventions.md:108-123`) and the Part A/Part B split (`sdlc-conventions.md:16-25`). See the
  open question on repo files below.
- Actor-establishment modes (`mission-control.md:158-163`). Replaced by the tracker's own login plus
  the write-access check in (c).
- ntfy and webhook notifications. `watch` pings the lead's T3 thread instead.

## (b) Work item states and transitions

One issue is one item. State is the set of t3rig labels on it; closing the issue ends it.

| State | Labels | Meaning |
|---|---|---|
| queued | `rig-queue` | Waiting for the lead |
| planning | `rig-queue` and `in-progress` | Lead took it and has not posted a plan |
| awaiting approval | `needs-approval` | Lead posted a plan, or a question asked before any plan was approved |
| in progress | `in-progress` | Plan approved (or P0), being built |
| blocked | `blocked` | Parked: the lead can't finish, a question asked mid-build, or `/hold` |
| done, denied, canceled | issue closed | `Closed: done`, `Closed: denied` or `Closed: canceled` |

An open item is in exactly one of these states. Planning is the only one with two labels; it is the
baseline's "take the issue" step.

```text
queued --lead takes--> planning
planning --plan posted--> awaiting approval        planning --P0 allowed--> in progress
planning --Question:--> awaiting approval --/answer--> planning   (a plan must still be posted)
in progress --Question:--> blocked --/answer--> in progress
awaiting approval --/approve--> in progress
awaiting approval --/deny--> closed (denied)
in progress --plan changes--> awaiting approval    (new plan, new /approve)
in progress --checks pass--> done
in progress --lead can't finish--> blocked
any open state except blocked --/hold--> blocked --/resolve--> queued
any open state --/drop--> closed (canceled)
```

A question is a lead comment starting `Question:`. Asked while planning, the item goes to awaiting
approval, and `/answer` returns it to planning: the lead must still post a plan, which needs its own
`/approve`. Asked while building, the item goes to blocked, and `/answer` returns it to in progress.
So `/answer` is for question-blocked items and `/resolve` for other blocked items. Blocking on a
question is new compared with the baseline, which picks the most conservative option and goes on.

The lead makes these transitions: take, post a plan, plan changes, P0 start, block, ask a question
and finish. Only a person's verb comment makes `approve`, `deny`, `answer`, `hold`, `drop` and
`resolve` transitions.

## (c) Human verbs and how a person issues them

A verb is a comment whose first line is a slash command. A bare label click is not a verb; it is
flagged (see below).

| Command | t3rig effect | Allowed in | Needs | OpenRig verb and deviation |
|---|---|---|---|---|
| `/approve` | to `in-progress` | awaiting approval, when the last lead comment is a plan (not counting watcher comments) | | `approve` closes the item (`done`, `no-follow-on`); here it is the plan-lock and work continues. |
| `/deny <reason>` | close, `Closed: denied` | awaiting approval only | reason | `deny` closes as `denied`; same effect, but the reason is required here and not in OpenRig. |
| `/answer <text>` | back to where the question was asked | an open question (awaiting approval or blocked by a question) | text | `answer` records the reply, sends it to the asking seat and closes the ask; here the comment is the reply and the lead reads it on the ping. |
| `/hold <reason>` | to `blocked` | any open state except blocked | reason | `hold` (reason required there too). |
| `/resolve <decision>` | `blocked` to `rig-queue` | blocked, no open question | decision | `resolve` moves to `in-progress`; here the lead re-takes it, so it re-plans. |
| `/drop <reason>` | close, `Closed: canceled` | any open state | reason | `drop` (reason required there too). |

```sh
gh issue comment 12 --body "/approve"
gh issue comment 12 --body "/deny the interface should stay as it is"
glab issue note 12 -m "/approve"
```

The verbs come from OpenRig's (`mission-control.md:97-107`). OpenRig requires fields only for
`annotate`, `hold`, `drop`, `route`, `handoff` and `resolve` (`mission-control.md:109-111`); `deny`
requiring a reason is stricter than OpenRig. A verb outside its allowed states, an unknown command
or a missing field gets a reply comment and changes nothing.

**Only a person approves, by convention, not by code.** The watcher never changes labels (see (e)),
so nothing stops the lead, or anyone with write access, from moving an item out of `needs-approval`.
The check is detective: a verb counts only if its author is not the lead's account
(`current_user()`) and has write access, and comments by the lead's account are never parsed as
verbs. Watcher comments use the lead's login, so those carrying the `t3rig` marker (see (e)) are
never counted as the lead's plan or question either. `watch` also flags any item that left
`needs-approval` without a valid verb newer than the lead's plan or question: it pings the lead,
which must put the label back and wait, and posts a comment on the issue so the operator sees it. A
person who clicks the label without commenting is flagged too, and then comments.

*Recommendation:* check write access with the tracker's permission API when a verb is first seen,
and cache the answer per author for the run. For GitHub, comment `authorAssociation` (`OWNER`,
`MEMBER`, `COLLABORATOR`) or `gh api repos/{owner}/{repo}/collaborators/{user}/permission` are the
likely sources; for GitLab, the project members API with an access level of Developer or above.
**Not verified:** whether `gh issue view --json comments` exposes `authorAssociation` (the field
list shown by `gh` 2.46 has `comments`, but not its fields), and the glab equivalent. Phase 1
settles this by testing both.

A label event has no reason, and who set it is only in the timeline. *Recommendation:* only a
comment command is a verb; a bare label change is never one.

## (d) How the planning dial decides when approval is needed

The lead plans each item at a rung (`planning-dial.md:10-25`) chosen from the work's uncertainty and
consequences, not how central it is (`planning-dial.md:37-45`). It writes the rung in the plan
comment (`planning-dial.md:53-54`).

| Rung | What the plan comment holds | Approval |
|---|---|---|
| P0 | A few bullets and where to look | Not needed, only as below |
| P1 (default, minimum) | Intent, requirements, a test-first proof list, files touched | Needed |
| P2 | P1, plus research with citations posted first | Needed |
| P3 | P2, plus an adversarial pass by `dev.review`: the lead briefs it with the product context, and the plan's proof list must change to show the amendments | Needed |
| P4 | P3, plus a design written before reading prior art, then compared. If it differs significantly, the lead posts a `Question:` instead of a plan (`planning-dial.md:23-25`) | Needed |

P4 stops for the owner only when the blind design differs significantly. Otherwise it is approved
like the rest.

Skipping approval at P0 is a deviation: OpenRig says approval starts at the mini-requirements
(`sdlc-conventions.md:108-123`), and P0 is those. *Recommendation, conservative:* the minimum rung
is P1. The lead may use P0 only when a person set the label `plan:P0`, or the issue author, who has
write access, wrote that no approval is needed. The lead may always go up a rung, and `plan:P1` to
`plan:P4` labels set the rung. Who set a label is only in the timeline; if `gh`/`glab` can't show it
cheaply (not checked), only the issue author's text counts. The lead errs up when a wrong plan would
be expensive, hard to undo and invisible from inside (`planning-dial.md:37-45`).

The default rung and the lowest rung that needs approval live in settings (see (g)).

## (e) How `watch` notices tracker changes

Today `watch` polls seat threads and pings a dispatcher (`src/t3rig/watch.py`). It remembers what it
has pinged in a state file under `~/.local/state/t3rig/` (`state_path`, `load_state`, `save_state`),
saved after every `tick`, so a restart neither repeats nor misses a ping. Delivery is at least once
across restarts: a crash can repeat a ping, never lose one. OpenRig's guarantee is at most once per
item and trigger per daemon run (`mission-control.md:190-203`). It runs under a lock so one watch
runs per rig.

*Recommendation:* extend `watch` rather than add a command. When tracker settings exist, each `tick`
also asks the adapter for every open item with any of the state labels. An item whose `updated_at`
differs from the recorded one is fetched with its comments, and events are derived:

- newly queued: an item with `rig-queue` that is not in state;
- a valid verb comment (approved, denied, answered, held, resolved, dropped) with an id newer than
  the item's `last_comment`;
- an item that left `needs-approval` with no valid verb (see (c)).

This is more than reusing the seat path. `_check_seat` (`watch.py:130`), `_apply` and `_deliver` are
keyed by seat and session name (`watch.py:245-266`) and `load_state` defaults to `{"seats": {}}`.
Item events need their own event type, which names the issue and has no seat, and the default state
gains `"items": {}`. They go to the seat named by `lead` in the settings (`dispatchers()` only knows
`delegates_to` edges). The state is `{issue: {"updated_at": ..., "labels": [...], "last_comment":
id}}`, updated only after the ping is delivered, like seats. A crash can repeat a ping, not lose
one.

Edited or deleted comments are not re-read: a verb is read once, by id.

The watcher posts comments (invalid verb, flagged label change) but never changes labels. The lead
does, on the ping. To avoid double posts after a crash, every watcher comment ends with a marker
`<!-- t3rig:reply <comment id> -->` naming the comment it answers (for a flagged label change, `<!--
t3rig:flag <updated_at> -->` with the `updated_at` seen when the label went missing, so a repeat
removal is flagged again), and the watcher looks for it before posting. If the marker check fails
because the comment list can't be read, it posts nothing and retries on the next tick. The reply is
therefore at most once per comment, and the ping stays at least once.

Polling cost: one `list` call plus one `view` per changed item per interval. *Open question:* the
default interval (15s for threads) is likely too fast for a tracker's rate limits; a separate
`--tracker-interval` of about 60s is a guess to measure in phase 2.

## (f) Adapter interface

One module, `src/t3rig/tracker.py`, shells out to `gh` or `glab` (no HTTP client, no new
dependency).

```python
class Tracker(Protocol):
    def list_items(self, labels: list[str]) -> list[Item]: ...  # open, any of these
    def comments(self, number: int, after: str | None) -> list[Comment]: ...
    def comment(self, number: int, body: str) -> None: ...
    def set_labels(self, number: int, add: list[str], remove: list[str]) -> None: ...
    def close(self, number: int, reason: str) -> None: ...  # "completed" or "not planned"
    def current_user(self) -> str: ...  # the lead's account
    def can_write(self, user: str) -> bool: ...  # the access check in (c)
```

`Item` is number, title, url, labels, updated_at. `reason` is GitHub's close reason (`completed` for
done, `not planned` for denied and canceled); whether `glab` has one is not checked. `Comment` is
id, author, body, created time. Two classes, `GitHub` and `GitLab`, each builds the command lines
and parses the output. Tests run the adapter against a fake `gh` and `glab` on `PATH` that print
fixed output, plus the same contract tests against both.

Differences I'm relying on, from the installed `gh` 2.46 and `glab` 1.53 help text only:

- `gh issue list` takes `--label` and `--json`; `gh issue view --json` has `comments` and `labels`.
- `glab issue list` takes `--label` and `--output json`; `glab issue note <id> -m <text>` comments.

Not checked: the JSON shapes of either, label add/remove flags, whether a missing label must be
created first, closing and its reasons, the permission calls, and how each paginates. These are
phase 1's first task. If `glab` can't do something, the adapter may call `glab api` for it. *Open
question:* whether GitLab's issue "labels" and "comments" (notes, including system notes) map
cleanly; system notes would have to be filtered out.

## (g) Where settings live

OpenRig has no field for an external tracker. Options: a t3rig-only key in `rig.yaml`, a separate
file, or flags.

*Recommendation:* a separate file next to the rig, `rig.tracker.yaml`, passed by `watch` and the
lead's instructions. OpenRig-compatible `rig.yaml` files stay valid for both tools, and t3rig
refuses unknown keys today, so a t3rig-only key would also need a parser change. Flags are not
enough once there are several settings.

```yaml
tracker: github              # or gitlab
repo: stfngrt/t3rig
labels:                      # one per state; these are the defaults
  queued: rig-queue
  in_progress: in-progress
  needs_approval: needs-approval
  blocked: blocked
default_rung: P1
lead: dev.lead               # the seat that gets the pings
approval_from: P1            # lowest rung needing approval
```

Credentials are never in the file. `gh` and `glab` use their own login. The lead account name for
the "not the lead" check comes from `gh api user` / `glab api user`.

## (h) Phases

Each phase is its own issue, and each leaves the tool working.

1. **Adapter.** `tracker.py` with both implementations, fake-CLI tests, and the verification of
   every "not checked" item above. No other change.
2. **Settings and watch.** `rig.tracker.yaml` loading, tracker events in `watch` with the `items`
   state, verb parsing and the write-access check. Pings the lead and posts the watcher comments;
   changes no labels.
3. **Lead instructions.** Rewrite the lead's "Ticket queue" for the label states, rungs and verbs,
   and run `rigs/self` on it.
4. **Plain-text plan templates**, per rung, if phase 3 shows the lead needs them.
5. **Optional:** a `t3rig queue` command to show items and states without opening the tracker.

## Open questions from #3

1. **Where tracker settings live.** *Recommendation:* the separate `rig.tracker.yaml` in (g).
2. **How much of OpenRig's mission and slice files to keep in the repo.** *Recommendation:* none.
   The issue holds intent, the plan comment holds the requirements and proof list, and the closing
   comment holds the checks. This keeps one source of truth and avoids files that can drift from the
   issue. Revisit if issues become too long to review; a design doc like this one is the exception
   and stays in `docs/design/`.
3. **Who may close an item.** *Recommendation:* the lead closes a finished item (`Closed: done`)
   only after checks pass, because the baseline already does and a person reads the closing comment.
   Only a person closes it as `denied` or `canceled`, through the verbs. An issue that says "leave
   it open for approval" is left open, as the baseline does.
4. **Does the lead's own account count as a person?** *Recommendation:* no. If the lead and the
   operator share one `gh` login, the "not the lead" check can't tell them apart. Open: use a
   separate bot account, or accept the check only when the accounts differ and warn otherwise.
5. **Label or comment as the approval.** See (c); *Recommendation:* comment.
6. **Rate limits and polling interval.** See (e); to be measured.
