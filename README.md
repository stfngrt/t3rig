<img src="assets/icon.svg" width="64" height="64" alt="">

# t3rig

Run [OpenRig](https://github.com/mvschwarz/openrig)-compatible `rig.yaml` files on
[T3 Code](https://t3.codes), with every seat as a T3 thread. There is no tmux and no daemon.

Status: early, simple version. It has been run on a two-seat Claude rig.

Full documentation: <https://stfngrt.github.io/t3rig/>

## Usage

```sh
uv run t3rig validate examples/two-seat/rig.yaml   # check the spec; starts nothing
uv run t3rig up examples/two-seat/rig.yaml         # start a thread per seat; safe to re-run
uv run t3rig up examples/skills/rig.yaml --yes     # also install the rig's skills; see Skills
uv run t3rig ps examples/two-seat/rig.yaml         # status, model, mode and links; --json too
uv run t3rig send examples/two-seat/rig.yaml dev.impl "Hello"        # add --wait for the reply
uv run t3rig send examples/two-seat/rig.yaml --pod dev "Hello"       # or --all for every seat
uv run t3rig log examples/two-seat/rig.yaml dev.impl                 # latest messages; --messages N (default 10, at least 1)
```

Messages carry a `From:`/`To:` header unless you pass `--raw`. Seats are told to name themselves with
`--from`, and a send without it says `From: operator`. It's self-declared, so treat it as a label
rather than proof of who sent the message.

### Permissions and stopping

Seats with a `permission_policy` or `effort`, and `t3rig down`, use T3's `/mcp` tools, which need a
sign-in. Other seats use the `t3` CLI and need none, but run in T3's default mode, which may be full
access.

```sh
uv run t3rig login --access auto                    # seats can't launch above this level
uv run t3rig up examples/restricted/rig.yaml        # lead at auto, review at approval-required
uv run t3rig stop examples/restricted/rig.yaml dev.review   # interrupt a run; the thread stays
uv run t3rig down examples/restricted/rig.yaml      # interrupt and archive; add --seat pod.member
```

| `permission_policy` | T3 mode | Roughly |
|---|---|---|
| `builtin:locked` | `approval-required` | Anything that changes something waits for a person |
| `builtin:standard` | `auto-accept-edits` | File edits run; other commands can wait |
| `builtin:open`, `builtin:auto` | `auto` | Runs on its own, with T3's own checks |
| `builtin:yolo` | `full-access` | Runs anything |

This is an approximation: OpenRig's policies are finer-grained rules and T3 has four modes, so custom
policy files are refused. A member's policy overrides the rig's. Each seat launches idle, and its first
message is sent only after T3 confirms its mode, provider, model and effort. A mismatch is archived.

The credential is kept in `~/.config/t3rig/credentials.json`, readable only by you, for 30 days. Stop
`watch` before `down`, or its pings to the archived dispatcher will fail.

Modes aren't a security boundary. They make a seat ask before acting, but `locked` seats still run
read-only commands, and a seat allowed to run shell commands could use your `t3` CLI or credential.
Restricted seats also have to ask before running `t3rig send`, so `watch` is how they report back.
They can also stop for approval on shell commands that read files outside the repo, so have a
dispatcher pass along what they need.

### Pinging the dispatcher

`t3rig watch` keeps a seat's dispatcher informed, so nothing depends on an agent remembering to
report back. A seat's dispatcher is the seat with a `delegates_to` edge to it.

```sh
uv run t3rig watch examples/two-seat/rig.yaml
```

- It pings when a seat finishes a run, including a failed one, and when a seat has a question or
  approval waiting. Seats that change together share one ping. A seat's reply to its first message
  doesn't count.
- A ping is a short pointer with a one-line excerpt and a link. The dispatcher reads the thread for
  the rest. A run stopped partway says so and shows no excerpt, since it has no result.
- A failed ping is retried on the next check, and prints an `ALERT` after three failures. A stuck
  seat with no dispatcher also prints one, and so does a seat stopped at a usage limit, which `watch`
  recognizes from the wording of its last reply.
- It keeps what it has pinged in a small file under `~/.local/state/t3rig/`, so a restart neither
  repeats old pings nor misses new ones. A crash can repeat a ping, but not lose one.
- It only works while running. It's a foreground command, not a daemon.
- It polls, every 15 seconds by default (`--interval`), so a ping can lag by that much.
- A dispatcher can't approve for a seat, and T3's tools don't let an agent do so. A person answers in
  T3. When signed in, the ping says what command the seat is waiting on and how to `t3rig stop` it, so
  the dispatcher can stop that run and send other instructions instead. Stopping doesn't approve
  anything, and the seat can't run the command.

A seat's thread is the one titled `pod-member@rig` (OpenRig's seat name), so renaming a thread
disconnects it from its seat.

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

Unlike OpenRig, all instructions go in the seat's first message, in OpenRig's layer order, whatever
their `delivery_hint`, except skills, which are installed (see below). Instructions are never written
to the repo, so a long-running seat can lose them when its conversation is compacted.

## Skills

A skill is declared in the agent's `resources.skills` as `{id, path}` and selected by a profile's
`uses.skills`. See `examples/skills/`. An id can't contain `:`, which marks `name:id`. The path is relative to the agent's folder and names either a
folder, copied whole and holding a `SKILL.md`, or one file, copied into `<id>/` under its own name.
A skill's `SKILL.md` needs YAML frontmatter with a `name` and a `description`, and some text after
it. That's stricter than OpenRig, which doesn't check declared skills.

- A bare id picks the agent's own skill, or else an import's. `name:id` picks an import's, and a bare
  id found in two imports is ambiguous. t3rig doesn't discover skills from the working folder, home
  or the OpenRig catalog, so a skill has to be declared in `resources.skills`.
- A `startup.files` entry is installed rather than sent when `delivery_hint` is `skill_install`, or,
  with `auto`, when its path ends in `SKILL.md` or its text starts with `# SKILL`. A `role`
  orientation or `guidance/role.md` stays text. It installs that one file as
  `<its parent folder's name>/<its name>`.
- Skills are copied into the seat's `cwd`: `.claude/skills/<id>/` for `claude-code` and
  `.agents/skills/<id>/` for `codex`. An import's skill is installed as `name:id`.

`t3rig up` plans the installs for every seat first and prints them. When there are skill changes to
write, it writes nothing and starts nothing unless you add `--yes`:

```
skills in /work/project:
  create  .claude/skills/tdd/    (2 files)  dev.impl, dev.lead
  update  .agents/skills/lint/   (1 file)   dev.review
```

Skills go to every seat sharing a `cwd`, not only the seats that selected them, because they share
the folder. The plan lists the seats that selected each skill. Two seats can want the same file only
if its content and permissions are identical.

t3rig only creates files and replaces ones it wrote itself, and it never deletes. It copies each
file's permission bits, so scripts stay executable. A change to only a file's permission bits (same
bytes) isn't picked up; change the bytes, or remove the installed file, which t3rig recreates when a
recorded file is missing. It records what it wrote, with hashes, in
`~/.local/state/t3rig/skills-<rig>-<hash>.json`, saving that record before it writes anything to the
project. Without `--yes`, `up` can still re-save that record when files already match it, but only in
its own state folder, never the project. It refuses, listing every problem and changing nothing, if
a target exists and wasn't written by t3rig (even with identical content), was edited since, is or
sits under a symlink, or isn't a regular file. Move or remove the file, or put the edit in the
skill's source. Before creating a file it checks the path is still free, and before replacing one it
re-checks that it's unchanged. A narrow window remains between that check and the write. Creating
files needs a filesystem with hard links; `up --yes` fails there, with no fallback. A file t3rig
wrote that the source no longer has stays put and is listed as a note, which `up` prints even when
nothing else changes. `down` leaves installed skills in place.

A `skill_install` startup file is copied as it is: it isn't checked for symlinks or frontmatter, as
in OpenRig.

A seat that's already running won't see changes made after it started. Claude Code reads project
skills from the folder the session was started in, and t3rig starts threads in the T3 project's
root and tells the seat to change folder, so skills in a `cwd` that isn't the project root might
not be picked up. That's not verified.

## Limits

- `delegates_to` edges decide who `watch` pings. Otherwise edges are only described in each seat's
  first message, so nothing enforces them. `delegates_to` cycles are refused.
- Threads start in the T3 project's root. A seat's `cwd` must be inside a T3 project, and the seat
  is told to change to it.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run t3rig --version
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run sphinx-build -W -b html docs docs/_build/html   # the docs site
```

## The self rig

`rigs/self` develops t3rig with t3rig; see [The self rig](https://stfngrt.github.io/t3rig/development.html#the-self-rig).
