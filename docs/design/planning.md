# Running the rig from the tracker (#3)

**Status: settled in [#15](https://github.com/stfngrt/t3rig/issues/15)**, from a grilling session
with the {term}`operator` on 2026-11-06. It replaces the proposal in
[#4](https://github.com/stfngrt/t3rig/issues/4), which had comment verbs, a `blocked` label, a
plan-approval gate and mission files; none of those are part of t3rig.

## Goal

Let the rig run from the issue tracker. The operator approves work by adding a label, and
{term}`watch` wakes the right seat when work is queued or a question is answered. Talking to the
operator stays with the {term}`project manager`. Issues hold the high-level decisions; commits and
docs hold the rest.

## Approval and states

One issue is one {term}`ticket`, and the issue is its whole record: no mission or slice files go in
the repo. t3rig reads labels and plain comments only. There are no slash commands or comment verbs.

Four labels make up the state set:

| Label | Meaning |
|---|---|
| {term}`needs-approval` | A `dev.pm` ticket waiting for the operator |
| {term}`rig-queue` | Approved, waiting for the lead |
| {term}`in-progress` | The lead is working on it |
| {term}`needs-answer` | Waiting for the operator to answer a question on the issue |

- Adding `rig-queue` is the only approval. The lead's plan comment is for information, not a second
  gate.
- A decision the ticket doesn't settle goes to `needs-answer`: the lead comments the open
  decisions, removes `rig-queue` and `in-progress`, and adds `needs-answer`. The operator answers
  with `dev.pm`, which writes the answers on the issue and removes `needs-answer`.
- Work the lead can't finish goes the same way: a comment saying why and what the operator must
  decide, then `needs-answer` in place of `rig-queue` and `in-progress`. So do questions in the
  lead's closing summary.
- An answer resumes the work without re-queueing it, since `rig-queue` already approved it. When
  `watch` pings the lead that `needs-answer` was removed, the lead reads the answers, adds
  `in-progress` back and continues that issue before taking new `rig-queue` work. If the operator
  denies or cancels instead, they close the issue, and a closed issue gets no ping.
- The lead closes finished work. The operator closes denied or canceled work.

## Planning dial

The {term}`planning dial` (P0 to P4) is guidance in the lead's role for how deep to plan. The lead
names the rung in its plan comment. It has no labels and no settings, and it never decides whether
approval is needed: `rig-queue` already did.

## Settings

t3rig's own settings sit in `rig.t3rig.yaml`, next to `rig.yaml`, which stays exactly OpenRig's
format:

```yaml
tracker:
  kind: github        # or gitlab
  repo: stfngrt/t3rig
  queue_seat: dev.lead
review_rounds: 2      # an issue can override this with a "Review rounds: N" line
```

The file is optional. `t3rig validate` checks it with the rig, including that `queue_seat` is one
of the rig's seats. `review_rounds` is read by the lead, which counts review rounds against it.
Credentials are never in the file: `gh` and `glab` use their own login.

## Tracker

`src/t3rig/tracker.py` is one small interface, open issues with their labels and an issue's
comments, with a `gh` backend and a `glab` backend. Both are tested against fake CLIs on `PATH`. A
live check against a real GitLab project is postponed.

## `watch` events

With a tracker set, {term}`watch` also polls the tracker, every 60 seconds by default
(`--tracker-interval`; the number is a guess to measure), and sends two {term}`pings <ping>`:

- An open issue gains `rig-queue`: ping `queue_seat`.
- `needs-answer` is removed from an open issue: ping the seat named in the `🤖 <seat>` signature of
  the question comment, or `queue_seat` if there isn't one.

It detects both by comparing each issue's labels with the ones it remembers in its state file.
`watch` reads the question comment when it first sees `needs-answer`: the newest comment with a
signature at that moment. Reading it later would find `dev.pm`'s signed answer instead.

Two conservative choices: an issue already carrying `rig-queue` when `watch` first sees it is pinged
once, so queued work isn't missed, unless it also has `in-progress` (decided on #15), and an issue
`watch` never saw with `needs-answer` gives no answer ping. A closed issue is forgotten, and a ping
names the issue by its full URL. Failed pings retry and alert as seat pings do. `watch` never
changes labels or writes comments.

## People and roles

- All conversation with the operator goes through `dev.pm`. The lead posts its questions on the
  issue with `needs-answer`, and the operator answers them with `dev.pm`.
- The lead counts review rounds against `review_rounds`, or the issue's `Review rounds: N` line.
- `dev.pm` prints full issue links, asks the operator only questions with a real choice, and keeps
  tickets for high-level, high-leverage work.

## Left open

- A live `glab` check against a real GitLab project.
- The polling interval.
- A third review round ([#12](https://github.com/stfngrt/t3rig/issues/12)).
