#!/usr/bin/env python3
"""r1_news_watchdog.py — alert if the daily travel-news collection produced nothing.

Read-only watchdog. Touches NO selection logic. Runs ~1h after Stage-2
(cron: 40 7 * * *  UTC == 10:40 MSK). Checks r1_news.json freshness; if empty
or stale (>STALE_HOURS), sends a Telegram alert to the owner via the TrendWatch
bot (token reused from openclaw.json — no new secret).

Usage:
  r1_news_watchdog.py           # normal daily check
  r1_news_watchdog.py --test    # send a test message to verify delivery
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

OPS = "/opt/newsapp/.openclaw/workspace/ops"
R1_NEWS = os.path.join(OPS, "r1_news.json")
OPENCLAW_CFG = "/opt/newsapp/.openclaw/openclaw.json"
OWNER_CHAT = "100000000"
STALE_HOURS = 20


def tg_token():
    d = json.load(open(OPENCLAW_CFG, encoding="utf-8"))
    return d["channels"]["telegram"]["accounts"]["trendwatch"]["botToken"]


def send(text):
    url = "https://api.telegram.org/bot" + tg_token() + "/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": OWNER_CHAT, "text": text, "disable_web_page_preview": "true",
    }).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20)
        return r.status
    except Exception as e:
        print("send err:", e)
        return None


def parse_dt(s):
    if not s:
        return None
    s = str(s).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def latest_and_count(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 0, None
    arr = d if isinstance(d, list) else (d.get("candidates") or d.get("items") or [])
    dts = [parse_dt(x.get("collected_at")) for x in arr if isinstance(x, dict)]
    dts = [x for x in dts if x]
    return len(arr), (max(dts) if dts else None)


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "--test" in sys.argv:
        st = send("🧪 openclaw watchdog: тест доставки. Если видишь это — алерты о сбое сбора travel-новостей будут доходить. (" + ts + ")")
        print(ts, "test send status:", st)
        return

    cnt, latest = latest_and_count(R1_NEWS)
    now = datetime.now(timezone.utc)
    age_h = (now - latest).total_seconds() / 3600 if latest else 9999.0
    stale = (cnt == 0) or (age_h > STALE_HOURS)
    print(ts, f"r1_news count={cnt} latest={latest} age_h={age_h:.1f} stale={stale}")

    empty = total = 0
    try:
        d = json.load(open(R1_NEWS, encoding="utf-8"))
        items = d if isinstance(d, list) else (d.get("candidates") or d.get("items") or [])
        total = len(items)
        empty = sum(1 for x in items if isinstance(x, dict) and not (x.get("summary_ru") or "").strip())
    except Exception:
        pass
    frac = (empty / total) if total else 0
    print(ts, f"empty_summaries {empty}/{total} ({frac*100:.0f}%)")

    if stale:
        send(
            "⚠️ openclaw: сегодня НЕ собрались travel-новости.\n\n"
            f"r1_news.json: {cnt} шт, последняя {age_h:.0f}ч назад.\n"
            "Phase-1 (сбор) не подготовил вход. Проверь: r1_fetch_urls / crontab / gateway."
        )
        print(ts, "ALERT SENT (stale)")
    elif frac >= 0.5 and total >= 3:
        send(
            "⚠️ openclaw: новости собрались, но у большинства ПУСТОЕ саммари.\n\n"
            f"Всего {total}, без саммари {empty} ({frac*100:.0f}%).\n"
            "Похоже, prefetch (догрузка текста) не отработал. Лог: /tmp/r1_pipeline.log"
        )
        print(ts, "ALERT SENT (empty summaries)")
    else:
        print(ts, "OK — news fresh")


if __name__ == "__main__":
    main()
