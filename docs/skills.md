# Skills

A skill is declared in the agent's `resources.skills` as `{id, path}` and selected by a profile's
`uses.skills`. See `examples/skills/` in the repository. An id can't contain `:`, which marks
`name:id`. The path is relative to the agent's folder and names either a folder, copied whole and
holding a `SKILL.md`, or one file, copied into `<id>/` under its own name. A skill's `SKILL.md` needs
YAML frontmatter with a `name` and a `description`, and some text after it. That's stricter than
OpenRig, which doesn't check declared skills.

## Selecting skills

- A bare id picks the agent's own skill, or else an import's. `name:id` picks an import's, and a bare
  id found in two imports is ambiguous. t3rig doesn't discover skills from the working folder, home
  or the OpenRig catalog, so a skill has to be declared in `resources.skills`.
- A `startup.files` entry is installed rather than sent when `delivery_hint` is `skill_install`, or,
  with `auto`, when its path ends in `SKILL.md` or its text starts with `# SKILL`. A `role`
  orientation or `guidance/role.md` stays text. It installs that one file as
  `<its parent folder's name>/<its name>`.
- Skills are copied into the seat's `cwd`: `.claude/skills/<id>/` for `claude-code` and
  `.agents/skills/<id>/` for `codex`. An import's skill is installed as `name:id`.

## The install plan

`t3rig up` plans the installs for every seat first and prints them. When there are skill changes to
write, it writes nothing and starts nothing unless you add `--yes`:

```text
skills in /work/project:
  create  .claude/skills/tdd/    (2 files)  dev.impl, dev.lead
  update  .agents/skills/lint/   (1 file)   dev.review
```

Skills go to every seat sharing a `cwd`, not only the seats that selected them, because they share
the folder. The plan lists the seats that selected each skill. Two seats can want the same file only
if its content and permissions are identical.

## What t3rig will and won't touch

t3rig only creates files and replaces ones it wrote itself, and it never deletes. It copies each
file's permission bits, so scripts stay executable. A change to only a file's permission bits (same
bytes) isn't picked up; change the bytes, or remove the installed file, which t3rig recreates when a
recorded file is missing. It records what it wrote, with hashes, in
`~/.local/state/t3rig/skills-<rig>-<hash>.json`, saving that record before it writes anything to the
project. Without `--yes`, `up` can still re-save that record when files already match it, but only in
its own state folder, never the project.

It refuses, listing every problem and changing nothing, if a target exists and wasn't written by
t3rig (even with identical content), was edited since, is or sits under a symlink, or isn't a regular
file. Move or remove the file, or put the edit in the skill's source. Before creating a file it
checks the path is still free, and before replacing one it re-checks that it's unchanged. A narrow
window remains between that check and the write. Creating files needs a filesystem with hard links;
`up --yes` fails there, with no fallback.

A file t3rig wrote that the source no longer has stays put and is listed as a note, which `up` prints
even when nothing else changes. `down` leaves installed skills in place.

A `skill_install` startup file is copied as it is: it isn't checked for symlinks or frontmatter, as
in OpenRig.

## Running seats

A seat that's already running won't see changes made after it started. Claude Code reads project
skills from the folder the session was started in, and t3rig starts threads in the T3 project's
root and tells the seat to change folder, so skills in a `cwd` that isn't the project root might
not be picked up. That's not verified.
