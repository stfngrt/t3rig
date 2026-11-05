# Glossary

t3rig's domain language: the terms it borrows from [OpenRig](https://github.com/mvschwarz/openrig),
what each means here, and which T3 Code concept carries it. OpenRig citations are `path:line` under
`docs/` in that repo. Where a word has two names in use, one is preferred and the rest are listed
as _Avoid_. Planning terms marked (proposal) come from {doc}`design/planning`, which isn't built.

## Topology

```{glossary}
:sorted:

Rig
  A team of seats started from one `rig.yaml`, named by its `name`. OpenRig: "a team or project
  purpose" (`reference/topology-naming.md:9-15`). In T3 a rig has no object of its own: its seats'
  threads live in a T3 project, and the rig name is the end of every thread title.

Pod
  A group of members that share a domain or context. OpenRig: `reference/topology-naming.md:9-15`;
  its id has no dots or `@` and is the first segment of the session name
  (`reference/rig-spec.md:718`). T3 has no equivalent; a pod appears only in thread titles.

Member
  A pod's entry for one role in the rig spec: an id, an `agent_ref` and a `profile`
  (`reference/rig-spec.md:740-742`), plus the runtime and `cwd` t3rig reads from the spec. The
  spec's word for what t3rig runs as a {term}`seat`.

Seat
  A member as t3rig runs it: one T3 {term}`thread`, addressed as `pod.member`. OpenRig: "a role
  within that pod" (`reference/topology-naming.md:9-15`).

Seat id
  The logical id `pod.member`, such as `dev.impl`, used on the command line
  (`reference/topology-naming.md:17-18`).
  _Avoid_: qualified id

Session name
  `pod-member@rig`, such as `dev-impl@self` (`reference/rig-spec.md:935-946`). t3rig sets it as the
  title of the seat's T3 thread and finds the seat by that title, so renaming the thread disconnects
  it.
  _Avoid_: seat name, session address

Edge
  A relationship between two members. Five kinds: `delegates_to` (the source hands work to the
  target), `spawned_by`, `can_observe`, `collaborates_with` and `escalates_to`
  (`reference/edge-types.md:20-28`, `reference/rig-spec.md:956-962`). t3rig only acts on
  `delegates_to`; it describes the rest in the {term}`brief`.

Dispatcher
  The seat with a `delegates_to` edge to a given seat, and so the one `watch` pings about it.
  t3rig's word; OpenRig speaks of a seat's delegation parent (`reference/edge-types.md:20-28`).

Operator
  The person using t3rig. `t3rig send` without `--from` says `From: operator`. In OpenRig the
  operator is also a startup layer (`reference/agent-startup-guide.md:196`) and, per its README, the
  kernel agent a person talks to; t3rig has neither. The operator is a person, whereas a "human
  verb" is an action a person takes on a queue item.
  _Avoid_: user, human

Culture file
  A rig-wide file of team conventions, set by `culture_file` (`reference/rig-spec.md:179`). t3rig
  puts its text in each seat's {term}`brief`.
```

## Agent specs

```{glossary}
:sorted:

Agent spec
  A reusable definition of an agent: defaults (runtime, model), imports, profiles, resources and
  startup files (`reference/agent-spec.md:154-157`). A member points to one with `agent_ref`.

Profile
  A named set of choices in an {term}`agent spec`, picked by a member's `profile`; it selects
  resources with {term}`uses` (`reference/agent-spec.md:154-157`).

Import
  Another agent spec whose resources become available to a profile's {term}`uses`
  (`reference/agent-spec.md:154-157`). Imports add resources to select from and can't import further
  specs.

Resource
  Something an agent spec offers, such as a skill or guidance; the pool that profiles select from
  (`reference/agent-spec.md:154-157`). t3rig supports skills and guidance.

uses
  The profile block that selects which {term}`resources <resource>`, including imported ones, are
  active (`reference/agent-spec.md:274`).

Guidance
  A resource of an `id` and a `path` whose text tells a seat how to work
  (`reference/agent-spec.md:430-436`). Rig- and role-specific WHO and WHAT, where a {term}`skill` is
  reusable HOW (`reference/agent-startup-guide.md:99-108`).

Startup file
  A file with a `path`, an orientation, a {term}`delivery hint` and `required`/`applies_on` settings
  (`reference/rig-spec.md:1069-1082`). t3rig puts the text of every startup file in the
  {term}`brief`, or installs it as a skill.

Layer order
  The order in which layers reach a seat: agent, profile, culture, rig, pod, member, then the
  operator. Later layers append and never replace (`reference/agent-startup-guide.md:169-181`).
  t3rig follows it in the {term}`brief` and has no operator layer.

Delivery hint
  How a startup file reaches a seat: `auto`, `guidance_merge`, `skill_install` or `send_text`
  (`reference/rig-spec.md:1069-1082`). t3rig sends text in the {term}`brief` whatever the hint,
  except files it installs as skills.

Skill
  A reusable procedure: a folder with a `SKILL.md`, declared in an agent spec's `resources.skills`
  (`reference/agent-startup-guide.md:99-108`). t3rig copies skills into the seat's `cwd`; see
  {doc}`skills`.

Permission policy
  A named rule for what a seat may do without asking. OpenRig's `builtin:locked`,
  `builtin:standard`, `builtin:open` and `builtin:yolo` (`reference/rig-spec.md:427-432`); t3rig
  also accepts `builtin:auto` and maps each onto a {term}`runtime mode`. Custom policy files are
  refused.
```

## Running

```{glossary}
:sorted:

Thread
  A T3 Code conversation with an agent, carrying one {term}`seat`. `t3rig up` starts it, `send`
  writes to it and `log` reads it. Its title is the seat's {term}`session name`; "thread" is the T3
  object, "session name" the OpenRig name it carries.
  _Avoid_: session, pane

Run
  What a seat does between a message and going idle again; T3 reports its state on the thread.
  `watch` pings when one ends. (A prompt that tells an agent to "end your turn" means the same
  thing.)
  _Avoid_: turn

Brief
  The first message a seat's thread receives: its identity, its edges and every layer of
  instructions in {term}`layer order <layer order>`. A seat launched through T3's `/mcp` (one with a
  {term}`permission policy` or `effort`) gets it only after T3 confirms the seat's settings; others
  get it as the message that starts the thread. It is sent once, so it can be lost to the agent when
  its context is compacted.
  _Avoid_: first message, instructions

Envelope
  The `From:`/`To:` header on a message, taken from OpenRig. It is a label the sender writes about
  itself, not proof of who sent it.

Ping
  A short message from `watch` to a {term}`dispatcher`: one line per seat, with an excerpt of at
  most 120 characters and a link to the thread.
  _Avoid_: notification

Watch
  The foreground command that polls the seats' threads and pings dispatchers when a seat finishes a
  run or needs input. Delivery is at least once.

Stop
  `t3rig stop`: interrupt a seat's current {term}`run`. The thread stays and can be messaged.

Down
  `t3rig down`: interrupt a seat and archive its thread.

Stuck seat
  A seat that can't continue without a person: it is waiting on an {term}`approval` or a question,
  or has stopped at a usage limit. `watch` pings its dispatcher, and prints an `ALERT` when it has
  none, or when the seat stopped at a usage limit (`src/t3rig/watch.py:214,281`).

Approval
  A request from a seat to run something, held by T3 until a person answers in T3. A dispatcher
  cannot grant it.

Credential
  The sign-in `t3rig login` stores in `~/.config/t3rig/credentials.json` for 30 days. It is needed
  for {term}`permission policies <permission policy>`, effort and {term}`down`.

Access level
  The highest {term}`runtime mode` the {term}`credential` allows, set by `t3rig login --access`;
  seats can't be launched above it.
  _Avoid_: permission level

Runtime mode
  T3's mode for a thread: `approval-required`, `auto-accept-edits`, `auto` or `full-access`. t3rig
  derives it from the {term}`permission policy` and checks that T3 applied it.
  _Avoid_: permission mode
```

## Planning and tracking

These terms come from OpenRig's coordination and SDLC documents. t3rig uses the ones marked
(proposal) only in {doc}`design/planning`.

```{glossary}
:sorted:

Queue item
  OpenRig's unit of owned work, with a state, a closure reason and a transition log
  (`as-built/architecture/coordination-primitive.md:45-54`). t3rig has none; the tracker's
  {term}`ticket` takes its place.

State
  Where a queue item is: `pending`, `in-progress`, `done`, `blocked`, `failed`, `denied`, `canceled`
  or `handed-off` (`as-built/architecture/coordination-primitive.md:45-52`). In t3rig (proposal),
  labels carry a ticket's state.

Closure
  Finishing a queue item as `done` with a reason from `handed_off_to`, `denied`, `canceled`,
  `no-follow-on`, `escalation` or `superseded`
  (`as-built/architecture/coordination-primitive.md:268-294`). In t3rig (proposal), a `Closed:` line
  in the last comment: done, denied or canceled.

Human verb
  What a person does to a queue item. OpenRig has nine: `approve`, `deny`, `route`, `annotate`,
  `hold`, `drop`, `handoff`, `resolve` and `answer`
  (`as-built/architecture/mission-control.md:97-107`). t3rig (proposal) takes six as comment
  commands and leaves out `route`, `handoff` and `annotate`.

Approve
  OpenRig: closes the item as `done`/`no-follow-on`. t3rig (proposal): approves a plan, and work
  goes on.

Deny
  Rejects the work and closes it as `denied`. t3rig (proposal): only on a plan awaiting approval,
  with a reason.

Hold
  Parks the item as `blocked` (`as-built/architecture/mission-control.md:97-107`). t3rig (proposal):
  to blocked, with a reason.

Drop
  Withdraws the item and closes it as `canceled`. t3rig (proposal): with a reason.

Resolve
  Takes an item parked on a human seat or a typed gate back to work, with decision evidence.
  OpenRig: to `in-progress` (`as-built/architecture/mission-control.md:97-107`); t3rig (proposal):
  from blocked to the queue.

Answer
  Records a person's answer to a pending question. t3rig (proposal): the comment is the reply.

Route
  Hands the item to another seat as a new item (`as-built/architecture/mission-control.md:97-107`).
  Not used by t3rig.

Handoff
  Like {term}`route`, in four steps. Not used by t3rig.

Annotate
  Adds a note without changing the item, for audit only. Not used by t3rig.

Mission
  OpenRig's folder of work, which `rig scope mission create` makes with `SPEC.md`, `mission.yaml`,
  `PROGRESS.md`, `NOTES.md` and `slices/` (`reference/sdlc-conventions.md:306-309`). t3rig has no
  mission object; a {term}`ticket` is the nearest.

Slice
  A part of a mission, with `SPEC.md`, `PROGRESS.md`, `PROOF.md` and `proof/`
  (`reference/sdlc-conventions.md:108-123`); `rig scope slice create` registers it in `mission.yaml`
  (`reference/sdlc-conventions.md:303-306`). t3rig keeps the spec in the issue instead.

Proof contract
  The checkbox list of deliverables, written as observable outcomes, that says what done means
  (`reference/sdlc-conventions.md:341-342`); the third section of a slice's `SPEC.md`. Approval is
  sign-off, never proof it is green (`reference/sdlc-conventions.md:379-380`).

Proof
  A slice's evidence, kept in `PROOF.md` and `proof/` (`reference/sdlc-conventions.md:108-123`).
  t3rig has none; the closing comment records the checks.

Planning dial
  How much planning a piece of work gets, from P0 to P4: P0 mini-requirements and pointers, P1 an
  authored spec (the default), P2 plus a research round, P3 plus an adversarial pass, P4 plus a
  blind design gate (`reference/planning-dial.md:3-25`). t3rig (proposal) approves from P1 up.

Wave
  Slices built in parallel in separate file territories, merged one at a time and reviewed once by
  non-writers (`reference/wave-sdlc.md:64-70`). t3rig has none.

Handover
  Replacing a running seat's session while keeping its name: `rig seat handover <seat> --source
  fresh|rebuild|fork:<seat>|discovered:<id> --reason <reason>`
  (`as-built/architecture/lifecycle-snapshot-restore.md:295-307`). t3rig has no command (proposed in
  {doc}`research/context-management`): a new thread under the same {term}`session name` would stand
  in.

Refocus
  Delivering orientation to a running seat at its turn boundaries to correct drift
  (`reference/refocus-channel.md:3-5,194-195`). t3rig has no refocus (proposed in
  {doc}`research/context-management`), so its {term}`brief` can be lost at compaction.
```

## This workflow

How the self rig (`rigs/self`) works; see {doc}`development` and `docs/agents/triage-labels.md`.

```{glossary}
:sorted:

Ticket
  A GitHub issue that is a unit of work for the self rig. Its labels carry its state.
  _Avoid_: work item

rig-queue
  The label the operator alone adds to approve a ticket; `dev.lead` takes labelled issues in number
  order.

needs-approval
  The label `dev.pm` puts on a finished ticket. `rig-queue` wins when both are set.

in-progress
  The label `dev.lead` adds when it takes a ticket.

blocked
  The label `dev.lead` swaps in when it can't finish a ticket.

needs-answer
  A question for the operator is waiting in a comment. The ticket stays open until answered.

Project manager
  The seat `dev.pm`: works with the operator before anything is built and writes tickets. It never
  edits code and never adds `rig-queue`.

Map
  A wayfinder issue, labelled `wayfinder:map`, that indexes the decisions made and the open decision
  tickets of work too big for one session.

Decision ticket
  A child issue of a {term}`map` that a person or agent resolves with a decision, labelled
  `wayfinder:<type>`. It is not implementation work and never gets `rig-queue`.
```
