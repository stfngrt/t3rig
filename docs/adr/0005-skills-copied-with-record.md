# Copy skills into the seat's folder and keep an ownership record

**Status:** accepted

`t3rig up` plans the copy of each {term}`skill` into the seat's `cwd` (`.claude/skills` or
`.agents/skills`) and writes nothing without `--yes`. The README says t3rig "only creates files and
replaces ones it wrote itself, and it never deletes", records what it wrote with hashes in
`~/.local/state/t3rig/` (outside the project), and refuses a target that exists and wasn't written
by t3rig, or was edited since (`615569b`).

**Consequence:** seats that share a folder share every skill, so the operator's own sessions see
them too (issue #7, {doc}`../design/per-seat-skills`). Why the shared folder rather than storage
outside the project, as OpenRig does: not recorded in the commit. T3 has no per-thread environment
or arguments to point a seat elsewhere ({doc}`../design/per-seat-skills`).
