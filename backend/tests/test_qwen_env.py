from __future__ import annotations

from pathlib import Path

from backend.app.agent.qwen_client import apply_dotenv, load_local_dotenv, parse_dotenv


def test_parse_dotenv_strips_quotes_and_skips_comments() -> None:
    values = parse_dotenv(
        """
# comment
DASHSCOPE_API_KEY="sk-test-key"
QWEN_MODEL=qwen-plus
EMPTY=
"""
    )
    assert values["DASHSCOPE_API_KEY"] == "sk-test-key"
    assert values["QWEN_MODEL"] == "qwen-plus"
    assert values["EMPTY"] == ""


def test_apply_dotenv_does_not_override_existing_values() -> None:
    environ = {"DASHSCOPE_API_KEY": "existing"}
    apply_dotenv({"DASHSCOPE_API_KEY": "new", "QWEN_MODEL": "qwen-plus"}, environ)
    assert environ["DASHSCOPE_API_KEY"] == "existing"
    assert environ["QWEN_MODEL"] == "qwen-plus"


def test_load_local_dotenv_from_explicit_path(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("DASHSCOPE_API_KEY=sk-from-file\n", encoding="utf-8")
    environ: dict[str, str] = {}
    assert load_local_dotenv(environ, path=dotenv) is True
    assert environ["DASHSCOPE_API_KEY"] == "sk-from-file"
