# Context management in a rig (research for #5)

**Status: research. Nothing here is implemented.** Recommendations are for the operator to approve.
Claims cite their source, or are marked *repo* (t3rig's own code or history) or *unverified*.

## Summary

- A seat's context is its only memory. Everything t3rig gives a seat today is in one first message (its {term}`brief`),
  and Claude Code's own docs say "detailed instructions from early in the conversation may be
  lost" when it compacts [^cc-works]. OpenRig reaches the same conclusion: "Editing a file is not
  delivery" (`docs/reference/refocus-channel.md:3-5`).
- What survives compaction depends on how it was loaded: root `CLAUDE.md` and unscoped rules are
  re-injected from disk, invoked skills are re-injected with a cap, a first message is only
  summarized [^cc-ctx].
- The cheapest wins are small: a way to re-send orientation, a bounded result-by-pointer convention
  for hand-offs, and a stale-orientation check. Hooks, a context library and work packets are not
  worth building now.

## Sources

Fetched: [^eng-ctx] [^eng-multi] [^cc-ctx] [^cc-works] [^cc-mem] [^cc-skills] [^cc-sub]
[^codex-agents] [^oai-compact]. OpenRig paths are in https://github.com/mvschwarz/openrig under
`docs/`, quoted from excerpts the lead supplied and **not re-fetched**. T3 facts are from the
lead's checks.

[^eng-ctx]: Anthropic, "Effective context engineering for AI agents",
    https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
[^eng-multi]: Anthropic, "How we built our multi-agent research system",
    https://www.anthropic.com/engineering/multi-agent-research-system
[^cc-ctx]: Claude Code docs, "Explore the context window", https://code.claude.com/docs/en/context-window
[^cc-works]: Claude Code docs, "How Claude Code works", https://code.claude.com/docs/en/how-claude-code-works
[^cc-mem]: Claude Code docs, "How Claude remembers your project", https://code.claude.com/docs/en/memory
[^cc-skills]: Claude Code docs, "Skills", https://code.claude.com/docs/en/skills
[^cc-sub]: Claude Code docs, "Subagents", https://code.claude.com/docs/en/sub-agents
[^codex-agents]: Codex docs, "AGENTS.md", https://developers.openai.com/codex/guides/agents-md
    (308-redirects to https://learn.chatgpt.com/docs/agent-configuration/agents-md, which was the
    page fetched)
[^oai-compact]: OpenAI API docs, "Compaction", https://developers.openai.com/api/docs/guides/compaction

## 1. Per seat

**At start, a t3rig seat gets one message** holding every layer (agent, culture, rig, pod, member),
whatever the `delivery_hint`, except installed skills (README "What's supported"; `seat_brief` in
`src/t3rig/rig.py`, *repo*). It fetches everything else on demand: code, issues, other seats'
threads. OpenRig prefers the opposite split: put as much as possible in context loading, with
managed `CLAUDE.md`/`AGENTS.md` blocks and installed skills before boot, and use `send_text` only
for grounding (`reference/agent-startup-guide.md:70-91,214-228`).

**What survives compaction** [^cc-ctx]:

| Loaded as | After compaction |
|---|---|
| First message (t3rig today) | Summarized with the conversation; detail "may be lost" [^cc-works] |
| `CLAUDE.md` in the launch directory and its parents, unscoped rules, auto memory | Re-injected from disk |
| `CLAUDE.md` in a subdirectory, `paths:` rules | Loaded when a file there is read or edited; summarized away at compaction, then reloaded on demand |
| Skill descriptions | Rebuilt and re-injected (v2.1.304 or later) |
| Invoked skill bodies | Re-injected, 5,000 tokens each, 25,000 total, oldest dropped first |
| Files read | Up to five re-read, most recently modified first; a file over 5,000 tokens comes back as a path only |

A new Claude Code subagent doesn't see the parent's conversation or invoked skills; it gets the
task message, its own prompt and `CLAUDE.md` [^cc-sub]. Codex builds its `AGENTS.md` chain once per
run, 32 KiB by default, and changes need a restart [^codex-agents]. How Codex CLI compacts is
*unverified*: the fetched OpenAI page describes the Responses API's opaque server-side compaction
item, not the CLI [^oai-compact]. How T3 compacts, or whether it does anything itself, is *unknown*.

**Consequences for t3rig:**

1. Anything a seat must keep (role, who to message, the checks to run) is at risk in a long-running
   seat. OpenRig refocuses on a schedule: hooks deliver orientation at `UserPromptSubmit`, `Stop`
   and `PostCompact` (`reference/refocus-channel.md:11-17`), and Claude's trigger is transcript
   growth (~300k tokens), not turns or time (`:51-55`). t3rig refuses hooks and has no signal for
   either tool, so the nearest equivalent is an explicit re-send.
2. Skills are the one durable channel t3rig already has. They are shared by every seat in a `cwd`
   (README "Skills"), so they can't carry per-seat roles in a shared checkout like `rigs/self`.
3. A managed `CLAUDE.md` block would be shared by every seat in that folder, so it fits culture and
   rig-level rules, not roles. Only a `CLAUDE.md` in the launch directory or its parents loads at
   launch and survives compaction [^cc-ctx]. T3 threads start in the T3 project's root (README
   "Limits"), so a block in the project root would load for every seat, including those whose `cwd`
   is a subfolder; a block in a subfolder would not. OpenRig's rules to copy: never overwrite a
   hand-edited block, and flag it as possibly stale (`agent-startup-guide.md:374-377`).
   *Unverified:* what launch directory T3 gives each provider session; the README already says
   skills in a non-root `cwd` might not be picked up.
4. Keep orientation small. Claude Code advises under 200 lines per `CLAUDE.md` and warns that
   contradicting instructions make Claude "pick one arbitrarily" [^cc-mem]. t3rig's `rigs/self`
   orientation is about 4 KB, so it is nowhere near the problem; the risk is layered rigs.

**When to hand a seat to a fresh thread.** Claude Code compacts automatically, so a full window
doesn't end a session [^cc-ctx]; a fresh thread is for when a seat has drifted or its transcript
is mostly noise. OpenRig's
`rig seat handover <seat> --source fresh|rebuild|fork:<seat>|discovered:<id> --reason <reason>`
keeps the seat's name and puts missing guidance back
(`as-built/architecture/lifecycle-snapshot-restore.md:295-307`; `agent-startup-guide.md:368-372`).
T3 has two paths. `t3_thread_transfer` covers only the **fork** path: it can `fork` a thread into a
new one with the same setup and no turn run, or `merge_back` (lead's checks). The **fresh** path is
a new thread (`t3 thread start`, `start_thread` in `src/t3rig/t3.py`) titled `pod-member@rig`, with
the old one archived (`down --seat` does that through `t3_thread_organize`). `up` skips seats that
already have a thread (`src/t3rig/rig.py`, *repo*), so the archive has to come first. `ps` already
uses the newest thread when there are several (*repo*), which is why the title must match. Whether
`up` starts a new thread for a seat whose only thread is archived is *unverified*. What a handover
should carry is the next section.

## 2. Between seats

**Pointers beat copies.** Anthropic's multi-agent system has subagents "pass lightweight references
back to the coordinator" and save plans to memory so the lead's context survives [^eng-multi], and
its context-engineering post recommends keeping "lightweight references such as file paths" and
loading data at runtime [^eng-ctx]. Claude Code subagents likewise return only a summary
[^cc-sub]. t3rig's pings already work this way: a line with a link and a 120-character excerpt
(`EXCERPT_CHARS`, `src/t3rig/watch.py:36`). `CLOSING` (`watch.py:43-46`) tells the dispatcher to
read the thread with `t3 thread show <id> --messages 3` and to reply only if the seat has more to
do (*repo*). So the design already costs the lead a read per ping, though one bounded in count
(`--messages 3`), not in size.

**Costs seen in this rig** (reported, not measured: the first two by issue #5, the third by the
lead's report from its run the night this was written):

- Every ping costs the lead a turn, and reading the reply costs the transcript: the lead runs
  `t3 thread show --messages N` and gets whatever the seat wrote. `t3 thread show` has no
  documented size cap per message (only `--messages N` and `--json`); the T3 MCP read has `limit`
  (1-100) and `maxCharsPerItem` (1-50000), which t3rig's own `log` does not expose.
- Briefs are sent once at `up`, and commands in a seat's first message went stale after a rename.
  OpenRig's answer is to derive what can be derived: prose "drifts", derived-from-source "can't
  rot" (`reference/knowledge-maturity.md:65-69`).
- Review needs the excerpts re-pasted each round, because seats can't read files outside the repo.
  The pattern is a message that stands alone. OpenRig says the same of its timers: "the body must
  stand alone" (`reference/keeping-a-watch.md:165-177`).

**Sizes.** A hand-off should be one screen: intent, files, the checks, what's out of scope, and
pointers for the rest. A ping should stay a pointer. OpenRig bounds its work packet at one line of
about 160 characters per row, at most 20 held and 10 next rows, sections cut at about 1,500
characters (`refocus-channel.md:136-174`); those numbers are a useful scale, not a measured optimum.
The best save for the dispatcher is a result written once to a durable place (an issue comment, a
file in the repo) and a ping that points at it. A reply that is a link plus three lines is cheaper
for the lead than a transcript, and it doubles as the audit record (#3/#4).

**Dispatcher losing track.** The lead has no memory of open work except its own context.
`docs/design/planning.md` puts that state in issue labels, so it survives a lead restart.
OpenRig derives "PARKED" (idle with open obligations: "a dropped baton") at read time and never
stores it (`reference/agent-state-taxonomy.md:89-101`). A cheap version for `ps`/`watch` is
*recommended* below.

## 3. Shared and durable state

| Where | Good for | Risk |
|---|---|---|
| Repo files (`README`, `docs/`, skills) | Stable rules, designs, procedures | Goes stale quietly; no owner per line |
| Issues and comments (#3/#4) | Work state, plans, approvals, results | Comments can be edited; needs a network call |
| `watch` state file (`~/.local/state/t3rig/`) | What has been pinged; at least once across restarts | Local to one machine |
| Seat memory (Claude auto memory, `NOTES.md`) | Learnings | Auto memory is per repository and machine-local, shared across worktrees and subdirectories [^cc-mem], so seats in one checkout share it: one seat's notes can contaminate another's |
| Thread transcripts | Everything, as data | Expensive to read; not an index |

Anthropic's structured note-taking (a `NOTES.md` or to-do list that the agent re-reads after a
reset) is the same idea as OpenRig's chain files [^eng-ctx]; OpenRig adds that a claim's location
tells you its trust, from data and field notes (days to weeks) up to canon (years)
(`reference/knowledge-maturity.md:19-31`), and that promotion needs a warrant (`:57-58`). Nothing in
that ladder is mechanized in OpenRig either (`:122-125`).

OpenRig also keeps "lore", knowledge earned by one position, under that seat's tree and composes
it by address, never by copying (`reference/lore-routing.md:3-6,130-134`). t3rig has no per-seat
tree, so this is left out. For t3rig: **stable rules live in the
repo, work state lives in issues, and a note in shared memory is a hint to check, not a fact,
whichever seat wrote it.**

**Noticing staleness.** OpenRig's work packet names notes older than 14 days with their age: "a cue
for judgment, not a staleness verdict" (`refocus-channel.md:136-174`). `/doctor prompt-audit` in
Claude Code checks instruction files for references to files or commands that don't exist and for
contradictions [^cc-mem]. t3rig can cheaply do the first part for its own orientation: record a
hash of each seat's orientation at `up` (like the skills record) and let `ps` say when the spec has
changed since. That tells you a running seat is out of date, which is the problem
`refocus-channel.md:3-5` names.

## 4. Cost

| Approach | Cost to the seat's context | Notes |
|---|---|---|
| One big first message | One-off, but it is summarized after compaction | Today |
| Skill descriptions | Per turn, for every installed skill; capped at 1,536 characters each [^cc-skills] | Bodies load only when invoked |
| Invoked skill body | Recurring while in context, "every line is a recurring token cost" [^cc-skills] | Re-injected up to 5,000 tokens |
| Managed `CLAUDE.md` block | Every session start, also after compaction | Keep under about 200 lines [^cc-mem] |
| Re-sending orientation | One message per refocus | OpenRig warns the heavy intervention when the light one was due is "the most common self-inflicted stall" (`refocus-channel.md:194-198`) |
| Pings and `watch` | A turn per ping | Batched per tick (*repo*); `keeping-a-watch.md:96`: each check "costs a turn", use the longest interval that serves |
| Subagent / delegate | Own window, summary back | Anthropic reports multi-agent systems using about 15 times the tokens of a chat, so a task must be valuable enough to pay for the extra tokens [^eng-multi] |
| Fork or fresh thread | New window, plus whatever the handover carries | Cheaper than a drifted window; costs the handover |

Judgement, not measured: the **lead** needs the smallest context but the longest life, so it
benefits most from pointers, labels and a re-sendable role. The **implementer** needs the largest
window for code and benefits from short-lived threads per issue. The **reviewer** needs a medium
window and a self-contained brief per round.

## 5. Failure modes

| Failure | Where it shows | Mitigation |
|---|---|---|
| Drift after compaction | Long-running lead forgets its rules | Re-send orientation; keep rules in a root file |
| Contradicting layers | Culture says one thing, role another; Claude may "pick one arbitrarily" [^cc-mem] | One owner per rule; OpenRig's rule: don't restate, "restatement is how drift is born" (`reference/sdlc-conventions.md:300-315`); layers only add (`agent-startup-guide.md:169-181`) |
| Trusting stale notes | A seat reads an old comment or `NOTES.md` as current | Dates, source pointers and derive-don't-copy; show age as OpenRig's packet does |
| Dispatcher loses open work | Lead restarts and forgets an in-progress item | Labels on issues (#3/#4); a `ps` flag for idle seats with open items |
| Edited or lost comments | The audit trail can be rewritten | Already noted in the design proposal |
| Seat can't see what it needs | Review can't read outside the repo | Pass the text in the message |
| Hand-edited managed block overwritten | A seat's local edit disappears | Never overwrite; flag (`agent-startup-guide.md:374-377`) |

## 6. Recommendations (ranked)

Each is a candidate issue. Sizes: S is a day or less, M a few days, L more.

| # | Recommendation | Size | Why |
|---|---|---|---|
| 1 | `t3rig refocus <seat>`: re-send the seat's current orientation as a short, marked message (add `--pod` and `--all`) | S | The only fix for compaction drift and for stale commands that needs no new mechanism; mirrors OpenRig's refocus, without hooks |
| 2 | Record each seat's orientation hash at `up`, and have `ps` flag a seat whose spec changed since | S | Makes "running seat is out of date" visible (`refocus-channel.md:3-5`) |
| 3 | Convention for results: a seat posts its result to an issue comment or a file and the reply and ping carry a link plus a few lines; written into the self rig's role files | S | Cuts the lead's reads and re-pasting, and doubles as the audit trail |
| 4 | Expose a size bound for `log` (characters per message) using the MCP read's `maxCharsPerItem`, for dispatchers | S | Today the lead can't cap what a transcript read costs; needs a sign-in, so verify first |
| 5 | A `ps`/`watch` hint for a seat that is idle with open items (derived at read time, never stored) | M | Addresses the lost baton; depends on #3/#4 labels existing |
| 6 | One marked block in the project-root `CLAUDE.md` for culture and rig-level rules, with an install record like skills. It never touches text outside the markers, and a hand-edited block is flagged, not overwritten (as OpenRig does, `agent-startup-guide.md:374-377`) | M | In the project root, where T3 threads launch, it survives compaction for free in Claude Code; shared by every seat, so no roles; a subfolder block would be lost at compaction; first verify T3's launch directory |
| 7 | `t3rig handover <seat>`, fresh path: archive the old thread, start a new one titled `pod-member@rig` with the seat's orientation plus a short packet (open work, links, what not to redo) | M | Mostly composes `down --seat` and `up`; the new work is the packet and the ordering. Useful once seats run long. Fresh is the default because a `fork` (via `t3_thread_transfer`, size L: it also needs its title set to `pod-member@rig`) carries the drifted transcript, unlike OpenRig's `fresh` source |

**Not recommended now:** hooks (t3rig refuses them, and compaction detection would need transcript
size tracking), a context library or reference resolution, OpenRig's work packet (the lead notes it
is "off by default; not yet shown to work natively"), and a compaction manager.

## Open questions

1. Does T3 compact threads itself, and can t3rig detect it? *Unknown.*
2. What launch directory does T3 give a provider session? t3rig's README says the project root.
   A `CLAUDE.md` below the launch directory is documented to load on demand [^cc-ctx]; whether
   skills below it are picked up is *unverified* (also in the README).
3. How does Codex CLI compact, and does it re-read `AGENTS.md` afterwards? *Unverified.*
4. Is a re-sent orientation weighted like the first one? *Unverified*, and for the same reason
   OpenRig keeps its refocus short.
