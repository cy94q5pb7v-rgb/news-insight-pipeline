"""File/URL text extraction, doc insertion, agent-driven enrichment."""
import re
import subprocess
import threading
import urllib.request
from core.article_fetch import fetch_article_text
import uuid
from datetime import datetime, timezone
from html import unescape as _html_unescape
from pathlib import Path

from fastapi import HTTPException

from core.config import KB_DIR, KB_MAX_TEXT, OPENCLAW, AGENT_ID
from core.kb_db import _kb_conn, _kb_can_moderate
from core.openclaw import _extract_reply, _parse_first_json_object


def _kb_extract_text(path: Path, ext: str) -> str:
    ext = ext.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:
            raise HTTPException(500, f"pypdf unavailable: {e}")
        reader = PdfReader(str(path))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if ext == ".docx":
        try:
            import docx
        except Exception as e:
            raise HTTPException(500, f"python-docx unavailable: {e}")
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs).strip()
    raise HTTPException(400, f"Неподдерживаемый формат: {ext}")


def _html_to_text(html: str) -> str:
    no_style = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", no_style)
    text = _html_unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _url_fetch(url: str) -> tuple[str, str, str]:
    """Return (title, text, mime). Raises HTTPException on failure.

    Cascade: urllib (fast, direct) → fetch_article_text (trafilatura/ru-fetch/snippets/Tavily)
    при ошибках, anti-bot блокировке или короткому контенту.
    """
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "URL должен начинаться с http:// или https://")

    # Tier 1: direct urllib (preserves existing behavior for non-blocked sites)
    title, text, mime = url, "", "text/html"
    raw_body = ""
    direct_fail = None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (insight-hub)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower() or "text/html"
            raw = resp.read(6 * 1024 * 1024)
        charset = "utf-8"
        m = re.search(r"charset=([A-Za-z0-9_-]+)", resp.headers.get("Content-Type") or "")
        if m: charset = m.group(1)
        try:
            body = raw.decode(charset, errors="replace")
        except Exception:
            body = raw.decode("utf-8", errors="replace")
        if "html" in mime or "<html" in body[:500].lower():
            title_m = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
            title = _html_unescape(title_m.group(1)).strip() if title_m else url
            text = _html_to_text(body)
            # Detect anti-bot / block page in extracted text
            tlow = text.lower()[:600] if text else ""
            block_markers = ("cloudflare ray id", "just a moment", "security verification",
                             "performing security", "attention required",
                             "выполнение проверки безопасности")
            if any(m in tlow for m in block_markers):
                text = ""  # trigger fallback
        else:
            # non-HTML — return as-is
            return url, body, mime
        raw_body = body
    except Exception as e:
        direct_fail = str(e)

    # Tier 2: fallback to shared article_fetch (trafilatura / ru-fetch / snippets / Tavily)
    if not text or len(text.strip()) < 400:
        try:
            ft_text, ft_mode = fetch_article_text(
                url,
                title_hint=title if title and title != url else "",
                trust_score=0.5,
                allow_tavily=True,
            )
            if ft_text and len(ft_text) >= 200:
                text = ft_text
                # Try to extract a better title from text head if we didn't get one
                if title == url or not title:
                    first_line = ft_text.split("\n", 1)[0].strip().lstrip("# ")
                    if first_line and 10 < len(first_line) < 300:
                        title = first_line
        except Exception:
            pass

    if not text:
        if direct_fail:
            raise HTTPException(400, f"Не удалось загрузить URL: {direct_fail}")
        raise HTTPException(400, "Не удалось извлечь текст из URL (даже через fallback'и)")

    return title[:300], text, mime or "text/html"


def _kb_insert(*, title: str, source_type: str, source_ref: str, file_ext: str,
               mime: str, size: int, content: str, tags: str, author: str) -> str:
    if not title.strip():
        title = source_ref or "Без названия"
    title = title.strip()[:300]
    content = (content or "").strip()
    if len(content.encode("utf-8")) > KB_MAX_TEXT:
        content = content.encode("utf-8")[:KB_MAX_TEXT].decode("utf-8", errors="ignore")
    doc_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    is_moderator = _kb_can_moderate(author)
    mod_status = "approved" if is_moderator else "pending"
    approved_by = author if is_moderator else ""
    approved_at = now if is_moderator else ""
    with _kb_conn() as c:
        c.execute(
            """INSERT INTO kb_docs (id, title, source_type, source_ref, file_ext, mime, size,
               content, tags, author, created_at, updated_at, enrichment_status,
               moderation_status, approved_by, approved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, title, source_type, source_ref, file_ext, mime, size,
             content, tags, author, now, now, "pending",
             mod_status, approved_by, approved_at),
        )
        c.execute(
            "INSERT INTO kb_fts (id, title, content, tags) VALUES (?,?,?,?)",
            (doc_id, title, content, tags),
        )
    _kb_enrich_bg(doc_id)
    return doc_id


# ── Agent-driven enrichment (summary + auto tags) ──────────────────────────

KB_ENRICH_PROMPT = """\
Ты получаешь текст материала из корпоративной базы знаний (исследования, интервью, отчёты). \
Верни РОВНО один JSON-объект и ничего больше — без комментариев, без ```markdown, без префиксов:

{
  "tldr": "одно предложение, 15-25 слов, суть материала",
  "summary_md": "markdown на русском, 350-800 слов, разделы (## заголовки): Контекст, Ключевые находки (буллеты), Цифры и факты (если есть в тексте — буллеты), Ограничения (если применимо), Что это значит",
  "tags": ["3-7 коротких русских тегов; lower-case; без # и пробелов в начале/конце; по сути, а не по форме"]
}

Правила:
- Пиши ТОЛЬКО на русском.
- Не выдумывай цифры, названия, имена, которых нет в исходнике. Если в тексте нет цифр — пропусти раздел «Цифры и факты».
- Summary должен звучать как брифинг для руководителя: конкретно, по существу, без воды.
- Теги: одно слово или короткое словосочетание (напр. «онбординг», «премиум-клиенты», «комиссии», «конверсия»).

Материал:

=== TITLE ===
{TITLE}

=== CONTENT ===
{CONTENT}
"""



import re as _re_inline

KB_INLINE_URL_MAX = 4   # max URLs to resolve per doc
KB_INLINE_TEXT_MAX = 2500  # max chars per resolved article in injected context


def _resolve_inline_urls(content: str, title_hint: str = "") -> str:
    """Find http(s) URLs in content, fetch text via cascade, append to content.

    Returns content with [URL N → fetched]\n<text>\n[/URL N] sections appended.
    Limit: KB_INLINE_URL_MAX URLs, KB_INLINE_TEXT_MAX chars each.
    Designed to give enrichment LLM full context WITHOUT needing browser_tool.
    """
    if not content:
        return content
    # Find URLs (skip common image/asset extensions)
    urls = []
    seen = set()
    for m in _re_inline.finditer(r'https?://[^\s<>"\')\]]+', content):
        u = m.group(0).rstrip(".,;:!?)>")
        if u in seen:
            continue
        if any(u.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".css", ".js", ".pdf")):
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= KB_INLINE_URL_MAX:
            break

    if not urls:
        return content

    try:
        from core.article_fetch import fetch_article_text
    except Exception:
        return content

    resolved_blocks = []
    for i, u in enumerate(urls, 1):
        try:
            text, mode = fetch_article_text(u, title_hint=title_hint, trust_score=0.6, allow_tavily=True)
            if text and len(text) >= 200:
                text = text[:KB_INLINE_TEXT_MAX]
                resolved_blocks.append(f"\n\n[Inline URL #{i} → fetched via {mode}]\nSource: {u}\n{text}\n[/Inline URL #{i}]")
            else:
                resolved_blocks.append(f"\n\n[Inline URL #{i} → unresolved ({mode})]\nSource: {u}\n[/Inline URL #{i}]")
        except Exception as e:
            resolved_blocks.append(f"\n\n[Inline URL #{i} → fetch error: {type(e).__name__}]\nSource: {u}\n[/Inline URL #{i}]")

    return content + "\n\n---\n# Inline URL Context (auto-fetched, не вошёл в основной текст документа):" + "".join(resolved_blocks)

KB_ENRICH_CONTENT_MAX = 40_000

_kb_enrich_procs: "dict[str, subprocess.Popen]" = {}
_kb_enrich_lock = threading.Lock()


def _kb_enrich_sync(doc_id: str) -> None:
    """Blocking enrichment: agent call + DB update. Safe to run in a worker thread."""
    try:
        with _kb_conn() as c:
            row = c.execute(
                "SELECT title, content FROM kb_docs WHERE id = ?", (doc_id,)
            ).fetchone()
        if not row:
            return
        title = row["title"] or ""
        content = row["content"] or ""
        # Pre-resolve inline URLs in content (gives LLM extra context, prevents browser_tool spawn)
        try:
            content = _resolve_inline_urls(content, title_hint=title)
        except Exception as e:
            print(f"[kb_enrich {doc_id}] inline URL resolve failed: {e}")
        if len(content) > KB_ENRICH_CONTENT_MAX:
            content = content[:KB_ENRICH_CONTENT_MAX] + "\n… [обрезано по лимиту]"
        prompt = KB_ENRICH_PROMPT.replace("{TITLE}", title).replace("{CONTENT}", content)
        proc = subprocess.Popen(
            [OPENCLAW, "agent", "--agent", AGENT_ID, "--message", prompt, "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        with _kb_enrich_lock:
            _kb_enrich_procs[doc_id] = proc
        try:
            stdout, stderr = proc.communicate(timeout=600)
        finally:
            with _kb_enrich_lock:
                _kb_enrich_procs.pop(doc_id, None)
        # check if cancelled in the meantime
        with _kb_conn() as c:
            cur_row = c.execute(
                "SELECT enrichment_status FROM kb_docs WHERE id=?", (doc_id,)
            ).fetchone()
        if cur_row and cur_row["enrichment_status"] == "cancelled":
            return
        if proc.returncode != 0:
            raise RuntimeError(f"agent exit {proc.returncode}: {stderr[:300]}")
        reply, err = _extract_reply(stdout)
        if err and not reply:
            raise RuntimeError(err)
        parsed = _parse_first_json_object(reply)
        if not parsed:
            raise RuntimeError("Агент не вернул валидный JSON")
        tldr = (parsed.get("tldr") or "").strip()[:500]
        summary = (parsed.get("summary_md") or "").strip()[:20_000]
        raw_tags = parsed.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",")]
        clean_tags = []
        seen = set()
        for t in raw_tags:
            if not isinstance(t, str):
                continue
            t = t.strip().lower().lstrip("#").strip()
            if not t or len(t) > 40 or t in seen:
                continue
            seen.add(t)
            clean_tags.append(t)
            if len(clean_tags) >= 7:
                break
        auto_tags_csv = ",".join(clean_tags)
        now = datetime.now(timezone.utc).isoformat()
        with _kb_conn() as c:
            c.execute(
                "UPDATE kb_docs SET summary=?, tldr=?, auto_tags=?, "
                "enrichment_status=?, enrichment_error='', updated_at=? WHERE id=?",
                (summary, tldr, auto_tags_csv, "done", now, doc_id),
            )
            row = c.execute(
                "SELECT tags FROM kb_docs WHERE id=?", (doc_id,)
            ).fetchone()
            combined = ",".join(
                x for x in ((row["tags"] or "") + "," + auto_tags_csv).split(",") if x.strip()
            )
            c.execute(
                "UPDATE kb_fts SET tags=? WHERE id=?", (combined, doc_id)
            )
    except Exception as e:
        try:
            with _kb_conn() as c:
                c.execute(
                    "UPDATE kb_docs SET enrichment_status=?, enrichment_error=? WHERE id=?",
                    ("error", str(e)[:400], doc_id),
                )
        except Exception:
            pass


def _kb_enrich_bg(doc_id: str) -> None:
    """Fire-and-forget enrichment in a daemon thread."""
    threading.Thread(target=_kb_enrich_sync, args=(doc_id,), daemon=True).start()
