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
    assert rig.culture == "be kind"


def test_refuses_openrig_only_features(tmp_path: Path) -> None:
    body = "services: {kind: compose}\n" + pods(MEMBER % ("a", "claude-code"))
    assert "rig.services: OpenRig feature not supported" in errors_for(write_rig(tmp_path, body))


def test_refuses_unknown_keys(tmp_path: Path) -> None:
    body = "surprise: 1\n" + pods(MEMBER % ("a", "claude-code"))
    assert "rig.surprise: unknown key" in errors_for(write_rig(tmp_path, body))


def test_refuses_other_runtimes(tmp_path: Path) -> None:
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "pi"))))
    assert "runtime: must be one of" in errors


def test_refuses_agent_with_skills(tmp_path: Path) -> None:
    agent = AGENT.replace("resources: {skills: []}", "resources: {skills: [{id: s}]}")
    errors = errors_for(write_rig(tmp_path, pods(MEMBER % ("a", "claude-code")), agent))
    assert "placing resources isn't supported" in errors


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
