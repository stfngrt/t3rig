"""Install the skills a rig declares into its seats' working folders.

t3rig only creates files, and only changes files it wrote itself. It records what it wrote, with
hashes, in a manifest outside the project, so a hand-written or hand-edited file is never replaced.
It never deletes anything.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from t3rig.rig import RigError
from t3rig.spec import SKILL_ROOTS, Rig, Seat

MANIFEST_VERSION = 1
FIX = "move or remove it, or fold the edit into the skill source"


@dataclass(frozen=True)
class PlannedFile:
    path: str  # Relative to the seat's folder.
    action: str  # create, update or unchanged
    data: bytes
    mode: int  # Permission bits, from the source file.
    expected: str | None = None  # For an update, the hash the file must still have.

    @property
    def folder(self) -> str:
        return "/".join(self.path.split("/")[:3])  # <skills root>/<skill>


@dataclass
class CwdPlan:
    cwd: Path
    manifest_path: Path
    previous: dict[str, str]  # What the manifest recorded.
    recorded: dict[str, str]  # What it will record once the files are written.
    files: list[PlannedFile]
    seats: dict[str, list[str]]  # Path -> the seats that want it.
    notes: list[str]

    @property
    def changes(self) -> list[PlannedFile]:
        return [f for f in self.files if f.action != "unchanged"]

    @property
    def needs_record(self) -> bool:
        """Whether the manifest is out of date, as when files match but weren't recorded."""
        return any(self.recorded.get(f.path) != self.previous.get(f.path) for f in self.files)


@dataclass
class SkillPlan:
    cwds: list[CwdPlan] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(cwd.changes for cwd in self.cwds)

    def lines(self) -> list[str]:
        out = []
        for cwd in self.cwds:
            out.append(f"skills in {cwd.cwd}:")
            out += _folder_lines(cwd)
            out += [f"  note: {note}" for note in cwd.notes]
        return out

    def note_lines(self) -> list[str]:
        """Only the notes, for when there is nothing to change."""
        out = []
        for cwd in self.cwds:
            if cwd.notes:
                out.append(f"skills in {cwd.cwd}:")
                out += [f"  note: {note}" for note in cwd.notes]
        return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_path(rig: Rig, cwd: Path) -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    digest = hashlib.sha256(str(cwd).encode()).hexdigest()[:8]
    return base / "t3rig" / f"skills-{rig.name}-{digest}.json"


def _load_manifest(path: Path, errors: list[str]) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        errors.append(f"{path}: can't read t3rig's record of installed skills: {error}")
        return None
    files = data.get("files") if isinstance(data, dict) else None
    valid = (
        isinstance(data, dict)
        and data.get("version") == MANIFEST_VERSION
        and isinstance(files, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items())
    )
    if not valid:
        errors.append(f"{path}: isn't a t3rig skills record (version {MANIFEST_VERSION})")
        return None
    return files


@dataclass
class _Wanted:
    data: bytes
    mode: int
    who: list[tuple[str, Path]]  # The seats that selected it, and the source each used.


def _wanted(cwd: Path, seats: list[Seat], errors: list[str]) -> dict[str, _Wanted]:
    """Every file the seats of one folder want. Two different sources for one path is an error."""
    wanted: dict[str, _Wanted] = {}
    for seat in seats:
        for item in seat.skills:
            path = f"{SKILL_ROOTS[seat.runtime]}/{item.folder}/{item.name}"
            try:
                data = item.source.read_bytes()
                mode = item.source.stat().st_mode & 0o777
            except OSError as error:
                errors.append(f"{seat.seat_id}: can't read {item.source}: {error.strerror}")
                continue
            known = wanted.get(path)
            if known is None:
                wanted[path] = _Wanted(data, mode, [(seat.seat_id, item.source)])
            elif (known.data, known.mode) != (data, mode):
                first_seat, first_source = known.who[0]
                errors.append(
                    f"{cwd / path}: {first_seat} ({first_source}) and {seat.seat_id} "
                    f"({item.source}) want different content or permissions here; "
                    "make the sources match"
                )
            else:
                known.who.append((seat.seat_id, item.source))
    return wanted


def _blocked(cwd: Path, path: str) -> str | None:
    """Why t3rig can't write this file safely, if it can't."""
    parts = PurePosixPath(path).parts
    current = cwd
    for index, part in enumerate(parts):
        current = current / part
        shown = "/".join(parts[: index + 1])
        if current.is_symlink():
            return f"{shown} is a symlink"
        if index < len(parts) - 1 and current.exists() and not current.is_dir():
            return f"{shown} isn't a folder"
    if not current.resolve().is_relative_to(cwd.resolve()):
        return "it resolves outside the seat's folder"
    if current.is_dir():
        return "it is a folder where a file is wanted"
    return "it isn't a regular file" if current.exists() and not current.is_file() else None


def _classify(
    cwd: Path, path: str, want: _Wanted, recorded: dict[str, str]
) -> tuple[PlannedFile | None, str | None]:
    """The plan for one file, or an error saying why t3rig won't touch it."""
    target = cwd / path
    if problem := _blocked(cwd, path):
        return None, f"{target}: {problem}; {FIX}"
    if not target.exists():
        return PlannedFile(path, "create", want.data, want.mode), None
    if path not in recorded:
        return None, f"{target}: exists and was not written by t3rig; {FIX}"
    try:
        on_disk = _sha(target.read_bytes())
    except OSError as error:
        return None, f"{target}: can't read it: {error.strerror}"
    if on_disk == _sha(want.data):
        # Also a file t3rig wrote just before the record was saved; it gets recorded again.
        return PlannedFile(path, "unchanged", want.data, want.mode), None
    if on_disk != recorded[path]:
        return None, f"{target}: edited since t3rig wrote it; {FIX}"
    return PlannedFile(path, "update", want.data, want.mode, on_disk), None


def _plan_cwd(rig: Rig, cwd: Path, seats: list[Seat], errors: list[str]) -> CwdPlan | None:
    start = len(errors)
    wanted = _wanted(cwd, seats, errors)
    where = manifest_path(rig, cwd)
    previous = _load_manifest(where, errors)
    if previous is None:
        return None
    files = []
    for path in sorted(wanted):
        planned, error = _classify(cwd, path, wanted[path], previous)
        if planned:
            files.append(planned)
        if error:
            errors.append(error)
    if len(errors) > start:
        return None
    stale = [p for p in previous if p not in wanted and os.path.lexists(cwd / p)]
    recorded = {p: previous[p] for p in stale} | {p: _sha(wanted[p].data) for p in wanted}
    notes = [f"{p} is no longer in source, left in place" for p in sorted(stale)]
    who = {path: [seat for seat, _ in want.who] for path, want in wanted.items()}
    return CwdPlan(cwd, where, previous, recorded, files, who, notes)


def plan_skills(rig: Rig) -> SkillPlan:
    """What installing the rig's skills would do, for every seat. Writes nothing."""
    by_cwd: dict[Path, list[Seat]] = {}
    for seat in rig.seats:
        if seat.skills:
            by_cwd.setdefault(seat.cwd, []).append(seat)
    plan = SkillPlan()
    for cwd, seats in by_cwd.items():
        planned = _plan_cwd(rig, cwd, seats, plan.errors)
        if planned is not None:
            plan.cwds.append(planned)
    return plan


def _folder_lines(cwd: CwdPlan) -> list[str]:
    rows = []
    for folder in dict.fromkeys(f.folder for f in cwd.files):
        group = [f for f in cwd.files if f.folder == folder]
        changed = [f for f in group if f.action != "unchanged"]
        if not changed:
            action = "unchanged"
        elif all(f.action == "create" for f in group):
            action = "create"
        else:
            action = "update"
        count = len(changed or group)
        seats = sorted({s for f in group for s in cwd.seats[f.path]})
        rows.append((action, f"{folder}/", f"({count} file{'s' * (count != 1)})", ", ".join(seats)))
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    return [
        "  " + "  ".join([*(cell.ljust(w) for cell, w in zip(row, widths, strict=False)), row[3]])
        for row in rows
    ]


@contextmanager
def _staged(path: Path, data: bytes, mode: int) -> Iterator[Path]:
    """The data in a temp file beside the target, with its mode; removed afterwards."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".t3rig-")
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
        yield temp
    finally:
        temp.unlink(missing_ok=True)


def _install(cwd: Path, item: PlannedFile) -> None:
    """Create the file without replacing anything, or replace it if it is still as planned."""
    target = cwd / item.path
    with _staged(target, item.data, item.mode) as temp:
        if item.expected is None:
            try:
                os.link(temp, target)  # Fails if the path exists, and there is no fallback.
            except FileExistsError:
                raise RigError(
                    f"{target}: appeared since the plan was made; not replacing it"
                ) from None
            except OSError as error:
                raise RigError(
                    f"{target}: can't create it without replacing: {error.strerror}"
                ) from error
        else:
            try:
                unedited = _sha(target.read_bytes()) == item.expected
            except OSError:
                unedited = False
            if not unedited:
                raise RigError(f"{target}: changed since the plan was made; not replacing it")
            os.replace(temp, target)


def _save_manifest(cwd: CwdPlan, files: dict[str, str]) -> None:
    document: dict[str, Any] = {"version": MANIFEST_VERSION, "cwd": str(cwd.cwd), "files": files}
    data = json.dumps(document, indent=2, sort_keys=True).encode()
    try:
        with _staged(cwd.manifest_path, data, 0o600) as temp:
            os.replace(temp, cwd.manifest_path)
    except OSError as error:
        raise RigError(
            f"can't save t3rig's record of installed skills at {cwd.manifest_path}: "
            f"{error.strerror}; nothing more was written to {cwd.cwd}"
        ) from error


def _record_partial(cwd: CwdPlan, written: dict[str, str]) -> str | None:
    """Record the files already written, so the next run owns them. Returns why it couldn't."""
    try:
        _save_manifest(cwd, {**cwd.previous, **written})
    except RigError as error:
        return str(error)
    return None


def _install_all(cwd: CwdPlan) -> None:
    written: dict[str, str] = {}
    try:
        for item in cwd.changes:
            _install(cwd.cwd, item)
            written[item.path] = _sha(item.data)
    except (OSError, RigError) as error:
        message = f"can't install skills in {cwd.cwd}: {error}"
        if problem := _record_partial(cwd, written):
            message += f" (and the files already written aren't recorded: {problem})"
        raise RigError(message) from error
    except BaseException:  # Ctrl-C and the like still leave the files recorded.
        _record_partial(cwd, written)
        raise


def apply_skills(plan: SkillPlan) -> None:
    """Write the planned files, then record them.

    The record is saved first as it was, so an unwritable state folder fails before the project is
    touched, and again afterwards with the new files.
    """
    pending = [cwd for cwd in plan.cwds if cwd.changes or cwd.needs_record]
    for cwd in pending:
        if cwd.changes:
            _save_manifest(cwd, cwd.previous)
    for cwd in pending:
        _install_all(cwd)
        _save_manifest(cwd, cwd.recorded)
