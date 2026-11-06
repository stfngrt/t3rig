# Issue tracker: GitHub (stfngrt/t3rig)

Issues and specs for this repo live as GitHub issues in `stfngrt/t3rig`. Use the `gh` CLI for all
operations. This is the tracker doc that the vendored Matt Pocock skills in `rigs/self/agents/*/skills/`
expect (see their `CHANGES.md`). It is based on `issue-tracker-github.md` from
https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`.

The installed `gh` is 2.46.0, which predates the `--parent` and `--blocked-by` flags, so this doc
uses `gh api` for sub-issues and blocking. Reads of the API fields below were checked on this repo;
the writes were not run and are *unverified*. Where a write fails, fall back to the text conventions
named below.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line
  bodies.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --label <label> --json number,title,labels`.
- **Sub-issue of a parent**: `gh api --method POST repos/stfngrt/t3rig/issues/<parent>/sub_issues -F
  sub_issue_id=<child-db-id>`, where the database id is `gh api repos/stfngrt/t3rig/issues/<n> --jq .id`
  (not the `#number`). Without sub-issues, put `Part of #<parent>` at the top of the child body.
- **Blocking**: GitHub's native issue dependencies. `gh api --method POST
  repos/stfngrt/t3rig/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Fall back to
  a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every
  blocker is closed.
- **Count open blockers**: `gh api repos/stfngrt/t3rig/issues/<n> --jq
  .issue_dependencies_summary.blocked_by` (open blockers only; 0 means startable).
- **Comment**: `gh issue comment <number> --body "..."`.
- **Labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Close**: post the explanation with `gh issue comment`, then `gh issue close <number>`.

File issues only into `stfngrt/t3rig`. Before the first `gh issue create` of a session, check the
target with `gh repo view --json nameWithOwner`.

## Labels

The labels are in `docs/agents/triage-labels.md`. In short, four labels are the whole state set:
`dev.pm` writes tickets and labels them `needs-approval`, only the operator adds `rig-queue` (the
only approval), `dev.lead` adds `in-progress` when it takes a `rig-queue` issue, in number order, and
`needs-answer` marks questions for the operator. There is no `blocked` label.

## Pull requests

This rig commits to `main` and doesn't use pull requests yet (#9). **PRs as a request surface: no.**

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
  `gh issue create --label wayfinder:map`. Create the label first if it doesn't exist
  (`gh label create wayfinder:map`); the same goes for the `wayfinder:` ticket labels.
- **Child ticket**: an issue linked to the map as a sub-issue (see **Sub-issue of a parent**). Labels:
  `wayfinder:<type>` (`research`, `grilling` or `task`). Once claimed, the ticket is assigned to the
  driving dev.
- **Blocking**: see **Blocking** under Conventions.
- **Frontier query**: list the map's open children, drop any with an open blocker or an assignee;
  first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write. Everyone here shares
  one `gh` login, so the assignee tells you a ticket is taken but not by whom.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a
  context pointer (gist + link) to the map's Decisions-so-far.
- Map and ticket issues carry only `wayfinder:` labels. They never get `rig-queue`.
