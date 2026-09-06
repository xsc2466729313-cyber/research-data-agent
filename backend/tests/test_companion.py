from backend.app.agent.companion import answer_companion, build_companion_messages
from backend.app.agent.models import CompanionMessage


class FakeCompanionClient:
    def __init__(self):
        self.messages = None

    def chat(self, *, messages):
        self.messages = messages
        return {"content": "这是根据当前研究上下文生成的动态回答。"}


def test_companion_prompt_keeps_context_and_recent_history() -> None:
    messages = build_companion_messages(
        message="解释这个数据集",
        history=[CompanionMessage(role="user", content="我想研究 Ia 型超新星"),
                 CompanionMessage(role="assistant", content="可以从光变曲线开始。")],
        context={"question": "我想研究 Ia 型超新星光变曲线", "dataset_size": "128 行 × 9 列", "secret": "must not pass"},
    )
    assert messages[0]["role"] == "system"
    assert "Ia 型超新星光变曲线" in messages[0]["content"]
    assert "128 行 × 9 列" in messages[0]["content"]
    assert "must not pass" not in messages[0]["content"]
    assert "科研兔" in messages[0]["content"]
    assert "许愿兔" not in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "解释这个数据集"}


def test_companion_uses_model_response_without_rewriting_it() -> None:
    client = FakeCompanionClient()
    answer = answer_companion(client=client, message="你好", history=[], context={})
    assert answer == "这是根据当前研究上下文生成的动态回答。"
    assert client.messages[-1]["content"] == "你好"
