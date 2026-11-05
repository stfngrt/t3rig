# Per-seat skills (proposal for #7)

**Status: proposal. Nothing here is implemented.** Everything marked *Recommendation* is for the
operator to approve or change. Claims cite a source, or are marked *repo* (t3rig's own code),
*lead* (the lead's checks of T3) or *unverified*.

## Problem

An {term}`agent spec` selects {term}`skills <skill>` for a {term}`seat`, but `t3rig up` copies them into the seat's `cwd`
(`.claude/skills/<id>/` or `.agents/skills/<id>/`, `src/t3rig/skills.py`, README "Skills", *repo*).
Every seat in that folder gets every skill, and so does any other Claude or Codex session the
operator opens there. In `rigs/self` the `ponytail` skill is for `dev.impl`, but all three seats
and the operator's own session share the project root and see it, and its description sits in each
session's context on every turn [^cc-skills].

## Sources

Fetched for this proposal: [^cc-skills] [^cc-plugins] [^cc-env] [^cc-sub] [^codex-skills]
[^codex-config] [^as-spec] [^as-impl]. OpenRig paths are in https://github.com/mvschwarz/openrig,
quoted from excerpts the lead supplied; the sources themselves were not read.

[^cc-skills]: Claude Code docs, "Skills", https://code.claude.com/docs/en/skills (read in full, over
    two fetches)
[^cc-plugins]: Claude Code docs, "Create a plugin",
    https://code.claude.com/docs/en/plugins/create.md
[^cc-env]: Claude Code docs, "Environment variables", https://code.claude.com/docs/en/env-vars
[^cc-sub]: Claude Code docs, "Subagents", https://code.claude.com/docs/en/sub-agents
[^codex-skills]: Codex docs, "Agent Skills", https://developers.openai.com/codex/skills
    (308-redirects to https://learn.chatgpt.com/docs/build-skills, which was the page fetched)
[^codex-config]: Codex docs, "Advanced configuration",
    https://developers.openai.com/codex/config-advanced (308-redirects to
    https://learn.chatgpt.com/docs/config-file/config-advanced, the page fetched)
[^as-spec]: Agent Skills, "Specification", https://agentskills.io/specification
[^as-impl]: Agent Skills, "How to add skills support to your agent",
    https://agentskills.io/client-implementation/adding-skills-support.md

## What the harnesses offer

**Claude Code** discovers skills from personal `~/.claude/skills/`, project `.claude/skills/` in the
launch directory and every parent up to the repository root, nested `<subdir>/.claude/skills/`, a
`--add-dir` directory, and plugins [^cc-skills].

- **Nested** skills load "the first time Claude reads or edits a file in that subdirectory"
  [^cc-skills].
- **`--add-dir`** loads that directory's `.claude/skills/`, but the
  `permissions.additionalDirectories` setting "grants file access only and loads none of these"
  [^cc-skills].
- **Plugins** load per session from `--plugin-dir` (repeatable, a directory or `.zip`) or from the
  `CLAUDE_CODE_PLUGIN_DIRS` environment variable (absolute paths, `:`-separated, v2.1.280 or later,
  "Project and local settings can't set this variable"). Their skills are namespaced
  `/plugin-name:skill` [^cc-plugins] [^cc-env].
- **`CLAUDE_CONFIG_DIR`** moves the whole configuration directory: "All settings, session history,
  and plugins" [^cc-env].
- **Controls:** `skillOverrides` (`on`, `name-only`, `user-invocable-only`, `off`; not for plugin
  skills) and `Skill(name)` permission rules [^cc-skills]. These live in settings files, which a
  project's seats share. Frontmatter `disable-model-invocation: true` keeps a skill's description
  out of context while it can still be invoked [^cc-skills].
- **Subagent `skills:`** preloads full skill content into one subagent, but "controls which skills
  are preloaded, not which skills the subagent can access" [^cc-sub].

**Codex** scans `$CWD/.agents/skills`, each parent up to the repository root, `$HOME/.agents/skills`
and `/etc/codex/skills`, and follows symlinks [^codex-skills]. The page documents no environment
variable or flag to add skill directories. A skill is disabled with `[[skills.config]]` entries (by
`path` or `name`) in `~/.codex/config.toml`, and bundled system skills with `[skills.bundled]
enabled = false` in a trusted project's `.codex/config.toml` [^codex-skills]. A skill's
`agents/openai.yaml` can set `policy: allow_implicit_invocation: false`: "Codex won't implicitly
invoke the skill based on user prompt; explicit `$skill` invocation still works" [^codex-skills].
`CODEX_HOME` (default `~/.codex`) holds config and state, and `-c key=value` overrides any config
key for one run [^codex-config]. User skills are under `$HOME`, not `CODEX_HOME`, so `CODEX_HOME`
doesn't move them [^codex-skills] [^codex-config].

**The Agent Skills spec** defines only a skill's contents, not where skills live. `.agents/skills/`
has "emerged as a widely-adopted convention", and some clients also scan `.claude/skills/`
[^as-spec] [^as-impl]. Which harnesses follow the spec is *unverified*: the client showcase page
didn't render a list.

## What T3 lets t3rig set

From the lead's checks: `t3 thread start` takes title, provider, model, worktree, branch, and
`--wait`/`--json`, and no env, cwd or settings flag. `t3_thread_launch` takes title, message,
`projectId`, `modelSelection {provider, model, options}` (the lead's wording), `runtimeMode`,
`interactionMode` and `workspaceStrategy {type: root|worktree|existing_worktree, baseRef, branch,
worktreePath, startFromOrigin}`. t3rig uses `projectId`, `runtimeMode` and `modelSelection` sent as
`{instanceId, model, options}`, with an `effort` option (`src/t3rig/rig.py:165-182`) and `t3 thread
start --title --provider --model` (`src/t3rig/t3.py:63-69`, *repo*). No provider `options` entry for
skills is known; the lead couldn't confirm one, and neither could I.

So **per-seat worktrees are reachable, and per-seat environment is not.** For
`CLAUDE_CODE_PLUGIN_DIRS`, `CLAUDE_CONFIG_DIR` or a Codex `-c` override, T3 would need a
per-thread `env` or extra provider arguments on `t3_thread_launch` and `t3 thread start`. For Codex
that still wouldn't help with
discovery, which is under `$HOME` and the working directory: a per-thread `HOME`, or a way to pass
`-c skills.config=...` per thread, would be needed (*unverified* that `-c` can set an array of
tables).

## How OpenRig does it

OpenRig writes `.claude/skills/<id>/` and `.agents/skills/<id>/` into the project "only for a seat
without seat storage" (`docs/reference/agent-startup-guide.md:750`). Otherwise skills sit in seat
storage it owns, "outside the person's project and their own skill folders, so a person's own agent
opened in the project sees none of the team's skills"
(`packages/daemon/src/domain/seat-skill-storage.ts:9-21`), keyed by rig and logical seat, never by
session, so a resume or handover finds them.

- **Claude:** a generated plugin named `openrig`, passed through `CLAUDE_CODE_PLUGIN_DIRS`
  (`seat-launch-additions.ts:9-12`, `docs/reference/refocus-channel.md:26-28`).
- **Codex:** no plugin; the skill trees sit in `<root>/skills` and a derived `catalog.md` is
  "delivered to the seat through its per-seat startup text" (`seat-skill-storage.ts:43,56-60`).
- **Both:** a startup instruction also tells the agent to read them, as a belt and suspenders
  (`agent-startup-guide.md:112-117`), and `rig skill loadout` changes a running seat's selection and
  tells it (`seat-skill-apply.ts:16-21`).

t3rig can copy the Codex shape, a seat-scoped folder plus a pointer in the brief. It can't copy the
Claude shape without per-thread env.

## Options

| Option | Isolates from other seats and the operator | Reachable in T3 | Native skill loading | Cost and catches |
|---|---|---|---|---|
| **A. Shared install** (today) | No | Yes | Yes, both | The problem |
| **B. Invocation policy in the skill** (Claude `disable-model-invocation: true`; Codex `allow_implicit_invocation: false`) | Partly: the description leaves other sessions' context, and the skill stays on disk for everyone | Yes | Claude: only a person typing `/name` runs it, and Claude Code blocks the model's own attempt [^cc-skills]. Codex: explicit `$skill` still works [^codex-skills] | It hides the skill from the seat that needs it too, so the seat can't use it on its own; the first message would have to carry `/name` or `$name`, and whether T3 passes that through as a command is *unverified*. A local patch to a vendored skill (`ponytail` is vendored at a pinned commit) |
| **C. Gitignored seat folder inside the project**, e.g. `.t3rig/seats/<rig>/<seat>/skills/<id>/`, a name no harness scans, pointed to in the brief | Yes for discovery: Claude and Codex don't scan it | Yes | No: read as files, not re-injected after compaction | An in-repo read should need no approval, unlike an outside-repo one (`rigs/self/culture.md`), but that is *unverified* and phase 1 tests it; no `~/.local/state` dependency for the files; shows as untracked in `git status` until the operator adds it to `.gitignore` (t3rig doesn't edit it); other seats can still read the files |
| **D. The same folder outside the project** (fallback), e.g. `~/.local/state/t3rig/seats/<rig>/<seat>/` | Yes for discovery | Yes | No, as C | Restricted seats stop for approval on outside-repo reads (`rigs/self/culture.md`); `additionalDirectories` may grant read access [^cc-skills], *unverified*; mirrors OpenRig's Codex path |
| **E. Per-seat worktree** with the skills installed in it | Yes: other checkouts never see them | Yes: `existing_worktree` (*lead*) | Yes, both | Breaks the shared-checkout rule; see below |
| **F. Per-seat plugin directory** (`CLAUDE_CODE_PLUGIN_DIRS`, `--plugin-dir`) | Yes | **No** (needs env or args) | Yes, namespaced | Claude only; blocked on T3 |
| **G. Per-seat `CLAUDE_CONFIG_DIR` or Codex `HOME`/`-c`** | Yes | **No** | Yes | Moves credentials, history and settings too [^cc-env]; blocked on T3 |
| **H. Nested per-seat subfolder as `cwd`** | Partly | Yes | Claude loads nested skills on first read there [^cc-skills]; Codex scans up from the launch directory, *unverified* after a `cd` | Fragile; not recommended |
| **I. Settings rules** (`skillOverrides`, `Skill(...)`, `[[skills.config]]`) | Only if settings are per seat | Only in a per-seat folder | Yes | Claude's settings are per project or user and Codex's per user (or trusted project), not per seat, so there is no gain over E |
| **J. Auto memory switches** (not skills: `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, or `autoMemoryEnabled` via `--settings`) | Yes, per session | **No** (an env var or a flag) | n/a | Seats and the operator's sessions in one project share one auto memory folder; a project setting would also turn off the operator's own memory. See "Seat memory" in {doc}`../development` |

## Recommendation

*Recommendation:* build **C** as the opt-in, make **D** a fallback, offer **E** as a separate
opt-in, and ask T3 for **F**.

- **Default (question for the operator):** existing rigs keep the shared install and opt in with
  `skills: seat`. Switching drops native loading (`/name`, re-injection after compaction), so it
  shouldn't happen to a rig silently. The alternative, making `seat` the default, fixes the operator
  exposure at once but changes every rig. The setting has two values, `shared` and `seat`.
- C is the only isolating option fully inside t3rig today that, if phase 1 confirms it, needs no
  outside-repo read. It works for both runtimes and copies the shape of OpenRig's Codex path (a
  seat-scoped folder plus a pointer in the startup text, `seat-skill-storage.ts:43,56-60`). Its
  costs: no native skill tool, no re-injection after compaction (#5's re-sendable orientation covers
  that), and the files are still readable by other seats. The folder is anchored at the T3 project
  root, and the brief uses absolute paths, since a seat changes directory.
- D is not a third setting value. It differs from C only in where the files live, and it is built
  only if phase 1 shows C fails for restricted seats (an in-repo read prompting). Then the same
  setting would put the folder outside the project, and restricted seats would still stop for
  approval on outside-repo reads. `rigs/self` runs `builtin:auto` (`rigs/self/rig.yaml`); whether
  T3's `auto` prompts on such reads is *unverified*.
- B is not a fix for this problem. It removes the skill from the operator's context only by
  removing it from the seat's own too.
- E isolates files as well as skills, which `rigs/self` may want anyway, but it changes how the team
  works, so it is its own issue.
- F is the better design if T3 adds a per-thread `env` or provider args: native loading, namespaced,
  nothing in the project. Raise it with T3 rather than build around it.

### Worktrees, the shared-checkout rule and committing

`rigs/self/culture.md` says seats share one checkout and must not disturb it. The skill-carrying
seat is the only one that would need a worktree, and in `rigs/self` that is `dev.impl`, the seat
that writes the code. Moving it changes three things:

- **Review:** `dev.review` reviews "the uncommitted diff" in the shared checkout. It can't see
  `dev.impl`'s changes in another worktree without reading outside its own folder, which restricted
  seats need approval for.
- **Committing:** the lead commits and pushes to `main` (`rigs/self/agents/lead/role.md`). It can't
  commit changes that sit in another worktree and on another branch; it would merge or cherry-pick
  them, and `dev.impl` would have to commit on its branch, which the "don't commit" rule forbids
  today.
- **Skills are untracked:** t3rig-installed skills are not committed. In this checkout
  `.claude/skills/` is excluded by hand in `.git/info/exclude`; t3rig doesn't write that. A linked
  worktree uses the main repository's `info/exclude` (checked with git 2.47.3), so a new worktree
  ignores the same paths but starts without the files. The install must go into the worktree before
  the seat launches, because Claude only picks up a new top-level skills directory with
  `/reload-skills` [^cc-skills]. So t3rig would create the worktree itself and launch with
  `existing_worktree` and its path (*lead*), not let T3 create one.

Where the worktree lives matters. A T3-created worktree is likely outside the project
(*unverified*), and README "Limits" requires a seat's `cwd` to be inside a T3 project. A
**gitignored worktree inside the project root**, such as `.t3rig/worktrees/<seat>`, fits that rule.
Whether T3 accepts a thread whose `cwd` is such a nested checkout is *unverified*.

## Phases

Each phase is its own issue, in this order.

1. **Verify restricted-seat reads and explicit invocation.** Size S. In each T3 mode
   (`approval-required`, `auto-accept-edits`, `auto`), test whether a seat can read a file under
   `.t3rig/` inside the project, and one outside it, without prompting; whether
   `permissions.additionalDirectories` fixes the outside case; whether a seat follows a catalog
   pointer in its first message; and whether `/name` or `$name` in a first message runs a skill
   (this settles option B). This decides C versus D, so it comes before any build.
2. **Seat folder and brief (C), Claude and Codex.** Size M. Write skills to
   `<T3 project root>/.t3rig/seats/<rig>/<seat>/skills/<id>/`, keyed by rig and seat, never by
   thread, with the existing install record and safety rules (`skills.py`). Add a catalog to the
   seat's brief (ids, descriptions, absolute paths) and a line telling it to read `SKILL.md`. Print
   the `.gitignore` line to add, since t3rig doesn't edit it and `.t3rig/` shows as untracked until
   then.
   - **Settings:** the opt-in `skills: seat|shared`, default `shared`, lives in the t3rig settings
     file from #3/#4 (name not settled), which `planning.md` proposes for tracker settings. It is
     not a separate file for this.
   - **Compaction:** depends on #5's `t3rig refocus` recommendation being approved first, because
     the catalog in the first message is summarised at compaction.
3. **Old-copy cleanup and docs for the seat folder.** Size S. t3rig never deletes, so the old shared
   copies under `.claude/skills/<id>/` and `.agents/skills/<id>/` stay.
   - **Cleanup:** `up` lists those its record shows it wrote and that are unchanged, with a `rm -r`
     command per folder that it prints but doesn't run, and a manual step for any it can't vouch for.
   - **Docs, examples and the rig:** update `rigs/self/agents/impl/role.md:10`, which points at
     `.claude/skills/ponytail/SKILL.md`; the README "Skills" section, which describes the old paths;
     and `examples/skills/` with its `.gitignore` entries, for the new paths.
4. **Per-seat worktrees (E), opt-in.** Size L. t3rig creates a worktree per carrying seat,
   preferably gitignored inside the project root, installs skills in it, and launches with
   `existing_worktree`; update `rigs/self` hand-off and commit rules.
5. **Ask T3 for per-thread env or provider args.** Then plugin directories (F) for Claude are a
   small change: generate a plugin with `.claude-plugin/plugin.json` and `skills/`, and pass
   `CLAUDE_CODE_PLUGIN_DIRS`. Size S for t3rig once T3 has it; the T3 work is outside this repo.
6. **Invocation-policy guidance (B), only if phase 1 shows explicit `/name` or `$name` works.**
   Size S. Document the policy keys for single-seat skills, with the first-message wording.

## Not verified

- Whether T3 gives provider sessions the project root as their launch directory and honours a
  worktree path, inside or outside the project (README says the project root).
- Whether `auto` mode prompts for reads outside the repo, and whether `additionalDirectories`
  grants them without a prompt.
- Whether a `/name` or `$name` at the start of a first message runs the skill through T3.
- Whether `-c` can set `skills.config` per thread in Codex.
- Which harnesses follow the Agent Skills spec beyond Claude Code and Codex.
- Whether a skill in a nested subfolder is found by a Codex session that `cd`s there after launch.
- The OpenRig sources above, which I did not read.
