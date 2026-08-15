from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from backend.app.sources.aact import AACTClinicalTrialsAdapter
from backend.app.sources.aact.models import AACTTableName, TrialResultsStatus
from backend.tests.test_aact_adapter import aact_request, table_by_name


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_AACT_INTEGRATION") != "1",
        reason="Set RUN_AACT_INTEGRATION=1 to call ClinicalTrials.gov API v2.",
    ),
]


def test_breast_trial_with_results_has_real_outcome_measurements(
    tmp_path: Path,
) -> None:
    adapter = AACTClinicalTrialsAdapter(cache_dir=tmp_path, timeout_seconds=120)
    request = aact_request(
        max_trials=1,
        query_terms="AREA[NCTId]NCT01104584",
        max_rows_per_table=1_000,
    )

    first = adapter.run(request)
    second = adapter.run(request)

    assert first.total_count == 1
    assert len(first.trials) == 1
    trial = first.trials[0]
    assert trial.nct_id == "NCT01104584"
    assert trial.trial_id == "NCT01104584"
    assert trial.has_results is True
    assert trial.results_status == TrialResultsStatus.AVAILABLE
    assert "Breast" in trial.brief_title
    assert trial.raw_study["protocolSection"]["identificationModule"]["nctId"] == (
        "NCT01104584"
    )

    measurements = table_by_name(first, AACTTableName.OUTCOME_MEASUREMENTS)
    assert measurements.row_count > 0
    assert measurements.upstream_row_count > 0
    assert all(row["nct_id"] == "NCT01104584" for row in measurements.rows)
    assert all("measurement" in row for row in measurements.rows)

    source = trial.source_item
    assert source.url == "https://clinicaltrials.gov/api/v2/studies/NCT01104584"
    path = Path(source.local_path or "")
    assert path.is_file()
    assert source.checksum == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    assert source.status == "retrieved"
    assert second.cache_hit is True
    assert second.source_items[0].status == "cached"


def test_breast_trial_without_results_is_not_labeled_negative(
    tmp_path: Path,
) -> None:
    result = AACTClinicalTrialsAdapter(
        cache_dir=tmp_path, timeout_seconds=120
    ).run(
        aact_request(
            max_trials=1,
            query_terms="AREA[NCTId]NCT03751449",
        )
    )

    assert result.total_count == 1
    trial = result.trials[0]
    assert trial.nct_id == "NCT03751449"
    assert trial.has_results is False
    assert trial.results_status == TrialResultsStatus.NOT_REPORTED
    measurements = table_by_name(result, AACTTableName.OUTCOME_MEASUREMENTS)
    assert measurements.row_count == 0
    serialized = json.dumps(result.model_dump(mode="json")).casefold()
    assert "negative_result" not in serialized
    assert "no_efficacy" not in serialized
