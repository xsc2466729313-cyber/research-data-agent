"""Freeze the development Gold Set after human review.

Does not copy rows into goldset/templates/. Does not invent SDTI.
Requires live HTTPS checks against allowlisted official hosts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.evaluation.goldset import GoldSetCsvLoader, compute_gold_set_checksum
from backend.app.evaluation.models import GoldSetBundle, GoldSetManifest, ReviewStatus, RiskLevel
from backend.app.goldset.models import SourceReference, VerificationStatus
from backend.app.goldset.source_verifier import OfficialSourceVerifier

INITIAL_LABELER = "development-draft-builder"
INDEPENDENT_REVIEWER = "xsc"
GOLD_SET_ID = "breast-cancer-development-20260829"
VERSION = "development-v1"

OFFICIAL_SOURCES: list[SourceReference] = [
    SourceReference(
        source_id="geo:GSE76360",
        source_database="geo",
        accession="GSE76360",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360",
    ),
    SourceReference(
        source_id="geo:GSE25066",
        source_database="geo",
        accession="GSE25066",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066",
    ),
    SourceReference(
        source_id="geo:GSE96058",
        source_database="geo",
        accession="GSE96058",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058",
    ),
    SourceReference(
        source_id="cbioportal:brca_metabric",
        source_database="cbioportal",
        accession="brca_metabric",
        url="https://www.cbioportal.org/api/studies/brca_metabric",
    ),
    SourceReference(
        source_id="cbioportal:breast_alpelisib_2020",
        source_database="cbioportal",
        accession="breast_alpelisib_2020",
        url="https://www.cbioportal.org/api/studies/breast_alpelisib_2020",
    ),
    SourceReference(
        source_id="cbioportal:brca_mskcc_2019",
        source_database="cbioportal",
        accession="brca_mskcc_2019",
        url="https://www.cbioportal.org/api/studies/brca_mskcc_2019",
    ),
    SourceReference(
        source_id="gdc:TCGA-BRCA",
        source_database="gdc",
        accession="TCGA-BRCA",
        url="https://api.gdc.cancer.gov/projects/TCGA-BRCA",
    ),
    SourceReference(
        source_id="aact:NCT01042379",
        source_database="aact",
        accession="NCT01042379",
        url="https://clinicaltrials.gov/api/v2/studies/NCT01042379",
    ),
]

EXTRA_OFFICIAL_PAGES = [
    {
        "source_id": "depmap:portal",
        "dataset_id": "DepMap",
        "url": "https://depmap.org/portal/",
        "must_contain": "depmap",
        "reason": "DepMap 不在 goldset_rules allowlist；额外核验 Broad 官方门户。",
    },
    {
        "source_id": "aact:home",
        "dataset_id": "AACT",
        "url": "https://aact.ctti-clinicaltrials.org/",
        "must_contain": "aact",
        "reason": "AACT 是 ClinicalTrials.gov 公开聚合层；具体 NCT 已走 allowlist。",
    },
    {
        "source_id": "civic:home",
        "dataset_id": "CIViC",
        "url": "https://civicdb.org/",
        "must_contain": "civic",
        "reason": "Gold 行 dataset_id=CIViC 指向知识库而非单个 EID；具体证据走 GraphQL。",
    },
]


def load_bundle(*, checksum: str = "0" * 64, frozen: bool = False) -> GoldSetBundle:
    return GoldSetCsvLoader().load(
        ROOT,
        GoldSetManifest(
            gold_set_id=GOLD_SET_ID,
            version=VERSION,
            frozen=frozen,
            frozen_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            initial_labeler=INITIAL_LABELER,
            independent_reviewer=INDEPENDENT_REVIEWER,
            deterministic_rules_verified=False,
            source_references_verified=False,
            high_risk_review_complete=False,
            human_reviewer=INDEPENDENT_REVIEWER,
            gold_set_checksum=checksum,
        ),
    )


def check_review_and_rules(bundle: GoldSetBundle) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    schema = yaml.safe_load(
        (REPO / "configs" / "canonical_schema.yaml").read_text(encoding="utf-8")
    )
    fields = schema["fields"]
    rows = [*bundle.retrieval_gold, *bundle.field_gold, *bundle.error_gold]
    if not rows:
        raise SystemExit("Gold Set CSVs are empty.")
    pending = [
        getattr(row, "case_id", getattr(row, "question_id", "?"))
        for row in rows
        if row.review_status is not ReviewStatus.APPROVED
    ]
    findings.append(
        {
            "rule_id": "ALL_ROWS_APPROVED",
            "passed": "true" if not pending else "false",
            "detail": "ok" if not pending else "unapproved: " + ",".join(pending[:12]),
        }
    )
    if pending:
        raise SystemExit("All rows must be approved before freeze.")

    field_by_id = {row.case_id: row for row in bundle.field_gold}
    error_by_id = {row.case_id: row for row in bundle.error_gold}

    def require(rule_id: str, ok: bool, detail: str) -> None:
        findings.append({"rule_id": rule_id, "passed": "true" if ok else "false", "detail": detail})
        if not ok:
            raise SystemExit(f"Rule failed: {rule_id}: {detail}")

    ihc2 = field_by_id["f04_ihc2_equivocal"]
    require(
        "HER2_IHC_2PLUS",
        ihc2.canonical_field == "her2_status"
        and ihc2.canonical_value == "Equivocal"
        and ihc2.allowed_auto_transform is False,
        "IHC 2+ must stay Equivocal and not auto-transform to Positive.",
    )
    cna = field_by_id["f12_cna_not_ihc"]
    require(
        "ERBB2_CNA_NOT_IHC",
        cna.canonical_value != "Positive" and cna.allowed_auto_transform is False,
        "ERBB2 CNA must not be labeled HER2 Positive.",
    )
    auc = field_by_id["f25_auc_not_pcr"]
    require(
        "CROSS_DOMAIN_RESPONSE",
        auc.canonical_value != "pCR" and auc.allowed_auto_transform is False,
        "Cell-line AUC must not be stored as patient pCR.",
    )
    for case_id in (
        "e01_ihc2_to_positive",
        "e02_cna_as_ihc",
        "e03_cross_study_id",
        "e04_auc_as_pcr",
        "e16_join_without_crosswalk",
    ):
        row = error_by_id[case_id]
        require(
            f"HIGH_RISK_{case_id}",
            row.risk_level is RiskLevel.HIGH and row.auto_repair_allowed is False,
            "High-risk error must not allow automatic repair.",
        )
    illegal_auto = [
        row.case_id
        for row in bundle.error_gold
        if row.risk_level is RiskLevel.HIGH and row.auto_repair_allowed
    ]
    require(
        "NO_HIGH_RISK_AUTO_REPAIR",
        not illegal_auto,
        "ok" if not illegal_auto else ",".join(illegal_auto),
    )
    for row in bundle.field_gold:
        config = fields.get(row.canonical_field)
        require(
            f"SCHEMA_FIELD_{row.case_id}",
            config is not None,
            row.canonical_field,
        )
        allowed = config.get("allowed") if config else None
        if allowed is not None:
            require(
                f"SCHEMA_VALUE_{row.case_id}",
                row.canonical_value in {str(item) for item in allowed},
                f"{row.canonical_field}={row.canonical_value}",
            )
    require(
        "INDEPENDENT_REVIEWER",
        INITIAL_LABELER.casefold() != INDEPENDENT_REVIEWER.casefold(),
        f"{INITIAL_LABELER} vs {INDEPENDENT_REVIEWER}",
    )
    return findings


def _curl_get(url: str, marker: str, allowed_host: str) -> dict:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        return {
            "status": "failed",
            "http_status": None,
            "checked_url": None,
            "response_sha256": None,
            "reason": "curl is not available for the official-host fallback.",
        }
    with tempfile.TemporaryDirectory() as tmp:
        body_path = Path(tmp) / "body.bin"
        completed = subprocess.run(
            [
                curl,
                "-sS",
                "-L",
                "--max-time",
                "20",
                "-A",
                "breast-research-goldset-verifier/0.1",
                "-o",
                str(body_path),
                "-w",
                "%{http_code} %{url_effective}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return {
                "status": "failed",
                "http_status": None,
                "checked_url": None,
                "response_sha256": None,
                "reason": completed.stderr.strip() or "curl official-host request failed.",
            }
        meta = completed.stdout.strip().rsplit(" ", 1)
        if len(meta) != 2:
            return {
                "status": "failed",
                "http_status": None,
                "checked_url": None,
                "response_sha256": None,
                "reason": "curl did not return status and final URL.",
            }
        status_text, final_url = meta
        try:
            http_status = int(status_text)
        except ValueError:
            http_status = None
        body = body_path.read_bytes()[:1_000_000]
        digest = hashlib.sha256(body).hexdigest()
        hostname = (urlparse(final_url).hostname or "").casefold()
        host_ok = hostname == allowed_host or hostname.endswith(f".{allowed_host}")
        marker_ok = marker.casefold().encode("utf-8") in body.lower()
        ok = (
            http_status is not None
            and 200 <= http_status < 300
            and host_ok
            and marker_ok
        )
        return {
            "status": "verified" if ok else "failed",
            "http_status": http_status,
            "checked_url": final_url,
            "response_sha256": digest,
            "reason": (
                "Official marker found via curl GET after Python httpx was blocked."
                if ok
                else "curl official-host fallback failed host, HTTP, or marker check."
            ),
        }


def verify_official_sources() -> list[dict]:
    verifier = OfficialSourceVerifier()
    records: list[dict] = []
    host_by_db = {
        "geo": "ncbi.nlm.nih.gov",
        "cbioportal": "cbioportal.org",
        "gdc": "gdc.cancer.gov",
        "aact": "clinicaltrials.gov",
        "civic": "civicdb.org",
    }
    try:
        for source in OFFICIAL_SOURCES:
            result = verifier.verify(source)
            record = {
                "kind": "allowlist",
                "method": "live_official_http_v1",
                "source_id": source.source_id,
                "accession": source.accession,
                "url": source.url,
                "status": result.status.value,
                "http_status": result.http_status,
                "checked_url": result.checked_url,
                "response_sha256": result.response_sha256,
                "reason": result.reason,
                "checked_at": result.checked_at.isoformat(),
            }
            if record["status"] != VerificationStatus.VERIFIED.value:
                fallback = _curl_get(
                    source.url,
                    source.accession,
                    host_by_db[source.source_database.value],
                )
                record.update(fallback)
                record["kind"] = "allowlist"
                record["method"] = "curl_get_official_fallback"
                record["checked_at"] = datetime.now(timezone.utc).isoformat()
            records.append(record)
    finally:
        verifier.close()
    failed = [item for item in records if item["status"] != VerificationStatus.VERIFIED.value]
    if failed:
        raise SystemExit(
            "Official allowlist verification failed: "
            + json.dumps(failed, ensure_ascii=False)
        )
    return records


def verify_civic_graphql() -> dict:
    payload = {
        "query": "query ($id: Int!) { evidenceItem(id: $id) { id name status } }",
        "variables": {"id": 7316},
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "breast-cancer-research-data-agent/0.6",
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = client.post("https://civicdb.org/api/graphql", json=payload)
    digest = hashlib.sha256(response.content[:1_000_000]).hexdigest()
    body = response.text
    hostname = (urlparse(str(response.url)).hostname or "").casefold()
    ok = (
        200 <= response.status_code < 300
        and "7316" in body
        and "ACCEPTED" in body
        and (hostname == "civicdb.org" or hostname.endswith(".civicdb.org"))
    )
    if not ok:
        raise SystemExit(
            "CIViC GraphQL verification failed: "
            + json.dumps(
                {"http_status": response.status_code, "body": body[:300]},
                ensure_ascii=False,
            )
        )
    return {
        "kind": "civic_graphql_post_v2",
        "source_id": "civic:evidence-7316",
        "accession": "7316",
        "url": "https://civicdb.org/api/graphql",
        "status": "verified",
        "http_status": response.status_code,
        "checked_url": str(response.url),
        "response_sha256": digest,
        "reason": "CIViC v2 GraphQL returned ACCEPTED evidence 7316 on civicdb.org.",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_extra_pages() -> list[dict]:
    records: list[dict] = []
    timeout = httpx.Timeout(15.0)
    headers = {"User-Agent": "breast-research-goldset-verifier/0.1"}
    host_by_id = {
        "depmap:portal": "depmap.org",
        "aact:home": "aact.ctti-clinicaltrials.org",
        "civic:home": "civicdb.org",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for item in EXTRA_OFFICIAL_PAGES:
            try:
                response = client.get(item["url"])
                body = response.content[:1_000_000]
                digest = hashlib.sha256(body).hexdigest()
                marker_ok = item["must_contain"].casefold().encode("utf-8") in body.lower()
                ok = 200 <= response.status_code < 300 and marker_ok
                record = {
                    "kind": "extra_official_page",
                    "method": "httpx_get",
                    "source_id": item["source_id"],
                    "dataset_id": item["dataset_id"],
                    "url": item["url"],
                    "status": "verified" if ok else "failed",
                    "http_status": response.status_code,
                    "checked_url": str(response.url),
                    "response_sha256": digest,
                    "reason": item["reason"]
                    if ok
                    else "HTTP or marker check failed for extra official page.",
                }
            except httpx.HTTPError as exc:
                record = {
                    "kind": "extra_official_page",
                    "method": "httpx_get",
                    "source_id": item["source_id"],
                    "dataset_id": item["dataset_id"],
                    "url": item["url"],
                    "status": "failed",
                    "http_status": None,
                    "checked_url": None,
                    "response_sha256": None,
                    "reason": f"{exc.__class__.__name__}: extra official page request failed.",
                }
            if record["status"] != "verified":
                fallback = _curl_get(
                    item["url"],
                    item["must_contain"],
                    host_by_id[item["source_id"]],
                )
                record.update(fallback)
                record["kind"] = "extra_official_page"
                record["method"] = "curl_get_official_fallback"
                record["dataset_id"] = item["dataset_id"]
                record["url"] = item["url"]
                if record["status"] == "verified":
                    record["reason"] = item["reason"]
            records.append(record)
    failed = [item for item in records if item["status"] != "verified"]
    if failed:
        raise SystemExit(
            "Extra official page verification failed: "
            + json.dumps(failed, ensure_ascii=False)
        )
    return records


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    templates = REPO / "goldset" / "templates"
    for name in ("retrieval_gold.csv", "field_gold.csv", "error_gold.csv"):
        text = (templates / name).read_text(encoding="utf-8-sig").strip()
        if "\n" in text:
            raise SystemExit(f"{name} in templates/ is not an empty header-only file.")

    bundle = load_bundle()
    findings = check_review_and_rules(bundle)
    allowlist = verify_official_sources()
    civic = verify_civic_graphql()
    extra = verify_extra_pages()
    checksum = compute_gold_set_checksum(bundle)
    frozen_at = datetime.now(timezone.utc)
    manifest = GoldSetManifest(
        gold_set_id=GOLD_SET_ID,
        version=VERSION,
        frozen=True,
        frozen_at=frozen_at,
        initial_labeler=INITIAL_LABELER,
        independent_reviewer=INDEPENDENT_REVIEWER,
        deterministic_rules_verified=True,
        source_references_verified=True,
        high_risk_review_complete=True,
        human_reviewer=INDEPENDENT_REVIEWER,
        gold_set_checksum=checksum,
    )
    envelope = {
        "split": "development",
        "not_frozen_test": True,
        "copied_to_templates": False,
        "official_sdti_entrypoint": "goldset/templates remains empty; dashboard SDTI stays NOT_EVALUATED",
        "notice": (
            "This freezes the development split after independent review by xsc. "
            "It is not the sealed frozen_test Gold Set and must not be reported as "
            "competition SDTI. System observations are still required before scores."
        ),
        "row_counts": {
            "retrieval_gold.csv": len(bundle.retrieval_gold),
            "field_gold.csv": len(bundle.field_gold),
            "error_gold.csv": len(bundle.error_gold),
        },
        "manifest": manifest.model_dump(mode="json"),
    }
    write_json(ROOT / "MANIFEST.json", envelope)
    write_json(
        ROOT / "SOURCE_VERIFICATION.json",
        {
            "method": (
                "live_official_http_v1; curl GET fallback if Python httpx is blocked; "
                "CIViC via production GraphQL POST; extra official pages outside allowlist"
            ),
            "allowlist": allowlist,
            "civic_graphql": civic,
            "extra_official_pages": extra,
        },
    )
    write_json(
        ROOT / "RULE_CHECKS.json",
        {
            "medical_rules": "configs/medical_rules.yaml",
            "canonical_schema": "configs/canonical_schema.yaml",
            "findings": findings,
        },
    )
    print(json.dumps(envelope, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
