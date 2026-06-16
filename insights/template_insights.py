"""INSIGHTS_HTML — extracted from web_app.py (Phase A refactor).
Only the string constant lives here; no imports, no logic.
"""
INSIGHTS_HTML = r"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>try{var w=window.Telegram&&window.Telegram.WebApp;if(w){w.ready();try{w.expand();}catch(_){}if(w.platform&&w.platform!=="unknown"){document.documentElement.classList.add("tg");}}}catch(e){}</script><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Гипотезы — Инсайт-хаб</title>
<style>
:root{--bg:#fafafa;--surface:#fff;--surface-2:#f4f4f6;--text:#0f0f12;--text-2:#2a2a30;--muted:#6c6c75;--muted-2:#9a9aa3;--border:rgba(15,15,18,.09);--border-strong:rgba(15,15,18,.14);--accent:#2563eb;--accent-bg:rgba(37,99,235,.08);--pos:#047857;--neg:#b91c1c;--warn:#b45309;--lc-synth:#6c6c75;--lc-synth-bg:rgba(108,108,117,.10);--lc-review:#2563eb;--lc-review-bg:rgba(37,99,235,.10);--lc-valid:#047857;--lc-valid-bg:rgba(4,120,87,.10);--lc-adopt:#b45309;--lc-adopt-bg:rgba(180,83,9,.10);--lc-arch:#9a9aa3;--lc-arch-bg:rgba(154,154,163,.08);--card:var(--surface);--primary:var(--accent);--primary-dark:#1d4ed8;--primary-soft:var(--accent-bg);--primary-softer:rgba(37,99,235,.04);--ring:37,99,235;--ok:var(--pos);--ok-soft:rgba(4,120,87,.10);--danger:var(--neg)}[data-theme="dark"]{--bg:#0e0e11;--surface:#16161b;--surface-2:#1d1d23;--text:#ececef;--text-2:#c2c2c8;--muted:#8a8a93;--muted-2:#5d5d65;--border:rgba(255,255,255,.08);--border-strong:rgba(255,255,255,.14);--accent:#6c8aff;--accent-bg:rgba(108,138,255,.13);--pos:#4ade80;--neg:#f87171;--warn:#fbbf24;--lc-synth:#8a8a93;--lc-synth-bg:rgba(138,138,147,.13);--lc-review:#6c8aff;--lc-review-bg:rgba(108,138,255,.13);--lc-valid:#4ade80;--lc-valid-bg:rgba(74,222,128,.13);--lc-adopt:#fbbf24;--lc-adopt-bg:rgba(251,191,36,.13);--lc-arch:#5d5d65;--lc-arch-bg:rgba(93,93,101,.10);--primary-dark:#a3b8ff;--primary-softer:rgba(108,138,255,.06)}
/* Phase A overrides — Insight Workspace foundation (insights.py) */
html,body{font-size:15.5px;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
header{background:var(--surface);border-bottom:1px solid var(--border)}
.sec-tabs-inner{background:var(--surface-2);border-color:var(--border)}
.sec-tab.active{background:var(--accent)!important;border-color:transparent!important;box-shadow:0 1px 2px rgba(15,15,18,.08),0 6px 18px -10px rgba(37,99,235,.45)!important}
.sec-tab.active .st-ico{background:rgba(255,255,255,.22);color:#fff}
.sec-tab[data-sec="kb"] .st-ico{background:var(--accent-bg);color:var(--accent)}
.sec-tab[data-sec="kb"]:hover:not(.active) .st-ico{background:var(--accent-bg);color:var(--accent)}
.sec-tab .kb-badge{background:var(--accent);box-shadow:0 1px 3px rgba(37,99,235,.40)}
.iw-theme-toggle{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--muted);cursor:pointer;font:inherit;font-size:16px;transition:color .12s,border-color .12s,background .12s}
.iw-theme-toggle:hover{color:var(--text);border-color:var(--border-strong);background:var(--surface-2)}
/* Phase B1: sticky filter bar */
.iw-fbar{position:sticky;top:65px;z-index:40;display:flex;align-items:center;gap:12px;padding:10px 22px;background:rgba(250,250,250,.85);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--border);min-height:56px}
[data-theme="dark"] .iw-fbar{background:rgba(14,14,17,.85)}
.iw-fbar-search{position:relative;flex:1;max-width:480px}
.iw-fbar-search input{width:100%;padding:8px 14px 8px 36px;border:1px solid var(--border);border-radius:8px;background:var(--surface);font-family:inherit;font-size:14px;color:var(--text);outline:none;transition:border-color .12s,box-shadow .12s}
.iw-fbar-search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.iw-fbar-search input::placeholder{color:var(--muted-2)}
.iw-fbar-search .ic{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:14px;height:14px;color:var(--muted-2);pointer-events:none}
.iw-fbar-search kbd{position:absolute;right:8px;top:50%;transform:translateY(-50%);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;color:var(--muted-2);background:var(--surface-2);border:1px solid var(--border);border-radius:4px;padding:1px 6px;line-height:1.5;pointer-events:none}
.iw-fbar-spacer{flex:1}
/* AS IS / Архив toggle — top-level view switcher */
.iw-vmode{display:inline-flex;gap:2px;background:var(--surface-2);padding:3px;border-radius:8px;font-size:12.5px;border:1px solid var(--border)}
.iw-vmode button{padding:6px 14px;border:none;background:transparent;border-radius:6px;color:var(--muted);cursor:pointer;font:inherit;font-size:12.5px;font-weight:600;transition:color .12s,background .12s;letter-spacing:.01em}
.iw-vmode button:hover{color:var(--text)}
.iw-vmode button.active{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(15,15,18,.10)}
.iw-vmode button .cnt{margin-left:6px;font-variant-numeric:tabular-nums;color:var(--muted-2);font-weight:500}
.iw-vmode button.active .cnt{color:var(--muted)}

.iw-fbar-btn{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 14px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:13px;font-weight:500;cursor:pointer;transition:border-color .12s,background .12s}
.iw-fbar-btn:hover{border-color:var(--border-strong);background:var(--surface-2)}
.iw-fbar-btn.primary{background:var(--accent);color:#fff;border-color:transparent}
.iw-fbar-btn.primary:hover{background:#1d4ed8}
[data-theme="dark"] .iw-fbar-btn.primary:hover{background:#5876f0}
.iw-fbar-btn svg{width:14px;height:14px}
@media(max-width:780px){.iw-fbar{padding:10px 14px;gap:8px}.iw-fbar-search{max-width:none}.iw-fbar-btn .iw-fbar-btn-lbl{display:none}}
/* Phase D: skeletons + keyboard help */
@keyframes iw-shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
.iw-skel{background:linear-gradient(90deg, var(--surface-2) 0%, var(--border) 50%, var(--surface-2) 100%);background-size:200% 100%;animation:iw-shimmer 1.4s linear infinite;border-radius:6px;display:inline-block;height:1em;width:100%}
.iw-skel-row{display:block;height:14px;margin:0 0 8px;border-radius:6px}
.iw-skel-row.short{width:60%}
.iw-skel-row.med{width:85%}
.iw-skel-card{padding:14px;background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:8px}
.iw-kbd-help{position:fixed;bottom:24px;left:24px;z-index:90;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:11.5px;color:var(--muted);box-shadow:0 4px 16px -8px rgba(0,0,0,.18);display:none}
.iw-kbd-help.show{display:flex;gap:14px;flex-wrap:wrap}
.iw-kbd-help kbd{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;background:var(--surface-2);border:1px solid var(--border);border-radius:4px;padding:1px 6px;color:var(--text);margin-right:4px}

/* Phase C: Kanban view + view toggle */
.iw-vtoggle{display:inline-flex;gap:2px;background:var(--surface-2);padding:3px;border-radius:8px}
.iw-vtoggle button{padding:5px 10px;border:none;background:transparent;border-radius:6px;color:var(--muted);cursor:pointer;font:inherit;font-size:12.5px;font-weight:500;transition:color .12s,background .12s;display:inline-flex;align-items:center;gap:5px}
.iw-vtoggle button:hover{color:var(--text)}
.iw-vtoggle button.active{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(15,15,18,.08)}
.iw-vtoggle button svg{width:13px;height:13px}
.iw-kanban{display:none;margin-top:16px}
.iw-kanban.active{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:12px;overflow-x:auto}
.iw-kb-col{background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:10px;min-width:220px;display:flex;flex-direction:column;min-height:300px}
.iw-kb-col.over{border-color:var(--accent);background:var(--accent-bg)}
.iw-kb-h{display:flex;align-items:center;gap:6px;padding:0 4px 8px;font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.iw-kb-h .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.iw-kb-h .lbl{flex:1}
.iw-kb-h .cnt{font-variant-numeric:tabular-nums;font-weight:600;color:var(--muted)}
.iw-kb-col[data-status="synthesized"] .iw-kb-h{color:var(--lc-synth)} .iw-kb-col[data-status="synthesized"] .iw-kb-h .dot{background:var(--lc-synth)}
.iw-kb-col[data-status="in_review"] .iw-kb-h{color:var(--lc-review)} .iw-kb-col[data-status="in_review"] .iw-kb-h .dot{background:var(--lc-review)}
.iw-kb-col[data-status="validated"] .iw-kb-h{color:var(--lc-valid)} .iw-kb-col[data-status="validated"] .iw-kb-h .dot{background:var(--lc-valid)}
.iw-kb-col[data-status="adopted"] .iw-kb-h{color:var(--lc-adopt)} .iw-kb-col[data-status="adopted"] .iw-kb-h .dot{background:var(--lc-adopt)}
.iw-kb-col[data-status="archived"] .iw-kb-h{color:var(--lc-arch)} .iw-kb-col[data-status="archived"] .iw-kb-h .dot{background:var(--lc-arch)}
.iw-kb-list{display:flex;flex-direction:column;gap:8px;flex:1;overflow-y:auto}
.iw-kb-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px;cursor:grab;transition:border-color .12s,box-shadow .12s}
.iw-kb-card:hover{border-color:var(--border-strong);box-shadow:0 2px 8px rgba(0,0,0,.04)}
.iw-kb-card.dragging{opacity:.4;cursor:grabbing}
.iw-kb-card .stmt{font-size:13.5px;font-weight:500;line-height:1.4;color:var(--text);margin-bottom:6px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.iw-kb-card .meta{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);flex-wrap:wrap}
.iw-kb-card .meta .cat{padding:1px 6px;border-radius:4px;background:var(--surface-2);font-weight:600;font-size:10.5px;letter-spacing:.02em}
.iw-kb-card .meta .conf{font-variant-numeric:tabular-nums}
.iw-kb-card .meta .owner{margin-left:auto;color:var(--accent);font-weight:600}
.iw-kb-card .meta .overdue{color:var(--neg);font-weight:600}
/* Hide List components when Kanban active (controlled by JS via body class) */
body.iw-kanban-active .iw-shell main > .graph-card,
body.iw-kanban-active .iw-shell main > .toolbar,
body.iw-kanban-active .iw-shell main > .hyp-list,
body.iw-kanban-active .iw-shell main > section{display:none!important}
/* Toast */
.iw-toast{position:fixed;bottom:24px;right:24px;z-index:300;background:var(--surface);border:1px solid var(--border-strong);border-radius:10px;padding:10px 14px;font-size:13.5px;color:var(--text);box-shadow:0 8px 24px -10px rgba(0,0,0,.30);min-width:200px;max-width:340px;transform:translateY(8px);opacity:0;transition:transform .2s ease,opacity .2s ease}
.iw-toast.show{transform:translateY(0);opacity:1}
.iw-toast.err{border-color:var(--neg);color:var(--neg)}
.iw-toast.ok{border-color:var(--pos);color:var(--pos)}

/* Phase B3: universal Add modal */
.iw-modal-bg{position:fixed;inset:0;background:rgba(15,15,18,.5);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:200;padding:20px}
.iw-modal-bg.open{display:flex}
.iw-modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;width:100%;max-width:560px;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 24px 60px -20px rgba(0,0,0,.30);overflow:hidden}
.iw-modal-h{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--border)}
.iw-modal-h h3{margin:0;font-size:16px;font-weight:600;color:var(--text);flex:1}
.iw-modal-h-close{background:transparent;border:none;color:var(--muted);cursor:pointer;font:inherit;font-size:20px;line-height:1;padding:4px;width:28px;height:28px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center}
.iw-modal-h-close:hover{background:var(--surface-2);color:var(--text)}
.iw-modal-body{padding:18px 20px;overflow-y:auto;flex:1}
.iw-modal-tabs{display:inline-flex;gap:2px;background:var(--surface-2);padding:3px;border-radius:8px;margin-bottom:14px;font-size:12.5px}
.iw-modal-tab{padding:5px 11px;border:none;background:transparent;border-radius:6px;color:var(--muted);cursor:pointer;font:inherit;font-size:12.5px;font-weight:500;transition:color .12s,background .12s;display:inline-flex;align-items:center;gap:6px}
.iw-modal-tab:hover{color:var(--text)}
.iw-modal-tab.active{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(15,15,18,.08)}
.iw-modal-tab svg{width:13px;height:13px}
.iw-modal-drop{border:1.5px dashed var(--border);border-radius:10px;padding:24px 16px;text-align:center;background:var(--surface-2);color:var(--muted);font-size:13.5px;cursor:pointer;transition:border-color .15s,background .15s}
.iw-modal-drop:hover,.iw-modal-drop.over{border-color:var(--accent);background:var(--accent-bg)}
.iw-modal-drop strong{color:var(--text);display:block;margin-bottom:4px;font-weight:600}
.iw-modal-fld{display:flex;flex-direction:column;gap:5px;margin-top:12px}
.iw-modal-fld label{font-size:11.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.iw-modal-fld input,.iw-modal-fld textarea{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface);font-family:inherit;font-size:14px;color:var(--text);outline:none;transition:border-color .12s,box-shadow .12s;resize:vertical}
.iw-modal-fld textarea{min-height:120px}
.iw-modal-fld input:focus,.iw-modal-fld textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.iw-modal-status{margin-top:10px;padding:8px 10px;border-radius:8px;font-size:13px;display:none}
.iw-modal-status.ok{display:block;background:rgba(4,120,87,.10);color:var(--pos);border:1px solid rgba(4,120,87,.20)}
.iw-modal-status.err{display:block;background:rgba(185,28,28,.10);color:var(--neg);border:1px solid rgba(185,28,28,.20)}
.iw-modal-f{display:flex;gap:8px;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--border);background:var(--surface)}
.iw-modal-f .iw-fbar-btn{height:36px;padding:0 16px}
.iw-modal-pickedfile{margin-top:8px;padding:8px 12px;background:var(--accent-bg);border-radius:8px;font-size:13px;color:var(--text);display:flex;align-items:center;gap:8px}
.iw-modal-pickedfile .x{margin-left:auto;background:transparent;border:none;color:var(--muted);cursor:pointer;font:inherit;font-size:14px}

/* Phase B2: shell + rail */
.iw-shell{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:240px minmax(0,1fr);gap:24px;padding:0 24px}
.iw-shell main{max-width:none!important;padding:20px 0!important;margin:0!important}
.iw-rail{position:sticky;top:135px;align-self:start;padding:18px 4px 24px;max-height:calc(100vh - 135px);overflow-y:auto;font-size:13.5px}
.iw-rail::-webkit-scrollbar{width:6px}
.iw-rail::-webkit-scrollbar-thumb{background:var(--border-strong);border-radius:6px}
.iw-rail-grp{margin-bottom:18px}
.iw-rail-cap{font-size:10.5px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;padding:0 10px 6px}
.iw-rail-item{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:6px;color:var(--text-2);cursor:pointer;border-left:2px solid transparent;transition:background .1s,color .1s;user-select:none}
.iw-rail-item:hover{background:var(--surface-2);color:var(--text)}
.iw-rail-item.active{background:var(--accent-bg);color:var(--text);border-left-color:var(--accent);font-weight:600}
.iw-rail-item .ic{width:14px;height:14px;flex-shrink:0;color:var(--muted)}
.iw-rail-item.active .ic{color:var(--accent)}
.iw-rail-item .lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.iw-rail-item .cnt{font-variant-numeric:tabular-nums;font-size:11.5px;color:var(--muted-2);font-weight:500}
.iw-rail-item.active .cnt{color:var(--accent)}
/* Hide existing toolbar — facets moved to rail */
.iw-shell .toolbar{display:none!important}
@media(max-width:980px){
  .iw-shell{grid-template-columns:1fr;padding:0 14px}
  .iw-rail{position:static;max-height:none;padding:14px 0;border-bottom:1px solid var(--border)}
  .iw-shell .toolbar{display:flex!important} /* fallback: show toolbar on mobile */
}


*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SB Sans Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5}
a{color:var(--primary-dark);text-decoration:none}
a:hover{text-decoration:underline}
header{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:18px;padding:12px 22px;border-bottom:1px solid var(--border);background:#fff;position:sticky;top:0;z-index:10}
header .meta-right{justify-self:end;display:flex;align-items:center;gap:12px}
@media(max-width:960px){header{grid-template-columns:1fr auto;grid-template-rows:auto auto;gap:10px 14px}header .meta-right{grid-column:2;grid-row:1}header .sec-tabs{grid-column:1 / -1;grid-row:2;justify-self:stretch}}
/* ── Global section tabs — mirror of the same bar on `/` (chat.py) ────────── */
.sec-tabs{display:flex;align-items:center;min-width:0}
.sec-tabs-inner{display:flex;align-items:center;gap:6px;overflow-x:auto;scrollbar-width:none;padding:2px;background:#f4f5f7;border:1px solid #ececef;border-radius:999px}
.sec-tabs-inner::-webkit-scrollbar{display:none}
.sec-tab{display:inline-flex;align-items:center;gap:10px;padding:6px 16px 6px 6px;border-radius:999px;background:transparent;border:1.5px solid transparent;cursor:pointer;font-family:inherit;color:#4a5058;text-decoration:none;white-space:nowrap;flex-shrink:0;transition:transform .2s cubic-bezier(.22,1,.36,1),box-shadow .22s,background .22s,border-color .22s,color .22s}
.sec-tab .st-ico{width:28px;height:28px;border-radius:50%;background:#e7eaee;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#4a5058;flex-shrink:0;transition:background .22s,color .22s}
.sec-tab .st-body{display:flex;flex-direction:column;gap:1px;line-height:1.15;text-align:left}
.sec-tab .st-ttl{font-size:13px;font-weight:600;letter-spacing:-.005em;color:inherit}
.sec-tab .st-sub{font-size:10.5px;font-weight:500;color:#8a91a0;letter-spacing:.01em;transition:color .22s}
@media(max-width:1180px){.sec-tab .st-sub{display:none}}
@media(max-width:760px){.sec-tab{padding-right:12px;gap:8px}.sec-tab .st-ico{width:26px;height:26px}}
.sec-tab:hover:not(.active){background:#fff;color:#1b1b1b;text-decoration:none}
.sec-tab:hover:not(.active) .st-ico{background:#dfe3e7}
.sec-tab.active{color:#fff;box-shadow:0 1px 2px rgba(15,16,18,.1),0 10px 22px -12px rgba(15,16,18,.35);pointer-events:none}
.sec-tab.active .st-ico{background:rgba(255,255,255,.22);color:#fff;box-shadow:inset 0 0 0 1px rgba(255,255,255,.16)}
.sec-tab.active .st-sub{color:rgba(255,255,255,.82)}
.sec-tab[data-sec="packages"].active{background:linear-gradient(135deg,#22b355 0%,#0e8a2e 100%);border-color:rgba(14,138,46,.45)}
.sec-tab[data-sec="travel"].active{background:linear-gradient(135deg,#43c2f0 0%,#0b6fa8 100%);border-color:rgba(11,111,168,.45)}
.sec-tab[data-sec="uxui"].active{background:linear-gradient(135deg,#b875ef 0%,#6a22a8 100%);border-color:rgba(106,34,168,.45)}
.sec-tab[data-sec="kb"].active{background:linear-gradient(135deg,#f4a83d 0%,#d37214 100%);border-color:rgba(211,114,20,.45)}
.sec-tab[data-sec="kb"] .st-ico{background:#fdecd3;color:#d37214}
.sec-tab[data-sec="kb"]:hover:not(.active) .st-ico{background:#fff7ea;color:#a7580e}
.back-btn{background:transparent;border:1px solid var(--border);border-radius:10px;padding:7px 12px 7px 10px;font-size:13px;color:var(--muted);cursor:pointer;font-family:inherit;display:inline-flex;align-items:center;gap:6px;text-decoration:none;transition:color .15s,border-color .15s,background .15s}
.back-btn:hover{color:var(--primary-dark);border-color:var(--primary);background:var(--primary-softer);text-decoration:none}
.back-btn svg{width:14px;height:14px;stroke-width:2}
.brand{display:flex;align-items:center;gap:10px;min-width:0}
.logo-mark{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--primary-dark));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:17px;box-shadow:0 3px 8px rgba(0,0,0,.14);flex-shrink:0}
.brand-text{display:flex;flex-direction:column;min-width:0}
header h1{margin:0;font-size:16px;font-weight:600;letter-spacing:.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)}
.sub{font-size:12px;color:var(--muted);margin-top:1px}
header .spacer{flex:1}
header .me{font-size:13px;color:var(--muted)}
header .tabs-top{display:flex;gap:4px;background:#eef1f3;padding:4px;border-radius:10px}
header .tabs-top a{padding:6px 14px;border-radius:7px;font-size:13px;font-weight:600;color:var(--muted);text-decoration:none;transition:color .12s,background .12s}
header .tabs-top a.active{background:#fff;color:var(--primary-dark);box-shadow:0 1px 3px rgba(0,0,0,.05)}
header .tabs-top a:hover:not(.active){color:var(--text);text-decoration:none}

main{max-width:1280px;margin:0 auto;padding:20px 24px;display:grid;grid-template-columns:1fr;gap:16px}
.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:12px 16px}
.toolbar .t-label{font-size:12.5px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.chip-row{display:inline-flex;background:#eef1f3;padding:2px;border-radius:8px;gap:2px}
.chip-row button{padding:3px 9px;border:none;background:transparent;border-radius:6px;font-family:inherit;font-size:11.5px;color:var(--muted);cursor:pointer;font-weight:600;transition:color .12s,background .12s;display:inline-flex;align-items:center;gap:4px;line-height:1.5}
.chip-row button:hover:not(.active){color:var(--text)}
.chip-row button.active{background:#fff;color:var(--primary-dark);box-shadow:0 1px 3px rgba(0,0,0,.05)}
.chip-row .cc{display:inline-block;min-width:14px;padding:0 4px;font-size:10px;font-weight:700;line-height:14px;text-align:center;border-radius:99px;background:rgba(0,0,0,.06);color:inherit}
.chip-row button.active .cc{background:var(--primary-soft);color:var(--primary-dark)}
.stats{color:var(--muted);font-size:13px;display:flex;gap:18px;flex-wrap:wrap}
.stats b{color:var(--text);font-weight:600}
.spacer{flex:1}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border:none;border-radius:10px;background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:#fff;font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.btn:hover{box-shadow:0 4px 12px rgba(var(--ring),.3)}
.btn:active{transform:translateY(1px)}
.btn:disabled{opacity:.55;cursor:not-allowed;transform:none;box-shadow:none}
.btn-ghost{background:#fff;color:var(--muted);border:1px solid var(--border)}
.btn-ghost:hover{color:var(--primary-dark);border-color:var(--primary);box-shadow:none}

.graph-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:0;position:relative;overflow:hidden;display:flex;flex-direction:column}
.graph-head{display:flex;align-items:center;gap:14px;padding:14px 18px;border-bottom:1px solid var(--border);background:linear-gradient(180deg,#fafbfc 0%,#fff 100%);flex-wrap:wrap}
.graph-head .gh-ttl{display:flex;flex-direction:column;gap:1px;min-width:0}
.graph-head .gh-eyebrow{font-size:10.5px;font-weight:700;color:var(--primary-dark);letter-spacing:.18em;text-transform:uppercase}
.graph-head h3{margin:0;font-size:14.5px;font-weight:600;color:var(--text);letter-spacing:-.01em;line-height:1.25}
.graph-head .gh-spacer{flex:1;min-width:12px}
.graph-head .gh-stat{font-size:11.5px;color:var(--muted);font-weight:600;letter-spacing:.01em;font-variant-numeric:tabular-nums;white-space:nowrap;padding:5px 10px;background:var(--primary-softer);border:1px solid var(--primary-soft);border-radius:99px;color:var(--primary-dark)}
.graph-head .gh-search{display:inline-flex;align-items:center;gap:7px;background:#fff;border:1px solid var(--border);border-radius:10px;padding:5px 11px;transition:border-color .14s,box-shadow .14s}
.graph-head .gh-search:focus-within{border-color:var(--primary);box-shadow:0 0 0 3px rgba(var(--ring),.12)}
.graph-head .gh-search svg{width:14px;height:14px;color:var(--muted)}
.graph-head .gh-search input{border:0;outline:0;background:transparent;font:inherit;font-size:12.5px;width:130px;color:var(--text)}
.graph-head .gh-search input::placeholder{color:var(--muted)}
.graph-head .gh-layouts button{font-size:11.5px;padding:5px 11px}
.graph-body{flex:1;position:relative;min-height:600px;overflow:hidden;background:
  radial-gradient(circle at 30% 20%, #f8fafc 0%, #eef2f7 60%, #e6ebf1 100%);
  background-image:
    radial-gradient(circle at 30% 20%, #f8fafc 0%, #eef2f7 60%, #e6ebf1 100%),
    radial-gradient(circle, #cdd4dc 0.6px, transparent 0.6px);
  background-size: auto, 18px 18px;
  background-position: 0 0, 0 0;
  background-blend-mode: normal, multiply}
#graphWrap{position:absolute;inset:0;width:100%;height:100%;cursor:grab}
#graphWrap.panning, #graphWrap:active{cursor:grabbing}
.graph-legend{position:absolute;top:14px;left:14px;background:rgba(255,255,255,.94);border:1px solid var(--border);border-radius:12px;padding:10px 12px;font-size:11.5px;color:var(--muted);display:flex;flex-direction:column;gap:6px;backdrop-filter:blur(8px);z-index:2;box-shadow:0 2px 12px rgba(0,0,0,.04);max-width:320px}
.graph-legend .lr{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.graph-legend .lr-cats{font-weight:600;color:var(--text);font-size:12px;padding-bottom:6px;border-bottom:1px dashed var(--border)}
.graph-legend .lr-cats .cdot{margin-right:4px}
.graph-legend .lr-meta span{display:inline-flex;align-items:center;gap:5px}
.graph-legend .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.graph-legend .dot.v{background:#1aa04a}
.graph-legend .dot.u{background:transparent;border:1.5px dashed #9aa1a6}
.graph-legend .cdot{display:inline-block;width:10px;height:10px;border-radius:50%;flex-shrink:0}
.graph-detail{position:absolute;left:16px;bottom:56px;width:300px;background:#fff;border:1px solid var(--border);border-radius:12px;padding:12px 14px;font-size:12.5px;color:var(--text);box-shadow:0 10px 30px rgba(0,0,0,.1);z-index:3;backdrop-filter:blur(8px);pointer-events:none;animation:gdIn .18s ease-out}
@keyframes gdIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.graph-detail .gd-kicker{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:7px}
.graph-detail .gd-cat{font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:99px;background:var(--primary-soft);color:var(--primary-dark);letter-spacing:.04em;text-transform:uppercase}
.graph-detail .gd-src{font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:99px;letter-spacing:.04em;text-transform:uppercase}
.graph-detail .gd-src-material{background:#eaf3fa;color:#0b6fa8}
.graph-detail .gd-src-news{background:#f2ecfb;color:#6a22a8}
.graph-detail .gd-src-mixed{background:#fbf2e6;color:var(--primary-dark)}
.graph-detail .gd-new{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:99px;background:#d14a00;color:#fff;letter-spacing:.05em;text-transform:uppercase}
.graph-detail .gd-ttl{font-size:13px;font-weight:600;line-height:1.4;margin:0 0 8px;color:var(--text);letter-spacing:-.005em}
.graph-detail .gd-row{display:flex;align-items:center;gap:12px;font-size:11px;color:var(--muted);padding-top:8px;border-top:1px dashed var(--border)}
.graph-detail .gd-conf{display:inline-flex;align-items:center;gap:6px;color:var(--primary-dark);font-weight:600}
.graph-detail .gd-conf-bar{display:inline-block;width:44px;height:4px;border-radius:3px;background:#eef1f3;overflow:hidden}
.graph-detail .gd-conf-fill{display:block;height:100%;background:linear-gradient(90deg,var(--primary),var(--primary-dark))}
.graph-detail .gd-v{color:var(--ok);font-weight:600}
.graph-detail .gd-cta{margin-top:8px;font-size:10.5px;color:var(--muted);letter-spacing:.02em;font-style:italic}
.graph-empty{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:var(--muted);padding:40px;gap:12px;z-index:4}

.gcontrols{position:absolute;right:14px;bottom:14px;display:flex;flex-direction:column;gap:6px;background:rgba(255,255,255,.94);border:1px solid var(--border);border-radius:10px;padding:6px;z-index:3;backdrop-filter:blur(8px);box-shadow:0 2px 12px rgba(0,0,0,.04)}
.gcontrols button{width:30px;height:30px;border:1px solid var(--border);background:#fff;border-radius:7px;cursor:pointer;font-size:14px;color:var(--muted);font-weight:600;transition:background .12s,color .12s,border-color .12s}
.gcontrols button:hover{background:var(--primary-soft);color:var(--primary-dark);border-color:var(--primary)}
/* Fullscreen graph mode */
.graph-card.is-fullscreen{position:fixed;inset:0;z-index:9999;border-radius:0;border:none;background:var(--card);box-shadow:none}
.graph-card.is-fullscreen .graph-body{min-height:auto;flex:1;height:calc(100vh - 64px)}
.graph-card.is-fullscreen .graph-head{position:sticky;top:0;background:#fff;z-index:5}
body.graph-fullscreen{overflow:hidden}
.gcontrols button.is-active{background:var(--primary-soft);color:var(--primary-dark);border-color:var(--primary)}
.gcontrols button#gFullscreen svg{width:14px;height:14px;display:block;margin:0 auto}


.list-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px}
.list-card h3{margin:0 0 12px;font-size:14px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.hyp-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}
.hcard{border:1px solid var(--border);border-radius:8px;padding:7px 10px;background:#fff;cursor:pointer;transition:border-color .15s,transform .08s,box-shadow .15s}
.hcard:hover{border-color:var(--primary);box-shadow:0 3px 10px rgba(0,0,0,.05)}
.hcard:active{transform:translateY(1px)}
.hcard .htitle{font-size:12px;font-weight:600;line-height:1.35;margin-bottom:4px;letter-spacing:-.01em}
.hcard .hmeta{display:flex;align-items:center;gap:3px;font-size:9.5px;color:var(--muted);flex-wrap:wrap;row-gap:3px}
.badge{display:inline-flex;align-items:center;gap:2px;padding:0 5px;border-radius:99px;font-size:9px;font-weight:600;line-height:1.45;height:14px}
.badge.cat{background:var(--primary-soft);color:var(--primary-dark)}
.badge.ev{background:#eef1f3;color:#445670}
.badge.v-true{background:var(--ok-soft);color:var(--ok)}
.badge.v-false{background:#fff5db;color:var(--warn)}
.badge.new{background:#d14a00;color:#fff;letter-spacing:.05em;text-transform:uppercase}
.badge.src-material{background:#eaf3fa;color:#0b6fa8}
.badge.src-news{background:#f2ecfb;color:#6a22a8}
.badge.src-mixed{background:#fbf2e6;color:var(--primary-dark)}
.hcard.is-new{border-color:#ffb58a;box-shadow:0 2px 10px rgba(209,74,0,.08)}
.conf-bar{display:inline-block;width:32px;height:3px;border-radius:3px;background:#eef1f3;overflow:hidden;vertical-align:middle}
.conf-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--primary),var(--primary-dark))}

/* drawer */
.drawer-bg{position:fixed;inset:0;background:rgba(0,0,0,.4);backdrop-filter:blur(4px);opacity:0;pointer-events:none;transition:opacity .2s;z-index:100}
.drawer-bg.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(720px,96vw);background:#fff;box-shadow:-20px 0 50px rgba(0,0,0,.18);transform:translateX(101%);transition:transform .28s cubic-bezier(.5,0,.2,1);z-index:110;display:flex;flex-direction:column}
.drawer.open{transform:translateX(0)}
.dr-head{padding:18px 22px;border-bottom:1px solid var(--border);display:flex;align-items:flex-start;gap:12px}
.dr-head h2{margin:0;font-size:17px;font-weight:600;letter-spacing:-.02px;flex:1;line-height:1.4}
.dr-close{background:#fff;border:1px solid var(--border);width:32px;height:32px;border-radius:50%;color:var(--muted);cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:color .12s,border-color .12s,background .12s}
.dr-close:hover{color:var(--primary-dark);border-color:var(--primary);background:var(--primary-softer)}
.dr-body{flex:1;overflow:auto;padding:20px 22px}
.section{margin-bottom:20px}
.section h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
.rationale{font-size:14px;line-height:1.6;color:var(--text);background:var(--primary-softer);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.conf-row{display:flex;align-items:center;gap:10px}
.conf-row .bar{flex:1;height:8px;border-radius:5px;background:#eef1f3;overflow:hidden}
.conf-row .bar i{display:block;height:100%;background:linear-gradient(90deg,var(--primary),var(--primary-dark))}
.conf-row .pct{font-size:13px;font-weight:600;color:var(--primary-dark);min-width:40px;text-align:right}

.src{border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:10px;position:relative;background:#fff}
.src.origin{border-color:var(--primary);background:var(--primary-softer);box-shadow:0 2px 8px rgba(var(--ring),.1)}
.src.origin::before{content:'первопричина';position:absolute;top:-8px;left:12px;background:var(--primary);color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;letter-spacing:.04em;text-transform:uppercase}
.src-head{display:flex;align-items:flex-start;gap:10px;margin-bottom:6px}
.src-ico{width:30px;height:30px;border-radius:8px;flex-shrink:0;background:var(--primary-soft);color:var(--primary-dark);font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center}
.src-title{flex:1;font-size:14px;font-weight:600;line-height:1.35;letter-spacing:-.01em}
.src-title a{color:inherit}
.src-title a:hover{color:var(--primary-dark)}
.quality{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;padding:2px 7px;border-radius:99px;flex-shrink:0}
.quality.green{background:var(--ok-soft);color:var(--ok)}
.quality.yellow{background:#fff5db;color:var(--warn)}
.quality.red{background:#fdecec;color:var(--danger)}
.quality.amber{background:#f2ecfb;color:#6a22a8}
.quality .qdot{width:6px;height:6px;border-radius:50%;background:currentColor}
.excerpt-wrap{margin-top:4px}
.excerpt-label{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:700;color:#a37200;background:#fff1b8;padding:2px 7px;border-radius:99px;letter-spacing:.05em;text-transform:uppercase;margin-bottom:5px}
.excerpt{font-size:13px;line-height:1.55;color:#3d2a00;padding:8px 12px;background:linear-gradient(transparent 0,transparent 2px,#fff3a8 2px,#fff3a8 calc(100% - 2px),transparent calc(100% - 2px));border-radius:4px;box-decoration-break:clone;-webkit-box-decoration-break:clone;font-weight:500;border-left:3px solid #f4c430}
.excerpt mark{background:#ffe066;color:inherit;padding:0 2px;border-radius:2px}
.src-actions{margin-top:8px;display:flex;gap:6px;font-size:12px}
.src-actions a{color:var(--primary-dark);font-weight:600}

.regen-modal{position:fixed;inset:0;background:rgba(0,0,0,.45);backdrop-filter:blur(4px);z-index:200;display:none;align-items:center;justify-content:center;padding:20px}
.regen-modal.open{display:flex}
.regen-card{background:#fff;border-radius:18px;padding:28px 32px;max-width:480px;width:100%;box-shadow:0 25px 60px rgba(0,0,0,.2)}
.regen-card h3{margin:0 0 10px;font-size:17px}
.regen-card p{color:var(--muted);font-size:13.5px;margin:6px 0 16px}
.rg-steps{display:flex;flex-direction:column;gap:10px;margin-bottom:16px}
.rg-step{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--muted)}
.rg-step.active{color:var(--text);font-weight:600}
.rg-step.done{color:var(--ok)}
.rg-step .dot2{width:18px;height:18px;border-radius:50%;background:#d7dadd;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff}
.rg-step.active .dot2{background:var(--primary);animation:pulse 1.2s infinite}
.rg-step.done .dot2{background:var(--ok)}
.rg-step.done .dot2::after{content:'✓';color:#fff;font-size:12px}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(var(--ring),.5)}50%{box-shadow:0 0 0 6px rgba(var(--ring),0)}}
.rg-err{background:#fdecec;color:var(--danger);border:1px solid #f4c9c3;border-radius:10px;padding:10px 12px;font-size:12.5px;margin-top:8px}
.rg-ok{background:var(--ok-soft);color:var(--ok);border:1px solid #c6e8cf;border-radius:10px;padding:10px 12px;font-size:13px;margin-top:8px;font-weight:600}
.rg-foot{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}

.empty-state{text-align:center;padding:60px 20px;color:var(--muted)}
.empty-state h3{margin:0 0 8px;color:var(--text);font-weight:600;font-size:18px}
.empty-state p{margin:0 auto 14px;max-width:420px;font-size:14px}
.pulse-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--primary);animation:pulse 1.2s infinite}
.hdr-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border:1px solid var(--border);border-radius:99px;background:#fff;color:var(--muted);font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;transition:color .12s,border-color .12s,background .12s}
.hdr-pill:hover{color:var(--primary-dark);border-color:var(--primary);background:var(--primary-soft);text-decoration:none}
.hdr-pill svg{flex-shrink:0}
@media(max-width:720px){.hdr-pill .hdr-pill-lbl{display:none}}
</style>
<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>
<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>
<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>
<style id="oc-usermenu">.ocu{position:relative;display:inline-flex}.ocu-btn{display:flex;align-items:center;gap:8px;padding:5px 10px 5px 5px;border:1px solid #e3e6e8;border-radius:99px;background:#fff;cursor:pointer;font-family:inherit;font-size:13px;color:#1b1b1b;transition:border-color .12s,box-shadow .12s}.ocu-btn:hover{border-color:#c7ccd1}.ocu-btn-bare{background:none;border:none;padding:0;cursor:pointer}.ocu-av{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#5b6b7b,#3a434d);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0}.ocu-name{max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ocu-chev{width:12px;height:12px;color:#8a91a0;transition:transform .15s}.ocu.open .ocu-chev{transform:rotate(180deg)}.ocu-drop{display:none;position:absolute;top:calc(100% + 6px);right:0;min-width:200px;background:#fff;border:1px solid #e6e8eb;border-radius:14px;box-shadow:0 20px 40px rgba(16,24,40,.16);padding:6px;z-index:400}.ocu.open .ocu-drop{display:block}.ocu-item{display:flex;align-items:center;gap:10px;padding:9px 12px;color:#1b1b1b;text-decoration:none;font-size:13.5px;border-radius:10px;transition:background .12s}.ocu-item:hover{background:#f2f4f7;text-decoration:none}.ocu-item svg{width:16px;height:16px;flex-shrink:0}.ocu-logout{color:#b42318}.ocu-logout:hover{background:#fef3f2}</style><style id="oc-mobfix">@media(max-width:768px){html,body{overflow-x:hidden}.iw-fbar{overflow-x:auto !important;-webkit-overflow-scrolling:touch}.iw-fbar-inner,.iw-fbar>div{flex-shrink:0}header .brand .sub{display:none}}</style><style id="m-layer">:root{--m-content-top:max(env(safe-area-inset-top,0px),var(--tg-content-safe-area-inset-top,0px));--m-safe-bottom:max(env(safe-area-inset-bottom,0px),var(--tg-safe-area-inset-bottom,0px));--m-nav-h:50px;--m-nav-total:calc(var(--m-nav-h) + var(--m-content-top));--ms-1:4px;--ms-2:8px;--ms-3:12px;--ms-4:16px;--ms-5:20px;--ms-6:24px;--ms-8:32px;--mr-sm:8px;--mr-md:12px;--mr-lg:16px;--mr-pill:999px;--mtap:44px;--m-gutter:16px;--m-card-bd:rgba(16,24,40,.08);--m-chip-bg:#f1f3f5;--m-chip-fg:#3a414b;--m-chip-bd:#e3e6ea;--m-acc:#1aa04a;--m-acc-soft:#eaf6ee}#mtop{display:none}@media(max-width:640px){body>header{display:none!important}#m-research .r-topbar{display:none!important}#m-research #rSub{display:none!important}#m-research .reader-shell{grid-template-columns:minmax(0,1fr)!important}#m-research .reader-wrap{min-width:0;max-width:100%}#m-research .reader{max-width:100%!important;width:auto!important;padding:16px 16px 80px!important;box-sizing:border-box}#m-research .reader table{display:block;overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}#m-research .reader img,#m-research .reader pre,#m-research .reader video{max-width:100%;height:auto}#m-chat #log{-webkit-overflow-scrolling:touch;overscroll-behavior:contain}#m-chat{overflow:hidden!important}#m-research .dsc-win{position:fixed!important;left:0!important;right:0!important;bottom:0!important;top:auto!important;width:100%!important;min-width:0!important;max-width:100%!important;height:82vh!important;min-height:0!important;border-radius:14px 14px 0 0!important;transform:none!important;z-index:1500!important}#m-research .dsc-win-resize,#m-research .dsc-edge-r,#m-research .dsc-edge-l,#m-research .dsc-edge-b{display:none!important}#m-research .dsc-win-header{cursor:default!important}#m-research .dsc-tabbar{top:auto!important;bottom:calc(82vh + 10px)!important;left:8px!important;right:8px!important;max-width:none!important;z-index:1499!important}#m-research .dsc-confirm{max-width:92vw!important}#m-research .toc-rail{display:none!important}#mtop{display:flex!important;position:fixed;top:0;left:0;right:0;z-index:1000;align-items:center;gap:8px;height:var(--m-nav-total);padding:var(--m-content-top) 10px 0;background:#fff;border-bottom:1px solid rgba(16,24,40,.08);box-sizing:border-box;transition:transform .22s ease;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}#mtop.up{transform:translateY(-100%)}.m-icbtn{flex:0 0 auto;width:40px;height:40px;display:grid;place-items:center;border:0;background:transparent;border-radius:10px;cursor:pointer;color:#1b1b1b}.m-icbtn svg{width:24px;height:24px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}.m-title{flex:1;min-width:0;font-size:17px;font-weight:600;color:#1b1b1b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}.m-avbtn{flex:0 0 auto;width:34px;height:34px;border:0;border-radius:50%;background:linear-gradient(135deg,#5b6b7b,#3a434d);color:#fff;font-size:12px;font-weight:700;cursor:pointer;display:grid;place-items:center}.m-avbtn span{color:#fff}body{padding-top:var(--m-nav-total)!important;padding-bottom:calc(18px + var(--m-safe-bottom))!important}.m-scrim{position:fixed;inset:0;z-index:1001;background:rgba(16,24,40,.45);opacity:0;transition:opacity .22s}.m-scrim.o{opacity:1}.m-drawer{position:fixed;top:0;bottom:0;left:0;z-index:1002;width:min(86vw,320px);display:flex;flex-direction:column;gap:2px;padding:calc(var(--m-content-top) + 14px) 10px calc(var(--m-safe-bottom) + 14px);background:#fff;box-shadow:2px 0 30px rgba(16,24,40,.22);transform:translateX(-100%);transition:transform .24s cubic-bezier(.2,.7,.2,1);overflow:auto;overscroll-behavior:contain;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}.m-drawer.o{transform:none}.m-acct{display:flex;align-items:center;gap:10px;padding:6px 10px 12px}.m-acct-av{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#5b6b7b,#3a434d);color:#fff;display:grid;place-items:center;font-size:14px;font-weight:700;flex:0 0 auto}.m-acct-name{font-size:16px;font-weight:700;color:#1b1b1b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.m-row{display:flex;align-items:center;min-height:46px;padding:0 12px;border-radius:10px;text-decoration:none;color:#1b1b1b;font-size:15px;font-weight:600}.m-row:active{background:rgba(16,24,40,.06);text-decoration:none}.m-row-logout{color:#b42318}.m-sep{height:1px;background:rgba(16,24,40,.08);margin:8px 8px}.m-links{display:flex;flex-direction:column;gap:2px}.m-link{display:flex;align-items:center;min-height:46px;padding:0 12px;border-radius:10px;text-decoration:none;color:#1b1b1b;font-size:15px;font-weight:600}.m-link:active{background:rgba(16,24,40,.06);text-decoration:none}.m-link.act{background:#eaf1ff;color:#1c52c2}.m-sub{display:flex;align-items:center;min-height:42px;padding:0 12px 0 30px;border-radius:10px;text-decoration:none;color:#3a414b;font-size:14px;font-weight:500;position:relative}.m-sub::before{content:"";position:absolute;left:17px;top:50%;width:5px;height:5px;border-radius:50%;background:#cfd4da;transform:translateY(-50%)}.m-sub:active{background:rgba(16,24,40,.06);text-decoration:none}.m-sub.act{background:#eaf1ff;color:#1c52c2}.m-sub.act::before{background:#1c52c2}.m-rsc{display:flex;flex-direction:column;gap:1px}.m-rsc-search{display:flex;align-items:center;gap:8px;min-height:42px;padding:0 12px 0 30px;border-radius:10px;color:#3a414b;font-size:14px;font-weight:500;cursor:pointer;border:0;background:transparent;width:100%;text-align:left;font-family:inherit}.m-rsc-search:active{background:rgba(16,24,40,.06)}.m-rsc-search svg{flex:0 0 auto;color:#8a91a0}#mDrawer .nav-rail{position:static!important;top:auto!important;height:auto!important;width:auto!important;max-height:none!important;border:0!important;background:transparent!important;padding:2px 0 2px 14px!important;overflow:visible!important;font-size:14px}#mDrawer .nav-rail .nr-body{display:block!important}main{padding-left:max(16px,env(safe-area-inset-left))!important;padding-right:max(16px,env(safe-area-inset-right))!important}input,textarea,select{font-size:16px!important}.kbd{display:none!important}.m-chips{display:flex;flex-wrap:nowrap;gap:var(--ms-2);overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding-bottom:var(--ms-1)}.m-chips::-webkit-scrollbar{display:none}.m-chips>*{flex:0 0 auto}.m-chip{min-height:32px;display:inline-flex;align-items:center;gap:6px;padding:0 var(--ms-3);border-radius:var(--mr-pill);background:var(--m-chip-bg);color:var(--m-chip-fg);border:1px solid var(--m-chip-bd);font-size:13px;font-weight:600;white-space:nowrap}.m-chip.is-active{background:var(--m-acc);color:#fff;border-color:transparent}.m-metrics{display:grid;grid-template-columns:1fr 1fr;gap:var(--ms-2);margin:var(--ms-3) 0}.m-metric{background:#fff;border:1px solid var(--m-card-bd);border-radius:var(--mr-md);padding:var(--ms-3)}.m-metric-num{font-size:26px;font-weight:700;line-height:1.1}.m-metric-cap{font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em}.m-card{background:#fff;border:1px solid var(--m-card-bd);border-radius:var(--mr-md);padding:var(--ms-4);margin-bottom:var(--ms-3)}.m-collapsed{display:none!important}.m-scrim2{position:fixed;inset:0;z-index:1400;background:rgba(16,24,40,.45);opacity:0;transition:opacity .2s}.m-scrim2.o{opacity:1}.m-sheet{position:fixed;left:0;right:0;bottom:0;z-index:1401;background:#fff;border-radius:16px 16px 0 0;box-shadow:0 -8px 30px rgba(16,24,40,.18);max-height:82vh;overflow:auto;transform:translateY(100%);transition:transform .24s cubic-bezier(.2,.7,.2,1);padding:var(--ms-4) var(--ms-4) calc(var(--ms-4) + var(--m-safe-bottom))}.m-sheet.o{transform:none}.m-sheet-grab{width:36px;height:4px;border-radius:2px;background:#d7dbe0;margin:0 auto var(--ms-3)}.m-sheet-h{font-size:16px;font-weight:700;margin-bottom:var(--ms-3);display:flex;align-items:center;justify-content:space-between}.m-fbtn{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 14px;border-radius:var(--mr-pill);border:1px solid var(--m-chip-bd);background:#fff;font-size:13px;font-weight:600;color:#1b1b1b;cursor:pointer;font-family:inherit}.m-fbtn .m-badge{background:var(--m-acc);color:#fff;border-radius:999px;font-size:11px;line-height:18px;padding:0 6px;min-width:18px;text-align:center}#m-news .stat-row{display:flex!important;flex-wrap:nowrap!important;overflow-x:auto;gap:8px!important;margin:8px 0!important;scrollbar-width:none}#m-news .stat-row::-webkit-scrollbar{display:none}#m-news .stat{flex:0 0 auto!important;min-width:0!important;padding:6px 12px!important;min-height:0!important;display:flex!important;flex-direction:column!important;align-items:flex-start;border:1px solid var(--m-card-bd);border-radius:10px;background:#fff;gap:0}#m-news .stat .value{font-size:17px!important;line-height:1.15!important;margin:0!important}#m-news .stat .label{font-size:10px!important;margin:0!important}#m-news .stat .sub{display:none!important}#m-news .filters .chips{flex-wrap:nowrap!important;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}#m-news .filters .chips::-webkit-scrollbar{display:none}#m-news .filters-row{gap:8px}#m-news #mNewsFbtn{margin:2px 0 6px}#m-feedback .tbl{display:block!important}#m-feedback .tbl thead{display:none!important}#m-feedback .tbl tbody,#m-feedback .tbl tr,#m-feedback .tbl td{display:block;width:auto}#m-feedback .tbl tr{background:#fff;border:1px solid var(--m-card-bd)!important;border-radius:12px;padding:12px;margin-bottom:10px}#m-feedback .tbl td{padding:2px 0;border:0!important}#m-feedback .tbl td.col-date{font-size:12px;color:#6b7280}#m-feedback .tbl td.text-cell{font-size:15px;line-height:1.45;white-space:normal;color:#1b1b1b;margin:6px 0}#m-feedback .tbl td.col-author,#m-feedback .tbl td.col-page,#m-feedback .tbl td.col-pri,#m-feedback .tbl td.col-status{display:inline-block!important;margin:2px 10px 2px 0;vertical-align:middle;font-size:12px}#m-feedback .tbl td.col-act{display:inline-block!important;margin-top:6px}#m-feedback .tbl td[colspan]{text-align:center;color:#6b7280}#m-admin #usersTable{display:block!important;overflow-x:auto;-webkit-overflow-scrolling:touch;white-space:nowrap;max-width:100%}#m-admin #usersTable td,#m-admin #usersTable th{white-space:nowrap}#m-insights .iw-rail{padding-left:16px;padding-right:16px;box-sizing:border-box}#m-insights #mInsFbtn{margin:8px 16px}#m-journey{--primary:#1aa04a!important;--primary-dark:#0e8a2e!important;--primary-darker:#0b6e25!important;--primary-soft:#bfe6cb!important;--primary-softer:#eef7f0!important;--primary-glow:#d6f0de!important;--ring:26,160,74!important;background:#f5f7f8!important}#m-journey .stage-card.add-card{border-color:#cfe6d6!important;background:linear-gradient(135deg,#fff,#eef7f0)!important}#m-journey main{display:block!important}#m-journey .products-side{position:static!important;width:auto!important;max-width:100%!important;height:auto!important;margin-bottom:12px}#m-journey .ph-head{flex-wrap:wrap!important;gap:8px;align-items:flex-start}#m-journey .ph-head .add-stage{width:100%;justify-content:center;margin-top:4px}#m-journey .stages-grid{grid-template-columns:1fr!important}#m-research .reader{font-size:16px;line-height:1.6}#m-research .reader-h1,#m-research .reader h1{font-size:22px!important;line-height:1.25!important}#m-research .reader h2,#m-research .reader-h2{font-size:18px!important;line-height:1.3!important}#m-research .reader h3{font-size:16px!important}#m-chat{height:100dvh!important;overflow:hidden!important;display:flex!important;flex-direction:column!important;padding-bottom:0!important}#m-chat #section-view{flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;height:auto!important}#m-chat #section-view>:not(.chat-col){display:none!important}#m-chat .chat-col{flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;height:auto!important}#m-chat #log{flex:1 1 auto!important;min-height:0!important;height:auto!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch;overscroll-behavior:contain}#m-chat .chat-col>footer{flex:0 0 auto!important;position:static!important;padding-bottom:calc(6px + var(--m-safe-bottom));border-top:1px solid rgba(16,24,40,.08)}#m-news .filters-row.m-coll .chips ~ *{display:none!important}html,body{overflow-x:hidden}}</style><script id="m-layer-js">(function(){function init(){var W=window.Telegram&&window.Telegram.WebApp,root=document.documentElement;function px(n){return (n||0)+"px";}function insets(){if(!W)return;try{var c=W.contentSafeAreaInset||{},s=W.safeAreaInset||{};var top=Math.max(c.top||0,s.top||0);root.style.setProperty("--m-content-top","max(env(safe-area-inset-top,0px),"+px(top)+")");root.style.setProperty("--m-safe-bottom","max(env(safe-area-inset-bottom,0px),"+px(s.bottom||0)+")");}catch(e){}}if(W){["safeAreaChanged","contentSafeAreaChanged","viewportChanged"].forEach(function(ev){try{W.onEvent&&W.onEvent(ev,insets);}catch(e){}});insets();try{W.setHeaderColor&&W.setHeaderColor("#ffffff");}catch(e){}try{W.disableVerticalSwipes&&W.disableVerticalSwipes();}catch(e){}}function $(id){return document.getElementById(id);}var dr=$("mDrawer"),sc=$("mScrim"),bg=$("mBurger"),ab=$("mAvatarBtn"),top=$("mtop");function op(){if(!dr)return;dr.hidden=false;sc.hidden=false;requestAnimationFrame(function(){dr.classList.add("o");sc.classList.add("o");});document.body.style.overflow="hidden";}function cl(){if(!dr)return;dr.classList.remove("o");sc.classList.remove("o");document.body.style.overflow="";setTimeout(function(){dr.hidden=true;sc.hidden=true;},240);}bg&&bg.addEventListener("click",op);ab&&ab.addEventListener("click",op);sc&&sc.addEventListener("click",cl);document.addEventListener("keydown",function(e){if(e.key==="Escape")cl();});var last=0,tick=false;window.addEventListener("scroll",function(){if(tick)return;tick=true;requestAnimationFrame(function(){var y=window.pageYOffset||0;if(Math.abs(y-last)>8){if(y>last&&y>64&&top)top.classList.add("up");else if(top)top.classList.remove("up");last=y;}tick=false;});},{passive:true});var path=(location.pathname.replace(/\/+$/,"")||"/");var best=null,bs=-1;document.querySelectorAll(".m-link,.m-sub").forEach(function(a){var dp=(a.getAttribute("data-p")||"").replace(/\/+$/,"")||"/";var ex=a.getAttribute("data-exact");var m=ex?(path===dp):((path===dp)||(dp!=="/"&&path.indexOf(dp+"/")===0)||(dp==="/"&&path==="/"));if(m){var sco=dp.length+(ex?100:0)+((path===dp)?50:0);if(sco>bs){bs=sco;best=a;}}});if(best){best.classList.add("act");var t=$("mTitle");if(t)t.textContent=best.textContent.trim();}if(path.indexOf("/research")===0&&((window.matchMedia&&window.matchMedia("(max-width:640px)").matches)||root.classList.contains("tg"))){var rsc=$("mRscSub");if(rsc){var sb=document.createElement("button");sb.className="m-rsc-search";sb.type="button";sb.innerHTML="<svg width=15 height=15 viewBox=\"0 0 16 16\" fill=none stroke=currentColor stroke-width=1.6><circle cx=7 cy=7 r=5></circle><path d=\"M11 11l3 3\"></path></svg><span>Поиск по проекту</span>";sb.addEventListener("click",function(){var b=$("rSearchBtn");if(b)b.click();cl();});rsc.appendChild(sb);var nr=$("navRail");if(nr){try{rsc.appendChild(nr);}catch(e){}nr.addEventListener("click",function(e){var hit=e.target&&e.target.closest&&e.target.closest(".nr-item,.nr-theme,a,button");if(!hit)return;var u0=location.href,tr=0,iv=setInterval(function(){tr++;if(location.href!==u0){clearInterval(iv);cl();}else if(tr>10){clearInterval(iv);}},60);});}}}if(document.getElementById("m-news")&&((window.matchMedia&&window.matchMedia("(max-width:640px)").matches)||root.classList.contains("tg"))){var fr=document.querySelector("#m-news .filters-row:not(.row2)")||document.querySelector("#m-news .filters-row");var r2=document.querySelector("#m-news .filters-row.row2");if(fr&&!document.getElementById("mNewsFbtn")){fr.classList.add("m-coll");if(r2)r2.classList.add("m-collapsed");var b=document.createElement("button");b.id="mNewsFbtn";b.className="m-fbtn";b.type="button";b.style.margin="6px 0";b.innerHTML="<span>Фильтры</span>";b.addEventListener("click",function(){var on=fr.classList.toggle("m-coll");if(r2){if(on)r2.classList.add("m-collapsed");else r2.classList.remove("m-collapsed");}});fr.parentNode.insertBefore(b,fr.nextSibling);}}var MOB=((window.matchMedia&&window.matchMedia("(max-width:640px)").matches)||root.classList.contains("tg"));if(document.getElementById("m-insights")&&MOB){var rail=document.querySelector("#m-insights .iw-rail");if(rail&&!document.getElementById("mInsFbtn")){rail.classList.add("m-collapsed");var ib=document.createElement("button");ib.id="mInsFbtn";ib.className="m-fbtn";ib.type="button";ib.innerHTML="<span>Фильтры</span>";ib.addEventListener("click",function(){rail.classList.toggle("m-collapsed");});rail.parentNode.insertBefore(ib,rail);}}if(document.getElementById("m-admin")&&MOB){var ac=[].slice.call(document.querySelectorAll("#m-admin .card")).filter(function(cc){var h=cc.querySelector("h1,h2,h3");return h&&/\u0414\u043e\u0431\u0430\u0432/.test(h.textContent||"");})[0];if(ac&&!ac.dataset.macc){var hd=ac.querySelector("h1,h2,h3");if(hd&&hd.parentElement===ac){ac.dataset.macc="1";var oth=[].slice.call(ac.children).filter(function(x){return x!==hd;});var col=true;function ap(){oth.forEach(function(x){x.style.display=col?"none":"";});}ap();hd.style.cursor="pointer";hd.insertAdjacentHTML("beforeend",' <span style="float:right;color:#8a91a0;font-weight:400">\u25be</span>');hd.addEventListener("click",function(){col=!col;ap();});}}}if(document.getElementById("m-kb")&&MOB){var uc=document.getElementById("uploadCard");if(uc&&!uc.dataset.macc){var kh=uc.querySelector("h1,h2,h3");if(kh&&kh.parentElement===uc){uc.dataset.macc="1";var ko=[].slice.call(uc.children).filter(function(x){return x!==kh;});var kc=true;function kap(){ko.forEach(function(x){x.style.display=kc?"none":"";});}kap();kh.style.cursor="pointer";kh.insertAdjacentHTML("beforeend",' <span style="float:right;color:#8a91a0;font-weight:400">\u25be</span>');kh.addEventListener("click",function(){kc=!kc;kap();});}}}if(document.getElementById("m-chat")&&MOB){var ci=document.getElementById("inp");if(ci)ci.placeholder="\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u0443\u2026";}if(document.getElementById("m-admin")){var att=document.getElementById("mTitle");if(att)att.textContent="Админка";}if(document.getElementById("m-chat")&&MOB){var lgb=document.getElementById("log");if(lgb){setTimeout(function(){lgb.scrollTop=lgb.scrollHeight;},350);setTimeout(function(){lgb.scrollTop=lgb.scrollHeight;},900);}}if(MOB){function ensSc(){try{if(document.documentElement.scrollHeight<=window.innerHeight){document.documentElement.style.setProperty("height","calc(100dvh + 1px)","important");}}catch(e){}}ensSc();window.addEventListener("load",ensSc);document.addEventListener("touchstart",function(){if(window.scrollY===0){window.scrollTo(0,1);}},{passive:true});}try{fetch("/me",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null;}).then(function(me){if(!me)return;var nm=me.username||me.user||"";var ini=(nm||"·").slice(0,2).toUpperCase();var a=$("mAvatar"),aa=$("mAcctAv"),an=$("mAcctName");if(a)a.textContent=ini;if(aa)aa.textContent=ini;if(an)an.textContent=nm||"Профиль";if(me.is_admin){var ad=$("mAdmin");if(ad)ad.hidden=false;}}).catch(function(){});}catch(e){}}if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();})();</script><style id="oc-plashka-unify">/* OC-Header: единый вид активной вкладки и иконок (стандарт, заменяет per-section градиенты) */
.sec-tab[data-sec].active,.iw-sec-tab[data-sec].active{background:var(--accent,#2563eb)!important;border-color:transparent!important;color:#fff!important;box-shadow:0 1px 2px rgba(15,15,18,.08),0 6px 18px -10px rgba(37,99,235,.45)!important}
.sec-tab[data-sec].active .st-ico,.iw-sec-tab[data-sec].active .st-ico{background:rgba(255,255,255,.22)!important;color:#fff!important}
.sec-tab[data-sec]:not(.active) .st-ico,.iw-sec-tab[data-sec]:not(.active) .st-ico{background:var(--surface-2,#f4f4f6)!important;color:var(--muted,#6c6c75)!important}
.sec-tab[data-sec].active .st-sub,.iw-sec-tab[data-sec].active .st-sub{color:rgba(255,255,255,.85)!important}
</style>
</head><body id="m-insights">
<!-- mobile nav layer -->
<header id="mtop" class="m-top"><button id="mBurger" class="m-icbtn" aria-label="Меню"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button><div class="m-title" id="mTitle">openclaw</div><button id="mAvatarBtn" class="m-avbtn" aria-label="Профиль"><span id="mAvatar">·</span></button></header>
<div id="mScrim" class="m-scrim" hidden></div>
<aside id="mDrawer" class="m-drawer" hidden aria-label="Меню" role="dialog"><div class="m-acct"><span class="m-acct-av" id="mAcctAv">·</span><div class="m-acct-name" id="mAcctName">Профиль</div></div><a id="mAdmin" class="m-row" href="/admin" hidden>Админка</a><a class="m-row m-row-logout" href="/logout">Выйти</a><div class="m-sep"></div><nav class="m-links"><a class="m-link" href="/" data-p="/">Чат</a><a class="m-link" href="/news" data-p="/news">Новости</a><a class="m-link" href="/methodology" data-p="/methodology">AI Методология</a><a class="m-link" href="/kb" data-p="/kb">База знаний</a><a class="m-sub" href="/kb" data-p="/kb" data-exact="1">Материалы</a><a class="m-sub" href="/kb/insights" data-p="/kb/insights">Гипотезы</a><a class="m-link" href="/research" data-p="/research">Research</a><div class="m-rsc" id="mRscSub"></div><a class="m-link" href="/conferences" data-p="/conferences">Конференции</a><a class="m-link" href="/journey" data-p="/journey">Путь клиента</a><a class="m-link" href="/suggestions" data-p="/suggestions">Идеи</a></nav></aside>
<header>
  <div class="brand">
    <div class="logo-mark">∴</div>
    <div class="brand-text">
      <h1>Инсайт-хаб</h1>
      <div class="sub">База материалов и гипотезы</div>
    </div>
  </div>
  <nav class="sec-tabs" aria-label="Разделы">
    <div class="sec-tabs-inner">
      <a class="sec-tab" href="/" data-sec="team">
        <span class="st-ico">◉</span>
        <span class="st-body"><span class="st-ttl">Команда</span><span class="st-sub">Travel · ПУ · UX/UI</span></span>
      </a>
      <a class="sec-tab" href="/news" data-sec="news">
        <span class="st-ico">📰</span>
        <span class="st-body"><span class="st-ttl">NEWS</span><span class="st-sub">Командный центр</span></span>
      </a>
      <a class="sec-tab" href="/methodology" data-sec="methodology" title="AI Методология — оценка применимости ИИ">
        <span class="st-ico">✓</span>
        <span class="st-body"><span class="st-ttl">AI Методология</span><span class="st-sub">Оценка применимости ИИ</span></span>
      </a>
      <a class="sec-tab active" href="/kb" data-sec="kb" aria-current="page">
        <span class="st-ico">∴</span>
        <span class="st-body"><span class="st-ttl">Инсайт-хаб</span><span class="st-sub">База знаний</span></span>
      </a>
      <a class="sec-tab" href="/research" data-sec="research" title="AI Research — глубинные исследования">
        <span class="st-ico">⊞</span>
        <span class="st-body"><span class="st-ttl">AI Research</span><span class="st-sub">Глубинные отчёты</span></span>
      </a><a class="sec-tab" href="/conferences" data-sec="conferences" title="Конференции — доклады и материалы"><span class="st-ico">❯</span><span class="st-body"><span class="st-ttl">Конференции</span><span class="st-sub">Доклады и материалы</span></span></a>
    </div>
  </nav>
  <div class="meta-right">
    <a href="/kb" class="back-btn" title="Вернуться в хаб">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M10 12L6 8l4-4"/></svg>
      В хаб
    </a>
    <button type="button" class="fb-cta" onclick="openFeedback()" title="Что улучшить или доработать?">
      <span class="fb-cta-lbl">Обратная связь</span>
    </button>
    <button type="button" class="iw-theme-toggle" id="iwThemeToggle" title="Сменить тему" aria-label="Сменить тему">
      <svg id="iwThemeIco" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
    </button>
    <a class="hdr-pill" href="/suggestions" title="Все предложения" aria-label="Все предложения">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M5 6h6M5 9h6M5 12h4"/></svg>
    </a>
    <div class="ocu" id="ocu"><button class="ocu-btn" id="ocu-btn" type="button"><span class="ocu-av">__INIT__</span><span class="ocu-name">__USER__</span><svg class="ocu-chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6l4 4 4-4"/></svg></button><div class="ocu-drop">__ADMIN_ITEM__<a class="ocu-item ocu-logout" href="/logout"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>Выйти</a></div></div><script>(function(){var m=document.getElementById('ocu'),b=document.getElementById('ocu-btn');if(m&&b){b.addEventListener('click',function(e){e.stopPropagation();m.classList.toggle('open');});document.addEventListener('click',function(e){if(!m.contains(e.target))m.classList.remove('open');});document.addEventListener('keydown',function(e){if(e.key==='Escape')m.classList.remove('open');});}})();</script>
  </div>
</header>
<div class="iw-fbar" role="search">
  <div class="iw-fbar-search">
    <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
    <input id="iwSearch" type="text" placeholder="Поиск инсайтов и материалов…" autocomplete="off">
    <kbd>/</kbd>
  </div>
  <div class="iw-fbar-spacer"></div>
  <div class="iw-vmode" id="iwVMode" role="tablist" aria-label="Версия пайплайна">
    <button type="button" data-vmode="asis" class="active" title="Актуальные гипотезы по новому V2 пайплайну">AS IS<span class="cnt" id="vmCntAsis">0</span></button>
    <button type="button" data-vmode="archive" title="Старые гипотезы — со старого промпта">Архив<span class="cnt" id="vmCntArch">0</span></button>
  </div>
  <div class="iw-vtoggle" id="iwViewToggle">
    <button type="button" data-view="list" class="active"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18M3 6h18M3 18h12"/></svg>Список</button>
    <button type="button" data-view="kanban"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="6" height="18" rx="1"/><rect x="11" y="3" width="6" height="12" rx="1"/><rect x="19" y="3" width="2" height="8" rx="1"/></svg>Kanban</button>
  </div>
  <button type="button" id="iwBtnRegen" class="iw-fbar-btn" title="Пересобрать инсайты из материалов">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15.5-6.36L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.36L3 16"/><path d="M3 21v-5h5"/></svg>
    <span class="iw-fbar-btn-lbl">Пересобрать</span>
  </button>
  <a href="/kb" id="iwBtnAdd" class="iw-fbar-btn primary" title="Добавить материал">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
    <span class="iw-fbar-btn-lbl">Добавить</span>
  </a>
</div>
<div class="iw-shell">
<aside class="iw-rail" aria-label="Фильтры">
  <div class="iw-rail-grp">
    <div class="iw-rail-cap">Workspace</div>
    <a class="iw-rail-item active" href="/kb/insights"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg><span class="lbl">Гипотезы</span></a>
    <a class="iw-rail-item" href="/kb"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8M10 9H8"/></svg><span class="lbl">Материалы</span></a>
  </div>
  <div class="iw-rail-grp">
    <div class="iw-rail-cap">Категория</div>
    <div data-rail="cat">
      <div class="iw-rail-item active" data-c=""><span class="ic">●</span><span class="lbl">Все</span><span class="cnt" data-cnt-cat=""></span></div>
      <div class="iw-rail-item" data-c="Travel"><span class="ic">✈</span><span class="lbl">Travel</span><span class="cnt" data-cnt-cat="Travel"></span></div>
      <div class="iw-rail-item" data-c="ПУ/подписки"><span class="ic">₽</span><span class="lbl">Пакеты услуг</span><span class="cnt" data-cnt-cat="ПУ/подписки"></span></div>
      <div class="iw-rail-item" data-c="UX/UI"><span class="ic">◎</span><span class="lbl">UX/UI</span><span class="cnt" data-cnt-cat="UX/UI"></span></div>
    </div>
  </div>
  <div class="iw-rail-grp">
    <div class="iw-rail-cap">Статус</div>
    <div data-rail="filter">
      <div class="iw-rail-item active" data-f="all"><span class="ic">○</span><span class="lbl">Все</span></div>
      <div class="iw-rail-item" data-f="validated"><span class="ic" style="color:var(--lc-valid)">✓</span><span class="lbl">Валидированные</span></div>
      <div class="iw-rail-item" data-f="new"><span class="ic" style="color:var(--lc-review)">★</span><span class="lbl">Новые</span></div>
    </div>
  </div>
  <div class="iw-rail-grp">
    <div class="iw-rail-cap">Источник</div>
    <div data-rail="src">
      <div class="iw-rail-item active" data-s=""><span class="ic">∎</span><span class="lbl">Все</span><span class="cnt" data-cnt-src=""></span></div>
      <div class="iw-rail-item" data-s="material"><span class="ic">📄</span><span class="lbl">Материалы</span><span class="cnt" data-cnt-src="material"></span></div>
      <div class="iw-rail-item" data-s="news"><span class="ic">📰</span><span class="lbl">Новости</span><span class="cnt" data-cnt-src="news"></span></div>
      <div class="iw-rail-item" data-s="mixed"><span class="ic">⊕</span><span class="lbl">Смешанные</span><span class="cnt" data-cnt-src="mixed"></span></div>
    </div>
  </div>
  <div class="iw-rail-grp">
    <div class="iw-rail-cap">Очередь</div>
    <a class="iw-rail-item" href="/kb/insights?view=mine"><span class="ic">⊕</span><span class="lbl">Мои</span></a>
    <div class="iw-rail-item" data-quick="overdue"><span class="ic" style="color:var(--neg)">⏰</span><span class="lbl">Просроченные</span></div>
    <div class="iw-rail-item" data-quick="new72"><span class="ic" style="color:var(--lc-review)">🆕</span><span class="lbl">Новые за 72ч</span></div>
  </div>
</aside>
<main>
  <div class="toolbar">
    <span class="t-label">Категория</span>
    <div class="chip-row" id="catRow">
      <button data-c="" class="active">Все</button>
      <button data-c="ПУ/подписки">ПУ/подписки <span class="cc" data-cc="ПУ/подписки">0</span></button>
      <button data-c="Travel">Travel <span class="cc" data-cc="Travel">0</span></button>
      <button data-c="UX/UI">UX/UI <span class="cc" data-cc="UX/UI">0</span></button>
    </div>
    <span class="t-label" style="margin-left:8px">Статус</span>
    <div class="chip-row" id="filterRow">
      <button data-f="all" class="active">Все</button>
      <button data-f="validated">Валидированные</button>
      <button data-f="single">1 источник</button>
    </div>
    <span class="t-label" style="margin-left:8px">Источник</span>
    <div class="chip-row" id="srcRow">
      <button data-s="" class="active">Все</button>
      <button data-s="material">Материалы <span class="cc" data-sc="material">0</span></button>
      <button data-s="news">Новости <span class="cc" data-sc="news">0</span></button>
      <button data-s="mixed">Смешанные <span class="cc" data-sc="mixed">0</span></button>
    </div>
    <div class="spacer"></div>
    <div class="stats" id="stats"></div>
    <button class="btn" id="regenBtn" style="display:none">↻ Пересобрать</button>
  </div>

  <div class="list-card">
    <h3 id="listLabel">Все гипотезы</h3>
    <div class="hyp-list" id="hypList"></div>
  </div>

  <div class="graph-card">
    <header class="graph-head">
      <div class="gh-ttl">
        <div class="gh-eyebrow">Сеть</div>
        <h3>Связи гипотез по общим источникам</h3>
      </div>
      <div class="gh-spacer"></div>
      <div class="gh-stat" id="gStat">—</div>
      <label class="gh-search" title="Поиск по формулировке">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="5"/><path d="M11 11l3 3"/></svg>
        <input id="gSearch" type="search" placeholder="Найти…">
      </label>
      <div class="chip-row gh-layouts" id="gLayoutRow">
        <button data-lo="fcose" class="active">Кластеры</button>
        <button data-lo="concentric">Радиально</button>
        <button data-lo="circle">Кольцом</button>
      </div>
    </header>
    <div class="graph-body">
      <div class="graph-legend">
        <div class="lr lr-cats">
          <span class="cdot" style="background:#0b6fa8"></span>Travel
          <span class="cdot" style="background:#0e8a2e"></span>ПУ/подписки
          <span class="cdot" style="background:#6a22a8"></span>UX/UI
        </div>
        <div class="lr lr-meta">
          <span><span class="dot v"></span>Валидирована</span>
          <span><span class="dot u"></span>Штрих = требует подтверждения</span>
        </div>
        <div class="lr lr-meta"><span>Размер ноды = число источников</span><span>Оранжевая обводка = новая</span></div>
      </div>
      <div id="graphWrap"></div>
      <div class="graph-detail" id="gDetail" hidden></div>
      <div class="gcontrols">
        <button id="gZoomIn" title="Приблизить">+</button>
        <button id="gZoomOut" title="Отдалить">−</button>
        <button id="gFit" title="Вписать в экран">⤢</button>
        <button id="gFullscreen" title="На весь экран (Esc — выйти)"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4"/></svg></button>
      </div>
      <div class="graph-empty" id="graphEmpty" style="display:none"></div>
    </div>
  </div>

  <div class="iw-kanban" id="iwKanban">
    <div class="iw-kb-col" data-status="synthesized"><div class="iw-kb-h"><span class="dot"></span><span class="lbl">Черновики</span><span class="cnt" data-cnt="synthesized">0</span></div><div class="iw-kb-list" data-list="synthesized"></div></div>
    <div class="iw-kb-col" data-status="in_review"><div class="iw-kb-h"><span class="dot"></span><span class="lbl">В работе</span><span class="cnt" data-cnt="in_review">0</span></div><div class="iw-kb-list" data-list="in_review"></div></div>
    <div class="iw-kb-col" data-status="validated"><div class="iw-kb-h"><span class="dot"></span><span class="lbl">Валидированные</span><span class="cnt" data-cnt="validated">0</span></div><div class="iw-kb-list" data-list="validated"></div></div>
    <div class="iw-kb-col" data-status="adopted"><div class="iw-kb-h"><span class="dot"></span><span class="lbl">Принятые</span><span class="cnt" data-cnt="adopted">0</span></div><div class="iw-kb-list" data-list="adopted"></div></div>
    <div class="iw-kb-col" data-status="archived"><div class="iw-kb-h"><span class="dot"></span><span class="lbl">Архив</span><span class="cnt" data-cnt="archived">0</span></div><div class="iw-kb-list" data-list="archived"></div></div>
  </div>
</main>
</div>

<div class="drawer-bg" id="drBg"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="dr-head">
    <h2 id="drTitle">…</h2>
    <button class="dr-close" id="drClose">×</button>
  </div>
  <div class="dr-body" id="drBody"></div>
</aside>

<div class="regen-modal" id="regenModal">
  <div class="regen-card">
    <h3>Пересобрать гипотезы</h3>
    <p>Агент проанализирует только новые материалы и новости — те, что ещё не попадали в предыдущие прогоны. Существующие гипотезы сохранятся, к ним добавятся новые.</p>
    <div class="rg-steps" id="rgSteps" style="display:none">
      <div class="rg-step" data-k="queued"><span class="dot2"></span>В очереди</div>
      <div class="rg-step" data-k="running"><span class="dot2"></span>Сбор материалов</div>
      <div class="rg-step" data-k="agent"><span class="dot2"></span>Анализ агентом</div>
      <div class="rg-step" data-k="storing"><span class="dot2"></span>Сохранение и валидация</div>
    </div>
    <div id="rgMsg"></div>
    <div class="rg-foot">
      <button class="btn btn-ghost" id="rgClose">Закрыть</button>
      <button class="btn" id="rgStart">Запустить</button>
    </div>
  </div>
</div>

<script>
/* Phase B0: theme persistence */
(function(){
  const KEY='iw_theme';
  function apply(t){
    document.documentElement.setAttribute('data-theme', t);
    if(document.body) document.body.setAttribute('data-theme', t);
    const ico = document.getElementById('iwThemeIco');
    if(ico) ico.innerHTML = (t === 'dark')
      ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
      : '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>';
  }
  let t = 'light';
  try { t = localStorage.getItem(KEY) || 'light'; } catch(e){}
  apply(t);
  document.addEventListener('DOMContentLoaded', function(){
    apply(t);
    const btn = document.getElementById('iwThemeToggle');
    if(btn) btn.addEventListener('click', function(){
      const cur = document.documentElement.getAttribute('data-theme') || 'light';
      const next = (cur === 'dark') ? 'light' : 'dark';
      try { localStorage.setItem(KEY, next); } catch(e){}
      apply(next);
    });
  });
})();
/* Phase B1: filter-bar wiring */
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const iw = document.getElementById('iwSearch');
    if(iw){
      iw.addEventListener('input', function(){
        const q = (iw.value||"").toLowerCase().trim();
        const items = document.querySelectorAll('.h-card,[data-hyp-id],.hyp-row,.insight-card');
        if(!items.length) return;
        items.forEach(el => {
          const txt = (el.textContent||"").toLowerCase();
          el.style.display = (!q || txt.includes(q)) ? "" : "none";
        });
      });
    }
    document.addEventListener('keydown', function(e){
      if(e.key === '/' && document.activeElement && 
         !(/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))){
        e.preventDefault();
        if(iw){ iw.focus(); iw.select(); }
      }
    });
    const btnRegen = document.getElementById('iwBtnRegen');
    if(btnRegen) btnRegen.addEventListener('click', function(){
      const ex = document.querySelector('[data-action="regenerate"], #regenBtn, .regen-btn, button[onclick*="regen"]');
      if(ex){ ex.click(); return; }
      btnRegen.disabled = true; btnRegen.querySelector('.iw-fbar-btn-lbl').textContent = 'Запуск…';
      fetch('/kb/insights/regenerate', {method:'POST'}).then(r=>r.json()).then(d=>{
        btnRegen.querySelector('.iw-fbar-btn-lbl').textContent = d.job_id ? 'В работе' : 'Готово';
        setTimeout(()=>{btnRegen.disabled=false;btnRegen.querySelector(".iw-fbar-btn-lbl").textContent="Пересобрать";}, 4000);
      }).catch(()=>{
        btnRegen.querySelector(".iw-fbar-btn-lbl").textContent="Ошибка";
        setTimeout(()=>{btnRegen.disabled=false;btnRegen.querySelector(".iw-fbar-btn-lbl").textContent="Пересобрать";}, 3000);
      });
    });
  });
})();
const me = { user: '__USER__', canUpload: __CANUPLOAD__, canModerate: __CANMOD__ };
let state = { viewMode: 'asis',  hypotheses: [], edges: [], filter: 'all', category: '', source: '', last_run: null, can_regenerate: false, category_counts: {}, source_counts: {} };

function escapeHtml(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function fmtDate(iso){
  if(!iso) return '—';
  const d = new Date(iso); if(isNaN(d)) return iso.slice(0,10);
  const t = new Date(); t.setHours(0,0,0,0);
  const dd = new Date(d); dd.setHours(0,0,0,0);
  const diff = Math.round((t - dd) / 86400000);
  if(diff === 0) return 'сегодня в ' + d.toTimeString().slice(0,5);
  if(diff === 1) return 'вчера';
  const m = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
  return d.getDate() + ' ' + m[d.getMonth()];
}

function applyFilter(hyps){
  let out = hyps;
  // AS IS / Архив split
  const vm = (state && state.viewMode) || 'asis';
  if(vm === 'archive'){
    out = out.filter(h => (h.lifecycle_status || 'synthesized') === 'archived');
  } else {
    out = out.filter(h => (h.lifecycle_status || 'synthesized') !== 'archived');
  }
  if(state.category) out = out.filter(h => h.category === state.category);
  if(state.source) out = out.filter(h => (h.source_kind || 'material') === state.source);
  if(state.filter === 'validated') out = out.filter(h => h.validated);
  else if(state.filter === 'single') out = out.filter(h => h.evidence_count <= 1);
  return out;
}

async function load(){
  const r = await fetch('/kb/insights/data', { cache: 'no-store' });
  if(!r.ok){ document.getElementById('graphEmpty').style.display='flex'; document.getElementById('graphEmpty').textContent='Ошибка загрузки'; return; }
  const d = await r.json();
  state.hypotheses = d.hypotheses || [];
  state.edges = d.edges || [];
  state.last_run = d.last_run;
  state.can_regenerate = !!d.can_regenerate;
  state.category_counts = d.category_counts || {};
  state.source_counts = d.source_counts || {};
  if(state.can_regenerate) document.getElementById('regenBtn').style.display='';
  // populate category counts
  document.querySelectorAll('[data-cc]').forEach(el => {
    const n = state.category_counts[el.dataset.cc] || 0;
    el.textContent = n;
  });
  document.querySelectorAll('[data-sc]').forEach(el => {
    const n = state.source_counts[el.dataset.sc] || 0;
    el.textContent = n;
  });
  // apply ?category= URL param
  const p = new URLSearchParams(location.search);
  const cat = p.get('category');
  if(cat){
    state.category = cat;
    document.querySelectorAll('#catRow button').forEach(b => b.classList.toggle('active', (b.dataset.c || '') === cat));
  }
  render();
  // optional focus hyp via ?focus=<id>
  const focus = p.get('focus');
  if(focus && state.hypotheses.some(h => h.id === focus)) openHyp(focus);
}


// AS IS / Архив toggle handler — updates state.viewMode and re-renders
function _iwVModeUpdateCounts(){
  const all = (state && state.hypotheses) || [];
  const asisN = all.filter(h => (h.lifecycle_status || 'synthesized') !== 'archived').length;
  const archN = all.filter(h => (h.lifecycle_status || 'synthesized') === 'archived').length;
  const a = document.getElementById('vmCntAsis');
  const r = document.getElementById('vmCntArch');
  if(a) a.textContent = String(asisN);
  if(r) r.textContent = String(archN);
}
function _iwVModeBind(){
  const wrap = document.getElementById('iwVMode');
  if(!wrap) return;
  wrap.querySelectorAll('button[data-vmode]').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.vmode;
      if(!mode) return;
      state.viewMode = mode;
      try { _iwResetView(); } catch(_){}
      wrap.querySelectorAll('button[data-vmode]').forEach(x => x.classList.toggle('active', x === btn));
      // Re-render everything
      try { render(); } catch(_){}
    });
  });
}
document.addEventListener('DOMContentLoaded', _iwVModeBind);

function render(){
  const all = state.hypotheses;
  const filtered = applyFilter(all);
  try { _iwVModeUpdateCounts(); } catch(_){}
  // stats
  const v = all.filter(h => h.validated).length;
  const single = all.filter(h => h.evidence_count <= 1).length;
  const statsEl = document.getElementById('stats');
  let statsHtml = '<span><b>' + all.length + '</b> всего</span>';
  statsHtml += '<span><b>' + v + '</b> валидированных</span>';
  statsHtml += '<span><b>' + single + '</b> одноисточных</span>';
  if(state.last_run && state.last_run.finished_at){
    statsHtml += '<span style="opacity:.7">Последний прогон: ' + fmtDate(state.last_run.finished_at) + '</span>';
  }
  statsEl.innerHTML = statsHtml;
  renderGraph(filtered);
  renderList(filtered);
  document.getElementById('listLabel').textContent =
    state.filter === 'validated' ? 'Валидированные гипотезы' :
    state.filter === 'single' ? 'Гипотезы с одним источником' : 'Все гипотезы';
}

/* ---- Interactive graph: Cytoscape.js + fcose ---- */
const CATEGORY_COLORS = {
  'ПУ/подписки': { base:'#0e8a2e', soft:'#d4eeda', border:'#0a6e23' },
  'Travel':      { base:'#0b6fa8', soft:'#cee5f2', border:'#085481' },
  'UX/UI':       { base:'#6a22a8', soft:'#e1d3ef', border:'#4e1a7a' }
};
function categoryColor(cat){
  return CATEGORY_COLORS[cat] || { base:'#7a6a52', soft:'#e6d8be', border:'#5d503e' };
}
function truncate(s, n){ s = s || ''; return s.length > n ? s.slice(0, n-1) + '…' : s; }

let cy = null;                 // current cytoscape instance
let currentLayout = 'fcose';   // active layout id
const _hypById = {};           // id -> hypothesis (for hover panel)

if (typeof cytoscape !== 'undefined' && typeof window !== 'undefined' && window.cytoscapeFcose){
  try { cytoscape.use(window.cytoscapeFcose); } catch(_){ /* already registered */ }
}

function layoutOptions(name){
  if (name === 'fcose') return {
    name: 'fcose', animate: true, animationDuration: 700,
    quality: 'default', randomize: true, fit: true, padding: 60,
    idealEdgeLength: 170, nodeSeparation: 130, tile: true,
    uniformNodeDimensions: false, nodeRepulsion: 9500,
    packComponents: true, gravity: 0.18, numIter: 3000,
    nestingFactor: 0.5, edgeElasticity: 0.45
  };
  if (name === 'concentric') return {
    name: 'concentric', animate: true, animationDuration: 500, fit: true, padding: 40,
    concentric: (n) => {
      if(n.data('isParent')) return -1;
      return (n.data('validated') ? 100 : 0) + (n.data('confidence') || 0) * 40 + Math.min(20, (n.data('evidence') || 0) * 2);
    },
    levelWidth: () => 1, spacingFactor: 1.35, minNodeSpacing: 28
  };
  if (name === 'circle') return {
    name: 'circle', animate: true, animationDuration: 500, fit: true, padding: 40,
    spacingFactor: 1.1
  };
  return { name: 'cose', animate: true, fit: true };
}

function renderDetail(h){
  const el = document.getElementById('gDetail');
  if(!el) return;
  if(!h){ el.hidden = true; el.innerHTML = ''; return; }
  const sk = h.source_kind || 'material';
  const skLabel = sk === 'news' ? 'новости' : (sk === 'mixed' ? 'смешанные' : 'материалы');
  const confPct = Math.round((h.confidence || 0) * 100);
  el.innerHTML =
    '<div class="gd-kicker">' +
      (h.category ? '<span class="gd-cat">' + escapeHtml(h.category) + '</span>' : '') +
      '<span class="gd-src gd-src-' + sk + '">' + skLabel + '</span>' +
      (h.is_new ? '<span class="gd-new">new</span>' : '') +
    '</div>' +
    '<div class="gd-ttl">' + escapeHtml(truncate(h.statement, 180)) + '</div>' +
    '<div class="gd-row">' +
      '<span class="gd-conf"><span class="gd-conf-bar"><span class="gd-conf-fill" style="width:' + confPct + '%"></span></span>' + confPct + '%</span>' +
      '<span>' + h.evidence_count + ' источ.</span>' +
      (h.validated ? '<span class="gd-v">✓ валидна</span>' : '') +
    '</div>' +
    '<div class="gd-cta">Клик — открыть детали →</div>';
  el.hidden = false;
}

function renderGraph(hyps){
  // Perf: large sets are slow with Cytoscape layout. Skip until user requests.
  const __THRESHOLD = 50;
  if(Array.isArray(hyps) && hyps.length > __THRESHOLD && !state.graphForced){
    const wrap = document.getElementById('graphWrap');
    const empty = document.getElementById('graphEmpty');
    if(empty){
      empty.style.display = 'flex';
      empty.innerHTML = '';
      const msg = document.createElement('div');
      msg.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:12px;padding:20px;text-align:center';
      msg.innerHTML = '<div style="color:var(--muted);font-size:14px;line-height:1.4">' +
        hyps.length + ' гипотез — слишком много для быстрого графа.<br>' +
        '<span style="font-size:12px;opacity:.7">Layout займёт несколько секунд.</span></div>';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'iw-fbar-btn';
      btn.style.cssText = 'min-width:200px;justify-content:center';
      btn.textContent = 'Всё равно построить граф';
      btn.addEventListener('click', () => {
        state.graphForced = true;
        try { render(); } catch(_){}
      });
      msg.appendChild(btn);
      empty.appendChild(msg);
    }
    if(wrap){ wrap.style.visibility = 'hidden'; }
    if(typeof cy !== 'undefined' && cy){ try { cy.destroy(); } catch(_){} cy = null; }
    return;
  }
  // Make sure graphWrap is visible (was hidden by guard above when threshold-skipped)
  const __wrap = document.getElementById('graphWrap');
  if(__wrap){ __wrap.style.visibility = ''; }
  const wrap = document.getElementById('graphWrap');
  const emp = document.getElementById('graphEmpty');
  const statEl = document.getElementById('gStat');
  if(cy){ try{ cy.destroy(); }catch(_){} cy = null; }
  wrap.innerHTML = '';
  renderDetail(null);
  if(!hyps.length){
    emp.style.display = 'flex';
    emp.innerHTML = !state.hypotheses.length
      ? '<h3 style="color:var(--text);margin:0 0 4px">Гипотез ещё нет</h3><p>' + (state.can_regenerate ? 'Нажмите «Пересобрать», чтобы агент проанализировал материалы и сформировал гипотезы.' : 'Попросите коллегу с правами пересобрать гипотезы.') + '</p>'
      : '<p>По выбранному фильтру нет гипотез.</p>';
    if(statEl) statEl.textContent = '0 нод · 0 связей';
    return;
  }
  emp.style.display = 'none';

  if(typeof cytoscape === 'undefined'){
    wrap.innerHTML = '<div style="padding:40px;text-align:center;color:var(--muted)">Библиотека графа не загрузилась. Проверьте подключение к сети.</div>';
    return;
  }

  for(const k in _hypById) delete _hypById[k];
  hyps.forEach(h => { _hypById[h.id] = h; });

  const idSet = new Set(hyps.map(h => h.id));
  const categories = {};
  hyps.forEach(h => { if(h.category) categories[h.category] = (categories[h.category] || 0) + 1; });

  const elements = [];
  Object.keys(categories).forEach(cat => {
    elements.push({
      group:'nodes',
      data:{ id:'cat:' + cat, label:cat + ' · ' + categories[cat], isParent:true, catName:cat },
      classes:'cat-parent'
    });
  });
  hyps.forEach(h => {
    const c = categoryColor(h.category);
    const sk = h.source_kind || 'material';
    elements.push({
      group: 'nodes',
      data: {
        id: h.id,
        label: truncate(h.statement, 90),
        category: h.category || '',
        parent: h.category ? ('cat:' + h.category) : undefined,
        evidence: h.evidence_count,
        confidence: h.confidence,
        validated: !!h.validated,
        isNew: !!h.is_new,
        sourceKind: sk,
        color: c.base, soft: c.soft, border: c.border,
        // small nudge for higher-evidence cards
        padTop: 10 + Math.min(6, Math.sqrt(Math.max(1, h.evidence_count)) * 2)
      },
      classes: (h.validated ? 'n-valid' : 'n-unvalid') + (h.is_new ? ' n-new' : '')
    });
  });
  (state.edges || []).forEach(e => {
    if(idSet.has(e.a) && idSet.has(e.b)){
      elements.push({ group:'edges', data:{ id: e.a + '__' + e.b, source: e.a, target: e.b, weight: e.w } });
    }
  });

  cy = cytoscape({
    container: wrap,
    elements: elements,
    minZoom: 0.3, maxZoom: 3, wheelSensitivity: 0.28,
    boxSelectionEnabled: false, selectionType: 'single',
    style: [
      /* ── Category-cluster compound parent: soft tinted zone ─────────── */
      { selector: 'node.cat-parent', style: {
        'label': 'data(label)',
        'text-valign': 'top', 'text-halign': 'left',
        'text-margin-y': -8, 'text-margin-x': 14,
        'font-size': 11, 'font-weight': 800,
        'color': '#475569',
        'text-transform': 'uppercase', 'letter-spacing': 1.4,
        'background-color': '#ffffff',
        'background-opacity': 0.55,
        'border-width': 1, 'border-style': 'dashed', 'border-color': '#cbd2d9',
        'shape': 'round-rectangle', 'corner-radius': '20',
        'padding': 28,
      }},
      /* ── Hypothesis card: text INSIDE rounded card, white bg, color border ─ */
      { selector: 'node[!isParent]', style: {
        'shape': 'round-rectangle',
        'corner-radius': '14',
        'background-color': '#ffffff',
        'background-opacity': 1,
        'border-width': 2,
        'border-color': 'data(color)',
        'border-opacity': 0.92,
        'label': 'data(label)',
        'font-size': 11.5,
        'font-weight': 600,
        'font-family': '-apple-system, BlinkMacSystemFont, "SB Sans Text", "Segoe UI", Roboto, Arial, sans-serif',
        'color': '#1b1b1b',
        'text-valign': 'center', 'text-halign': 'center',
        'text-wrap': 'wrap',
        'text-max-width': '180px',
        'line-height': 1.3,
        'width': 'label', 'height': 'label',
        'padding-left': 16, 'padding-right': 16,
        'padding-top': 'data(padTop)', 'padding-bottom': 'data(padTop)',
        'shadow-blur': 8, 'shadow-color': '#0f172a',
        'shadow-opacity': 0.08, 'shadow-offset-x': 0, 'shadow-offset-y': 2,
        'transition-property': 'border-color border-width background-color opacity shadow-opacity color',
        'transition-duration': '180ms'
      }},
      /* ── Validated: solid colored fill, white text, no shadow change ── */
      { selector: 'node.n-valid', style: {
        'background-color': 'data(color)',
        'background-opacity': 0.96,
        'border-color': 'data(border)',
        'border-width': 0,
        'color': '#ffffff',
        'shadow-opacity': 0.18
      }},
      /* ── Unvalidated: dashed border to signal "draft" ─────────────── */
      { selector: 'node.n-unvalid', style: {
        'border-style': 'dashed',
        'border-width': 1.8
      }},
      /* ── New: orange halo + accent ring ───────────────────────────── */
      { selector: 'node.n-new', style: {
        'overlay-color': '#fb923c',
        'overlay-opacity': 0.18,
        'overlay-padding': 6,
        'border-color': '#ea580c',
        'border-width': 2.5
      }},
      /* ── Edges: thin neutral lines, weight = thickness ────────────── */
      { selector: 'edge', style: {
        'curve-style': 'bezier',
        'control-point-step-size': 40,
        'width': 'mapData(weight, 1, 6, 1.2, 4)',
        'line-color': '#94a3b8',
        'line-style': 'solid',
        'opacity': 0.42,
        'target-arrow-shape': 'none',
        'transition-property': 'line-color opacity width',
        'transition-duration': '160ms'
      }},
      /* ── Faded: dim siblings on hover ─────────────────────────────── */
      { selector: '.faded', style: { 'opacity': 0.16, 'text-opacity': 0.4 } },
      /* ── Hover highlight: sharp green glow + thicker border ───────── */
      { selector: 'node.hl', style: {
        'border-color': '#0e8a2e',
        'border-width': 3.2,
        'shadow-opacity': 0.32, 'shadow-blur': 18, 'shadow-color': '#0e8a2e',
        'overlay-color': '#0e8a2e', 'overlay-opacity': 0.06, 'overlay-padding': 4,
        'z-index': 10
      }},
      { selector: 'edge.hl', style: {
        'line-color': '#0e8a2e',
        'width': 'mapData(weight, 1, 6, 2.2, 5.5)',
        'opacity': 0.92,
        'z-index': 9
      }},
      /* ── Search match: orange ring, brought to front ──────────────── */
      { selector: 'node.search-hit', style: {
        'border-color': '#d14a00',
        'border-width': 3.6,
        'shadow-color': '#d14a00', 'shadow-opacity': 0.32, 'shadow-blur': 22,
        'z-index': 11
      }}
    ],
    layout: layoutOptions(currentLayout)
  });

  cy.on('tap', 'node', (evt) => {
    const n = evt.target;
    if(n.data('isParent')) return;
    openHyp(n.id());
  });
  cy.on('mouseover', 'node', (evt) => {
    const n = evt.target;
    if(n.data('isParent')) return;
    const nb = n.closedNeighborhood();
    cy.elements().difference(nb).addClass('faded');
    n.addClass('hl');
    nb.edges().addClass('hl');
    renderDetail(_hypById[n.id()]);
  });
  cy.on('mouseout', 'node', () => {
    cy.elements().removeClass('faded hl');
    renderDetail(null);
  });
  cy.on('tap', (evt) => { if(evt.target === cy) renderDetail(null); });

  if(statEl){
    const edgeN = cy.edges().length;
    statEl.textContent = hyps.length + ' нод · ' + edgeN + ' связей';
  }
}

/* graph toolbar: layout + search + zoom */
(function wireGraphToolbar(){
  const layRow = document.getElementById('gLayoutRow');
  const search = document.getElementById('gSearch');
  const zIn = document.getElementById('gZoomIn');
  const zOut = document.getElementById('gZoomOut');
  const zFit = document.getElementById('gFit');
  if(layRow) layRow.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if(!b) return;
    layRow.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
    currentLayout = b.dataset.lo;
    if(cy){ cy.layout(layoutOptions(currentLayout)).run(); }
  });
  if(search) search.addEventListener('input', () => {
    if(!cy) return;
    const q = (search.value || '').trim().toLowerCase();
    cy.elements().removeClass('faded search-hit');
    if(!q) return;
    const hits = cy.nodes('[!isParent]').filter(n => {
      const h = _hypById[n.id()];
      return h && ((h.statement || '') + ' ' + (h.rationale || '')).toLowerCase().indexOf(q) >= 0;
    });
    if(hits.length === 0){ cy.nodes('[!isParent]').addClass('faded'); return; }
    hits.addClass('search-hit');
    cy.elements().difference(hits.closedNeighborhood()).addClass('faded');
  });
  if(zIn)  zIn.addEventListener('click',  () => { if(cy) cy.animate({ zoom: cy.zoom() * 1.2 }, { duration: 220 }); });
  if(zOut) zOut.addEventListener('click', () => { if(cy) cy.animate({ zoom: cy.zoom() / 1.2 }, { duration: 220 }); });
  if(zFit) zFit.addEventListener('click', () => { if(cy) cy.animate({ fit: { padding: 40 } }, { duration: 420 }); });

  // Fullscreen toggle
  const zFull = document.getElementById('gFullscreen');
  function exitFullscreen() {
    const card = document.querySelector('.graph-card.is-fullscreen');
    if(!card) return;
    card.classList.remove('is-fullscreen');
    document.body.classList.remove('graph-fullscreen');
    if(zFull) { zFull.classList.remove('is-active'); zFull.title = 'На весь экран (Esc — выйти)'; }
    setTimeout(() => { if(cy) { try { cy.resize(); cy.fit(undefined, 40); } catch(_){} } }, 120);
  }
  function enterFullscreen() {
    const card = document.querySelector('.graph-card');
    if(!card) return;
    card.classList.add('is-fullscreen');
    document.body.classList.add('graph-fullscreen');
    if(zFull) { zFull.classList.add('is-active'); zFull.title = 'Свернуть (Esc)'; }
    setTimeout(() => { if(cy) { try { cy.resize(); cy.fit(undefined, 40); } catch(_){} } }, 220);
  }
  if(zFull) zFull.addEventListener('click', () => {
    const card = document.querySelector('.graph-card');
    if(!card) return;
    if(card.classList.contains('is-fullscreen')) exitFullscreen();
    else enterFullscreen();
  });
  document.addEventListener('keydown', (e) => {
    if(e.key === 'Escape' && document.body.classList.contains('graph-fullscreen')) {
      exitFullscreen();
    }
  });
  // Resize observer — если окно меняется в fullscreen, ресайз cytoscape
  if(typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => { if(cy && document.body.classList.contains('graph-fullscreen')) try { cy.resize(); } catch(_){} });
    const gw = document.getElementById('graphWrap');
    if(gw) ro.observe(gw);
  }
})();


// Reset paging/forced-graph state on filter change — keeps performance predictable.
function _iwResetView(){
  if(state){
    state.listLimit = _LIST_PAGE_SIZE;
    state.graphForced = false;
  }
}
const _LIST_PAGE_SIZE = 30;
function _renderHCard(h){
  const el = document.createElement('div');
  el.className = 'hcard' + (h.is_new ? ' is-new' : '');
  const bits = [];
  if(h.is_new) bits.push('<span class="badge new">new</span>');
  if(h.category) bits.push('<span class="badge cat">' + escapeHtml(h.category) + '</span>');
  const sk = h.source_kind || 'material';
  const skLabel = sk === 'news' ? 'новости' : (sk === 'mixed' ? 'смешанные' : 'материалы');
  bits.push('<span class="badge src-' + sk + '">' + skLabel + '</span>');
  bits.push('<span class="badge ev">' + h.evidence_count + ' источн.</span>');
  if(h.validated) bits.push('<span class="badge v-true">✓ валидна</span>');
  bits.push('<span class="conf-bar"><i style="width:' + Math.round(h.confidence*100) + '%"></i></span>');
  el.innerHTML =
    '<div class="htitle">' + escapeHtml(h.statement) + '</div>' +
    '<div class="hmeta">' + bits.join(' ') + '</div>';
  el.addEventListener('click', () => openHyp(h.id));
  return el;
}
function renderList(hyps){
  const root = document.getElementById('hypList');
  root.innerHTML = '';
  if(!hyps.length){
    root.innerHTML = '<div style="color:var(--muted);padding:20px;text-align:center">Гипотез в выбранном фильтре нет.</div>';
    return;
  }
  const limit = state.listLimit || _LIST_PAGE_SIZE;
  const total = hyps.length;
  const visible = Math.min(limit, total);
  for(let i = 0; i < visible; i++){
    root.appendChild(_renderHCard(hyps[i]));
  }
  if(visible < total){
    const remaining = total - visible;
    const moreWrap = document.createElement('div');
    moreWrap.style.cssText = 'padding:14px 0 4px 0;text-align:center';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'iw-fbar-btn';
    btn.style.cssText = 'min-width:200px;justify-content:center';
    btn.textContent = 'Показать ещё ' + Math.min(_LIST_PAGE_SIZE, remaining) + ' (всего ' + remaining + ')';
    btn.addEventListener('click', () => {
      state.listLimit = (state.listLimit || _LIST_PAGE_SIZE) + _LIST_PAGE_SIZE;
      try { render(); } catch(_){}
    });
    moreWrap.appendChild(btn);
    root.appendChild(moreWrap);
  }
}

/* filter chips */
document.getElementById('filterRow').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if(!b) return;
  document.querySelectorAll('#filterRow button').forEach(x => x.classList.toggle('active', x === b));
  _iwResetView();
  state.filter = b.dataset.f;
  render();
});
document.getElementById('catRow').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if(!b) return;
  document.querySelectorAll('#catRow button').forEach(x => x.classList.toggle('active', x === b));
  _iwResetView();
  state.category = b.dataset.c || '';
  render();
});
document.getElementById('srcRow').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if(!b) return;
  document.querySelectorAll('#srcRow button').forEach(x => x.classList.toggle('active', x === b));
  _iwResetView();
  state.source = b.dataset.s || '';
  render();
});

/* drawer */
const drBg = document.getElementById('drBg');
const drawer = document.getElementById('drawer');
document.getElementById('drClose').addEventListener('click', closeDrawer);
drBg.addEventListener('click', closeDrawer);
document.addEventListener('keydown', e => { if(e.key === 'Escape' && drawer.classList.contains('open')) closeDrawer(); });
function closeDrawer(){ drawer.classList.remove('open'); drBg.classList.remove('open'); drawer.setAttribute('aria-hidden','true'); }

async function openHyp(id){
  drawer.classList.add('open'); drBg.classList.add('open');
  drawer.setAttribute('aria-hidden','false');
  const body = document.getElementById('drBody');
  const title = document.getElementById('drTitle');
  title.textContent = 'Загрузка…'; body.innerHTML = '';
  try {
    const r = await fetch('/kb/insights/' + encodeURIComponent(id));
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const h = await r.json();
    title.textContent = h.statement;
    const confPct = Math.round(h.confidence * 100);
    const badges = [
      (h.is_new ? '<span class="badge new">new</span>' : ''),
      (h.category ? '<span class="badge cat">' + escapeHtml(h.category) + '</span>' : ''),
      '<span class="badge ev">' + h.evidence_count + ' источн.</span>',
      (h.validated ? '<span class="badge v-true">✓ валидирована (>90%)</span>' : ''),
    ].filter(Boolean).join(' ');
    const addedLine = h.created_at
      ? '<div style="font-size:12px;color:var(--muted);margin-top:8px">Добавлено: ' + fmtDate(h.created_at) + '</div>'
      : '';
    const srcHtml = h.sources.map(s => {
      const isNews = s.kind === 'news' || s.source_type === 'news';
      const docIco = isNews ? 'NEWS' :
        (s.source_type === 'url' ? 'URL' : (s.source_type === 'text' ? 'NOTE' : (s.file_ext || '.').replace('.','').toUpperCase() || 'DOC'));
      const openHref = isNews ? (s.source_ref || '#') :
        (s.source_type === 'url' ? s.source_ref :
         s.source_type === 'file' ? '/kb/' + encodeURIComponent(s.doc_id) + '/file' :
         '/kb#' + s.doc_id);
      const openLabel = isNews ? 'Открыть новость ↗' :
        (s.source_type === 'url' ? 'Открыть источник ↗' :
         s.source_type === 'file' ? 'Скачать оригинал' :
         'Открыть в Инсайт-хабе');
      const qLevel = isNews ? 'amber' : s.quality.level;
      const qLabel = isNews ? 'новость' : (qLevel === 'green' ? 'ок' : qLevel === 'yellow' ? 'проверить' : 'слабый');
      const qDesc = (s.quality.reasons && s.quality.reasons.length) ? s.quality.reasons.join(', ') : (qLevel === 'green' ? 'хорошее качество' : '');
      const newsMeta = isNews && s.news_source
        ? '<div style="font-size:11px;color:var(--muted);margin-top:-4px;margin-bottom:6px">' + escapeHtml(s.news_source) + (s.origin ? ' · ' + (s.origin === 'packages' ? 'Банкинг' : 'Travel') : '') + '</div>'
        : '';
      return '<div class="src ' + (s.is_origin ? 'origin' : '') + '">' +
        '<div class="src-head">' +
          '<div class="src-ico">' + docIco + '</div>' +
          '<div class="src-title">' + escapeHtml(s.title) + '</div>' +
          '<div class="quality ' + qLevel + '" title="' + escapeHtml(qDesc) + '"><span class="qdot"></span>' + qLabel + '</div>' +
        '</div>' +
        newsMeta +
        (s.excerpt ? '<div class="excerpt-wrap"><div class="excerpt-label">💡 Цитата, породившая гипотезу</div><div class="excerpt"><mark>« ' + escapeHtml(s.excerpt) + ' »</mark></div></div>' : '') +
        '<div class="src-actions"><a href="' + escapeHtml(openHref) + '" target="' + (s.source_type === 'text' ? '_self' : '_blank') + '" rel="noopener">' + openLabel + '</a></div>' +
        '</div>';
    }).join('');
    body.innerHTML =
      '<div class="section"><div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">' + badges + '</div>' +
      '<div class="conf-row"><span style="font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em">Уверенность</span><div class="bar"><i style="width:' + confPct + '%"></i></div><span class="pct">' + confPct + '%</span></div>' +
      addedLine + '</div>' +
      '<div class="section"><h4>Почему это гипотеза</h4><div class="rationale">' + escapeHtml(h.rationale) + '</div></div>' +
      '<div class="section"><h4>Источники (' + h.sources.length + ')</h4>' + (srcHtml || '<div style="color:var(--muted)">Источники не найдены</div>') + '</div>';
  } catch(e){
    body.innerHTML = '<div style="color:var(--danger);padding:12px">Ошибка: ' + escapeHtml(String(e)) + '</div>';
  }
}

/* regen flow */
const regenModal = document.getElementById('regenModal');
document.getElementById('regenBtn').addEventListener('click', () => {
  regenModal.classList.add('open');
  document.getElementById('rgSteps').style.display = 'none';
  document.getElementById('rgMsg').innerHTML = '';
  document.getElementById('rgStart').disabled = false;
  document.getElementById('rgStart').textContent = 'Запустить';
});
document.getElementById('rgClose').addEventListener('click', () => regenModal.classList.remove('open'));

let pollTimer = null;
document.getElementById('rgStart').addEventListener('click', async () => {
  const btn = document.getElementById('rgStart');
  const msg = document.getElementById('rgMsg');
  btn.disabled = true; btn.textContent = 'Запуск…';
  msg.innerHTML = '';
  document.getElementById('rgSteps').style.display = '';
  setStep('queued');
  try {
    const r = await fetch('/kb/insights/regenerate', { method: 'POST' });
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail || 'HTTP ' + r.status);
    pollJob(d.job_id);
  } catch(e){
    msg.innerHTML = '<div class="rg-err">' + escapeHtml(String(e.message || e)) + '</div>';
    btn.disabled = false; btn.textContent = 'Запустить';
  }
});

function setStep(k){
  const keys = ['queued','running','agent','storing'];
  const i = keys.indexOf(k);
  document.querySelectorAll('.rg-step').forEach((el, idx) => {
    el.classList.remove('active','done');
    if(idx < i) el.classList.add('done');
    else if(idx === i) el.classList.add('active');
  });
}

function pollJob(jobId){
  if(pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch('/kb/insights/regenerate/status/' + encodeURIComponent(jobId));
      const d = await r.json();
      setStep(d.status);
      if(d.status === 'done'){
        clearInterval(pollTimer); pollTimer = null;
        document.querySelectorAll('.rg-step').forEach(el => el.classList.add('done'));
        const res = d.result || {};
        const parts = [];
        if(res.new_materials != null || res.new_news != null){
          const bits = [];
          if(res.new_materials) bits.push(res.new_materials + ' материалов');
          if(res.new_news) bits.push(res.new_news + ' новостей');
          parts.push('Проанализировано нового: ' + (bits.join(', ') || '0'));
        } else {
          parts.push('Проанализировано: ' + (res.docs || 0));
        }
        parts.push((res.proposed || 0) + ' новых гипотез, ' + (res.validated || 0) + ' валидированных');
        document.getElementById('rgMsg').innerHTML =
          '<div class="rg-ok">' + parts.join(' · ') + '</div>';
        document.getElementById('rgStart').textContent = 'Закрыть';
        document.getElementById('rgStart').disabled = false;
        document.getElementById('rgStart').onclick = () => {
          regenModal.classList.remove('open');
          document.getElementById('rgStart').onclick = null;
          location.reload();
        };
      } else if(d.status === 'error'){
        clearInterval(pollTimer); pollTimer = null;
        document.getElementById('rgMsg').innerHTML = '<div class="rg-err">' + escapeHtml(d.error || 'Ошибка') + '</div>';
        document.getElementById('rgStart').disabled = false;
        document.getElementById('rgStart').textContent = 'Попробовать снова';
      }
    } catch(e){ /* keep polling */ }
  }, 2500);
}

load();
window.addEventListener('resize', () => { render(); });
/* Phase B2: rail wiring */
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const rail = document.querySelector('.iw-rail');
    if(!rail) return;
    rail.addEventListener('click', function(e){
      const it = e.target.closest('.iw-rail-item');
      if(!it) return; if(it.tagName === 'A') return; /* let anchor links navigate */
      const grp = it.closest('[data-rail]');
      if(grp){
        grp.querySelectorAll('.iw-rail-item').forEach(x => x.classList.toggle('active', x === it));
        const kind = grp.dataset.rail;
        const c = it.dataset.c, f = it.dataset.f, s = it.dataset.s;
        if(kind === 'cat'){
          const target = document.querySelector('#catRow button[data-c="' + (c||'') + '"]');
          if(target) target.click();
        } else if(kind === 'filter'){
          const target = document.querySelector('#filterRow button[data-f="' + (f||'all') + '"]');
          if(target) target.click();
        } else if(kind === 'src'){
          const target = document.querySelector('#srcRow button[data-s="' + (s||'') + '"]');
          if(target) target.click();
        }
      } else {
        const q = it.dataset.quick;
        const iw = document.getElementById('iwSearch');
        if(q && iw){
          if(q === 'overdue') iw.value = 'overdue';
          else if(q === 'new72') iw.value = 'new';
          iw.dispatchEvent(new Event('input', {bubbles:true}));
        }
      }
    });
    function syncCounts(){
      const st = window.state; if(!st) return;
      const cc = st.category_counts || {};
      document.querySelectorAll('[data-cnt-cat]').forEach(el => {
        const k = el.dataset.cntCat || '';
        let n = 0; if(k === '') Object.values(cc).forEach(v => n += (v||0));
        else n = (cc[k]||0); el.textContent = n ? String(n) : '';
      });
      const sc = st.source_counts || {};
      document.querySelectorAll('[data-cnt-src]').forEach(el => {
        const k = el.dataset.cntSrc || '';
        let n = 0; if(k === '') Object.values(sc).forEach(v => n += (v||0));
        else n = (sc[k]||0); el.textContent = n ? String(n) : '';
      });
    }
    document.addEventListener('iw:state-updated', syncCounts);
    setInterval(syncCounts, 1500); /* fallback poll until existing renderer dispatches event */
  });
})();

/* Phase B3: universal Add modal */
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const bg = document.getElementById('iwAddModalBg');
    if(!bg) return;
    const closeEls = [document.getElementById('iwModalClose'), document.getElementById('iwModalCancel'), bg];
    const tabs = document.querySelectorAll('.iw-modal-tab');
    const panes = document.querySelectorAll('.iw-modal-pane');
    const status = document.getElementById('iwModalStatus');
    const submit = document.getElementById('iwModalSubmit');
    const fileInp = document.getElementById('iwModalFile');
    const drop = document.getElementById('iwModalDrop');
    const pickedRow = document.getElementById('iwModalPicked');
    const pickedName = document.getElementById('iwModalPickedName');
    const pickedX = document.getElementById('iwModalPickedX');
    let mode = 'file';
    let pickedFile = null;
    function setMode(m){
      mode = m;
      tabs.forEach(t => t.classList.toggle('active', t.dataset.mode === m));
      panes.forEach(p => p.style.display = (p.dataset.mode === m) ? '' : 'none');
      setStatus('');
    }
    function setStatus(text, kind){
      status.className = 'iw-modal-status' + (kind ? ' ' + kind : '');
      status.textContent = text || '';
    }
    function open(){
      bg.classList.add('open');
      setStatus('');
      setTimeout(()=>{
        const firstInp = bg.querySelector('.iw-modal-pane:not([style*="display:none"]) input,.iw-modal-pane:not([style*="display:none"]) textarea');
        if(firstInp) firstInp.focus();
      }, 50);
    }
    function close(){
      bg.classList.remove('open');
    }
    closeEls.forEach(el => el && el.addEventListener('click', e => {
      if(el === bg && e.target !== bg) return; // only close on bg click outside modal
      close();
    }));
    tabs.forEach(t => t.addEventListener('click', () => setMode(t.dataset.mode)));
    // File picking
    if(drop && fileInp){
      drop.addEventListener('click', () => fileInp.click());
      drop.addEventListener('dragover', e => {e.preventDefault(); drop.classList.add('over')});
      drop.addEventListener('dragleave', () => drop.classList.remove('over'));
      drop.addEventListener('drop', e => {
        e.preventDefault(); drop.classList.remove('over');
        if(e.dataTransfer.files && e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
      });
      fileInp.addEventListener('change', e => {
        if(e.target.files && e.target.files[0]) setFile(e.target.files[0]);
      });
    }
    function setFile(f){
      pickedFile = f;
      if(pickedRow && pickedName){
        pickedName.textContent = f.name + ' (' + (f.size/1024|0) + ' KB)';
        pickedRow.style.display = 'flex';
      }
      setMode('file');
    }
    if(pickedX) pickedX.addEventListener('click', () => {
      pickedFile = null;
      if(pickedRow) pickedRow.style.display = 'none';
      if(fileInp) fileInp.value = '';
    });
    // Auto-detect on paste in any text input inside modal
    bg.addEventListener('paste', e => {
      const txt = (e.clipboardData || window.clipboardData).getData('text');
      if(/^https?:\/\//i.test(txt.trim())){
        // URL detected
        const urlInp = document.getElementById('iwModalUrl');
        if(urlInp && document.activeElement !== urlInp){
          urlInp.value = txt.trim();
          setMode('url');
          e.preventDefault();
        }
      }
    });
    // Submit
    if(submit) submit.addEventListener('click', async () => {
      submit.disabled = true; submit.textContent = 'Сохранение...';
      try {
        let r, msg;
        if(mode === 'file'){
          if(!pickedFile){ setStatus('Выбери файл', 'err'); submit.disabled=false; submit.textContent='Сохранить'; return; }
          const fd = new FormData();
          fd.append('file', pickedFile);
          fd.append('title', document.getElementById('iwModalFileTitle').value || '');
          fd.append('tags', document.getElementById('iwModalFileTags').value || '');
          r = await fetch('/kb/upload', {method:'POST', body:fd});
        } else if(mode === 'url'){
          const url = document.getElementById('iwModalUrl').value.trim();
          if(!url){ setStatus('Введи URL', 'err'); submit.disabled=false; submit.textContent='Сохранить'; return; }
          r = await fetch('/kb/url', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
            url, title: document.getElementById('iwModalUrlTitle').value || '', tags: document.getElementById('iwModalUrlTags').value || ''
          })});
        } else { // text
          const title = document.getElementById('iwModalTextTitle').value.trim();
          const content = document.getElementById('iwModalTextBody').value.trim();
          if(!title || !content){ setStatus('Нужны заголовок и текст', 'err'); submit.disabled=false; submit.textContent='Сохранить'; return; }
          r = await fetch('/kb/text', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
            title, content, tags: document.getElementById('iwModalTextTags').value || ''
          })});
        }
        if(r.ok){
          setStatus('Готово, материал добавлен', 'ok');
          // reset all inputs
          ['iwModalFileTitle','iwModalFileTags','iwModalUrl','iwModalUrlTitle','iwModalUrlTags','iwModalTextTitle','iwModalTextBody','iwModalTextTags'].forEach(id => {
            const el = document.getElementById(id); if(el) el.value = '';
          });
          if(pickedX) pickedX.click();
          // Auto-close after 1.2s
          setTimeout(close, 1200);
          // Trigger reload of list if existing reload function present
          if(typeof loadList === 'function') setTimeout(loadList, 300);
          if(typeof refresh === 'function') setTimeout(refresh, 300);
        } else {
          const data = await r.json().catch(() => ({}));
          setStatus(data.detail || 'Ошибка ' + r.status, 'err');
        }
      } catch(e){
        setStatus('Не удалось отправить', 'err');
      }
      submit.disabled = false; submit.textContent = 'Сохранить';
    });
    // Esc to close
    document.addEventListener('keydown', e => {
      if(e.key === 'Escape' && bg.classList.contains('open')) close();
      if((e.metaKey || e.ctrlKey) && e.key === 'n' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)){
        e.preventDefault(); open();
      }
    });
    // Wire +Add button across templates
    const addBtns = document.querySelectorAll('#iwBtnAdd');
    addBtns.forEach(btn => {
      // If it's an <a> tag (insights.py), prevent navigation and open modal instead
      btn.addEventListener('click', function(e){
        e.preventDefault();
        open();
      });
    });
    // Expose for manual triggers
    window.iwOpenAddModal = open;
  });
})();

/* Phase C: Kanban view + drag-drop + toast */
(function(){
  function showToast(msg, kind){
    const t = document.createElement('div');
    t.className = 'iw-toast' + (kind ? ' ' + kind : '');
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 3000);
  }
  window.iwToast = showToast;
  function escapeHtmlIw(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function categoryShort(c){
    return ({'Travel':'TRAVEL','ПУ/подписки':'ПУ','UX/UI':'UX/UI'}[c] || c || '');
  }
  function renderKanban(){
    const st = window.state;
    if(!st || !Array.isArray(st.hypotheses)) return;
    const STATUSES = ['synthesized','in_review','validated','adopted','archived'];
    STATUSES.forEach(s => {
      const list = document.querySelector('.iw-kb-list[data-list="'+s+'"]');
      const cnt = document.querySelector('.iw-kb-col[data-status="'+s+'"] [data-cnt="'+s+'"]');
      if(!list) return;
      const items = st.hypotheses.filter(h => (h.lifecycle_status || 'synthesized') === s);
      if(cnt) cnt.textContent = items.length;
      list.innerHTML = '';
      items.forEach(h => {
        const card = document.createElement('div');
        card.className = 'iw-kb-card'; card.draggable = true;
        card.dataset.hypId = h.id; card.dataset.status = s;
        const overdue = h.is_overdue ? '<span class="overdue">⏰ просрочено</span>' : '';
        const owner = h.owner_username ? '<span class="owner">@'+escapeHtmlIw(h.owner_username)+'</span>' : '';
        const conf = (typeof h.confidence === 'number') ? '<span class="conf">'+(h.confidence*100|0)+'%</span>' : '';
        const cat = h.category ? '<span class="cat">'+escapeHtmlIw(categoryShort(h.category))+'</span>' : '';
        card.innerHTML = '<div class="stmt">'+escapeHtmlIw(h.statement||'')+'</div><div class="meta">'+cat+conf+overdue+owner+'</div>';
        card.addEventListener('click', () => {
          // Open the existing hypothesis drawer if openHyp/showHyp present
          if(typeof showHyp === 'function') showHyp(h.id);
          else if(typeof openDrawer === 'function') openDrawer(h.id);
        });
        list.appendChild(card);
      });
    });
    // Wire drag/drop after render (idempotent — element refs new every render)
    wireDragDrop();
  }
  function wireDragDrop(){
    const cards = document.querySelectorAll('.iw-kb-card');
    cards.forEach(c => {
      c.addEventListener('dragstart', e => {
        c.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', JSON.stringify({id: c.dataset.hypId, from: c.dataset.status}));
      });
      c.addEventListener('dragend', () => c.classList.remove('dragging'));
    });
    const cols = document.querySelectorAll('.iw-kb-col');
    cols.forEach(col => {
      col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('over'); });
      col.addEventListener('dragleave', () => col.classList.remove('over'));
      col.addEventListener('drop', async e => {
        e.preventDefault();
        col.classList.remove('over');
        let payload;
        try { payload = JSON.parse(e.dataTransfer.getData('text/plain')); } catch(err){ return; }
        const target = col.dataset.status;
        if(target === payload.from) return;
        const card = document.querySelector('.iw-kb-card[data-hyp-id="'+payload.id+'"]');
        if(!card) return;
        // Optimistic move
        const list = col.querySelector('.iw-kb-list');
        list.appendChild(card);
        card.dataset.status = target;
        try {
          const r = await fetch('/kb/insights/'+payload.id+'/lifecycle', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({status: target, confirm: target === 'archived'})
          });
          if(r.ok){
            showToast('Статус обновлён → '+({synthesized:'Черновик',in_review:'В работе',validated:'Валидирована',adopted:'Принята',archived:'Архив'}[target]||target), 'ok');
            // Update local state and refresh counts
            if(window.state && Array.isArray(window.state.hypotheses)){
              const h = window.state.hypotheses.find(x => x.id === payload.id);
              if(h) h.lifecycle_status = target;
              renderKanban();
            }
          } else {
            const data = await r.json().catch(() => ({}));
            showToast(data.detail || 'Не удалось перевести статус', 'err');
            renderKanban(); // revert
          }
        } catch(err){
          showToast('Сеть недоступна', 'err');
          renderKanban();
        }
      });
    });
  }
  function setView(v){
    const kanban = document.getElementById('iwKanban');
    const buttons = document.querySelectorAll('#iwViewToggle button');
    buttons.forEach(b => b.classList.toggle('active', b.dataset.view === v));
    if(v === 'kanban'){
      document.body.classList.add('iw-kanban-active');
      if(kanban) kanban.classList.add('active');
      renderKanban();
    } else {
      document.body.classList.remove('iw-kanban-active');
      if(kanban) kanban.classList.remove('active');
    }
    try { localStorage.setItem('iw_view', v); } catch(e){}
  }
  document.addEventListener('DOMContentLoaded', function(){
    const toggle = document.getElementById('iwViewToggle');
    if(!toggle) return;
    toggle.addEventListener('click', e => {
      const b = e.target.closest('button[data-view]');
      if(b) setView(b.dataset.view);
    });
    let v = 'list';
    try { v = localStorage.getItem('iw_view') || 'list'; } catch(e){}
    if(v === 'kanban'){ setView('kanban'); }
    // Re-render kanban whenever state changes (poll fallback)
    let lastLen = -1;
    setInterval(() => {
      if(!document.body.classList.contains('iw-kanban-active')) return;
      const st = window.state;
      if(!st || !Array.isArray(st.hypotheses)) return;
      if(st.hypotheses.length !== lastLen){ lastLen = st.hypotheses.length; renderKanban(); }
    }, 1500);
  });
})();

/* Phase D: keyboard shortcuts + regen toast progress */
(function(){
  function isInputFocused(){
    const t = document.activeElement;
    return t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && !t.classList.contains('iw-modal-tab');
  }
  function focusSearch(){
    const iw = document.getElementById('iwSearch');
    if(iw){ iw.focus(); iw.select(); }
  }
  document.addEventListener('keydown', function(e){
    // cmd/ctrl+K → search
    if((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')){
      e.preventDefault(); focusSearch(); return;
    }
    if(isInputFocused()) return;
    // gh = go to /kb/insights, gd = go to /kb (vim-like 2-key shortcut)
    if(e.key === 'g'){
      const handler = function(e2){
        document.removeEventListener('keydown', handler, true);
        if(e2.key === 'h'){ window.location.href = '/kb/insights'; e2.preventDefault(); }
        else if(e2.key === 'd' || e2.key === 'm'){ window.location.href = '/kb'; e2.preventDefault(); }
      };
      document.addEventListener('keydown', handler, true);
      setTimeout(() => document.removeEventListener('keydown', handler, true), 1000);
      return;
    }
    // j/k = next/prev hypothesis in list (works only on /kb/insights with .h-card)
    if(e.key === 'j' || e.key === 'k'){
      const cards = Array.from(document.querySelectorAll('.h-card,[data-hyp-id]'));
      if(!cards.length) return;
      let cur = cards.findIndex(c => c.classList.contains('iw-focused') || c === document.activeElement);
      if(cur < 0) cur = -1;
      cur = (e.key === 'j') ? Math.min(cards.length - 1, cur + 1) : Math.max(0, cur - 1);
      cards.forEach((c,i) => c.classList.toggle('iw-focused', i === cur));
      cards[cur].scrollIntoView({block:'nearest', behavior:'smooth'});
      e.preventDefault();
      return;
    }
    // Enter → click focused card
    if(e.key === 'Enter'){
      const f = document.querySelector('.iw-focused');
      if(f){ f.click(); e.preventDefault(); }
      return;
    }
    // ? → show help
    if(e.key === '?' && e.shiftKey){
      const help = document.getElementById('iwKbdHelp');
      if(help){ help.classList.toggle('show'); }
    }
  });
  // Regen toast progress polling
  document.addEventListener('DOMContentLoaded', function(){
    const btn = document.getElementById('iwBtnRegen');
    if(!btn) return;
    btn.addEventListener('click', function(){ /* progress overlay handled by polling */ }, {capture:false});
    // Override fetch wrapper for /regenerate to start polling
    const origFetch = window.fetch.bind(window);
    window.fetch = function(url, opts){
      const p = origFetch(url, opts);
      if(typeof url === 'string' && url.endsWith('/kb/insights/regenerate') && opts && opts.method === 'POST'){
        p.then(r => r.clone().json().then(d => {
          if(d && d.job_id && window.iwToast) {
            window.iwToast('Regenerate запущен — поллим...', 'ok');
            pollRegen(d.job_id);
          }
        }).catch(() => {})).catch(() => {});
      }
      return p;
    };
    function pollRegen(jobId){
      const start = Date.now();
      const intv = setInterval(async () => {
        if(Date.now() - start > 10*60*1000){ clearInterval(intv); return; }
        try {
          const r = await fetch('/kb/insights/regenerate/status/' + jobId);
          if(!r.ok){ clearInterval(intv); return; }
          const d = await r.json();
          if(d.status === 'finished' || d.status === 'ok' || d.finished_at){
            clearInterval(intv);
            const added = d.added || d.new_count || 0;
            const upd = d.updated || d.updated_count || 0;
            window.iwToast && window.iwToast('Regenerate готов: +' + added + ' новых, ' + upd + ' обновлено', 'ok');
            if(typeof refresh === 'function') refresh();
          } else if(d.status === 'failed' || d.status === 'error'){
            clearInterval(intv);
            window.iwToast && window.iwToast('Regenerate упал: ' + (d.error || 'unknown'), 'err');
          }
        } catch(e){ /* keep polling */ }
      }, 4000);
    }
  });
})();

</script>
__FEEDBACK_WIDGET__
<div class="iw-modal-bg" id="iwAddModalBg">
  <div class="iw-modal" role="dialog" aria-labelledby="iwModalTitle">
    <div class="iw-modal-h">
      <h3 id="iwModalTitle">Добавить материал</h3>
      <button type="button" class="iw-modal-h-close" id="iwModalClose" aria-label="Закрыть">&times;</button>
    </div>
    <div class="iw-modal-body">
      <div class="iw-modal-tabs" role="tablist">
        <button type="button" class="iw-modal-tab active" data-mode="file" role="tab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>Файл</button>
        <button type="button" class="iw-modal-tab" data-mode="url" role="tab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>URL</button>
        <button type="button" class="iw-modal-tab" data-mode="text" role="tab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>Текст</button>
      </div>
      <div class="iw-modal-pane" data-mode="file">
        <div class="iw-modal-drop" id="iwModalDrop">
          <strong>Перетащи файл или вставь ссылку</strong>
          PDF, DOCX, TXT, MD &mdash; до 30 МБ
          <input type="file" id="iwModalFile" accept=".pdf,.docx,.txt,.md,.markdown" hidden>
        </div>
        <div class="iw-modal-pickedfile" id="iwModalPicked" style="display:none">
          <span id="iwModalPickedName"></span>
          <button class="x" id="iwModalPickedX" aria-label="Сбросить">&times;</button>
        </div>
        <div class="iw-modal-fld"><label>Заголовок (необязательно)</label><input type="text" id="iwModalFileTitle" placeholder="Если пусто — имя файла"></div>
        <div class="iw-modal-fld"><label>Теги через запятую</label><input type="text" id="iwModalFileTags" placeholder="ресёрч, онбординг"></div>
      </div>
      <div class="iw-modal-pane" data-mode="url" style="display:none">
        <div class="iw-modal-fld"><label>URL</label><input type="url" id="iwModalUrl" placeholder="https://..."></div>
        <div class="iw-modal-fld"><label>Заголовок (необязательно)</label><input type="text" id="iwModalUrlTitle" placeholder="Если пусто — &lt;title&gt; страницы"></div>
        <div class="iw-modal-fld"><label>Теги через запятую</label><input type="text" id="iwModalUrlTags" placeholder="конкурент, статья"></div>
      </div>
      <div class="iw-modal-pane" data-mode="text" style="display:none">
        <div class="iw-modal-fld"><label>Заголовок</label><input type="text" id="iwModalTextTitle" placeholder="Например: Интервью с Анной"></div>
        <div class="iw-modal-fld"><label>Текст</label><textarea id="iwModalTextBody" placeholder="Вставь заметки, транскрипт, идеи..."></textarea></div>
        <div class="iw-modal-fld"><label>Теги через запятую</label><input type="text" id="iwModalTextTags" placeholder="интервью, B2C"></div>
      </div>
      <div class="iw-modal-status" id="iwModalStatus"></div>
    </div>
    <div class="iw-modal-f">
      <button type="button" class="iw-fbar-btn" id="iwModalCancel">Отмена</button>
      <button type="button" class="iw-fbar-btn primary" id="iwModalSubmit">Сохранить</button>
    </div>
  </div>
</div>
<div class="iw-kbd-help" id="iwKbdHelp">
  <div><kbd>⌘K</kbd> поиск</div>
  <div><kbd>j</kbd>/<kbd>k</kbd> навигация</div>
  <div><kbd>↵</kbd> открыть</div>
  <div><kbd>g</kbd>+<kbd>h</kbd> к гипотезам</div>
  <div><kbd>g</kbd>+<kbd>m</kbd> к материалам</div>
  <div><kbd>?</kbd> подсказка</div>
</div>
</body></html>"""

