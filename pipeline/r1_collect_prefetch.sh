#!/bin/bash
# Collect fresh R1 news URLs + prefetch article_text. Runs before morning (06:40 UTC)
# and evening (18:00 UTC) f0f0dc16 classification. flock-guarded; logs to /tmp.
exec >> /tmp/r1_collect_cron.log 2>&1
echo "=== START $(date -u +'%Y-%m-%d %H:%M:%S') UTC ==="
cd /opt/newsapp/.openclaw/workspace/scripts || exit 1
flock -n /tmp/r1_refresh.lock bash -c '/usr/bin/python3 r1_fetch_urls.py --mode=collect && /usr/bin/python3 r1_prefetch.py' || echo "LOCKED or failed"
echo "=== DONE $(date -u +'%H:%M:%S') UTC ==="
