import os
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


def test_declared_skills_no_seat_uses_are_not_read(tmp_path: Path) -> None:
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
        ("{files: [{path: s.md, delivery_hint: bogus}]}", "delivery_hint: must be one of"),
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


@pytest.mark.parametrize("version", ['"1"', '"0.1"', '"0.2"', "v-next", "'  '"])
def test_accepts_any_non_empty_rig_version(tmp_path: Path, version: str) -> None:
    path = write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")))
    path.write_text(path.read_text().replace('version: "0.2"', f"version: {version}", 1))
    assert load_rig(path).name == "r"


@pytest.mark.parametrize(
    "version_line",
    ["", "version: ''\n", "version: 0.2\n", "version: 1\n", "version: [a]\n"],
)
def test_refuses_missing_empty_or_non_string_rig_version(tmp_path: Path, version_line: str) -> None:
    path = write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")))
    path.write_text(path.read_text().replace('version: "0.2"\n', version_line, 1))
    assert "rig.version: must be a non-empty string" in errors_for(path)


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


SKILL = "---\nname: tdd\ndescription: Test first.\n---\nWrite the test first.\n"


def skill_agent(resources: str, uses: str, imports: str = "") -> str:
    return (
        f'name: a\nversion: "1"\n{imports}resources: {resources}\n'
        f"profiles: {{default: {{uses: {{skills: {uses}}}}}}}\n"
    )


def write_skill(directory: Path, text: str = SKILL) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(text)


def skill_rig(root: Path, resources: str, uses: str, runtime: str = "claude-code") -> Path:
    return write_rig(root, pods(MEMBER % ("a", runtime)), skill_agent(resources, uses))


def installs(rig: Path) -> list[tuple[str, str, str]]:
    return [(f.folder, f.name, f.source.name) for f in load_rig(rig).seats[0].skills]


def test_selected_skill_folder_is_installed_whole(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agents" / "a"
    write_skill(agent_dir / "tdd")
    (agent_dir / "tdd" / "ref").mkdir()
    (agent_dir / "tdd" / "ref" / "notes.md").write_text("notes")
    rig = skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}, {id: other, path: x}]}", "[tdd]")
    assert installs(rig) == [
        ("tdd", "SKILL.md", "SKILL.md"),
        ("tdd", "ref/notes.md", "notes.md"),
    ]


def test_single_file_skill_keeps_its_own_name(tmp_path: Path) -> None:
    write_skill(tmp_path / "agents" / "a")
    (tmp_path / "agents" / "a" / "SKILL.md").rename(tmp_path / "agents" / "a" / "one.md")
    rig = skill_rig(tmp_path, "{skills: [{id: one, path: one.md}]}", "[one]")
    assert installs(rig) == [("one", "one.md", "one.md")]


def test_skill_install_root_follows_runtime(tmp_path: Path) -> None:
    write_skill(tmp_path / "agents" / "a" / "tdd")
    for runtime in ("claude-code", "codex"):
        rig = skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}]}", "[tdd]", runtime)
        assert load_rig(rig).seats[0].skills


@pytest.mark.parametrize(
    ("resources", "expected"),
    [
        ("{skills: [{id: s, path: /abs}]}", "path: must be a relative path"),
        ("{skills: [{id: s, path: 'C:\\x'}]}", "path: must be a relative path"),
        ("{skills: [{id: s, path: 'C:/x'}]}", "path: must be a relative path"),
        ("{skills: [{id: s, path: '../x'}]}", "path: must be a relative path"),
        ("{skills: [{id: s, path: 'a\\..\\x'}]}", "path: must be a relative path"),
        ("{skills: [{id: s, path: ''}]}", "path: must be a relative path"),
        ("{skills: [{id: s}]}", "path: must be a relative path"),
        ("{skills: [{id: '', path: x}]}", "id: required non-empty string"),
        ("{skills: [{path: x}]}", "id: required non-empty string"),
        ("{skills: [{id: a/b, path: x}]}", "can't be a skill folder name"),
        ("{skills: [{id: 'a:b', path: x}]}", "can't contain ':'"),
        ("{skills: [{id: '..', path: x}]}", "can't be a skill folder name"),
        ("{skills: [{id: s, path: x}, {id: s, path: y}]}", "duplicate id 's'"),
        ("{skills: [{id: s, path: x, extra: 1}]}", "extra: unknown key"),
        ("{skills: [x]}", "must be a mapping"),
        ("{skills: x}", "skills: must be a list"),
        ("{surprise: 1}", "resources.surprise: unknown key"),
        ("{plugins: [x]}", "resources.plugins: OpenRig feature not supported"),
        ("{runtime_resources: [x]}", "resources.runtime_resources: OpenRig feature"),
        ("{subagents: [x]}", "resources.subagents: OpenRig feature"),
        ("{hooks: [x]}", "resources.hooks: OpenRig feature"),
    ],
)
def test_refuses_bad_resources_even_when_unselected(
    tmp_path: Path, resources: str, expected: str
) -> None:
    assert expected in errors_for(skill_rig(tmp_path, resources, "[]"))


def test_empty_unsupported_resources_are_fine(tmp_path: Path) -> None:
    assert load_rig(skill_rig(tmp_path, "{plugins: [], hooks: []}", "[]"))


@pytest.mark.parametrize("key", ["subagents", "plugins", "runtime_resources"])
def test_still_refuses_uses_of_other_resources(tmp_path: Path, key: str) -> None:
    agent = AGENT.replace("uses: {skills: []}", f"uses: {{{key}: [x]}}")
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")), agent))
    assert f"uses.{key}: OpenRig feature not supported" in errors


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("no frontmatter", "needs frontmatter"),
        ("---\nname: x\nbody", "needs frontmatter"),
        ("---\n- a\n---\nbody\n", "YAML mapping"),
        ("---\nname: [\n---\nbody\n", "isn't valid YAML"),
        ("---\ndescription: d\n---\nbody\n", "'name'"),
        ("---\nname: '  '\ndescription: d\n---\nbody\n", "'name'"),
        ("---\nname: x\n---\nbody\n", "'description'"),
        ("---\nname: 1\ndescription: d\n---\nbody\n", "'name'"),
        ("---\nname: x\ndescription: d\n---\n  \n", "nothing after"),
    ],
)
def test_refuses_skills_without_usable_frontmatter(
    tmp_path: Path, text: str, expected: str
) -> None:
    write_skill(tmp_path / "agents" / "a" / "tdd", text)
    errors = errors_for(skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}]}", "[tdd]"))
    assert expected in errors


def test_skill_name_needn_match_its_id_and_crlf_is_fine(tmp_path: Path) -> None:
    write_skill(tmp_path / "agents" / "a" / "tdd", SKILL.replace("\n", "\r\n"))
    assert installs(skill_rig(tmp_path, "{skills: [{id: other, path: tdd}]}", "[other]"))


def test_folder_skill_needs_a_skill_md(tmp_path: Path) -> None:
    (tmp_path / "agents" / "a" / "tdd").mkdir(parents=True)
    (tmp_path / "agents" / "a" / "tdd" / "README.md").write_text(SKILL)
    errors = errors_for(skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}]}", "[tdd]"))
    assert "has no SKILL.md" in errors


def test_refuses_missing_skill_source(tmp_path: Path) -> None:
    errors = errors_for(skill_rig(tmp_path, "{skills: [{id: tdd, path: ghost}]}", "[tdd]"))
    assert "can't read" in errors


def test_refuses_symlinks_and_paths_leaving_the_folder(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agents" / "a"
    write_skill(tmp_path / "outside")
    write_skill(agent_dir / "inner")
    (agent_dir / "inner" / "link.md").symlink_to(tmp_path / "outside" / "SKILL.md")
    (agent_dir / "escape").symlink_to(tmp_path / "outside")
    resources = "{skills: [{id: inner, path: inner}, {id: escape, path: escape}]}"
    errors = errors_for(skill_rig(tmp_path, resources, "[inner, escape]"))
    assert "link.md is a symlink" in errors
    assert "must be a real path inside" in errors


def test_refuses_a_fifo_in_a_skill_tree(tmp_path: Path) -> None:
    write_skill(tmp_path / "agents" / "a" / "tdd")
    os.mkfifo(tmp_path / "agents" / "a" / "tdd" / "pipe")
    errors = errors_for(skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}]}", "[tdd]"))
    assert "pipe isn't a regular file" in errors


@pytest.mark.parametrize(
    ("uses", "expected"),
    [
        ("[ghost]", "'ghost' not found in resource pool"),
        ("['a:']", "isn't a valid skill id"),
        ("[':b']", "isn't a valid skill id"),
        ("['']", "isn't a valid skill id"),
        ("[1]", "skill ids must be strings"),
        ("x", "must be a list"),
        ("['nope:tdd']", "'nope:tdd' not found in resource pool"),
    ],
)
def test_refuses_bad_skill_refs(tmp_path: Path, uses: str, expected: str) -> None:
    resources = "{skills: [{id: tdd, path: tdd}]}"
    write_skill(tmp_path / "agents" / "a" / "tdd")
    assert expected in errors_for(skill_rig(tmp_path, resources, uses))


def test_unknown_skill_message_says_nothing_is_discovered(tmp_path: Path) -> None:
    errors = errors_for(skill_rig(tmp_path, "{}", "[ghost]"))
    assert "doesn't discover skills from the working folder, home or the OpenRig catalog" in errors
    assert "declare it in resources.skills" in errors


def import_skill_agent(uses: str, own: str = "[]", imports: str = "[{ref: 'local:../../shared'}]"):
    return (
        f'name: a\nversion: "1"\nimports: {imports}\nresources: {{skills: {own}}}\n'
        f"profiles: {{default: {{uses: {{skills: {uses}}}}}}}\n"
    )


def shared_skills(root: Path, directory: str = "shared", name: str = "shared") -> tuple[str, str]:
    write_skill(root / directory / "tdd")
    text = f'name: {name}\nversion: "2"\nresources: {{skills: [{{id: tdd, path: tdd}}]}}\n'
    return directory, text


def test_imported_skills_resolve_in_the_imports_folder(tmp_path: Path) -> None:
    shared = shared_skills(tmp_path)
    for ref, folder in (("tdd", "tdd"), ("shared:tdd", "shared:tdd")):
        rig = write_imports(tmp_path, import_skill_agent(f"['{ref}']"), shared)
        (item,) = load_rig(rig).seats[0].skills
        assert (item.folder, item.name) == (folder, "SKILL.md")
        assert item.source == tmp_path / "shared" / "tdd" / "SKILL.md"


def test_own_skill_wins_over_imported_for_a_bare_id(tmp_path: Path) -> None:
    shared = shared_skills(tmp_path)
    write_skill(tmp_path / "agents" / "a" / "mine", SKILL.replace("Write", "Mine"))
    agent = import_skill_agent("[tdd]", own="[{id: tdd, path: mine}]")
    (item,) = load_rig(write_imports(tmp_path, agent, shared)).seats[0].skills
    assert item.source.parent.name == "mine"


def test_refuses_ambiguous_bare_skill_in_two_imports(tmp_path: Path) -> None:
    shared = shared_skills(tmp_path)
    other = shared_skills(tmp_path, "other", "other")
    imports = "[{ref: 'local:../../shared'}, {ref: 'local:../../other'}]"
    errors = errors_for(
        write_imports(tmp_path, import_skill_agent("[tdd]", "[]", imports), shared, other)
    )
    assert "'tdd' is ambiguous (shared, other); use name:id" in errors
    rig = write_imports(tmp_path, import_skill_agent("['other:tdd']", "[]", imports), shared, other)
    assert load_rig(rig).seats[0].skills[0].folder == "other:tdd"


def test_imported_resources_are_checked(tmp_path: Path) -> None:
    shared = ("shared", 'name: shared\nversion: "2"\nresources: {plugins: [x]}\n')
    errors = errors_for(write_imports(tmp_path, import_skill_agent("[]"), shared))
    assert "resources.plugins: OpenRig feature not supported" in errors


def test_selected_skill_twice_installs_once(tmp_path: Path) -> None:
    write_skill(tmp_path / "agents" / "a" / "tdd")
    rig = skill_rig(tmp_path, "{skills: [{id: tdd, path: tdd}]}", "[tdd, tdd]")
    assert len(load_rig(rig).seats[0].skills) == 1


def startup_rig(root: Path, files: str, layout: dict[str, str] | None = None) -> Path:
    for name, text in (layout or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    body = f"startup: {{files: [{files}]}}\n" + pods(MEMBER % ("a", "claude-code"))
    return write_rig(root, body)


def test_auto_hint_installs_files_named_skill_md(tmp_path: Path) -> None:
    rig = startup_rig(tmp_path, "{path: startup/SKILL.md}", {"startup/SKILL.md": "hi"})
    seat = load_rig(rig).seats[0]
    assert seat.startup == ()
    assert [(f.folder, f.name) for f in seat.skills] == [("startup", "SKILL.md")]


def test_skill_md_in_the_rig_folder_is_named_for_that_folder(tmp_path: Path) -> None:
    seat = load_rig(startup_rig(tmp_path, "{path: SKILL.md}", {"SKILL.md": "hi"})).seats[0]
    assert seat.skills[0].folder == tmp_path.name


def test_auto_hint_matches_any_name_ending_in_skill_md(tmp_path: Path) -> None:
    rig = startup_rig(tmp_path, "{path: x/MY-SKILL.md}", {"x/MY-SKILL.md": "hi"})
    seat = load_rig(rig).seats[0]
    assert [(f.folder, f.name) for f in seat.skills] == [("x", "MY-SKILL.md")]


def test_auto_hint_sniffs_a_skill_heading(tmp_path: Path) -> None:
    rig = startup_rig(
        tmp_path,
        "{path: s/notes.md}, {path: t/other.md}",
        {"s/notes.md": "# SKILL\nx", "t/other.md": "# Other\nx"},
    )
    seat = load_rig(rig).seats[0]
    assert [f.folder for f in seat.skills] == ["s"]
    assert [item.path for item in seat.startup] == ["t/other.md"]


def test_role_files_stay_text(tmp_path: Path) -> None:
    files = "{path: SKILL.md, orientation: role}, {path: guidance/role.md}"
    rig = startup_rig(tmp_path, files, {"SKILL.md": "# SKILL", "guidance/role.md": "# SKILL"})
    seat = load_rig(rig).seats[0]
    assert seat.skills == ()
    assert [item.path for item in seat.startup] == ["SKILL.md", "guidance/role.md"]


def test_explicit_hints_are_kept(tmp_path: Path) -> None:
    files = (
        "{path: a/x.md, delivery_hint: skill_install}, {path: b/SKILL.md, delivery_hint: send_text}"
    )
    seat = load_rig(startup_rig(tmp_path, files, {"a/x.md": "hi", "b/SKILL.md": "hi"})).seats[0]
    assert [(f.folder, f.name) for f in seat.skills] == [("a", "x.md")]
    assert [item.path for item in seat.startup] == ["b/SKILL.md"]


def test_skill_install_files_keep_applies_on_and_required(tmp_path: Path) -> None:
    files = "{path: a/SKILL.md, applies_on: [restore]}, {path: b/SKILL.md, required: false}"
    assert load_rig(startup_rig(tmp_path, files)).seats[0].skills == ()
    assert "can't read" in errors_for(startup_rig(tmp_path, "{path: ghost/SKILL.md}"))
