"""Load and validate the subset of OpenRig's RigSpec format that t3rig can run.

Anything outside the subset is refused, so a rig never runs with part of its spec ignored.
"""

import os
import re
import stat
from dataclasses import dataclass, field
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
USES_KEYS = {"guidance", "skills"}
OPENRIG_ONLY_USES_KEYS = {"subagents", "plugins", "runtime_resources"}
RESOURCE_KEYS = {"guidance", "skills"}
OPENRIG_ONLY_RESOURCE_KEYS = {"plugins", "runtime_resources", "subagents", "hooks"}
SKILL_KEYS = {"id", "path"}
# Where each runtime looks for project skills, relative to the seat's folder.
SKILL_ROOTS = {"claude-code": ".claude/skills", "codex": ".agents/skills"}
STARTUP_KEYS = {"files", "actions"}
STARTUP_FILE_KEYS = {"path", "orientation", "delivery_hint", "required", "applies_on"}
TEXT_DELIVERY_HINTS = {"auto", "guidance_merge", "send_text"}
DELIVERY_HINTS = TEXT_DELIVERY_HINTS | {"skill_install"}
# As OpenRig does: the role guidance file stays text; the frontmatter pattern splits a SKILL.md.
ROLE_GUIDANCE = re.compile(r"(^|[\\/])guidance[\\/]role\.md$")
FRONTMATTER = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$")

SETTINGS_FILE = "rig.t3rig.yaml"
TRACKER_KINDS = ("github", "gitlab")
TASK_SCOPES = ("issue", "round")  # A per-task seat's thread lasts one issue, or one review round.
DEFAULT_REVIEW_ROUNDS = 2

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RIG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class SpecError(Exception):
    """A rig spec that can't be run. Holds every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class StartupText:
    """Instructions for a seat, delivered in its brief."""

    path: str
    text: str


@dataclass(frozen=True)
class SkillFile:
    """A file to copy into a seat's skills folder, as <skills root>/<folder>/<name>."""

    folder: str
    name: str
    source: Path


StartupItem = StartupText | SkillFile


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
    skills: tuple[SkillFile, ...] = ()

    @property
    def seat_id(self) -> str:
        return f"{self.pod}.{self.id}"


@dataclass(frozen=True)
class Edge:
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class TrackerSettings:
    kind: str
    repo: str
    queue_seat: str


@dataclass(frozen=True)
class Rig:
    name: str
    path: Path
    seats: tuple[Seat, ...]
    edges: tuple[Edge, ...]
    summary: str | None = None
    tracker: TrackerSettings | None = None
    review_rounds: int = DEFAULT_REVIEW_ROUNDS
    notify_seat: str | None = None
    per_task: dict[str, str] = field(default_factory=dict)  # Seat id to task scope.
    max_parallel: int = 1

    def is_per_task(self, seat: Seat) -> bool:
        return seat.seat_id in self.per_task

    def session_name(self, seat: Seat) -> str:
        """OpenRig's session name for a seat, used here as the T3 thread title."""
        return f"{seat.pod}-{seat.id}@{self.name}"

    def seat(self, seat_id: str) -> Seat | None:
        return next((s for s in self.seats if s.seat_id == seat_id), None)


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


def _resolve_hint(hint: str, orientation: Any, path: str, text: str) -> str:
    """The delivery for a startup file, resolved per file as OpenRig does for `auto`."""
    if hint != "auto":
        return hint
    if orientation == "role" or ROLE_GUIDANCE.search(path):
        return "send_text"
    if path.endswith("SKILL.md") or text.startswith("# SKILL"):
        return "skill_install"
    return "guidance_merge" if path.endswith(".md") else "send_text"


def _check_folder_name(name: str, where: str, errors: list[str]) -> bool:
    if name in ("", ".", "..") or "/" in name or "\\" in name:
        errors.append(f"{where}: {name!r} can't be a skill folder name")
        return False
    return True


def _parse_startup(raw: Any, base: Path, where: str, errors: list[str]) -> list[StartupItem]:
    """A startup block's files. Text goes in the brief; a skill_install file is copied."""
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
    items: list[StartupItem] = []
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
        if hint not in DELIVERY_HINTS:
            errors.append(f"{file_where}.delivery_hint: must be one of {sorted(DELIVERY_HINTS)}")
            continue
        applies_on = entry.get("applies_on", ["fresh_start"])
        if not isinstance(applies_on, list) or "fresh_start" not in applies_on:
            continue  # A new thread is always a fresh start.
        target = base / path
        if not target.exists() and entry.get("required", True) is False:
            continue
        text = _read_text(target, file_where, errors)
        if text is None:
            continue
        if _resolve_hint(hint, entry.get("orientation"), path, text) != "skill_install":
            items.append(StartupText(path, text))
        elif _check_folder_name(target.parent.name, f"{file_where}.path", errors):
            # The folder is the file's parent folder, so the rig folder names a top-level SKILL.md.
            items.append(SkillFile(target.parent.name, target.name, target))
    return items


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
    skills: dict[str, str]


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
        skills = _parse_resources(spec.get("resources"), f"{item_where} ({name}).resources", errors)
        imports.append(_Import(name, target, spec, skills))
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


def _is_safe_skill_path(path: str) -> bool:
    """As OpenRig does: relative, with no `..` segment once `\\` is read as `/`."""
    unified = path.replace("\\", "/")
    drive = re.match(r"^[A-Za-z]:/", unified)
    parts = unified.split("/")
    return bool(unified) and not unified.startswith("/") and not drive and ".." not in parts


def _parse_skill_pool(raw: Any, where: str, errors: list[str]) -> dict[str, str]:
    """An agent's resources.skills, as id -> path. Every entry is checked, selected or not."""
    if not isinstance(raw, list):
        errors.append(f"{where}: must be a list")
        return {}
    pool: dict[str, str] = {}
    seen: set[Any] = set()
    for index, entry in enumerate(raw):
        entry_where = f"{where}[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{entry_where}: must be a mapping")
            continue
        _check_keys(entry, SKILL_KEYS, set(), entry_where, errors)
        skill_id, path = entry.get("id"), entry.get("path")
        valid_id = isinstance(skill_id, str) and bool(skill_id)
        if not valid_id:
            errors.append(f"{entry_where}.id: required non-empty string")
        elif ":" in skill_id:
            errors.append(f"{entry_where}.id: can't contain ':' (a ref with ':' reads as name:id)")
            valid_id = False
        elif _check_folder_name(skill_id, f"{entry_where}.id", errors):
            if skill_id in seen:
                errors.append(f"{entry_where}.id: duplicate id {skill_id!r}")
            seen.add(skill_id)
        valid_path = isinstance(path, str) and _is_safe_skill_path(path)
        if not valid_path:
            errors.append(f"{entry_where}.path: must be a relative path with no '..' segment")
        elif valid_id:
            pool.setdefault(skill_id, path)
    return pool


def _parse_resources(raw: Any, where: str, errors: list[str]) -> dict[str, str]:
    """Check an agent's resources and return its skills. Guidance is checked when selected."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return {}
    _check_keys(raw, RESOURCE_KEYS, OPENRIG_ONLY_RESOURCE_KEYS, where, errors)
    if raw.get("skills") is None:
        return {}
    return _parse_skill_pool(raw["skills"], f"{where}.skills", errors)


def _skill_problem(text: str) -> str | None:
    """Why text isn't a usable SKILL.md. This is stricter than OpenRig, which checks less."""
    match = FRONTMATTER.match(text)
    if match is None:
        return "needs frontmatter between '---' lines"
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return f"has frontmatter that isn't valid YAML: {error}"
    if not isinstance(meta, dict):
        return "needs frontmatter that is a YAML mapping"
    for key in ("name", "description"):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            return f"needs a non-blank string {key!r} in its frontmatter"
    return None if match.group(2).strip() else "has nothing after its frontmatter"


def _skill_tree(source: Path, where: str, errors: list[str]) -> list[str] | None:
    """Files under a skill folder, as posix paths. Only regular files and folders are allowed."""
    names = []
    for current, folders, files in os.walk(source):
        for entry in (*folders, *files):
            path = Path(current) / entry
            if path.is_symlink():
                errors.append(f"{where}: {path} is a symlink")
                return None
            if entry in files and not stat.S_ISREG(path.lstat().st_mode):
                errors.append(f"{where}: {path} isn't a regular file")
                return None
        names += [(Path(current) / name).relative_to(source).as_posix() for name in files]
    return sorted(names)


def _skill_files(
    folder: str, base: Path, path: str, where: str, errors: list[str]
) -> list[SkillFile]:
    """The files of one skill: a folder copied whole, or one file copied under its own name."""
    base = base.resolve()
    source = base / path.replace("\\", "/")
    if source.is_symlink() or not source.resolve().is_relative_to(base):
        errors.append(f"{where}: {path!r} must be a real path inside {base}")
        return []
    if source.is_dir():
        names = _skill_tree(source, where, errors)
        if names is None:
            return []
        if "SKILL.md" not in names:
            errors.append(f"{where}: {path!r} has no SKILL.md")
            return []
        skill_md = source / "SKILL.md"
    elif source.is_file():
        names, skill_md = [source.name], source
    else:
        errors.append(f"{where}: can't read {source}")
        return []
    text = _read_text(skill_md, where, errors)
    problem = _skill_problem(text) if text is not None else None
    if problem:
        errors.append(f"{where}: {skill_md} {problem}")
    if text is None or problem:
        return []
    return [SkillFile(folder, name, source / name if source.is_dir() else source) for name in names]


def _find_skill(
    ref: Any,
    own: dict[str, str],
    directory: Path,
    imports: list[_Import],
    where: str,
    errors: list[str],
) -> tuple[Path, str] | None:
    """Where a skill is declared. `name:id` names an import; a bare id tries the agent first."""
    if not isinstance(ref, str):
        errors.append(f"{where}: skill ids must be strings (got {ref!r})")
        return None
    namespace, colon, rest = ref.partition(":")
    bare = rest if colon else ref
    if not ref or (colon and not (namespace and bare)):
        errors.append(f"{where}: {ref!r} isn't a valid skill id; use id or name:id")
        return None
    if not colon and bare in own:
        return directory, own[bare]
    if colon:
        found = [i for i in imports if i.name == namespace and bare in i.skills]
    else:
        found = [i for i in imports if bare in i.skills]
    if len(found) > 1:
        errors.append(
            f"{where}: {ref!r} is ambiguous ({', '.join(i.name for i in found)}); use name:id"
        )
        return None
    if not found:
        errors.append(
            f"{where}: {ref!r} not found in resource pool; t3rig doesn't discover skills from "
            "the working folder, home or the OpenRig catalog, so declare it in resources.skills"
        )
        return None
    return found[0].directory, found[0].skills[bare]


def _selected_skills(
    selected: Any,
    own: dict[str, str],
    directory: Path,
    imports: list[_Import],
    where: str,
    errors: list[str],
) -> list[SkillFile]:
    if selected is None:
        return []
    if not isinstance(selected, list):
        errors.append(f"{where}: must be a list")
        return []
    files: list[SkillFile] = []
    done: list[Any] = []
    for ref in selected:
        if ref in done:
            continue
        done.append(ref)
        found = _find_skill(ref, own, directory, imports, where, errors)
        # The folder is named as the ref is written, so an import's skill is `name:id`.
        if found is not None and _check_folder_name(ref, where, errors):
            files += _skill_files(ref, *found, where, errors)
    return files


@dataclass(frozen=True)
class _Agent:
    """What an agent spec contributes to a seat."""

    model: str | None = None
    effort: str | None = None
    startup: tuple[StartupItem, ...] = ()
    skills: tuple[SkillFile, ...] = ()


def _load_agent(
    agent_ref: str, profile: str, rig_root: Path, where: str, errors: list[str]
) -> _Agent:
    """The model and effort an agent spec prefers, and its instructions and skills in order."""
    directory = _agent_dir(agent_ref, rig_root)
    if directory is None:
        errors.append(f"{where}.agent_ref: must be local:<relative path> or path:<absolute path>")
        return _Agent()
    agent = _read_yaml_mapping(directory / "agent.yaml", f"{where}.agent_ref", errors)
    if agent is None:
        return _Agent()
    _check_keys(agent, AGENT_KEYS, set(), f"{where} agent", errors)
    for key in ("name", "version"):
        if not isinstance(agent.get(key), str):
            errors.append(f"{where} agent.{key}: required string")
    profiles = agent.get("profiles") or {}
    selected = profiles.get(profile) if isinstance(profiles, dict) else None
    if not isinstance(selected, dict):
        errors.append(f"{where}.profile: agent has no profile {profile!r}")
        return _Agent()
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
    own_skills = _parse_resources(agent.get("resources"), f"{where} agent.resources", errors)
    imports = _load_imports(agent, directory, f"{where} agent.imports", errors)
    skills = _selected_skills(
        uses.get("skills"), own_skills, directory, imports, f"{profile_where}.uses.skills", errors
    )
    startup = [
        *_selected_guidance(agent, uses, directory, imports, f"{profile_where}.uses", errors),
        *_parse_startup(agent.get("startup"), directory, f"{where} agent.startup", errors),
        *_parse_startup(selected.get("startup"), directory, f"{profile_where}.startup", errors),
    ]
    return _Agent(
        preferred_model or default_model,
        preferred_effort or default_effort,
        tuple(startup),
        tuple(skills),
    )


def _parse_seat(
    member: Any,
    pod_id: str,
    rig_root: Path,
    shared_startup: list[StartupItem],
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
    agent = _load_agent(member["agent_ref"], member["profile"], rig_root, where, errors)
    member_startup = _parse_startup(member.get("startup"), rig_root, f"{where}.startup", errors)
    # OpenRig's layer order: agent, profile, culture, rig, pod, member.
    startup = [*agent.startup, *shared_startup, *member_startup]
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
        model=member.get("model") or agent.model,
        effort=member.get("effort") or agent.effort,
        runtime_mode=_parse_policy(
            member.get("permission_policy"), f"{where}.permission_policy", errors
        )
        or rig_mode,
        startup=tuple(item for item in startup if isinstance(item, StartupText)),
        skills=(*agent.skills, *(item for item in startup if isinstance(item, SkillFile))),
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


def _load_notify_seat(data: dict[str, Any], seats: set[str], errors: list[str]) -> str | None:
    notify_seat = data.get("notify_seat")
    if notify_seat is not None and notify_seat not in seats:
        errors.append(f"{SETTINGS_FILE}.notify_seat: no seat {notify_seat!r} in the rig")
    return notify_seat


def _positive_int(data: dict[str, Any], key: str, default: int, errors: list[str]) -> int:
    value = data.get(key, default)
    if type(value) is not int or value < 1:
        errors.append(f"{SETTINGS_FILE}.{key}: must be a positive integer (got {value!r})")
    return value


def _load_per_task(data: dict[str, Any], seats: set[str], errors: list[str]) -> dict[str, str]:
    raw = data.get("per_task") or {}
    if not isinstance(raw, dict):
        errors.append(f"{SETTINGS_FILE}.per_task: must map seat ids to a task scope")
        return {}
    for seat, scope in raw.items():
        if seat not in seats:
            errors.append(f"{SETTINGS_FILE}.per_task: no seat {seat!r} in the rig")
        if scope not in TASK_SCOPES:
            errors.append(
                f"{SETTINGS_FILE}.per_task.{seat}: must be one of {', '.join(TASK_SCOPES)} "
                f"(got {scope!r})"
            )
    return dict(raw)


def _load_tracker(raw: Any, seats: set[str], errors: list[str]) -> TrackerSettings | None:
    if raw is None:
        return None
    where = f"{SETTINGS_FILE}.tracker"
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be a mapping")
        return None
    _check_keys(raw, {"kind", "repo", "queue_seat"}, set(), where, errors)
    kind, repo, queue_seat = raw.get("kind"), raw.get("repo"), raw.get("queue_seat")
    if kind not in TRACKER_KINDS:
        errors.append(f"{where}.kind: must be one of {', '.join(TRACKER_KINDS)} (got {kind!r})")
    if not isinstance(repo, str) or not repo:
        errors.append(f"{where}.repo: must be a non-empty string (got {repo!r})")
    if queue_seat not in seats:
        errors.append(f"{where}.queue_seat: no seat {queue_seat!r} in the rig")
    return TrackerSettings(kind, repo, queue_seat)


def _load_settings(rig_root: Path, seats: set[str], errors: list[str]) -> dict[str, Any]:
    """t3rig's own settings as `Rig` fields, kept out of `rig.yaml` (OpenRig's format)."""
    path = rig_root / SETTINGS_FILE
    if not path.exists():
        return {}
    data = _read_yaml_mapping(path, SETTINGS_FILE, errors)
    if data is None:
        return {}
    keys = {"tracker", "review_rounds", "notify_seat", "per_task", "max_parallel"}
    _check_keys(data, keys, set(), SETTINGS_FILE, errors)
    return {
        "tracker": _load_tracker(data.get("tracker"), seats, errors),
        "review_rounds": _positive_int(data, "review_rounds", DEFAULT_REVIEW_ROUNDS, errors),
        "notify_seat": _load_notify_seat(data, seats, errors),
        "per_task": _load_per_task(data, seats, errors),
        "max_parallel": _positive_int(data, "max_parallel", 1, errors),
    }


def load_rig(path: str | Path) -> Rig:
    """Parse a rig file. Raises SpecError listing every problem."""
    rig_path = Path(path).resolve()
    errors: list[str] = []
    data = _read_yaml_mapping(rig_path, "rig", errors)
    if data is None:
        raise SpecError(errors)
    rig_root = rig_path.parent

    _check_keys(data, RIG_KEYS, OPENRIG_ONLY_RIG_KEYS, "rig", errors)
    version = data.get("version")
    if not isinstance(version, str) or not version:
        errors.append(f"rig.version: must be a non-empty string (got {version!r})")
    name = data.get("name")
    if not isinstance(name, str) or not RIG_NAME_PATTERN.match(name):
        errors.append(f"rig.name: must be letters, digits, '.', '-' or '_' (got {name!r})")

    rig_mode = _parse_policy(data.get("permission_policy"), "rig.permission_policy", errors)
    rig_startup: list[StartupItem] = []
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

    seat_ids = {seat.seat_id for seat in seats}
    edges: list[Edge] = []
    for edge, where in pod_edges:
        _check_edge_ends(edge, False, seat_ids, where, errors)
        edges.append(edge)
    for edge_index, raw in enumerate(data.get("edges") or []):
        where = f"rig.edges[{edge_index}]"
        edge = _parse_edge(raw, None, where, errors)
        if edge is not None:
            _check_edge_ends(edge, True, seat_ids, where, errors)
            edges.append(edge)

    settings = _load_settings(rig_root, seat_ids, errors)
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
        **settings,
    )
