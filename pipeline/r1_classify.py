#!/usr/bin/env python3
"""Helper: deterministic case_type classifier.

Использование из Stage-2 cron:
    python3 /opt/newsapp/.openclaw/workspace/scripts/r1_classify.py \
        "<title>" "<article_text up to 1500 chars>"

Печатает на stdout одну из строк:
    AI travel
    Travel в банкинге
    AI travel в банкинге
    NONE   (значит drop item)

Та же логика что в r1_fetch_urls.py::_classify_case_type — отдельный helper
чтобы Stage-2 LLM-агент мог вызывать без LLM-галлюцинаций.
"""
import re
import sys

_AI_KEYWORDS_RE = re.compile(
    r"\b(AI|ИИ|GPT[-\s]?\d*|ChatGPT|Gemini|Copilot|Claude|LLM|"
    r"AI[-\s]?агент|AI[-\s]?ассистент|AI[-\s]?помощник|AI[-\s]?чат[-\s]?бот|"
    r"ИИ[-\s]?агент|ИИ[-\s]?ассистент|ИИ[-\s]?помощник|"
    r"GenAI|Gen[\-\s]?AI|generative\s+AI|искусственн\w+\s+интеллект)\b|"
    r"\bнейросет\w*|нейронн\w+\s+сет|"
    r"machine\s+learning|deep\s+learning|"
    r"генеративн\w*\s+(?:AI|ИИ|модел|интеллект)",
    re.I,
)
_BANKING_KEYWORDS_RE = re.compile(
    r"\b(Сбер|Сбербанк|СберПрайм|СберТревел|Сбер\s*Travel|"
    r"Тинькофф|T[-\s]?Bank|TBank|T-?PRO|"
    r"ВТБ\b|ВТБ[-\s]?Прайм|ВТБ[-\s]?Привилегия|"
    r"Альфа[-\s]?Банк|Альфа[-\s]?Премиум|Альфа[-\s]?Тревел|Альфа[-\s]?Travel|"
    r"Газпромбанк|Газпром[-\s]?банк|"
    r"Райффайзен|Райфф?айзен[-\s]?банк|"
    r"МТС[-\s]?Банк|МТС[-\s]?Travel|МТС[-\s]?Тревел|"
    r"Открытие[-\s]?банк|Совкомбанк|Промсвязьбанк|Россельхозбанк|"
    r"Тинькофф[-\s]?Travel|Тинькофф[-\s]?Тревел|"
    r"Visa|Mastercard|Amex|American\s+Express|"
    r"Revolut|Klarna|N26|Monzo|Wise|Stripe|PayPal|"
    r"Яндекс[-\s]?Плюс|"
    r"СберПремьер|Сбер[-\s]?Премьер|"
    r"Альфа[-\s]?Премиум[-\s]?Direct)\b|"
    r"\bкэшбэк\b|\bкешбэк\b|\bcashback\b|"
    r"программ[ыа]\s+лояльност|loyalty\s+program|frequent\s+flyer\s+program|"
    r"премиальн\w*\s+карт|premium\s+card|premier\s+card|"
    r"co[-\s]?brand\w*\s+(?:карт|card)|карт[аы]\s+(?:с\s+)?мил|"
    r"банков\w*\s+(?:карт|продукт|сервис|услуг|приложен)|"
    r"\bcredit\s+card\b|\bdebit\s+card\b|"
    r"\bmiles?\b|\bмили\b|reward\s+points|"
    r"DragonPass|PriorityPass|MirPass|MaxAirport|"
    r"\bлаундж\b|lounge\s+access|"
    r"travel[-\s]?страхов\w+|travel\s+insurance|"
    r"travel[-\s]?(?:карт|card)|travel[-\s]?cashback|travel[-\s]?кэшбэк|"
    r"\bбанк(?:ов\w*|у|а|и|е|ом|ах)?\s+(?:объяв|запус|анонс|представ|"
    r"добав|интегр|подпис|сообщ|расши|предлаг|"
    r"совмест|partnership|сотруднич)|"
    r"банков\s+(?:России|РФ)|"
    r"\bbank\s+(?:launch|introduce|announce|unveil|partner|integrat)|"
    r"\bbanking\b|fintech|финтех|"
    r"\bnobank|neobank|необанк",
    re.I,
)
_TRAVEL_KEYWORDS_RE = re.compile(
    r"\bтуризм\w*|\bтурист\w*|\bтуроперат\w*|"
    r"путешеств\w*|поездк\w*|"
    r"отел[ьяиеёов]|\bhotel\w*|hospitality|гостиниц\w*|"
    r"авиа\w*|\bairline\w*|airway|\bflight\b|flights\b|перелёт\w*|перелет\w*|"
    r"\brail\b|\bтрэвел\w*|\btravel\b|\btravel-",
    re.I,
)


def classify(title: str, text: str) -> str:
    if not title and not text:
        return "NONE"
    blob = (title or "") + " " + (text or "")[:1500]
    has_ai = bool(_AI_KEYWORDS_RE.search(blob))
    has_banking = bool(_BANKING_KEYWORDS_RE.search(blob))
    has_travel = bool(_TRAVEL_KEYWORDS_RE.search(blob))
    if not has_travel:
        return "NONE"
    if has_ai and has_banking:
        return "AI travel в банкинге"
    if has_ai:
        return "AI travel"
    if has_banking:
        return "Travel в банкинге"
    return "NONE"


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else ""
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    print(classify(title, text))
