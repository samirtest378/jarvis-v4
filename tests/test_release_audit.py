from pathlib import Path

from scripts.release_audit import CONFIRMATION_FILES, human_release_blockers


def _write_minimum_release_tree(root: Path) -> None:
    (root / "docs").mkdir()
    (root / "LICENSE").write_text(
        "COMMERCIAL USE PROHIBITED WITHOUT LICENSE",
        encoding="utf-8",
    )
    (root / "docs" / "PRIVACY.md").write_text(
        "Before sale, replace this section with verified seller details.",
        encoding="utf-8",
    )


def test_human_release_blockers_cover_every_non_automatable_gate(tmp_path: Path):
    _write_minimum_release_tree(tmp_path)

    blockers = human_release_blockers(tmp_path)

    assert any("upstream license prohibits sale" in blocker for blocker in blockers)
    assert any("privacy contact" in blocker for blocker in blockers)
    for filename in CONFIRMATION_FILES.values():
        assert any(filename in blocker for blocker in blockers)


def test_verified_files_and_real_privacy_contact_remove_document_blockers(tmp_path: Path):
    _write_minimum_release_tree(tmp_path)
    (tmp_path / "LICENSE").write_text("commercial terms confirmed", encoding="utf-8")
    (tmp_path / "docs" / "PRIVACY.md").write_text(
        "Contact: Example GmbH, privacy@example.com",
        encoding="utf-8",
    )
    for filename in CONFIRMATION_FILES.values():
        (tmp_path / "docs" / filename).write_text("Reviewed evidence on file.", encoding="utf-8")

    assert human_release_blockers(tmp_path) == []
