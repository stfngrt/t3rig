"""Load and validate the subset of OpenRig's RigSpec format that t3rig can run.

Anything outside the subset is refused, so a rig never runs with part of its spec ignored.
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

RIG_KEYS = {
    "version",
    "name",
    "summary",
    "culture_file",
    "permission_policy",
    "startup",
    "pods",
    "edges",
}
OPENRIG_ONLY_RIG_KEYS = {
    "managed_blocks",
    "docs",
    "services",
    "workspace",
    "non_interruptive",
    "env",
}
POD_KEYS = {"id", "label", "summary", "startup", "members", "edges"}
OPENRIG_ONLY_POD_KEYS = {"continuity_policy"}
MEMBER_KEYS = {
    "id",
    "label",
    "agent_ref",
    "profile",
    "runtime",
    "model",
    "effort",
    "permission_policy",
    "cwd",
    "startup",
}
OPENRIG_ONLY_MEMBER_KEYS = {
    "codex_config_profile",
    "advisor",
    "role",
    "claude_permissions",
    "claude_token",
    "claude_mcp",
    "codex_permissions",
    "restore_policy",
    "compaction_strategy",
    "mechanic",
    "session_source",
    "starter_ref",
    "env",
    "agent_file",
    "append_system_prompt_file",
    "plugin_dirs",
    "plugin_channels",
}
EDGE_KEYS = {"kind", "from", "to"}
EDGE_KINDS = {"delegates_to", "spawned_by", "can_observe", "collaborates_with", "escalates_to"}
RUNTIMES = {"claude-code", "codex"}
AGENT_KEYS = {
    "name",
    "version",
    "description",
    "defaults",
    "imports",
    "resources",
    "profiles",
    "startup",
}
IMPORT_KEYS = {"ref", "version"}
PROFILE_KEYS = {"summary", "description", "preferences", "uses", "startup", "lifecycle"}
PREFERENCE_KEYS = {"runtime", "model", "effort", "lifecycle"}
OPENRIG_ONLY_PREFERENCE_KEYS = {"advisor"}
# T3 has four modes and OpenRig's policies are finer-grained rules, so this is approximate. Each
# maps to a mode no looser where one exists; `open` and `auto` rely on T3's auto mode's own checks.
POLICY_MODES = {
    "builtin:locked": "approval-required",
    "builtin:standard": "auto-accept-edits",
    "builtin:open": "auto",
    "builtin:auto": "auto",
    "builtin:yolo": "full-access",
}
# Lifecycle settings matching how a T3 thread already behaves, so they change nothing.
LIFECYCLE_DEFAULTS = {
    "execution_mode": "interactive_resident",
    "compaction_strategy": "default-compaction",
    "restore_policy": "resume_if_possible",
}
USES_KEYS = {"guidance"}
OPENRIG_ONLY_USES_KEYS = {"skills", "subagents", "plugins", "runtime_resources"}
STARTUP_KEYS = {"files", "actions"}
STARTUP_FILE_KEYS = {"path", "orientation", "delivery_hint", "required", "applies_on"}
TEXT_DELIVERY_HINTS = {"auto", "guidance_merge", "send_text"}

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RIG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class SpecError(Exception):
    """A rig spec that can't be run. Holds every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class StartupText:
    """Instructions for a seat, delivered in its first message."""

    path: str
    text: str


@dataclass(frozen=True)
class Seat:
    pod: str
    id: str
    runtime: str
    cwd: Path
    agent_ref: str
    profile: str
    label: str | None = None
    model: str | None = None
    effort: str | None = None
    runtime_mode: str | None = None
    startup: tuple[StartupText, ...] = ()

    @property
    def qualified_id(self) -> str:
        return f"{self.pod}.{self.id}"


@dataclass(frozen=True)
class Edge:
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class Rig:
    name: str
    path: Path
    seats: tuple[Seat, ...]
    edges: tuple[Edge, ...]
    summary: str | None = None

    def session_name(self, seat: Seat) -> str:
        """OpenRig's canonical seat name, used here as the T3 thread title."""
        return f"{seat.pod}-{seat.id}@{self.name}"

    def seat(self, qualified_id: str) -> Seat | None:
        return next((s for s in self.seats if s.qualified_id == qualified_id), None)


def _check_keys(
    obj: dict[str, Any], supported: set[str], openrig_only: set[str], where: str, errors: list[str]
) -> None:
    for key, value in obj.items():
        if key in supported:
            continue
        if key in openrig_only:
            if value:
                errors.append(f"{where}.{key}: OpenRig feature not supported by t3rig yet")
        else:
            errors.append(f"{where}.{key}: unknown key")


def _check_id(value: Any, where: str, errors: list[str]) -> bool:
    if isinstance(value, str) and ID_PATTERN.match(value):
        return True
    errors.append(f"{where}: must be letters, digits, '-' or '_' (got {value!r})")
    return False


def _read_yaml_mapping(path: Path, where: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text())
    except OSError as error:
        errors.append(f"{where}: can't read {path}: {error.strerror}")
        return None
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        errors.append(f"{where}: {path} isn't valid YAML: {error}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{where}: {path} must be a YAML mapping")
        return None
    return data


def _is_safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(path) and not pure.is_absolute() and ".." not in pure.parts


def _agent_dir(agent_ref: str, rig_root: Path) -> Path | None:
    # Unlike startup files, OpenRig lets agent_ref climb out of the rig's folder.
    if agent_ref.startswith("local:") and not Path(agent_ref.removeprefix("local:")).is_absolute():
        return rig_root / agent_ref.removeprefix("local:")
    if agent_ref.startswith("path:") and Path(agent_ref.removeprefix("path:")).is_absolute():
        return Path(agent_ref.removeprefix("path:"))
    return None


def _read_text(path: Path, where: str, errors: list[str]) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as error:
        errors.append(f"{where}: can't read {path}: {error}")
        return None


def _parse_startup(raw: Any, base: Path, where: str, errors: list[str]) -> list[StartupText]:
    """A startup block's files, as text. OpenRig places some in the harness; here all are text."""
    if raw is None:
        return []
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return []
    _check_keys(raw, STARTUP_KEYS, set(), where, errors)
    if raw.get("actions"):
        errors.append(f"{where}.actions: startup actions aren't supported by t3rig yet")
    files = raw.get("files") or []
    if not isinstance(files, list):
        errors.append(f"{where}.files: must be a list")
        return []
    texts = []
    for index, entry in enumerate(files):
        file_where = f"{where}.files[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{file_where}: must be a mapping")
            continue
        _check_keys(entry, STARTUP_FILE_KEYS, set(), file_where, errors)
        path = entry.get("path")
        if not isinstance(path, str) or not _is_safe_relative(path):
            errors.append(f"{file_where}.path: must be a relative path inside its folder")
            continue
        hint = entry.get("delivery_hint", "auto")
        if hint not in TEXT_DELIVERY_HINTS or (hint == "auto" and path.endswith("SKILL.md")):
            errors.append(f"{file_where}: installing skills isn't supported by t3rig yet")
            continue
        applies_on = entry.get("applies_on", ["fresh_start"])
        if not isinstance(applies_on, list) or "fresh_start" not in applies_on:
            continue  # A new thread is always a fresh start.
        target = base / path
        if not target.exists() and entry.get("required", True) is False:
            continue
        text = _read_text(target, file_where, errors)
        if text is not None:
            texts.append(StartupText(path, text))
    return texts


def _check_lifecycle(raw: Any, where: str, errors: list[str]) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for key, value in raw.items():
        if LIFECYCLE_DEFAULTS.get(key) != value:
            errors.append(f"{where}.{key}: only {LIFECYCLE_DEFAULTS.get(key)!r} works with t3rig")


def _parse_policy(raw: Any, where: str, errors: list[str]) -> str | None:
    """The T3 mode for an OpenRig permission_policy."""
    if raw is None:
        return None
    if raw not in POLICY_MODES:
        errors.append(
            f"{where}: must be one of {sorted(POLICY_MODES)}; custom policies can't be applied"
        )
        return None
    return POLICY_MODES[raw]


def _parse_preferences(raw: Any, where: str, errors: list[str]) -> tuple[str | None, str | None]:
    """Check agent defaults or profile preferences, and return their model and effort."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return None, None
    _check_keys(raw, PREFERENCE_KEYS, OPENRIG_ONLY_PREFERENCE_KEYS, where, errors)
    _check_lifecycle(raw.get("lifecycle"), f"{where}.lifecycle", errors)
    values = []
    for key in ("model", "effort"):
        value = raw.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{where}.{key}: must be a string")
            value = None
        values.append(value)
    return values[0], values[1]


@dataclass(frozen=True)
class _Import:
    name: str
    directory: Path
    spec: dict[str, Any]


def _load_imports(
    agent: dict[str, Any], directory: Path, where: str, errors: list[str]
) -> list[_Import]:
    """An agent's imports, under OpenRig's rules. They only add resources for `uses` to select."""
    raw = agent.get("imports") or []
    if not isinstance(raw, list):
        errors.append(f"{where}: must be a list")
        return []
    imports: list[_Import] = []
    for index, entry in enumerate(raw):
        item_where = f"{where}[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{item_where}: must be a mapping")
            continue
        _check_keys(entry, IMPORT_KEYS, set(), item_where, errors)
        ref = entry.get("ref")
        target = _agent_dir(ref, directory) if isinstance(ref, str) else None
        if target is None:
            errors.append(
                f"{item_where}.ref: must be local:<relative path> or path:<absolute path>"
            )
            continue
        if target.resolve() == directory.resolve():
            errors.append(f"{item_where}.ref: an agent can't import itself")
            continue
        spec = _read_yaml_mapping(target / "agent.yaml", f"{item_where}.ref", errors)
        if spec is None:
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name or ":" in name:
            errors.append(f"{item_where}: imported spec needs a name without ':' (got {name!r})")
            continue
        wanted = entry.get("version")
        if wanted is not None and spec.get("version") != wanted:
            errors.append(
                f"{item_where}: requires version {wanted!r}, but {name} is {spec.get('version')!r}"
            )
        if spec.get("imports"):
            errors.append(f"{item_where}: imported spec {name} can't have imports of its own")
        if any(existing.name == name for existing in imports):
            errors.append(f"{item_where}: two imports are named {name!r}")
        imports.append(_Import(name, target, spec))
    return imports


def _guidance_path(spec: dict[str, Any], guidance_id: str) -> str | None:
    resources = spec.get("resources")
    pool = resources.get("guidance") if isinstance(resources, dict) else None
    for item in pool if isinstance(pool, list) else []:
        if isinstance(item, dict) and item.get("id") == guidance_id:
            return item.get("path")
    return None


def _find_guidance(
    guidance_id: Any,
    agent: dict[str, Any],
    directory: Path,
    imports: list[_Import],
    where: str,
    errors: list[str],
) -> tuple[Path, str] | None:
    """Find a guidance resource. `name:id` names an import; a bare id tries the agent first."""
    if not isinstance(guidance_id, str):
        errors.append(f"{where}: guidance ids must be strings (got {guidance_id!r})")
        return None
    candidates: list[tuple[str, Path, dict[str, Any]]]
    if ":" in guidance_id:
        namespace, bare = guidance_id.split(":", 1)
        candidates = [(i.name, i.directory, i.spec) for i in imports if i.name == namespace]
        if not candidates:
            errors.append(f"{where}: {guidance_id!r} names no imported spec")
            return None
    else:
        bare = guidance_id
        own = _guidance_path(agent, bare)
        if own is not None:
            candidates = [("", directory, agent)]
        else:
            candidates = [
                (i.name, i.directory, i.spec)
                for i in imports
                if _guidance_path(i.spec, bare) is not None
            ]
            if len(candidates) > 1:
                names = ", ".join(name for name, _, _ in candidates)
                errors.append(f"{where}: {bare!r} is ambiguous ({names}); qualify it as name:id")
                return None
    for _, base, spec in candidates:
        path = _guidance_path(spec, bare)
        if isinstance(path, str) and _is_safe_relative(path):
            return base, path
    errors.append(f"{where}: no guidance resource {guidance_id!r} with a safe path")
    return None


def _selected_guidance(
    agent: dict[str, Any],
    uses: dict[str, Any],
    base: Path,
    imports: list[_Import],
    where: str,
    errors: list[str],
) -> list[StartupText]:
    selected = uses.get("guidance") or []
    texts = []
    for guidance_id in selected if isinstance(selected, list) else []:
        found = _find_guidance(guidance_id, agent, base, imports, f"{where}.guidance", errors)
        if found is None:
            continue
        root, path = found
        text = _read_text(root / path, f"{where}.guidance", errors)
        if text is not None:
            texts.append(StartupText(path, text))
    return texts


def _load_agent(
    agent_ref: str, profile: str, rig_root: Path, where: str, errors: list[str]
) -> tuple[str | None, str | None, list[StartupText]]:
    """Return the model and effort an agent spec prefers, and its instructions in order."""
    directory = _agent_dir(agent_ref, rig_root)
    if directory is None:
        errors.append(f"{where}.agent_ref: must be local:<relative path> or path:<absolute path>")
        return None, None, []
    agent = _read_yaml_mapping(directory / "agent.yaml", f"{where}.agent_ref", errors)
    if agent is None:
        return None, None, []
    _check_keys(agent, AGENT_KEYS, set(), f"{where} agent", errors)
    for key in ("name", "version"):
        if not isinstance(agent.get(key), str):
            errors.append(f"{where} agent.{key}: required string")
    profiles = agent.get("profiles") or {}
    selected = profiles.get(profile) if isinstance(profiles, dict) else None
    if not isinstance(selected, dict):
        errors.append(f"{where}.profile: agent has no profile {profile!r}")
        return None, None, []
    profile_where = f"{where} profile"
    _check_keys(selected, PROFILE_KEYS, set(), profile_where, errors)
    _check_lifecycle(selected.get("lifecycle"), f"{profile_where}.lifecycle", errors)
    uses = selected.get("uses") or {}
    if not isinstance(uses, dict):
        errors.append(f"{profile_where}.uses: must be a mapping")
        uses = {}
    _check_keys(uses, USES_KEYS, OPENRIG_ONLY_USES_KEYS, f"{profile_where}.uses", errors)

    default_model, default_effort = _parse_preferences(
        agent.get("defaults"), f"{where} agent.defaults", errors
    )
    preferred_model, preferred_effort = _parse_preferences(
        selected.get("preferences"), f"{profile_where}.preferences", errors
    )
    imports = _load_imports(agent, directory, f"{where} agent.imports", errors)
    texts = [
        *_selected_guidance(agent, uses, directory, imports, f"{profile_where}.uses", errors),
        *_parse_startup(agent.get("startup"), directory, f"{where} agent.startup", errors),
        *_parse_startup(selected.get("startup"), directory, f"{profile_where}.startup", errors),
    ]
    return preferred_model or default_model, preferred_effort or default_effort, texts


def _parse_seat(
    member: Any,
    pod_id: str,
    rig_root: Path,
    shared_startup: list[StartupText],
    rig_mode: str | None,
    where: str,
    errors: list[str],
) -> Seat | None:
    if not isinstance(member, dict):
        errors.append(f"{where}: must be a mapping")
        return None
    _check_keys(member, MEMBER_KEYS, OPENRIG_ONLY_MEMBER_KEYS, where, errors)
    valid = _check_id(member.get("id"), f"{where}.id", errors)
    for key in ("agent_ref", "profile", "cwd"):
        if not isinstance(member.get(key), str) or not member[key]:
            errors.append(f"{where}.{key}: required string")
            valid = False
    for key in ("label", "model", "effort"):
        if key in member and not isinstance(member[key], str):
            errors.append(f"{where}.{key}: must be a string")
            valid = False
    runtime = member.get("runtime")
    if runtime not in RUNTIMES:
        errors.append(f"{where}.runtime: must be one of {sorted(RUNTIMES)} (got {runtime!r})")
        valid = False
    if not valid:
        return None
    agent_model, agent_effort, agent_startup = _load_agent(
        member["agent_ref"], member["profile"], rig_root, where, errors
    )
    member_startup = _parse_startup(member.get("startup"), rig_root, f"{where}.startup", errors)
    cwd = (rig_root / Path(member["cwd"]).expanduser()).resolve()
    if not cwd.is_dir():
        errors.append(f"{where}.cwd: {cwd} isn't a directory")
    return Seat(
        pod=pod_id,
        id=member["id"],
        runtime=runtime,
        cwd=cwd,
        agent_ref=member["agent_ref"],
        profile=member["profile"],
        label=member.get("label"),
        model=member.get("model") or agent_model,
        effort=member.get("effort") or agent_effort,
        runtime_mode=_parse_policy(
            member.get("permission_policy"), f"{where}.permission_policy", errors
        )
        or rig_mode,
        # OpenRig's layer order: agent, profile, culture, rig, pod, member.
        startup=(*agent_startup, *shared_startup, *member_startup),
    )


def _parse_edge(raw: Any, pod_id: str | None, where: str, errors: list[str]) -> Edge | None:
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return None
    _check_keys(raw, EDGE_KEYS, set(), where, errors)
    kind, source, target = raw.get("kind"), raw.get("from"), raw.get("to")
    if kind not in EDGE_KINDS:
        errors.append(f"{where}.kind: must be one of {sorted(EDGE_KINDS)} (got {kind!r})")
        return None
    if not isinstance(source, str) or not isinstance(target, str):
        errors.append(f"{where}: from and to must be strings")
        return None
    if pod_id is None:
        return Edge(kind, source, target)
    return Edge(kind, f"{pod_id}.{source}", f"{pod_id}.{target}")


def _check_edge_ends(
    edge: Edge, cross_pod: bool, seats: set[str], where: str, errors: list[str]
) -> None:
    for end, value in (("from", edge.source), ("to", edge.target)):
        if value not in seats:
            shown = value if cross_pod else value.split(".", 1)[-1]
            errors.append(f"{where}.{end}: no seat {shown!r}")
    if cross_pod and edge.source.split(".")[0] == edge.target.split(".")[0]:
        errors.append(f"{where}: both ends are in one pod; put this edge under that pod")


def _delegation_cycles(edges: list[Edge]) -> list[str]:
    """`t3rig watch` pings along delegates_to edges, so a cycle would ping forever."""
    targets: dict[str, list[str]] = {}
    for edge in edges:
        if edge.kind == "delegates_to":
            targets.setdefault(edge.source, []).append(edge.target)

    def reaches(start: str, goal: str, seen: set[str]) -> bool:
        for target in targets.get(start, []):
            if target == goal:
                return True
            if target not in seen:
                seen.add(target)
                if reaches(target, goal, seen):
                    return True
        return False

    return [
        f"delegates_to edges form a cycle through {seat}"
        for seat in sorted(targets)
        if reaches(seat, seat, set())
    ]


def load_rig(path: str | Path) -> Rig:
    """Parse a rig file. Raises SpecError listing every problem."""
    rig_path = Path(path).resolve()
    errors: list[str] = []
    data = _read_yaml_mapping(rig_path, "rig", errors)
    if data is None:
        raise SpecError(errors)
    rig_root = rig_path.parent

    _check_keys(data, RIG_KEYS, OPENRIG_ONLY_RIG_KEYS, "rig", errors)
    if data.get("version") != "0.2":
        errors.append(f'rig.version: must be "0.2" (got {data.get("version")!r})')
    name = data.get("name")
    if not isinstance(name, str) or not RIG_NAME_PATTERN.match(name):
        errors.append(f"rig.name: must be letters, digits, '.', '-' or '_' (got {name!r})")

    rig_mode = _parse_policy(data.get("permission_policy"), "rig.permission_policy", errors)
    rig_startup: list[StartupText] = []
    culture_file = data.get("culture_file")
    if culture_file is not None:
        if not isinstance(culture_file, str) or not _is_safe_relative(culture_file):
            errors.append("rig.culture_file: must be a relative path inside the rig")
        else:
            culture = _read_text(rig_root / culture_file, "rig.culture_file", errors)
            if culture is not None:
                rig_startup.append(StartupText(culture_file, culture))
    rig_startup += _parse_startup(data.get("startup"), rig_root, "rig.startup", errors)

    seats: list[Seat] = []
    pod_edges: list[tuple[Edge, str]] = []
    pods = data.get("pods")
    if not isinstance(pods, list) or not pods:
        errors.append("rig.pods: must be a non-empty list")
        pods = []
    seen_pods: set[str] = set()
    for pod_index, pod in enumerate(pods):
        where = f"pods[{pod_index}]"
        if not isinstance(pod, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        _check_keys(pod, POD_KEYS, OPENRIG_ONLY_POD_KEYS, where, errors)
        if not isinstance(pod.get("label"), str):
            errors.append(f"{where}.label: required string")
        pod_id = pod.get("id")
        if not _check_id(pod_id, f"{where}.id", errors):
            continue
        if pod_id in seen_pods:
            errors.append(f"{where}.id: duplicate pod {pod_id!r}")
        seen_pods.add(pod_id)
        pod_startup = _parse_startup(pod.get("startup"), rig_root, f"{where}.startup", errors)
        members = pod.get("members")
        if not isinstance(members, list) or not members:
            errors.append(f"{where}.members: must be a non-empty list")
            members = []
        seen_members: set[str] = set()
        for member_index, member in enumerate(members):
            member_where = f"{where}.members[{member_index}]"
            shared = [*rig_startup, *pod_startup]
            seat = _parse_seat(member, pod_id, rig_root, shared, rig_mode, member_where, errors)
            if seat is None:
                continue
            if seat.id in seen_members:
                errors.append(f"{member_where}.id: duplicate member {seat.id!r}")
            seen_members.add(seat.id)
            seats.append(seat)
        for edge_index, raw in enumerate(pod.get("edges") or []):
            edge_where = f"{where}.edges[{edge_index}]"
            edge = _parse_edge(raw, pod_id, edge_where, errors)
            if edge is not None:
                pod_edges.append((edge, edge_where))

    qualified = {seat.qualified_id for seat in seats}
    edges: list[Edge] = []
    for edge, where in pod_edges:
        _check_edge_ends(edge, False, qualified, where, errors)
        edges.append(edge)
    for edge_index, raw in enumerate(data.get("edges") or []):
        where = f"rig.edges[{edge_index}]"
        edge = _parse_edge(raw, None, where, errors)
        if edge is not None:
            _check_edge_ends(edge, True, qualified, where, errors)
            edges.append(edge)

    if not errors:
        errors.extend(_delegation_cycles(edges))
    if errors:
        raise SpecError(errors)
    return Rig(
        name=name,
        path=rig_path,
        seats=tuple(seats),
        edges=tuple(edges),
        summary=data.get("summary"),
    )
