# Task threads run in T3 worktrees

**Status:** accepted (#38); supersedes ADR 0007's worktree location and ADR 0008's project-root
start

t3rig, not the lead, gives an issue its git worktree: the first {term}`task thread` for issue `#N`
is launched in a new T3 worktree on the branch `issue-N`, started from the remote's default branch,
at T3's default location (outside the repo). Every later task thread of that issue, such as a
review round, binds the same worktree with `existing_worktree`, found by its branch, so a worktree
the lead made by hand is used too. ADR 0008 kept task threads in the project root because the
seats' installed skills aren't in a T3 worktree. t3rig now launches the thread idle, installs into
the worktree the skills `up` installs in the seat's folder, and only then sends the brief, so the
seat starts with them. That needs `t3_thread_launch`, so a task thread with a worktree needs
`t3rig login`.

The lead still commits (with `git -C <worktree>`) and still removes the worktree and branch after
the merge; T3 keeps a worktree when its thread is archived. `worktrees: false` in `rig.t3rig.yaml`
keeps task threads in the project root, as for a project that isn't a git repository.

Checked against T3 on 2026-11-21: `existing_worktree` binds any worktree of the project, inside the
repo or outside it, and `t3 thread list --project` still lists threads that run in worktrees. T3
checks a new worktree out after the launch returns (about 5 seconds), so t3rig waits up to a minute
for the thread's `worktreePath`. When the branch already exists, the worktree never comes and there
is no error, so t3rig archives that thread before it starts.
