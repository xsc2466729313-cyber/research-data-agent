"""Promote held-out official_candidate CSVs into goldset/templates/.

Independent reviewer xsc authorized writing the official entry.
Never copies goldset/breast_cancer/development/.
Never invents SDTI or copies development observations into the official column.
Does not mark frozen_test. Official SDTI stays NOT_EVALUATED until a gold_set
evaluation is actually run against this paper.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TEMPLATES = REPO / "goldset" / "templates"
DEVELOPMENT = REPO / "goldset" / "breast_cancer" / "development"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.evaluation.goldset import (  # noqa: E402
    REQUIRED_HEADERS,
    GoldSetCsvLoader,
    compute_gold_set_checksum,
)
from backend.app.evaluation.models import GoldSetManifest, ReviewStatus  # noqa: E402

REVIEWER = "xsc"
GOLD_SET_ID = "breast-cancer-official-candidate-20260829"
VERSION = "official-candidate-v1"
REVIEWED_AT = datetime(2026, 8, 29, 12, 10, tzinfo=timezone.utc)
CSV_NAMES = tuple(REQUIRED_HEADERS)


def _decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit("Official-candidate CSV is not UTF-8 or GB18030.")


def read_rows(path: Path) -> list[dict[str, str]]:
    text = _decode_csv_bytes(path.read_bytes())
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise SystemExit(f"{path.name} has no data rows.")
    return [{key: row.get(key, "") for key in REQUIRED_HEADERS[path.name]} for row in rows]


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _ids(rows: list[dict[str, str]], column: str) -> set[str]:
    return {row[column].strip() for row in rows}


def load_development_ids() -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    for filename, column in (
        ("retrieval_gold.csv", "question_id"),
        ("field_gold.csv", "case_id"),
        ("error_gold.csv", "case_id"),
    ):
        with (DEVELOPMENT / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            ids[filename] = {row[column].strip() for row in csv.DictReader(handle)}
    with (DEVELOPMENT / "retrieval_gold.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        ids["research_question"] = {row["research_question"].strip() for row in csv.DictReader(handle)}
    return ids


def envelope(checksum: str, row_counts: dict[str, int]) -> dict[str, object]:
    return {
        "split": "official_candidate",
        "not_frozen_test": True,
        "copied_to_templates": True,
        "frozen": False,
        "official_sdti_entrypoint": (
            "goldset/templates holds held-out official_candidate rows; "
            "dashboard official SDTI stays NOT_EVALUATED until a gold_set evaluation "
            "is run against this paper"
        ),
        "notice": (
            "xsc approved the held-out official candidate on 2026-08-29 and wrote it "
            "to goldset/templates. Not frozen_test. Not frozen for scoring. "
            "Do not copy development-split observations into the official dashboard column."
        ),
        "reviewed_by": REVIEWER,
        "reviewed_at": REVIEWED_AT.isoformat().replace("+00:00", "Z"),
        "row_counts": row_counts,
        "manifest": {
            "gold_set_id": GOLD_SET_ID,
            "version": VERSION,
            "frozen": False,
            "frozen_at": REVIEWED_AT.isoformat().replace("+00:00", "Z"),
            "initial_labeler": "official-candidate-draft-builder",
            "independent_reviewer": REVIEWER,
            "deterministic_rules_verified": False,
            "source_references_verified": False,
            "high_risk_review_complete": True,
            "human_reviewer": REVIEWER,
            "gold_set_checksum": checksum,
        },
    }


def main() -> None:
    if DEVELOPMENT in ROOT.parents or ROOT == DEVELOPMENT:
        raise SystemExit("Refuse to promote development split into templates.")

    tables = {name: read_rows(ROOT / name) for name in CSV_NAMES}
    for name, rows in tables.items():
        pending = [row for row in rows if row["review_status"].strip().casefold() != "approved"]
        if pending:
            raise SystemExit(f"{name} still has unapproved rows; refuse to write templates.")
        if any("66.94" in " ".join(row.values()) or "SDTI" in " ".join(row.values()) for row in rows):
            raise SystemExit(f"{name} contains SDTI/score text; refuse to write templates.")

    development_ids = load_development_ids()
    if _ids(tables["retrieval_gold.csv"], "question_id") & development_ids["retrieval_gold.csv"]:
        raise SystemExit("Refuse to copy development retrieval question_id values into templates.")
    if _ids(tables["field_gold.csv"], "case_id") & development_ids["field_gold.csv"]:
        raise SystemExit("Refuse to copy development field case_id values into templates.")
    if _ids(tables["error_gold.csv"], "case_id") & development_ids["error_gold.csv"]:
        raise SystemExit("Refuse to copy development error case_id values into templates.")
    questions = {row["research_question"].strip() for row in tables["retrieval_gold.csv"]}
    if questions & development_ids["research_question"]:
        raise SystemExit("Refuse to copy development research_question text into templates.")

    for name, rows in tables.items():
        write_csv(ROOT / name, REQUIRED_HEADERS[name], rows)
        write_csv(TEMPLATES / name, REQUIRED_HEADERS[name], rows)

    placeholder = GoldSetManifest(
        gold_set_id=GOLD_SET_ID,
        version=VERSION,
        frozen=False,
        frozen_at=REVIEWED_AT,
        initial_labeler="official-candidate-draft-builder",
        independent_reviewer=REVIEWER,
        deterministic_rules_verified=False,
        source_references_verified=False,
        high_risk_review_complete=True,
        human_reviewer=REVIEWER,
        gold_set_checksum="0" * 64,
    )
    candidate_bundle = GoldSetCsvLoader().load(ROOT, placeholder)
    template_bundle = GoldSetCsvLoader().load(TEMPLATES, placeholder)
    checksum = compute_gold_set_checksum(candidate_bundle)
    if compute_gold_set_checksum(template_bundle) != checksum:
        raise SystemExit("templates checksum does not match official_candidate.")
    if any(row.review_status is not ReviewStatus.APPROVED for row in (
        *candidate_bundle.retrieval_gold,
        *candidate_bundle.field_gold,
        *candidate_bundle.error_gold,
    )):
        raise SystemExit("Promoted rows are not all approved.")

    row_counts = {
        "retrieval_gold.csv": len(candidate_bundle.retrieval_gold),
        "field_gold.csv": len(candidate_bundle.field_gold),
        "error_gold.csv": len(candidate_bundle.error_gold),
    }
    payload = envelope(checksum, row_counts)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "MANIFEST.json").write_text(text, encoding="utf-8")
    (TEMPLATES / "MANIFEST.json").write_text(text, encoding="utf-8")

    inspection = GoldSetCsvLoader().inspect(TEMPLATES)
    if inspection.status.value != "NOT_EVALUATED":
        raise SystemExit("templates inspect must remain NOT_EVALUATED until a real evaluation run.")
    print(
        json.dumps(
            {
                "gold_set_id": GOLD_SET_ID,
                "version": VERSION,
                "copied_to_templates": True,
                "frozen": False,
                "not_frozen_test": True,
                "reviewer": REVIEWER,
                "checksum": checksum,
                **row_counts,
                "inspect_status": inspection.status.value,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
