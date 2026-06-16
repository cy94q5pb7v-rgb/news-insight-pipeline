"""Parsers for openclaw CLI output + shared agent message snippets."""
import json


# Compact silent rules appended to every agent message. They are framed as
# internal directives ("не упоминай в ответе") so the agent doesn't echo them
# back. We also strip any leak server-side via _scrub_agent_reply().
LANG_RU_HINT = (
    "\n\n[Внутреннее правило · не упоминай в ответе]"
    " Финальный текст для пользователя — строго на русском."
    " Названия компаний/брендов и общеизвестные термины (API, KPI, P2P, fintech,"
    " SaaS, cashback, retention, ARR, MAU, NPS, BNPL, lounge, premium) оставляй"
    " в оригинале. Иностранные цитаты и куски — переводи перед использованием."
)


def with_ru_lang(message: str) -> str:
    """Convenience wrapper — append the Russian-language hint to a message."""
    return (message or "") + LANG_RU_HINT


# When the agent echoes our internal rules back to the user, scrub them out.
# Keep this conservative — only strip clear-cut acknowledgment artifacts, never
# legitimate sentences that happen to mention a file path.
import re as _re

# 1) "Принял правила." / "Принято." opening + optional bullet list of "Буду …"
_LEAK_PREAMBLE_RE = _re.compile(
    r"(?is)^\s*"
    r"(?:Принял[аои]?\s+правил[аы]\.?|Принято\.?|Понял\s+правил[аы]\.?|Понятно\.?)"
    r"\s*\n+"
    r"(?:Буд(?:у|ем)[^\n]*\n+)?"
    r"(?:[\-–—•*]\s*[^\n]+\n*){0,8}"
)
# 2) Lines that ARE our system rules verbatim (start with bracket marker)
_LEAK_RULE_LINE_RE = _re.compile(
    r"(?im)^\s*\[\s*(?:Внутренн|СИСТЕМНОЕ\s+ПРАВИЛО)[^\n]*\n?"
)
# 3) The transport-level [[reply_to_current]] tag that sometimes leaks
_LEAK_TAG_RE = _re.compile(r"\[\[reply_to_current\]\]")


def _scrub_agent_reply(text: str) -> str:
    """Strip echoes of internal rules from the user-visible reply.

    Conservative: only removes our own rule-blocks and the
    `[[reply_to_current]]` transport tag. Doesn't touch legitimate sentences
    that just happen to mention a file path."""
    if not text:
        return text
    cleaned = _LEAK_PREAMBLE_RE.sub("", text)
    cleaned = _LEAK_RULE_LINE_RE.sub("", cleaned)
    cleaned = _LEAK_TAG_RE.sub("", cleaned)
    # Collapse runs of empty lines left behind
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    # If the entire reply was just a rule-echo and nothing else, the agent
    # didn't actually answer anything — show a short stub instead of leaking
    # the rules back to the user.
    if not cleaned and text.strip():
        return "Понял задачу. Что нужно сделать дальше?"
    return cleaned


def _extract_reply(raw: str) -> tuple[str, str]:
    """Parse openclaw `agent --json` stdout → (reply_text, error_msg).

    Either reply is non-empty and error is "", or reply is "" and error describes
    what went wrong. Never raises."""
    start = raw.find("{")
    if start < 0:
        return "", f"no json in stdout (head: {raw[:200]!r})"
    try:
        obj = json.loads(raw[start:])
    except json.JSONDecodeError as e:
        return "", f"bad json: {e}"
    reply = ""
    for p in (obj.get("result") or {}).get("payloads") or []:
        t = (p or {}).get("text")
        if t:
            reply += (("\n\n" if reply else "") + t)
    if not reply:
        reply = obj.get("summary") or ""
    return reply, ""


def _extract_session_id(raw: str) -> str:
    """Pull the agent's sessionId out of the JSON envelope (for --session-id reuse)."""
    start = raw.find("{")
    if start < 0:
        return ""
    try:
        obj = json.loads(raw[start:])
    except Exception:
        return ""
    meta = ((obj.get("result") or {}).get("meta") or {}).get("agentMeta") or {}
    return meta.get("sessionId") or ""


def _parse_first_json_object(raw: str) -> dict | None:
    """Find the first balanced {...} substring and parse as JSON.

    Handles quoted strings with escaped braces correctly. Returns None if
    nothing parseable is found."""
    start = raw.find("{")
    while start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except json.JSONDecodeError:
                        break
        start = raw.find("{", start + 1)
    return None
