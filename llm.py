"""LLM seam — единая точка подключения модели для суммаризации + рейтинга новостей.

В реальном конвейере суммаризацию и оценку важности новости делает LLM
(см. `core/llm_agent.py`, где это вызов CLI-агента). Здесь — чистый «шов»
(seam): абстрактный интерфейс `LLMBackend` и детерминированная заглушка
`StubBackend`, благодаря которой демо (`examples/run_pipeline.py`) работает
полностью офлайн, без API-ключей и без сети.

Чтобы подключить настоящую модель — реализуй свой `LLMBackend` и передай его
в демо/конвейер вместо `StubBackend()`. Скелет внизу файла.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

__all__ = ["LLMBackend", "StubBackend"]


@runtime_checkable
class LLMBackend(Protocol):
    """Контракт любого ИИ-бэкенда.

    Реализация должна вернуть dict ровно с этими ключами:
        {"summary": str, "rating": int (1..5), "rationale": str}
    """

    def summarize_and_rate(self, title: str, text: str, topic: str) -> dict:
        ...


# ── Детерминированная заглушка (без сети, без ключей) ────────────────────────

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

# Сигналы «важности» — повышают рейтинг, если встречаются в тексте.
_SIGNAL_RE = re.compile(
    r"\b(запуск\w*|launch\w*|объяв\w*|announce\w*|партнёрств\w*|partnership|"
    r"интеграц\w*|integrat\w*|инвестиц\w*|invest\w*|приобрет\w*|acquir\w*|"
    r"первый|first|крупнейш\w*|largest|рекорд\w*|record|"
    r"миллиард\w*|billion|миллион\w*|million|"
    r"AI|ИИ|нейросет\w*|GPT|LLM)\b",
    re.I,
)


def _first_sentences(text: str, n: int = 2) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    summary = " ".join(parts[:n]) if parts else text
    return summary[:600]


class StubBackend:
    """Офлайн-заглушка. Детерминированно (без рандома) формирует summary и rating.

    - summary: первые ~2 предложения текста (или заголовок, если текста нет);
    - rating 1..5: базируется на длине текста + числе «сигналов важности»
      + бонус за тему, попавшую в банкинг/AI;
    - rationale: человекочитаемое объяснение оценки.

    Реализует протокол LLMBackend, но НЕ ходит в сеть.
    """

    def summarize_and_rate(self, title: str, text: str, topic: str) -> dict:
        title = title or ""
        text = text or ""
        body = text if len(text.strip()) >= len(title.strip()) else title

        summary = _first_sentences(body, n=2) or title or "(нет текста)"

        signals = len(_SIGNAL_RE.findall(body))
        length = len(body)

        score = 1
        if length >= 200:
            score += 1
        if length >= 800:
            score += 1
        if signals >= 2:
            score += 1
        if topic and topic != "NONE" and "банкинге" in topic:
            score += 1
        rating = max(1, min(5, score))

        rationale = (
            f"эвристика заглушки: длина текста={length} симв., "
            f"сигналов важности={signals}, тема='{topic or 'NONE'}'. "
            f"Замените StubBackend реальной моделью для содержательной оценки."
        )
        return {"summary": summary, "rating": rating, "rationale": rationale}


# ── Скелет реального бэкенда (раскомментируй и дополни своим вызовом) ──────────
#
# import os
# from anthropic import Anthropic   # pip install anthropic
#
# class MyLLMBackend:  # неявно реализует протокол LLMBackend
#     """Пример подключения реальной модели (Anthropic Claude).
#     Для OpenAI/локальной модели — замени тело summarize_and_rate своим вызовом.
#     """
#
#     def __init__(self, model: str = "claude-3-5-haiku-latest"):
#         self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
#         self.model = model
#
#     def summarize_and_rate(self, title: str, text: str, topic: str) -> dict:
#         prompt = (
#             f"Тема: {topic}\nЗаголовок: {title}\n\nТекст:\n{text[:4000]}\n\n"
#             "Верни JSON: {\"summary\": <2-3 предложения>, "
#             "\"rating\": <1..5 важность>, \"rationale\": <почему такая оценка>}."
#         )
#         resp = self.client.messages.create(
#             model=self.model, max_tokens=400,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         import json
#         data = json.loads(resp.content[0].text)
#         return {
#             "summary": str(data["summary"]),
#             "rating": int(data["rating"]),
#             "rationale": str(data.get("rationale", "")),
#         }
