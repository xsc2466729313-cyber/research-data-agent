import json

from scripts.run_variant_matrix import run


def test_variant_matrix_freezes_controls_without_fake_scores(tmp_path):
    artifact = run(tmp_path)
    payload = json.loads((artifact / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "NOT_EVALUATED"
    assert len(payload["variants"]) == 5
    assert all(row["metrics"] == {} for row in payload["variants"])
    assert payload["controls"]
