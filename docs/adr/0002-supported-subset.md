# Run a subset of OpenRig specs, and refuse the rest

**Status:** accepted

t3rig runs the parts of an OpenRig spec it can honour on T3 and refuses the rest with a clear error:
"Specs using features outside the supported subset are refused" (`8c4e2bf`). Where it does support
something it copies OpenRig's rules: instructions at every layer (`a516666`), imports that only add
resources for {term}`uses` to select (`ee7e3f4`), and any non-empty `version` (`7c294ab`).

{doc}`/rig-specs` lists what is refused (plugins, subagents, hooks, runtime resources, startup
actions, custom permission policies, services, continuity policies). Why refusing was chosen over
ignoring: not recorded.
