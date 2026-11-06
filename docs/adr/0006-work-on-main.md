# The self rig works on `main` until pull requests land

**Status:** superseded by ADR 0007

The self {term}`rig`'s lead commits and pushes to `main` (`rigs/self/agents/lead/role.md`, added in
`f1264af`), and its seats share one checkout that none of them may disturb (`rigs/self/culture.md`,
added in `c002fd2`). The self rig itself was added in `63b5ce5`. Issue #9 moves rigs to a
pull-request workflow and says: "The self rig keeps working on `main` until this lands."

Why `main` was chosen first: not recorded beyond that. Consequences are that `pr` is installed for
the lead but unused, and review reads the uncommitted diff.
