# Each issue gets a worktree and a pull request

**Status:** accepted (#9), supersedes ADR 0006

The self {term}`rig`'s lead creates a git worktree per issue in `.worktrees/<n>` on a branch
`issue-<n>`, and opens a pull request for it. The pull request is the review target: `dev.review`
reviews its diff and posts its findings on it, fixes are pushed to the same branch, and the lead
squash-merges once CI is green and review is done, then removes the worktree and branch. The main
checkout stays untouched while an issue is worked. One issue is worked at a time; a second
implementer for parallel issues comes later. Worktrees live inside the repo so restricted
{term}`seats <seat>` don't stop for approval. Pull requests go out under the {term}`operator`'s
account, signed with the seat, until the rig has its own identity.
