"""KB (materials) routes: /kb page + /kb/upload /text /url /list /search + /kb/{doc_id}/*."""
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from templates import KB_HTML, FEEDBACK_WIDGET_HTML
from web_app import (
    _require_auth, _find_user, _kb_conn, _kb_require_read, _kb_require_upload, _kb_require_moderate,
    _kb_can_upload, _kb_can_moderate, _kb_row_to_dict, _kb_extract_text, _kb_insert, _kb_enrich_bg,
    _url_fetch, KB_DIR, KB_ALLOWED_EXT, KB_MAX_FILE, KB_MAX_TEXT,
)

router = APIRouter()


@router.get("/kb", response_class=HTMLResponse)
async def kb_page(user: str = Depends(_require_auth)):
    _kb_require_read(user)
    can_upload = "true" if _kb_can_upload(user) else "false"
    can_mod = "true" if _kb_can_moderate(user) else "false"
    is_admin = bool((_find_user(user) or {}).get("is_admin"))
    init = (user[:1] or "·").upper()
    admin_item = ('<a class="ocu-item" href="/admin"><svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z\"/><path d=\"M9 12l2 2 4-4\"/></svg>Админка</a>') if is_admin else ""
    return HTMLResponse(
        KB_HTML.replace("__USER__", user).replace("__CANUPLOAD__", can_upload)
               .replace("__CANMOD__", can_mod).replace("__INIT__", init).replace("__ADMIN_ITEM__", admin_item)
               .replace("__FEEDBACK_WIDGET__", FEEDBACK_WIDGET_HTML),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/kb/upload")
async def kb_upload(
    user: str = Depends(_require_auth),
    file: UploadFile = File(...),
    title: str = Form(""),
    tags: str = Form(""),
):
    _kb_require_upload(user)
    name = (file.filename or "").strip()
    ext = Path(name).suffix.lower()
    if ext not in KB_ALLOWED_EXT:
        raise HTTPException(400, f"Разрешены: {', '.join(sorted(KB_ALLOWED_EXT))}")
    data = await file.read()
    if len(data) > KB_MAX_FILE:
        raise HTTPException(413, f"Файл > {KB_MAX_FILE // 1024 // 1024} MB")
    doc_id = uuid.uuid4().hex[:16]
    dest = KB_DIR / (doc_id + ext)
    dest.write_bytes(data)
    try:
        text = _kb_extract_text(dest, ext)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if not text.strip():
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Не удалось извлечь текст из файла")
    now = datetime.now(timezone.utc).isoformat()
    t = (title.strip() or Path(name).stem)[:300]
    cleaned_tags = ",".join(x.strip() for x in tags.split(",") if x.strip())[:500]
    with _kb_conn() as c:
        c.execute(
            """INSERT INTO kb_docs (id, title, source_type, source_ref, file_ext, mime, size,
               content, tags, author, created_at, updated_at, enrichment_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, t, "file", name, ext, file.content_type or "", len(data),
             text, cleaned_tags, user, now, now, "pending"),
        )
        c.execute(
            "INSERT INTO kb_fts (id, title, content, tags) VALUES (?,?,?,?)",
            (doc_id, t, text, cleaned_tags),
        )
    _kb_enrich_bg(doc_id)
    return {"ok": True, "id": doc_id}


@router.post("/kb/text")
async def kb_text(request: Request, user: str = Depends(_require_auth)):
    _kb_require_upload(user)
    body = await request.json()
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()
    tags = (body.get("tags") or "").strip()
    if not content:
        raise HTTPException(400, "Пустой текст")
    if len(content.encode("utf-8")) > KB_MAX_TEXT:
        raise HTTPException(413, "Текст слишком большой")
    cleaned_tags = ",".join(x.strip() for x in tags.split(",") if x.strip())[:500]
    doc_id = _kb_insert(
        title=title or "Заметка", source_type="text", source_ref="", file_ext="",
        mime="text/plain", size=len(content.encode("utf-8")),
        content=content, tags=cleaned_tags, author=user,
    )
    return {"ok": True, "id": doc_id}


@router.post("/kb/url")
async def kb_url(request: Request, user: str = Depends(_require_auth)):
    _kb_require_upload(user)
    body = await request.json()
    url = (body.get("url") or "").strip()
    title_override = (body.get("title") or "").strip()
    tags = (body.get("tags") or "").strip()
    if not url:
        raise HTTPException(400, "Пустой URL")
    title, text, mime = _url_fetch(url)
    if not text.strip():
        raise HTTPException(400, "Не удалось извлечь текст со страницы")
    cleaned_tags = ",".join(x.strip() for x in tags.split(",") if x.strip())[:500]
    doc_id = _kb_insert(
        title=title_override or title, source_type="url", source_ref=url,
        file_ext="", mime=mime, size=len(text.encode("utf-8")),
        content=text, tags=cleaned_tags, author=user,
    )
    return {"ok": True, "id": doc_id}


@router.get("/kb/list")
async def kb_list(
    user: str = Depends(_require_auth),
    q: str = "",
    limit: int = 100,
    offset: int = 0,
):
    limit = max(1, min(200, int(limit or 100)))
    offset = max(0, int(offset or 0))
    is_mod = _kb_can_moderate(user)
    with _kb_conn() as c:
        if is_mod:
            total = c.execute("SELECT COUNT(*) FROM kb_docs").fetchone()[0]
            pending_total = c.execute(
                "SELECT COUNT(*) FROM kb_docs WHERE moderation_status='pending'"
            ).fetchone()[0]
            rows = c.execute(
                "SELECT * FROM kb_docs ORDER BY "
                "CASE WHEN moderation_status='pending' THEN 0 ELSE 1 END, created_at DESC "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            total = c.execute(
                "SELECT COUNT(*) FROM kb_docs "
                "WHERE moderation_status='approved' OR author=?",
                (user,),
            ).fetchone()[0]
            pending_total = c.execute(
                "SELECT COUNT(*) FROM kb_docs "
                "WHERE moderation_status='pending' AND author=?",
                (user,),
            ).fetchone()[0]
            rows = c.execute(
                "SELECT * FROM kb_docs "
                "WHERE moderation_status='approved' OR author=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user, limit, offset),
            ).fetchall()
    return JSONResponse({
        "items": [_kb_row_to_dict(r) for r in rows],
        "total": total,
        "pending_total": pending_total,
        "can_upload": _kb_can_upload(user),
        "can_moderate": is_mod,
    }, headers={"Cache-Control": "no-store"})


def _fts_query(q: str) -> str:
    tokens = re.findall(r"[\w\-]+", q, flags=re.UNICODE)
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"*' for t in tokens[:12])


@router.get("/kb/search")
async def kb_search(user: str = Depends(_require_auth), q: str = "", limit: int = 30):
    limit = max(1, min(100, int(limit or 30)))
    q = (q or "").strip()
    if not q:
        return {"items": []}
    fts = _fts_query(q)
    if not fts:
        return {"items": []}
    is_mod = _kb_can_moderate(user)
    with _kb_conn() as c:
        try:
            if is_mod:
                rows = c.execute(
                    """SELECT d.*, snippet(kb_fts, 1, '<mark>', '</mark>', '…', 24) AS snip
                       FROM kb_fts f JOIN kb_docs d ON d.id = f.id
                       WHERE kb_fts MATCH ?
                       ORDER BY bm25(kb_fts) LIMIT ?""",
                    (fts, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT d.*, snippet(kb_fts, 1, '<mark>', '</mark>', '…', 24) AS snip
                       FROM kb_fts f JOIN kb_docs d ON d.id = f.id
                       WHERE kb_fts MATCH ?
                         AND (d.moderation_status='approved' OR d.author=?)
                       ORDER BY bm25(kb_fts) LIMIT ?""",
                    (fts, user, limit),
                ).fetchall()
        except sqlite3.OperationalError as e:
            raise HTTPException(400, f"Bad search query: {e}")
    items = []
    for r in rows:
        d = _kb_row_to_dict(r)
        d["snippet"] = r["snip"]
        items.append(d)
    return {"items": items, "query": q}


@router.get("/kb/{doc_id}")
async def kb_get(doc_id: str, user: str = Depends(_require_auth)):
    with _kb_conn() as c:
        row = c.execute("SELECT * FROM kb_docs WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    is_mod = _kb_can_moderate(user)
    mod_status = (row["moderation_status"] if "moderation_status" in row.keys() else "approved") or "approved"
    if mod_status == "pending" and not is_mod and row["author"] != user:
        raise HTTPException(404, "not found")
    d = _kb_row_to_dict(row, include_content=True)
    d["can_delete"] = (row["author"] == user) or is_mod
    d["can_approve"] = is_mod and mod_status == "pending"
    return JSONResponse(d, headers={"Cache-Control": "no-store"})


@router.post("/kb/{doc_id}/approve")
async def kb_approve(doc_id: str, user: str = Depends(_require_auth)):
    _kb_require_moderate(user)
    now = datetime.now(timezone.utc).isoformat()
    with _kb_conn() as c:
        row = c.execute("SELECT moderation_status FROM kb_docs WHERE id=?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if (row["moderation_status"] or "approved") == "approved":
            return JSONResponse({"ok": True, "moderation_status": "approved"},
                                headers={"Cache-Control": "no-store"})
        c.execute(
            "UPDATE kb_docs SET moderation_status='approved', approved_by=?, approved_at=?, updated_at=? WHERE id=?",
            (user, now, now, doc_id),
        )
    return JSONResponse({"ok": True, "moderation_status": "approved", "approved_by": user, "approved_at": now},
                        headers={"Cache-Control": "no-store"})


@router.post("/kb/{doc_id}/enrich")
async def kb_reenrich(doc_id: str, user: str = Depends(_require_auth)):
    _kb_require_upload(user)
    with _kb_conn() as c:
        row = c.execute("SELECT enrichment_status FROM kb_docs WHERE id=?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if row["enrichment_status"] == "pending":
            return JSONResponse({"ok": True, "status": "pending"}, headers={"Cache-Control": "no-store"})
        c.execute(
            "UPDATE kb_docs SET enrichment_status=?, enrichment_error='' WHERE id=?",
            ("pending", doc_id),
        )
    _kb_enrich_bg(doc_id)
    return JSONResponse({"ok": True, "status": "pending"}, headers={"Cache-Control": "no-store"})


@router.get("/kb/{doc_id}/file")
async def kb_file(doc_id: str, user: str = Depends(_require_auth)):
    with _kb_conn() as c:
        row = c.execute("SELECT * FROM kb_docs WHERE id = ?", (doc_id,)).fetchone()
    if not row or row["source_type"] != "file":
        raise HTTPException(404, "not found")
    ext = row["file_ext"] or ""
    p = KB_DIR / (doc_id + ext)
    if not p.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(
        str(p),
        filename=row["source_ref"] or (doc_id + ext),
        media_type=row["mime"] or "application/octet-stream",
    )


@router.delete("/kb/{doc_id}")
async def kb_delete(doc_id: str, user: str = Depends(_require_auth)):
    is_mod = _kb_can_moderate(user)
    with _kb_conn() as c:
        row = c.execute("SELECT * FROM kb_docs WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if row["author"] != user and not is_mod:
            raise HTTPException(403, "Удалять может только автор или модератор")
        ext = row["file_ext"] or ""
        c.execute("DELETE FROM kb_fts WHERE id = ?", (doc_id,))
        c.execute("DELETE FROM kb_docs WHERE id = ?", (doc_id,))
        c.execute(
            "DELETE FROM kb_hypothesis_sources WHERE doc_id = ?", (doc_id,)
        )
    if ext:
        (KB_DIR / (doc_id + ext)).unlink(missing_ok=True)
    return {"ok": True}
