from pathlib import Path

from scripts.release_audit import CONFIRMATION_FILES, CONFIRMATION_MARKERS, human_release_blockers


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
        body = (
            "Status: APPROVED\n"
            "Reviewed by: Example Reviewer\n"
            "Review date: 2026-08-09\n"
            "Scope: JARVIS v4.1.2 Windows x64 commercial release\n"
            + "\n".join(CONFIRMATION_MARKERS[filename])
            + "\n"
        )
        if filename in {"WINDOWS_SIGNING_CONFIRMATION.md", "RELEASE_QA_CONFIRMATION.md"}:
            body += f"Artifact SHA-256: {'a' * 64}\n"
        (tmp_path / "docs" / filename).write_text(body, encoding="utf-8")

    assert human_release_blockers(tmp_path) == []


def test_placeholder_confirmation_files_do_not_unlock_a_sale(tmp_path: Path):
    _write_minimum_release_tree(tmp_path)
    (tmp_path / "LICENSE").write_text("commercial terms confirmed", encoding="utf-8")
    (tmp_path / "docs" / "PRIVACY.md").write_text(
        "Contact: Example GmbH, privacy@example.com",
        encoding="utf-8",
    )
    for filename in CONFIRMATION_FILES.values():
        (tmp_path / "docs" / filename).write_text("Reviewed evidence on file.", encoding="utf-8")

    blockers = human_release_blockers(tmp_path)
    for filename in CONFIRMATION_FILES.values():
        assert any(f"incomplete verified" in blocker and filename in blocker for blocker in blockers)


def test_confirmation_for_a_different_release_does_not_unlock_a_sale(tmp_path: Path):
    _write_minimum_release_tree(tmp_path)
    (tmp_path / "LICENSE").write_text("commercial terms confirmed", encoding="utf-8")
    (tmp_path / "docs" / "PRIVACY.md").write_text(
        "Contact: Example GmbH, privacy@example.com",
        encoding="utf-8",
    )
    for filename in CONFIRMATION_FILES.values():
        body = (
            "Status: APPROVED\n"
            "Reviewed by: Example Reviewer\n"
            "Review date: 2026-08-09\n"
            "Scope: JARVIS v4.1.1 Windows x64 commercial release\n"
            + "\n".join(CONFIRMATION_MARKERS[filename])
            + "\n"
        )
        if filename in {"WINDOWS_SIGNING_CONFIRMATION.md", "RELEASE_QA_CONFIRMATION.md"}:
            body += f"Artifact SHA-256: {'a' * 64}\n"
        (tmp_path / "docs" / filename).write_text(body, encoding="utf-8")

    blockers = human_release_blockers(tmp_path)
    for filename in CONFIRMATION_FILES.values():
        assert any(f"incomplete verified" in blocker and filename in blocker for blocker in blockers)
