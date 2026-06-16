# -*- coding: utf-8 -*-
# One-shot evening pipeline check -> reports numbers to Nikita's Telegram.
import json, os, subprocess, urllib.request, urllib.parse, sys, datetime

OPS = "/opt/newsapp/.openclaw/workspace/ops"
TODAY = datetime.datetime.utcnow().strftime("%Y-%m-%d")
CHAT = "100000000"

def mt(p):
    try: return datetime.datetime.utcfromtimestamp(os.path.getmtime(p)).strftime("%H:%M UTC")
    except Exception: return "—"

def load(p):
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d if isinstance(d, list) else (d.get("items") or d.get("candidates") or d.get("urls") or [])
    except Exception: return []

urls = load(OPS + "/r1_urls.json"); urls_mt = mt(OPS + "/r1_urls.json")
news = load(OPS + "/r1_news.json"); news_mt = mt(OPS + "/r1_news.json")
empty = sum(1 for x in news if not (x.get("summary_ru") or "").strip())

# trigger accumulate via the running web app
try:
    sys.path.insert(0, "/opt/newsapp/web")
    from core.auth import _make_token
    tok = _make_token("admin")
    subprocess.run(["curl", "-s", "-o", "/dev/null", "-b", "session=" + tok,
                    "http://127.0.0.1:8000/travel/news"], timeout=40)
except Exception:
    pass

arch = load(OPS + "/travel_news_archive.json")
today_n = sum(1 for x in arch if (x.get("collected_at") or "").startswith(TODAY))
total_n = len(arch)

base_today = 0
try:
    base_today = int(open("/tmp/r1_evening_baseline.txt").read().split()[0])
except Exception:
    pass
evening_added = today_n - base_today

verdict = "✅ 3д-окно дало прирост за вечер" if evening_added > 0 else "⚠️ прироста за вечер нет — стоит глянуть причину"
msg = (
    "📊 Вечерний цикл новостей openclaw (окно 3 дня)\n\n"
    "1) Сбор ссылок: обновлён в %s, кандидатов %d\n"
    "2) Отбор f0f0dc16: %s, новостей %d (без саммари: %d)\n"
    "3) В ленте сегодня: %d (утром было %d)\n"
    "   → добавлено за вечер: %d\n"
    "Архив всего: %d\n\n%s"
) % (urls_mt, len(urls), news_mt, len(news), empty, today_n, base_today, evening_added, total_n, verdict)

def token():
    try:
        cfg = json.load(open("/opt/newsapp/.openclaw/openclaw.json", encoding="utf-8"))
        return cfg["channels"]["telegram"]["accounts"]["trendwatch"]["botToken"]
    except Exception:
        return None

tk = token()
if tk:
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": msg}).encode()
    try:
        urllib.request.urlopen("https://api.telegram.org/bot" + tk + "/sendMessage", data=data, timeout=20)
        print("telegram: sent")
    except Exception as e:
        print("telegram: send failed", type(e).__name__)
else:
    print("telegram: no token")
print("--- report ---")
print(msg)
