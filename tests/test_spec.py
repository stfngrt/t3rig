from pathlib import Path

import pytest

from t3rig.spec import SpecError, load_rig

AGENT = (
    'name: a\nversion: "1"\nresources: {skills: []}\nprofiles: {default: {uses: {skills: []}}}\n'
)
MEMBER = "{id: %s, agent_ref: 'local:agents/a', profile: default, runtime: %s, cwd: .}"


def write_rig(root: Path, body: str, agent: str = AGENT) -> Path:
    (root / "agents" / "a").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "a" / "agent.yaml").write_text(agent)
    path = root / "rig.yaml"
    path.write_text(f'version: "0.2"\nname: r\n{body}')
    return path


def pods(*members: str, extra: str = "") -> str:
    return f"pods:\n  - {{id: dev, label: Dev, members: [{', '.join(members)}]{extra}}}\n"


def errors_for(path: Path) -> str:
    with pytest.raises(SpecError) as info:
        load_rig(path)
    return "\n".join(info.value.errors)


def test_loads_seats_and_edges(tmp_path: Path) -> None:
    (tmp_path / "culture.md").write_text("be kind")
    body = "culture_file: culture.md\n" + pods(
        MEMBER % ("a", "claude-code"),
        MEMBER % ("b", "codex"),
        extra=", edges: [{kind: delegates_to, from: a, to: b}]",
    )
    rig = load_rig(write_rig(tmp_path, body))
    assert [s.qualified_id for s in rig.seats] == ["dev.a", "dev.b"]
    assert rig.session_name(rig.seats[0]) == "dev-a@r"
    assert rig.seats[0].cwd == tmp_path.resolve()
    assert rig.edges[0].source == "dev.a" and rig.edges[0].target == "dev.b"
    assert [item.text for item in rig.seats[0].startup] == ["be kind"]


def test_refuses_openrig_only_features(tmp_path: Path) -> None:
    body = "services: {kind: compose}\n" + pods(MEMBER % ("a", "claude-code"))
    assert "rig.services: OpenRig feature not supported" in errors_for(write_rig(tmp_path, body))


def test_refuses_unknown_keys(tmp_path: Path) -> None:
    body = "surprise: 1\n" + pods(MEMBER % ("a", "claude-code"))
    assert "rig.surprise: unknown key" in errors_for(write_rig(tmp_path, body))


def test_refuses_other_runtimes(tmp_path: Path) -> None:
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "pi"))))
    assert "runtime: must be one of" in errors


def test_refuses_agent_using_skills(tmp_path: Path) -> None:
    agent = AGENT.replace("uses: {skills: []}", "uses: {skills: [s]}")
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")), agent))
    assert "uses.skills: OpenRig feature not supported" in errors


def test_ignores_declared_skills_no_seat_uses(tmp_path: Path) -> None:
    agent = AGENT.replace("resources: {skills: []}", "resources: {skills: [{id: s, path: s}]}")
    assert load_rig(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")), agent))


def write_layers(root: Path) -> Path:
    """A rig with one instruction file at every startup layer."""
    agent_dir = root / "agents" / "a"
    agent_dir.mkdir(parents=True)
    for name in ("guide", "agent", "profile"):
        (agent_dir / f"{name}.md").write_text(name)
    for name in ("culture", "rig", "pod", "member"):
        (root / f"{name}.md").write_text(name)
    agent = """
name: a
version: "1"
resources: {guidance: [{id: role, path: guide.md}, {id: unused, path: nope.md}]}
startup: {files: [{path: agent.md}]}
profiles:
  default:
    uses: {guidance: [role]}
    startup: {files: [{path: profile.md}]}
"""
    member = (
        "{id: a, agent_ref: 'local:agents/a', profile: default, runtime: claude-code, cwd: ., "
        "startup: {files: [{path: member.md}]}}"
    )
    extra = ", startup: {files: [{path: pod.md}]}"
    body = "culture_file: culture.md\nstartup: {files: [{path: rig.md}]}\n"
    return write_rig(root, body + pods(member, extra=extra), agent)


def test_startup_layers_follow_openrig_order(tmp_path: Path) -> None:
    rig = load_rig(write_layers(tmp_path))
    assert [item.text for item in rig.seats[0].startup] == [
        "guide",
        "agent",
        "profile",
        "culture",
        "rig",
        "pod",
        "member",
    ]


@pytest.mark.parametrize(
    ("startup", "expected"),
    [
        ("{files: [{path: ghost.md}]}", "can't read"),
        ("{files: [{path: ../secret.md}]}", "relative path inside"),
        ("{files: [{path: s.md, delivery_hint: skill_install}]}", "installing skills"),
        ("{files: [{path: x/SKILL.md}]}", "installing skills"),
        ("{actions: [{type: send_text, value: hi, idempotent: true}]}", "startup actions"),
    ],
)
def test_refuses_startup_it_cant_deliver(tmp_path: Path, startup: str, expected: str) -> None:
    body = f"startup: {startup}\n" + pods(MEMBER % ("a", "claude-code"))
    assert expected in errors_for(write_rig(tmp_path, body))


def test_skips_optional_missing_and_restore_only_files(tmp_path: Path) -> None:
    (tmp_path / "later.md").write_text("later")
    files = "[{path: ghost.md, required: false}, {path: later.md, applies_on: [restore]}]"
    body = f"startup: {{files: {files}}}\n" + pods(MEMBER % ("a", "claude-code"))
    assert load_rig(write_rig(tmp_path, body)).seats[0].startup == ()


def agent_with(extra: str, profile_extra: str = "") -> str:
    return (
        f'name: a\nversion: "1"\n{extra}\n'
        f"profiles: {{default: {{uses: {{skills: []}}{profile_extra}}}}}\n"
    )


def test_model_precedence_is_member_then_profile_then_agent(tmp_path: Path) -> None:
    defaults = "defaults: {model: from-agent}"
    prefs = ", preferences: {model: from-profile}"
    claude = MEMBER % ("a", "claude-code")
    assert load_rig(write_rig(tmp_path, pods(claude), agent_with(defaults))).seats[0].model == (
        "from-agent"
    )
    rig = load_rig(write_rig(tmp_path, pods(claude), agent_with(defaults, prefs)))
    assert rig.seats[0].model == "from-profile"
    own = claude.replace("cwd: .", "cwd: ., model: from-member")
    rig = load_rig(write_rig(tmp_path, pods(own), agent_with(defaults, prefs)))
    assert rig.seats[0].model == "from-member"


def test_lifecycle_defaults_pass_and_others_are_refused(tmp_path: Path) -> None:
    claude = pods(MEMBER % ("a", "claude-code"))
    fine = "defaults: {lifecycle: {restore_policy: resume_if_possible}}"
    assert load_rig(write_rig(tmp_path, claude, agent_with(fine)))
    bad = "defaults: {lifecycle: {restore_policy: checkpoint_only}}"
    assert "restore_policy" in errors_for(write_rig(tmp_path, claude, agent_with(bad)))


def test_effort_precedence_is_member_then_profile_then_agent(tmp_path: Path) -> None:
    claude = MEMBER % ("a", "claude-code")
    defaults = "defaults: {effort: low}"
    prefs = ", preferences: {effort: high}"
    assert (
        load_rig(write_rig(tmp_path, pods(claude), agent_with(defaults))).seats[0].effort == "low"
    )
    rig = load_rig(write_rig(tmp_path, pods(claude), agent_with(defaults, prefs)))
    assert rig.seats[0].effort == "high"
    own = claude.replace("cwd: .", "cwd: ., effort: max")
    assert (
        load_rig(write_rig(tmp_path, pods(own), agent_with(defaults, prefs))).seats[0].effort
        == "max"
    )


def test_refuses_advisor(tmp_path: Path) -> None:
    claude = pods(MEMBER % ("a", "claude-code"))
    advisor = "defaults: {advisor: x}"
    assert "defaults.advisor" in errors_for(write_rig(tmp_path, claude, agent_with(advisor)))


def test_member_policy_overrides_rig_policy(tmp_path: Path) -> None:
    claude = MEMBER % ("a", "claude-code")
    own = (MEMBER % ("b", "claude-code")).replace(
        "cwd: .", "cwd: ., permission_policy: builtin:locked"
    )
    body = "permission_policy: builtin:auto\n" + pods(claude, own)
    seats = load_rig(write_rig(tmp_path, body)).seats
    assert [s.runtime_mode for s in seats] == ["auto", "approval-required"]


def test_no_policy_means_no_mode(tmp_path: Path) -> None:
    rig = load_rig(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code"))))
    assert rig.seats[0].runtime_mode is None


def test_refuses_custom_policies(tmp_path: Path) -> None:
    body = "permission_policy: policies/mine.policy.md\n" + pods(MEMBER % ("a", "claude-code"))
    assert "custom policies can't be applied" in errors_for(write_rig(tmp_path, body))


def write_imports(root: Path, agent: str, *shared: tuple[str, str]) -> Path:
    """Add specs under root/<dir> holding agent text, then a rig using the given agent."""
    for directory, text in shared:
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / "agent.yaml").write_text(text)
    return write_rig(root, pods(MEMBER % ("a", "claude-code")), agent)


def import_agent(guidance: str, imports: str = "[{ref: 'local:../../shared'}]") -> str:
    return (
        f'name: a\nversion: "1"\nimports: {imports}\n'
        f"profiles: {{default: {{uses: {{guidance: [{guidance}]}}}}}}\n"
    )


SHARED = (
    "shared",
    'name: shared\nversion: "2"\nresources: {guidance: [{id: role, path: role.md}]}\n'
    "startup: {files: [{path: not-delivered.md}]}\n",
)


def test_imported_guidance_reads_from_the_imported_folder(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "role.md").write_text("shared role")
    for guidance in ("role", "shared:role"):
        rig = load_rig(write_imports(tmp_path, import_agent(guidance), SHARED))
        assert [item.text for item in rig.seats[0].startup] == ["shared role"]


def test_own_guidance_wins_over_imported(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "role.md").write_text("shared role")
    (tmp_path / "agents" / "a").mkdir(parents=True)
    (tmp_path / "agents" / "a" / "own.md").write_text("own role")
    agent = import_agent("role") + "resources: {guidance: [{id: role, path: own.md}]}\n"
    rig = load_rig(write_imports(tmp_path, agent, SHARED))
    assert rig.seats[0].startup[0].text == "own role"
    qualified = agent.replace("guidance: [role]", "guidance: [shared:role]")
    rig = load_rig(write_imports(tmp_path, qualified, SHARED))
    assert rig.seats[0].startup[0].text == "shared role"


def test_unused_imports_add_nothing(tmp_path: Path) -> None:
    agent = (
        'name: a\nversion: "1"\nimports: [{ref: "local:../../shared"}]\nprofiles: {default: {}}\n'
    )
    assert load_rig(write_imports(tmp_path, agent, SHARED)).seats[0].startup == ()


def test_refuses_ambiguous_guidance(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "role.md").write_text("x")
    other = ("other", SHARED[1].replace("name: shared", "name: other"))
    imports = "[{ref: 'local:../../shared'}, {ref: 'local:../../other'}]"
    errors = errors_for(write_imports(tmp_path, import_agent("role", imports), SHARED, other))
    assert "'role' is ambiguous (shared, other)" in errors


@pytest.mark.parametrize(
    ("imports", "guidance", "shared", "expected"),
    [
        ("[{ref: 'local:../../shared', version: '9'}]", "", SHARED[1], "requires version '9'"),
        ("[{ref: 'local:../../ghost'}]", "", SHARED[1], "can't read"),
        ("[{ref: 'local:.'}]", "", SHARED[1], "can't import itself"),
        ("[{ref: 'https://x/y'}]", "", SHARED[1], "must be local:"),
        (
            "[{ref: 'local:../../shared'}]",
            "",
            SHARED[1] + "imports: [{ref: 'local:../x'}]\n",
            "imports of its own",
        ),
        ("[{ref: 'local:../../shared'}]", "", 'name: "a:b"\n', "without ':'"),
        ("[{ref: 'local:../../shared'}]", "nope:role", SHARED[1], "names no imported spec"),
        ("[{ref: 'local:../../shared'}]", "ghost", SHARED[1], "no guidance resource 'ghost'"),
        (
            "[{ref: 'local:../../shared'}, {ref: 'path:SHARED'}]",
            "",
            SHARED[1],
            "two imports are named 'shared'",
        ),
    ],
)
def test_refuses_bad_imports(
    tmp_path: Path, imports: str, guidance: str, shared: str, expected: str
) -> None:
    imports = imports.replace("SHARED", str(tmp_path / "shared"))
    errors = errors_for(
        write_imports(tmp_path, import_agent(guidance, imports), ("shared", shared))
    )
    assert expected in errors


def test_agent_needs_name_and_version(tmp_path: Path) -> None:
    agent = "profiles: {default: {}}\n"
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")), agent))
    assert "agent.name" in errors and "agent.version" in errors


def test_refuses_edge_to_missing_seat(tmp_path: Path) -> None:
    extra = ", edges: [{kind: delegates_to, from: a, to: ghost}]"
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code"), extra=extra)))
    assert "no seat 'ghost'" in errors


def test_refuses_cross_pod_edge_within_one_pod(tmp_path: Path) -> None:
    body = pods(MEMBER % ("a", "claude-code"), MEMBER % ("b", "claude-code"))
    body += "edges: [{kind: delegates_to, from: dev.a, to: dev.b}]\n"
    assert "both ends are in one pod" in errors_for(write_rig(tmp_path, body))


def test_reports_every_problem(tmp_path: Path) -> None:
    errors = errors_for(write_rig(tmp_path, "surprise: 1\nservices: {kind: compose}\npods: []\n"))
    assert all(text in errors for text in ("surprise", "services", "rig.pods"))


def test_refuses_delegation_cycles(tmp_path: Path) -> None:
    extra = ", edges: [{kind: delegates_to, from: a, to: b}, {kind: delegates_to, from: b, to: a}]"
    body = pods(MEMBER % ("a", "claude-code"), MEMBER % ("b", "claude-code"), extra=extra)
    assert "form a cycle" in errors_for(write_rig(tmp_path, body))


def test_agent_ref_can_climb_out_of_the_rig_folder(tmp_path: Path) -> None:
    rig_root = tmp_path / "rigs" / "one"
    rig_root.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "agent.yaml").write_text(AGENT)
    (rig_root / "rig.yaml").write_text(
        'version: "0.2"\nname: r\n'
        + pods(MEMBER.replace("local:agents/a", "local:../../shared") % ("a", "claude-code"))
    )
    assert load_rig(rig_root / "rig.yaml").seats[0].id == "a"
