"""Constants, paths, regex patterns shared across modules."""
import re
import secrets
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SECRET_FILE = APP_DIR / ".jwt_secret"
if not SECRET_FILE.exists():
    SECRET_FILE.write_text(secrets.token_hex(32))
SECRET = SECRET_FILE.read_text().strip()

JWT_ALG = "HS256"
COOKIE = "session"
USERS_FILE = APP_DIR / "users.json"
ALL_SECTIONS = ["team", "kb"]
# Legacy section keys kept for back-compat with hypothesis categories (ПУ/подписки↔packages, Travel↔travel, UX/UI↔uxui).
LEGACY_SECTIONS = ["packages", "travel", "uxui"]

OPENCLAW = "openclaw"
AGENT_ID = "trendwatch"

# Chat image attachments
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}
MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB

# Agent-generated files to drop into the chat (per-job subdir)
CHAT_DROPS_DIR = APP_DIR / "chat_drops"
CHAT_DROPS_DIR.mkdir(exist_ok=True)
CHAT_DROP_MAX_FILES = 20

# Per-user cross-device state (chat/journey)
STATE_DIR = APP_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)
STATE_KINDS = {"chat", "journey"}
STATE_MAX_BYTES = 5 * 1024 * 1024

# Knowledge base (materials)
KB_DIR = APP_DIR / "kb_files"
KB_DIR.mkdir(exist_ok=True)
KB_DB_PATH = APP_DIR / "kb.db"
KB_MAX_FILE = 30 * 1024 * 1024
KB_MAX_TEXT = 5 * 1024 * 1024
KB_ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md", ".markdown"}

# News archives
R1_NEWS_PATH = Path("/opt/newsapp/.openclaw/workspace/ops/r1_news.json")
TRAVEL_ARCHIVE_PATH = Path("/opt/newsapp/.openclaw/workspace/ops/travel_news_archive.json")
DIGEST_RUN_PATH = Path("/opt/newsapp/.openclaw/cron/runs/00000000-0000-0000-0000-000000000000.jsonl")
PACKAGES_ARCHIVE_PATH = Path("/opt/newsapp/.openclaw/workspace/ops/packages_news_archive.json")

# Near-duplicate title detection
NEAR_DUP_THRESHOLD = 0.7
NEAR_DUP_WINDOW_DAYS = 5
PACKAGES_BACKFILL_DAYS = 7

_TITLE_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
_TITLE_STOP = {
    "в", "и", "на", "с", "по", "из", "за", "для", "о", "об", "к", "от", "до",
    "при", "что", "это", "быть", "был", "была", "было", "или", "же", "только",
    "уже", "ещё", "еще", "у", "не", "но", "а", "да", "же", "бы", "ли", "через",
    "также", "как", "со", "во", "the", "a", "an", "of", "and", "or", "to", "in",
    "on", "for", "with", "by", "at", "from",
}

# Admin / misc
_USER_RE = re.compile(r"^[a-z0-9_]{2,32}$")
_DIGEST_ITEM_RE = re.compile(
    r"^\s*\d+\.\s*📰\s*\*\*(.+?)\*\*\s*[—\-–]+\s*🔗\s*(\S+?)(?:\s*[—\-–]+\s*🕒\s*([^\n]+?))?\s*$",
    re.MULTILINE,
)
_HTML_CLEANUP_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>|<[^>]+>|\s+", re.DOTALL | re.IGNORECASE,
)
