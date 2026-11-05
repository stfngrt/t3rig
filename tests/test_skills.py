import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from t3rig import skills
from t3rig.rig import RigError
from t3rig.skills import apply_skills, manifest_path, plan_skills
from t3rig.spec import Rig, Seat, SkillFile


@pytest.fixture(autouse=True)
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path / "state"


def source(root: Path, name: str, text: str) -> Path:
    path = root / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def seat(
    cwd: Path, seat_id: str, *files: SkillFile, runtime: str = "claude-code", pod: str = "dev"
) -> Seat:
    return Seat(
        pod=pod,
        id=seat_id,
        runtime=runtime,
        cwd=cwd,
        agent_ref="local:a",
        profile="p",
        skills=files,
    )


def rig_of(cwd: Path, *seats: Seat) -> Rig:
    return Rig(name="r", path=cwd / "rig.yaml", seats=seats, edges=())


@pytest.fixture
def work(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def tdd(tmp_path: Path, text: str = "v1") -> SkillFile:
    return SkillFile("tdd", "SKILL.md", source(tmp_path, "tdd/SKILL.md", text))


def install(rig: Rig) -> None:
    plan = plan_skills(rig)
    assert plan.errors == []
    apply_skills(plan)


def test_no_skills_means_an_empty_plan(work: Path) -> None:
    plan = plan_skills(rig_of(work, seat(work, "a")))
    assert plan.errors == [] and not plan.has_changes and plan.lines() == []


def test_create_installs_files_and_records_them(tmp_path: Path, work: Path) -> None:
    extra = SkillFile("tdd", "ref/notes.md", source(tmp_path, "tdd/notes.md", "notes"))
    rig = rig_of(work, seat(work, "a", tdd(tmp_path), extra))
    plan = plan_skills(rig)
    assert plan.lines() == [
        f"skills in {work}:",
        "  create  .claude/skills/tdd/  (2 files)  dev.a",
    ]
    apply_skills(plan)
    assert (work / ".claude/skills/tdd/SKILL.md").read_text() == "v1"
    assert (work / ".claude/skills/tdd/ref/notes.md").read_text() == "notes"
    recorded = json.loads(manifest_path(rig, work).read_text())
    assert recorded["version"] == 1 and recorded["cwd"] == str(work)
    assert sorted(recorded["files"]) == [
        ".claude/skills/tdd/SKILL.md",
        ".claude/skills/tdd/ref/notes.md",
    ]
    assert not list(work.rglob(".t3rig-*"))


def test_rerun_changes_nothing(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    plan = plan_skills(rig)
    assert plan.errors == [] and not plan.has_changes
    assert plan.lines() == [
        f"skills in {work}:",
        "  unchanged  .claude/skills/tdd/  (1 file)  dev.a",
    ]


def test_source_change_updates_the_file(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    tdd(tmp_path, "v2")
    plan = plan_skills(rig)
    assert plan.lines()[1].startswith("  update  .claude/skills/tdd/")
    apply_skills(plan)
    assert (work / ".claude/skills/tdd/SKILL.md").read_text() == "v2"
    assert not plan_skills(rig).has_changes


def test_hand_edit_is_refused_and_left_alone(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    target = work / ".claude/skills/tdd/SKILL.md"
    target.write_text("mine")
    tdd(tmp_path, "v2")
    plan = plan_skills(rig)
    (error,) = plan.errors
    assert (
        str(target) in error
        and "edited since t3rig wrote it" in error
        and "move or remove" in error
    )
    assert target.read_text() == "mine"


def test_unmanaged_file_is_refused_even_with_identical_bytes(tmp_path: Path, work: Path) -> None:
    target = work / ".claude/skills/tdd/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("v1")
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert str(target) in error and "not written by t3rig" in error


def test_deleted_file_is_recreated(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    (work / ".claude/skills/tdd/SKILL.md").unlink()
    plan = plan_skills(rig)
    assert plan.lines()[1].startswith("  create  ")
    apply_skills(plan)
    assert (work / ".claude/skills/tdd/SKILL.md").read_text() == "v1"


def test_seats_sharing_a_folder_install_identical_files_once(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)), seat(work, "b", tdd(tmp_path)))
    plan = plan_skills(rig)
    assert plan.errors == []
    assert plan.lines()[1] == "  create  .claude/skills/tdd/  (1 file)  dev.a, dev.b"


def test_seats_wanting_different_bytes_are_an_error_naming_both(tmp_path: Path, work: Path) -> None:
    other = SkillFile("tdd", "SKILL.md", source(tmp_path, "other/SKILL.md", "different"))
    plan = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)), seat(work, "b", other)))
    (error,) = plan.errors
    assert "dev.a" in error and "dev.b" in error and "different content" in error
    assert "tdd/SKILL.md" in error and "other/SKILL.md" in error


def test_every_seat_is_planned_and_grouped_by_folder(tmp_path: Path, work: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    rig = rig_of(
        work, seat(work, "a", tdd(tmp_path)), seat(elsewhere, "b", tdd(tmp_path)), seat(work, "c")
    )
    assert [c.cwd for c in plan_skills(rig).cwds] == [work, elsewhere]


def test_codex_seats_install_under_agents(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path), runtime="codex"))
    install(rig)
    assert (work / ".agents/skills/tdd/SKILL.md").read_text() == "v1"
    assert not (work / ".claude").exists()


def test_symlinked_folder_or_file_is_refused(tmp_path: Path, work: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (work / ".claude").symlink_to(outside)
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert ".claude is a symlink" in error
    assert list(outside.iterdir()) == []

    (work / ".claude").unlink()
    (work / ".claude/skills/tdd").mkdir(parents=True)
    (work / ".claude/skills/tdd/SKILL.md").symlink_to(outside / "elsewhere.md")
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert "SKILL.md is a symlink" in error


def test_skill_folder_symlink_is_refused(tmp_path: Path, work: Path) -> None:
    (work / ".claude/skills").mkdir(parents=True)
    (work / ".claude/skills/tdd").symlink_to(tmp_path)
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert "skills/tdd is a symlink" in error


def test_folder_where_a_file_is_wanted_is_refused(tmp_path: Path, work: Path) -> None:
    (work / ".claude/skills/tdd/SKILL.md").mkdir(parents=True)
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert "is a folder where a file is wanted" in error


def test_file_where_a_folder_is_wanted_is_refused(tmp_path: Path, work: Path) -> None:
    (work / ".claude").write_text("not a folder")
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert ".claude isn't a folder" in error


@pytest.mark.parametrize(
    "content", ["not json", "[]", '{"version": 2, "files": {}}', '{"version": 1}']
)
def test_unreadable_manifest_is_an_error(tmp_path: Path, work: Path, content: str) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    path = manifest_path(rig, work)
    path.parent.mkdir(parents=True)
    path.write_text(content)
    (error,) = plan_skills(rig).errors
    assert str(path) in error


def test_nothing_is_written_when_any_seat_has_an_error(tmp_path: Path, work: Path) -> None:
    clean = tmp_path / "clean"
    clean.mkdir()
    (work / ".claude/skills/tdd").mkdir(parents=True)
    (work / ".claude/skills/tdd/SKILL.md").write_text("hand written")
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)), seat(clean, "b", tdd(tmp_path)))
    plan = plan_skills(rig)
    assert len(plan.errors) == 1
    assert not (clean / ".claude").exists()
    assert not manifest_path(rig, clean).exists() and not manifest_path(rig, work).exists()


def test_stale_file_is_left_in_place_and_noted(tmp_path: Path, work: Path) -> None:
    both = [tdd(tmp_path), SkillFile("tdd", "old.md", source(tmp_path, "tdd/old.md", "old"))]
    install(rig_of(work, seat(work, "a", *both)))
    rig = rig_of(work, seat(work, "a", tdd(tmp_path, "v2")))
    plan = plan_skills(rig)
    assert (
        plan.lines()[-1]
        == "  note: .claude/skills/tdd/old.md is no longer in source, left in place"
    )
    apply_skills(plan)
    assert (work / ".claude/skills/tdd/old.md").read_text() == "old"
    assert ".claude/skills/tdd/old.md" in json.loads(manifest_path(rig, work).read_text())["files"]


def test_operator_files_in_a_skill_folder_are_ignored(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    (work / ".claude/skills/tdd/mine.md").write_text("mine")
    plan = plan_skills(rig)
    assert plan.errors == [] and not plan.has_changes


def test_failed_write_still_records_what_was_written(
    tmp_path: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    second = SkillFile("tdd", "z.md", source(tmp_path, "tdd/z.md", "z"))
    rig = rig_of(work, seat(work, "a", tdd(tmp_path), second))
    plan = plan_skills(rig)
    (work / ".claude/skills/tdd/z.md").mkdir(parents=True)  # Appears after planning.
    with pytest.raises(RigError, match="can't install skills"):
        apply_skills(plan)
    recorded = json.loads(manifest_path(rig, work).read_text())["files"]
    assert list(recorded) == [".claude/skills/tdd/SKILL.md"]


def listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


@pytest.fixture
def read_only_state(state_home: Path) -> Iterator[Path]:
    """The state folder, existing but not writable."""
    folder = state_home / "t3rig"
    folder.mkdir(parents=True)
    folder.chmod(0o500)
    if os.access(folder, os.W_OK):
        pytest.skip("permissions aren't enforced (running as root?)")
    yield folder
    folder.chmod(0o700)


@pytest.mark.usefixtures("read_only_state")
def test_unwritable_state_folder_fails_before_touching_the_project(
    tmp_path: Path, work: Path
) -> None:
    plan = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path))))
    assert plan.errors == []
    with pytest.raises(RigError, match="can't save t3rig's record"):
        apply_skills(plan)
    assert listing(work) == []


def test_final_manifest_failure_is_reported(
    tmp_path: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path))))
    saves = []
    real = os.replace

    def replace(src: Any, dst: Any) -> None:
        if str(dst).endswith(".json") and saves:
            raise OSError(28, "No space left on device")
        saves.append(dst)
        real(src, dst)

    monkeypatch.setattr("t3rig.skills.os.replace", replace)
    with pytest.raises(RigError, match="No space left"):
        apply_skills(plan)


def test_executable_bit_is_kept_and_no_temp_files_remain(tmp_path: Path, work: Path) -> None:
    script = source(tmp_path, "tdd/run.sh", "#!/bin/sh\n")
    script.chmod(0o755)
    plain = tdd(tmp_path)
    plain.source.chmod(0o640)
    rig = rig_of(work, seat(work, "a", plain, SkillFile("tdd", "run.sh", script)))
    install(rig)
    skill = work / ".claude/skills/tdd"
    assert (skill / "run.sh").stat().st_mode & 0o777 == 0o755
    assert (skill / "SKILL.md").stat().st_mode & 0o777 == 0o640
    assert sorted(p.name for p in skill.iterdir()) == ["SKILL.md", "run.sh"]
    script.write_text("#!/bin/sh\necho changed\n")
    install(rig)
    assert (skill / "run.sh").stat().st_mode & 0o777 == 0o755


def test_seats_with_different_permissions_conflict(tmp_path: Path, work: Path) -> None:
    first = tdd(tmp_path)
    other = SkillFile("tdd", "SKILL.md", source(tmp_path, "other/SKILL.md", "v1"))
    other.source.chmod(0o755)
    plan = plan_skills(rig_of(work, seat(work, "a", first), seat(work, "b", other)))
    assert "different content or permissions" in plan.errors[0]


def test_create_refuses_a_file_that_appeared_after_planning(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    plan = plan_skills(rig)
    target = work / ".claude/skills/tdd/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand written")
    with pytest.raises(RigError, match="appeared since the plan was made"):
        apply_skills(plan)
    assert target.read_text() == "hand written"
    assert [p.name for p in target.parent.iterdir()] == ["SKILL.md"]


def test_create_without_hard_links_is_an_error_not_a_fallback(
    tmp_path: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(src: Any, dst: Any) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr("t3rig.skills.os.link", no_links)
    plan = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path))))
    with pytest.raises(RigError, match="can't create it without replacing"):
        apply_skills(plan)
    assert listing(work) == [".claude", ".claude/skills", ".claude/skills/tdd"]


def test_update_refuses_a_file_edited_after_planning(tmp_path: Path, work: Path) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    tdd(tmp_path, "v2")
    plan = plan_skills(rig)
    target = work / ".claude/skills/tdd/SKILL.md"
    target.write_text("edited just now")
    with pytest.raises(RigError, match="changed since the plan was made"):
        apply_skills(plan)
    assert target.read_text() == "edited just now"
    assert [p.name for p in target.parent.iterdir()] == ["SKILL.md"]


def test_matching_file_with_a_stale_record_is_unchanged_and_re_recorded(
    tmp_path: Path, work: Path
) -> None:
    rig = rig_of(work, seat(work, "a", tdd(tmp_path)))
    install(rig)
    path = manifest_path(rig, work)
    old = json.loads(path.read_text())
    old["files"][".claude/skills/tdd/SKILL.md"] = "0" * 64  # As if the update's record was lost.
    path.write_text(json.dumps(old))
    plan = plan_skills(rig)
    assert plan.errors == [] and not plan.has_changes
    apply_skills(plan)
    assert json.loads(path.read_text())["files"][".claude/skills/tdd/SKILL.md"] != "0" * 64
    tdd(tmp_path, "v2")
    assert plan_skills(rig).errors == []


def test_stale_entry_whose_file_is_gone_is_dropped_quietly(tmp_path: Path, work: Path) -> None:
    both = [tdd(tmp_path), SkillFile("tdd", "old.md", source(tmp_path, "tdd/old.md", "old"))]
    install(rig_of(work, seat(work, "a", *both)))
    (work / ".claude/skills/tdd/old.md").unlink()
    rig = rig_of(work, seat(work, "a", tdd(tmp_path, "v2")))
    plan = plan_skills(rig)
    assert plan.note_lines() == []
    apply_skills(plan)
    assert list(json.loads(manifest_path(rig, work).read_text())["files"]) == [
        ".claude/skills/tdd/SKILL.md"
    ]


def test_notes_alone_are_available_without_changes(tmp_path: Path, work: Path) -> None:
    both = [tdd(tmp_path), SkillFile("tdd", "old.md", source(tmp_path, "tdd/old.md", "old"))]
    install(rig_of(work, seat(work, "a", *both)))
    plan = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path))))
    assert not plan.has_changes
    assert plan.note_lines() == [
        f"skills in {work}:",
        "  note: .claude/skills/tdd/old.md is no longer in source, left in place",
    ]


def test_target_that_is_not_a_regular_file_is_refused(tmp_path: Path, work: Path) -> None:
    target = work / ".claude/skills/tdd/SKILL.md"
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    (error,) = plan_skills(rig_of(work, seat(work, "a", tdd(tmp_path)))).errors
    assert "isn't a regular file" in error


def test_interrupt_after_the_first_file_still_records_it(
    tmp_path: Path, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    second = SkillFile("tdd", "z.md", source(tmp_path, "tdd/z.md", "z"))
    rig = rig_of(work, seat(work, "a", tdd(tmp_path), second))
    plan = plan_skills(rig)
    real = skills._install
    calls = []

    def interrupted(cwd: Path, item: Any) -> None:
        calls.append(item.path)
        if len(calls) == 2:
            raise KeyboardInterrupt
        real(cwd, item)

    monkeypatch.setattr(skills, "_install", interrupted)
    with pytest.raises(KeyboardInterrupt):
        apply_skills(plan)
    recorded = json.loads(manifest_path(rig, work).read_text())["files"]
    assert list(recorded) == [".claude/skills/tdd/SKILL.md"]
    assert (work / ".claude/skills/tdd/SKILL.md").read_text() == "v1"
    assert not (work / ".claude/skills/tdd/z.md").exists()
