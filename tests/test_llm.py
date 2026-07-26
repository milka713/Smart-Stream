import pytest
from unittest.mock import patch, MagicMock

from app.services.llm import LLMGateway, _build_prompt, _parse_response


def test_build_prompt():
    prompt = _build_prompt("SpaceX Launch", "Falcon 9 launched today...", ["Space News", "AI"])
    assert "SpaceX Launch" in prompt
    assert "Falcon 9 launched today" in prompt
    assert "Space News" in prompt
    assert "AI" in prompt
    assert "JSON" in prompt


def test_parse_response_valid():
    result = _parse_response('{"matched": true, "topic": "Space", "digest": "Launch summary"}')
    assert result["matched"] is True
    assert result["topic"] == "Space"
    assert result["digest"] == "Launch summary"


def test_parse_response_with_markdown():
    result = _parse_response('```json\n{"matched": false, "topic": null, "digest": null}\n```')
    assert result["matched"] is False
    assert result["topic"] is None


def test_parse_response_invalid():
    result = _parse_response("not json at all")
    assert result["matched"] is False


def test_parse_response_empty():
    result = _parse_response("")
    assert result["matched"] is False


def test_classify_no_topics():
    llm = LLMGateway.__new__(LLMGateway)  # no __init__ — skip OpenAI client creation
    result = llm.classify_and_reformat("Title", "Content", [])
    assert result["matched"] is False


@patch("app.services.llm.OpenAI")
def test_classify_matched(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"matched": true, "topic": "AI", "digest": "New AI model"}'
    mock_client.chat.completions.create.return_value = mock_response

    llm = LLMGateway()
    result = llm.classify_and_reformat("New AI model released", "Details...", ["AI", "Space"])
    assert result["matched"] is True
    assert result["topic"] == "AI"
    assert result["digest"] == "New AI model"


@patch("app.services.llm.OpenAI")
def test_classify_not_matched(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"matched": false, "topic": null, "digest": null}'
    mock_client.chat.completions.create.return_value = mock_response

    llm = LLMGateway()
    result = llm.classify_and_reformat("Cooking recipe", "How to bake...", ["AI", "Space"])
    assert result["matched"] is False


@patch("app.services.llm.OpenAI")
def test_classify_empty_content_retry(mock_openai_class):
    """When reasoning consumes all tokens, content is empty — should retry."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # First call returns empty content, second returns valid
    mock_response1 = MagicMock()
    mock_response1.choices[0].message.content = ""

    mock_response2 = MagicMock()
    mock_response2.choices[0].message.content = '{"matched": true, "topic": "AI", "digest": "ok"}'

    mock_client.chat.completions.create.side_effect = [mock_response1, mock_response2]

    llm = LLMGateway()
    result = llm.classify_and_reformat("Title", "Content", ["AI"])
    assert result["matched"] is True
    assert mock_client.chat.completions.create.call_count == 2
