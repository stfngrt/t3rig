---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when discussing codebase terminology, writing or editing the glossary (`docs/glossary.md`), or recording or editing an ADR.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline: challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `docs/glossary.md` for vocabulary is not this skill: that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## File structure

The glossary and the decisions are pages of the Sphinx docs site, in one context:

```
docs/
├── glossary.md               ← the glossary, a MyST {glossary} directive
└── adr/
    ├── index.md              ← toctree listing every ADR
    ├── 0001-seats-are-threads.md
    └── 0002-supported-subset.md
```

Add a new ADR to the toctree in `docs/adr/index.md`. Leave `docs/agents/` alone: it is for the
seats and is excluded from the site. The site must still build with `-W`, so every `{term}`
reference you write has to resolve.

Create files lazily: only when you have something to write.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `docs/glossary.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account': do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible. Which is right?"

### Update docs/glossary.md inline

When a term is resolved, update `docs/glossary.md` right there. Don't batch these up: capture them as they happen. Use the format in [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md).

The glossary should be totally devoid of implementation details. Do not treat it as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse**: the cost of changing your mind later is meaningful
2. **Surprising without context**: a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off**: there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./ADR-FORMAT.md).

## In this rig

Among dev.lead, dev.impl and dev.review, only dev.impl edits files (dev.lead's one exception is
excerpt files, see the culture). If you're not dev.impl, don't edit `docs/glossary.md` or
`docs/adr/`: settle the term or the decision, then put the exact glossary entry or ADR text in the
ticket (or the task you send), and dev.impl applies it.
