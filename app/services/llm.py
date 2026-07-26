import json
import logging
import time
from typing import Dict, List, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

RETRY_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504, 529}
MAX_RETRIES = 3
BACKOFF_BASE = 2


def _build_prompt(title: str, content: str, topics: List[str]) -> str:
    topics_list = "\n".join(f"- {t}" for t in topics)
    return f"""Ты — аналитик новостей. Тебе нужно определить, относится ли новость к одной из следующих тематических веток:

{topics_list}

Новость:
Заголовок: {title}
Текст: {content[:3000]}

Ответь строго в формате JSON (без markdown, без пояснений):
{{"matched": true, "topic": "имя_ветки", "digest": "краткий информативный дайджест 2-3 предложения"}}
или
{{"matched": false, "topic": null, "digest": null}}

Если новость подходит под несколько веток — выбери одну, наиболее релевантную."""


def _parse_response(content: str) -> Dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM response as JSON: {text[:200]}")
        return {"matched": False, "topic": None, "digest": None}


class LLMGateway:
    def __init__(self):
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout,
        )

    def classify_and_reformat(
        self, title: str, content: str, topics: List[str]
    ) -> Dict:
        """Classify article against topics and reformat if matched.

        Returns dict: {"matched": bool, "topic": str|None, "digest": str|None}
        """
        if not topics:
            return {"matched": False, "topic": None, "digest": None}

        prompt = _build_prompt(title, content, topics)

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=settings.llm_max_tokens,
                    temperature=0.6,
                )

                choice = response.choices[0].message
                content_text = choice.content or ""
                if not content_text.strip():
                    logger.warning("Empty content from LLM (reasoning consumed all tokens), retrying...")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(BACKOFF_BASE ** (attempt + 1))
                        continue
                    return {"matched": False, "topic": None, "digest": None}

                return _parse_response(content_text)

            except Exception as e:
                is_retryable = False
                if hasattr(e, "status_code") and e.status_code in RETRY_STATUS_CODES:
                    is_retryable = True

                if is_retryable and attempt < MAX_RETRIES - 1:
                    delay = BACKOFF_BASE ** (attempt + 1)
                    logger.warning(f"LLM retryable error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM error after {attempt + 1} attempts: {e}")
                    return {"matched": False, "topic": None, "digest": None}

        return {"matched": False, "topic": None, "digest": None}

    def health_check(self) -> bool:
        try:
            import httpx
            health_url = settings.llm_base_url.rsplit("/v1", 1)[0] + "/health"
            response = httpx.get(health_url, timeout=10)
            return response.status_code == 200
        except Exception:
            return False
