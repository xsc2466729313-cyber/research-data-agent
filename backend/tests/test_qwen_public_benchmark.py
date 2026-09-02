from __future__ import annotations

import httpx

from backend.app.agent.qwen_client import QwenClient, QwenSettings


def test_pico_batch_names_element_and_expands_sparse_indices() -> None:
    client = QwenClient(
        settings=QwenSettings(
            api_key="test",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3.8-max",
            workspace_id=None,
        ),
        client=httpx.Client(),
    )
    captured: dict = {}

    def fake_chat_json(*, system: str, payload: dict) -> dict:
        captured.update(payload)
        return {"positive_indices": {"doc-1": [1, 3]}}

    client._chat_json = fake_chat_json  # type: ignore[method-assign]
    assert client.label_pico_batch(
        [{"item_id": "doc-1", "tokens": ["the", "drug", "and", "therapy"]}],
        element="interventions",
    ) == {"doc-1": [0, 1, 0, 1]}
    assert captured["当前元素"] == "interventions"
    client.close()
