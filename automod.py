"""Content-aware auto-moderation.

The rate limiter in bot.py only ever counted messages per second, so the common
raid pattern -- a fresh account dropping referral/casino screenshots with a promo
code into a few channels -- never tripped it. Everything here looks at what the
message actually says, scores it, and hands bot.py a verdict to enforce.

Kept free of discord.py imports so the scoring can be exercised directly.
"""

import datetime
import hashlib
import io
import json
import os
import re
import threading
import time
import unicodedata
from collections import defaultdict, deque

# Pillow is optional on purpose. With it we can perceptually hash an image and
# recognise the same screenshot after a re-encode or crop; without it we fall back
# to Discord's own size/width/height metadata, which costs no bandwidth at all and
# still catches a file re-uploaded verbatim. imagehash was rejected: it drags in
# numpy and scipy for an algorithm that fits in a dozen lines.
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:                                   # pragma: no cover
    Image = None
    PIL_AVAILABLE = False

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
CONFIG_FILE = os.path.join(DATA_DIR, "automod.json")
BLOCKED_IMAGES_FILE = os.path.join(DATA_DIR, "blocked_images.json")
os.makedirs(DATA_DIR, exist_ok=True)

_config_lock = threading.Lock()
_blocked_lock = threading.Lock()


# ----------------- CONFIG -----------------

DEFAULTS = {
    "enabled": True,
    # Content scoring
    "scam_threshold": 5,          # score at or above this counts as scam/referral spam
    "scam_action": "timeout",     # what a first confirmed hit does: warn | timeout | ban
    "scam_timeout_minutes": 60,
    "ban_on_repeat": True,        # a second scam hit from the same user bans them
    "purge_on_scam": True,        # delete the rest of their recent messages too
    # Signal categories to ignore, by label -- for wording that is normal in this
    # server (a trading server talking crypto, an LFG server saying "dm me").
    "disabled_signals": [],
    # Discrete rules
    "block_invites": True,
    "block_mass_mentions": True,
    "mention_limit": 5,
    # Flood rules
    "rate_limit": 5,              # messages ...
    "rate_window": 6.0,           # ... within this many seconds
    "rate_timeout_minutes": 5,
    "duplicate_limit": 3,         # same text repeated this many times ...
    "duplicate_window": 60.0,     # ... within this many seconds
    "crosspost_limit": 3,         # same text in this many distinct channels
    "attachment_limit": 5,        # images in one message
    # Image rules -- the referral-screenshot raid, where the text gives nothing away
    "image_checks": True,
    "image_deep_hash": True,      # download and perceptually hash (costs bandwidth);
                                  # off = metadata-only fingerprints, no download
    "image_dupe_limit": 3,        # same image this many times from one member
    "image_raid_accounts": 3,     # same image from this many different accounts
    "image_dupe_window": 300.0,   # how long an image stays in the comparison set
    "image_hash_distance": 6,     # max differing bits (of 64) still "the same image"
    "max_image_bytes": 8000000,   # never download an attachment larger than this
    # Cloud OCR -- reads the words inside an image. OFF by default, and it sends
    # member-posted images to a third party, so it is strictly opt-in.
    "ocr_enabled": False,
    "ocr_max_images": 2,          # images per message worth paying for
    "ocr_max_per_hour": 60,       # hard ceiling on billable calls
    "ocr_only_untrusted": True,   # skip members with roles / older accounts
    "ocr_cache_days": 30,         # how long a read result is reused
    # Context signals
    "new_account_days": 14,
    "new_member_hours": 72,
    # Lists
    "allow_domains": [],
    "block_domains": [],
    "extra_keywords": [],
    "exempt_channels": [],
    "exempt_roles": [],
}

_config = dict(DEFAULTS)


def load_config():
    """Read data/automod.json, filling in any key the file predates."""
    global _config
    with _config_lock:
        merged = dict(DEFAULTS)
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in DEFAULTS:
                        merged[key] = value
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        _config = merged
        return dict(_config)


# ----------------- PER-GUILD OVERRIDES -----------------

# automod.json holds the bot owner's defaults; a guild stores only the keys it
# actually changed. New servers therefore inherit sensible tuning, and improving
# a default still reaches every guild that never overrode it.

GUILD_DIR = os.path.join(DATA_DIR, "guilds")
os.makedirs(GUILD_DIR, exist_ok=True)

_overrides = {}


def _guild_file(guild_id):
    return os.path.join(GUILD_DIR, "%s.json" % str(guild_id))


def _guild_overrides(guild_id):
    """This guild's overrides, cached. Callers must hold _config_lock."""
    key = str(guild_id)
    if key not in _overrides:
        try:
            with open(_guild_file(key), "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            _overrides[key] = {k: v for k, v in loaded.items()
                               if k in DEFAULTS} if isinstance(loaded, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _overrides[key] = {}
    return _overrides[key]


def get_config(guild_id=None):
    """Effective settings: the owner's defaults, with this guild's changes on top."""
    with _config_lock:
        merged = dict(_config)
        if guild_id is not None:
            merged.update(_guild_overrides(guild_id))
        return merged


def guild_overrides(guild_id):
    """Only the keys this guild has changed -- what the dashboard shows as custom."""
    with _config_lock:
        return dict(_guild_overrides(guild_id))


def clear_guild_overrides(guild_id):
    """Drop a guild's customisation so it follows the defaults again."""
    key = str(guild_id)
    with _config_lock:
        _overrides[key] = {}
        try:
            os.remove(_guild_file(key))
        except OSError:
            pass


def reset_guild_cache():
    """Forget cached overrides so the next read comes off disk (tests)."""
    with _config_lock:
        _overrides.clear()


def _coerce(key, value):
    """Force an incoming value to the shape of its default, or raise ValueError."""
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(default, float):
        return max(0.0, float(value))
    if isinstance(default, int):
        return max(0, int(value))
    if isinstance(default, list):
        if isinstance(value, str):
            value = re.split(r"[,\n]", value)
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(default, str):
        text = str(value).strip().lower()
        if key == "scam_action" and text not in ("warn", "timeout", "ban"):
            raise ValueError("bad scam_action")
        return text
    return value


def save_guild_config(guild_id, updates):
    """Store only the keys this guild actually changes. Returns its effective config."""
    key = str(guild_id)
    with _config_lock:
        current = dict(_guild_overrides(key))
        for name, value in (updates or {}).items():
            if name not in DEFAULTS:
                continue
            try:
                coerced = _coerce(name, value)
            except (TypeError, ValueError):
                continue
            # Matching the default again means this guild no longer overrides it.
            if coerced == _config.get(name):
                current.pop(name, None)
            else:
                current[name] = coerced
        _overrides[key] = current
        tmp = _guild_file(key) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(current, fh, indent=2)
            os.replace(tmp, _guild_file(key))
        except OSError:
            pass
        merged = dict(_config)
        merged.update(current)
        return merged


def save_config(updates):
    """Merge `updates` into the owner's defaults and persist."""
    global _config
    with _config_lock:
        merged = dict(_config)
        for key, value in (updates or {}).items():
            if key not in DEFAULTS:
                continue
            default = DEFAULTS[key]
            try:
                if isinstance(default, bool):
                    if isinstance(value, str):
                        value = value.strip().lower() in ("1", "true", "yes", "on")
                    else:
                        value = bool(value)
                elif isinstance(default, float):
                    value = max(0.0, float(value))
                elif isinstance(default, int):
                    value = max(0, int(value))
                elif isinstance(default, list):
                    if isinstance(value, str):
                        value = re.split(r"[,\n]", value)
                    value = [str(v).strip().lower() for v in value if str(v).strip()]
                elif isinstance(default, str):
                    value = str(value).strip().lower()
                    if key == "scam_action" and value not in ("warn", "timeout", "ban"):
                        continue
            except (TypeError, ValueError):
                continue
            merged[key] = value
        _config = merged
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
                json.dump(merged, fh, indent=2)
        except OSError:
            pass
        return dict(merged)


load_config()


# ----------------- TEXT NORMALISATION -----------------

# Spammers space out or leet-speak the trigger words ("c a s i n o", "fr33 m0ney"),
# so every check runs against a flattened copy of the text.
_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "@": "a", "$": "s", "!": "i", "|": "i",
})

_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")
_SEPARATED_LETTERS = re.compile(r"\b(?:[a-z][^a-z0-9\s]?\s){2,}[a-z]\b")


def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = _ZERO_WIDTH.sub("", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().translate(_LEET)
    # "c a s i n o" / "c-a-s-i-n-o" -> "casino"
    text = _SEPARATED_LETTERS.sub(lambda m: re.sub(r"[^a-z]", "", m.group(0)), text)
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)        # "freeeee" -> "free"
    return re.sub(r"\s+", " ", text).strip()


def despace(text):
    """Letters and digits only.

    OCR regularly loses the spaces between words ("WithdrawalSuccess"), and
    spammers insert punctuation for the same effect ("f.r.e.e m.o.n.e.y"). Both
    collapse to the same string here, so a phrase can be matched either way.
    """
    return re.sub(r"[^a-z0-9]", "", normalize(text))


# ----------------- SIGNALS -----------------

# (weight, label, phrases) -- a category scores once no matter how many of its
# phrases hit, so a wall of synonyms cannot inflate the score on its own.
KEYWORD_RULES = [
    (3, "giveaway bait", (
        "giving away", "give away", "giveaway", "claim your reward", "claim reward",
        "claim your bonus", "claim your prize", "free money", "free cash", "free gift",
        "free nitro", "nitro free", "steam gift", "free robux", "free gift card",
    )),
    (3, "referral / promo code", (
        "promo code", "bonus code", "referral code", "ref code", "activate code",
        "use my code", "use code", "my referral", "referral link", "ref link",
        "signup bonus", "sign up bonus", "deposit bonus", "no deposit", "rakeback",
        "register and get", "sign up and get", "register using",
    )),
    (3, "gambling", (
        "casino", "roulette", "jackpot", "sportsbook", "blackjack", "betting site",
        "bet now", "free spins", "wager requirement", "gambling site",
    )),
    (2, "payout proof", (
        "withdrawal success", "withdraw success", "successfully withdraw",
        "was successfully", "instant withdraw", "cashout proof", "payout proof",
        "profit proof", "withdrawal proof", "easy money", "daily profit",
    )),
    (2, "crypto bait", (
        "usdt", "bitcoin", "btc wallet", "eth wallet", "crypto wallet", "trust wallet",
        "metamask", "airdrop", "seed phrase", "mining profit", "crypto casino",
    )),
    (2, "celebrity bait", (
        "mrbeast", "mr beast", "beast games", "elon musk", "elonmusk",
    )),
    (2, "urgency", (
        "limited time", "limited offer", "offer is limited", "hurry up", "act fast",
        "only today", "first 100", "first 50", "last chance", "dont miss", "do not miss",
    )),
    (2, "dm bait", (
        "dm me", "dm for", "message me for", "pm me", "inbox me", "add me on",
        "telegram me", "hit me up on", "whatsapp me",
    )),
    (3, "account trade", (
        "selling account", "account for sale", "cheap boosting", "buy followers",
        "cheap gift card", "selling nitro",
    )),
]

KEYWORD_LABELS = {label for _, label, _ in KEYWORD_RULES}

# Everything `disabled_signals` can switch off, in the order the dashboard shows them.
# Admin-driven signals (blocked domain/keyword, brand lookalikes) are deliberately
# absent: those exist because a moderator asked for them.
TOGGLEABLE_SIGNALS = [(label, weight) for weight, label, _ in KEYWORD_RULES] + [
    ("money amount", 2),
    ("link shortener", 2),
    ("external link", 1),
    ("images + link", 2),
]

# Link-shaped signals alone (an unknown domain, a shortener, a price) are too weak to
# punish on -- plenty of real chat looks like that. Enforcement needs at least one of
# these: scam wording, an admin-blocked keyword/domain, or a brand lookalike.
def _has_content_signal(reasons):
    return any(
        r in KEYWORD_LABELS or r.startswith(("blocked keyword", "blocked domain",
                                             "blocked image", "brand lookalike"))
        for r in reasons
    )


SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "t.ly", "is.gd", "rb.gy", "shorturl.at",
    "rebrand.ly", "shorte.st", "adf.ly", "lnkd.in", "ow.ly", "buff.ly", "t.co",
    "linktr.ee", "bio.link", "s.id", "gg.gg",
}

SAFE_DOMAINS = {
    "discord.com", "discordapp.com", "discordapp.net", "cdn.discordapp.com",
    "media.discordapp.net", "youtube.com", "youtu.be", "twitch.tv", "twitter.com",
    "x.com", "tenor.com", "giphy.com", "imgur.com", "reddit.com", "github.com",
    "gitlab.com", "spotify.com", "medal.tv", "steamcommunity.com", "steampowered.com",
    "wikipedia.org", "google.com", "docs.google.com", "tiktok.com", "instagram.com",
    "soundcloud.com", "j4fn.site",
}

# Lookalikes: a domain that borrows a trusted brand but is not the real thing.
BRAND_WORDS = ("discord", "steam", "nitro", "roblox", "epicgames", "riotgames")

URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b[a-z0-9][a-z0-9-]{1,62}\.(?:com|net|org|io|gg|co|me|xyz|top|vip|site|club"
    r"|online|link|app|fun|bet|casino|win|pro|live|shop|store|info|biz|ru|cn)\b",
    re.IGNORECASE,
)
INVITE_RE = re.compile(
    r"(?:discord(?:app)?\.com/invite|discord\.gg|discord\.me|dsc\.gg|invite\.gg)/\s*([a-z0-9-]+)",
    re.IGNORECASE,
)
MONEY_RE = re.compile(
    r"(?:[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:usd|eur|dollars?|k\b))",
    re.IGNORECASE,
)


def extract_domains(text):
    """Hostnames referenced by the raw message text, deduped and lowercased."""
    domains = []
    for raw in URL_RE.findall(text or ""):
        host = re.sub(r"^https?://", "", raw, flags=re.IGNORECASE)
        host = host.split("/")[0].split("?")[0].split("#")[0].split("@")[-1]
        host = host.split(":")[0].lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        if host and "." in host and host not in domains:
            domains.append(host)
    return domains


def _is_safe(host, allow_domains):
    for safe in list(SAFE_DOMAINS) + list(allow_domains or []):
        if host == safe or host.endswith("." + safe):
            return True
    return False


def score_content(text, *, attachments=0, config=None):
    """Score a message body on its own. Returns (score, [reasons])."""
    cfg = config or get_config()
    flat = normalize(text)
    raw = text or ""
    score = 0
    reasons = []

    off = {str(s).strip().lower() for s in cfg.get("disabled_signals", [])}
    squashed = despace(text)

    def says(phrase):
        flattened = normalize(phrase)
        if flattened and flattened in flat:
            return True
        # Fall back to a space-free comparison, but only for phrases long enough
        # that running them together cannot collide with ordinary prose.
        squashed_phrase = despace(phrase)
        return len(squashed_phrase) >= 8 and squashed_phrase in squashed

    for weight, label, phrases in KEYWORD_RULES:
        if label in off:
            continue
        if any(says(p) for p in phrases):
            score += weight
            reasons.append(label)

    extra = [k for k in cfg.get("extra_keywords", []) if k and says(k)]
    if extra:
        score += 3
        reasons.append("blocked keyword (%s)" % extra[0])

    domains = extract_domains(raw)
    blocked = [d for d in domains if any(
        d == b or d.endswith("." + b) for b in cfg.get("block_domains", []))]
    shorteners = [d for d in domains if d in SHORTENERS]
    unsafe = [d for d in domains if not _is_safe(d, cfg.get("allow_domains", []))]
    lookalikes = [
        d for d in unsafe
        if any(b in d.replace("-", "").replace(".", "") for b in BRAND_WORDS)
    ]

    if blocked:
        score += 5
        reasons.append("blocked domain (%s)" % blocked[0])
    if lookalikes:
        score += 4
        reasons.append("brand lookalike domain (%s)" % lookalikes[0])
    if shorteners and "link shortener" not in off:
        score += 2
        reasons.append("link shortener")
    if unsafe and not blocked and not lookalikes and not shorteners \
            and "external link" not in off:
        score += 1
        reasons.append("external link")

    if "money amount" not in off and MONEY_RE.search(raw):
        score += 2
        reasons.append("money amount")

    # The referral-screenshot shape: proof images plus somewhere to sign up.
    if "images + link" not in off and attachments and unsafe:
        score += 2
        reasons.append("images + link")

    return score, reasons


# ----------------- IMAGE FINGERPRINTING -----------------

_RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1) if Image else None


def dhash(data, size=8):
    """64-bit difference hash of image bytes, or None if it cannot be read.

    Compares each pixel with its right-hand neighbour in a tiny greyscale copy, so
    re-encoding, resizing and mild cropping leave most bits untouched while a
    genuinely different picture differs in many.
    """
    if not PIL_AVAILABLE or not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("L").resize((size + 1, size), _RESAMPLE)
            pixels = list(im.getdata())
    except Exception:          # unreadable, truncated, or a decompression bomb
        return None
    if len(pixels) < (size + 1) * size:
        return None
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | int(pixels[base + col] < pixels[base + col + 1])
    return bits


def fingerprint_image(data):
    """Fingerprint from the actual bytes: exact digest plus a perceptual hash."""
    if not data:
        return None
    return {"exact": hashlib.sha256(data).hexdigest(), "perceptual": dhash(data)}


def fingerprint_meta(size, width=0, height=0):
    """Fingerprint from Discord's attachment metadata -- no download required.

    Weaker than a perceptual hash (any edit changes it) but free, and a raid that
    re-uploads one saved file still collides.
    """
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return None
    return {"exact": "meta:%d:%d:%d" % (size, int(width or 0), int(height or 0)),
            "perceptual": None}


def images_match(a, b, distance=6):
    if not a or not b:
        return False
    if a.get("exact") and a.get("exact") == b.get("exact"):
        return True
    left, right = a.get("perceptual"), b.get("perceptual")
    if left is None or right is None:
        return False
    return bin(left ^ right).count("1") <= distance


# ----------------- BLOCKED IMAGE LIST -----------------

# A moderator marking one scam screenshot immunises the server against it for good:
# the next account to upload that picture is caught on its FIRST post, with no
# repetition and no wording to go on. Kept per guild, the way warnings are.

_blocked_images = None


def _blocked_store():
    """The whole store, loaded once. Callers must hold _blocked_lock."""
    global _blocked_images
    if _blocked_images is None:
        try:
            with open(BLOCKED_IMAGES_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            _blocked_images = loaded if isinstance(loaded, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _blocked_images = {}
    return _blocked_images


def _save_blocked(store):
    tmp = BLOCKED_IMAGES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2)
        os.replace(tmp, BLOCKED_IMAGES_FILE)
    except OSError:
        pass


def blocked_images(guild_id):
    with _blocked_lock:
        return list(_blocked_store().get(str(guild_id), []))


def add_blocked_image(guild_id, fingerprint, note="", moderator=""):
    """Remember one image as scam. Returns the stored entry, or None if known."""
    if not fingerprint:
        return None
    with _blocked_lock:
        store = _blocked_store()
        entries = store.setdefault(str(guild_id), [])
        for existing in entries:
            if images_match(fingerprint, existing, DEFAULTS["image_hash_distance"]):
                return None
        entry = {
            "id": int(time.time() * 1000) % 1000000000,
            "exact": fingerprint.get("exact"),
            "perceptual": fingerprint.get("perceptual"),
            "note": (note or "").strip()[:120],
            "moderator": str(moderator)[:80],
            "time": datetime.datetime.now(datetime.timezone.utc)
                            .replace(microsecond=0).isoformat(),
        }
        entries.append(entry)
        _save_blocked(store)
        return entry


def remove_blocked_image(guild_id, entry_id):
    """Drop one entry by id. Returns True if something was removed."""
    with _blocked_lock:
        store = _blocked_store()
        entries = store.get(str(guild_id), [])
        kept = [e for e in entries if str(e.get("id")) != str(entry_id)]
        if len(kept) == len(entries):
            return False
        store[str(guild_id)] = kept
        _save_blocked(store)
        return True


def match_blocked_image(guild_id, fingerprints, distance=6):
    """Return the blocklist entry matching any of these images, else None."""
    if not fingerprints:
        return None
    with _blocked_lock:
        entries = _blocked_store().get(str(guild_id), [])
        for fingerprint in fingerprints:
            if not fingerprint:
                continue
            for entry in entries:
                if images_match(fingerprint, entry, distance):
                    return entry
    return None


def reset_blocked_cache():
    """Forget the in-memory copy so the next read comes off disk (tests)."""
    global _blocked_images
    with _blocked_lock:
        _blocked_images = None


# ----------------- CLOUD OCR: GATE, BUDGET, CACHE -----------------

# A cloud read costs money and latency, so it has to be rare. Three gates keep it
# that way: only when the words already in the message are not damning enough,
# only from members with nothing to vouch for them, and never twice for the same
# picture. The cache matches perceptually, so a re-encoded repost is free too.

OCR_CACHE_FILE = os.path.join(DATA_DIR, "ocr_cache.json")
_ocr_lock = threading.Lock()
_ocr_cache = None
_ocr_calls = deque(maxlen=5000)


def _ocr_store():
    """Loaded once. Callers must hold _ocr_lock."""
    global _ocr_cache
    if _ocr_cache is None:
        try:
            with open(OCR_CACHE_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            _ocr_cache = loaded if isinstance(loaded, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _ocr_cache = []
    return _ocr_cache


def _save_ocr_cache(entries):
    tmp = OCR_CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entries[-2000:], fh)
        os.replace(tmp, OCR_CACHE_FILE)
    except OSError:
        pass


def ocr_cache_get(fingerprint, distance=6, max_age_days=30, now=None):
    """Text already read from this picture, or None."""
    if not fingerprint:
        return None
    now = now if now is not None else time.time()
    cutoff = now - max_age_days * 86400
    with _ocr_lock:
        for entry in reversed(_ocr_store()):
            if entry.get("time", 0) < cutoff:
                continue
            if images_match(fingerprint, entry, distance):
                return entry.get("text", "")
    return None


def ocr_cache_put(fingerprint, text, now=None):
    if not fingerprint:
        return
    now = now if now is not None else time.time()
    with _ocr_lock:
        entries = _ocr_store()
        entries.append({
            "exact": fingerprint.get("exact"),
            "perceptual": fingerprint.get("perceptual"),
            "text": (text or "")[:2000],
            "time": now,
        })
        _save_ocr_cache(entries)


def reset_ocr_cache():
    """Drop the in-memory cache and the call ledger (tests)."""
    global _ocr_cache
    with _ocr_lock:
        _ocr_cache = None
        _ocr_calls.clear()


def ocr_budget_left(config=None, now=None):
    """Billable calls still allowed this hour."""
    cfg = config or get_config()
    now = now if now is not None else time.time()
    ceiling = cfg.get("ocr_max_per_hour", 60)
    with _ocr_lock:
        recent = sum(1 for t in _ocr_calls if now - t < 3600)
    return max(0, ceiling - recent)


def ocr_note_call(now=None):
    """Record that a billable call was made."""
    with _ocr_lock:
        _ocr_calls.append(now if now is not None else time.time())


def should_ocr(*, text_score, images, has_roles=False, account_age_days=None,
               join_age_hours=None, config=None, now=None):
    """Is this message worth paying a cloud read for? Returns (bool, why)."""
    cfg = config or get_config()
    if not cfg.get("ocr_enabled", False):
        return False, "ocr disabled"
    if not cfg.get("image_checks", True):
        return False, "image checks off"
    if not images:
        return False, "no images"
    if text_score >= cfg.get("scam_threshold", 5):
        return False, "already over threshold"

    if cfg.get("ocr_only_untrusted", True):
        fresh_account = (account_age_days is not None
                         and account_age_days <= cfg.get("new_account_days", 14))
        fresh_member = (join_age_hours is not None
                        and join_age_hours <= cfg.get("new_member_hours", 72))
        if has_roles and not (fresh_account or fresh_member):
            return False, "established member"

    if ocr_budget_left(cfg, now) <= 0:
        return False, "hourly budget spent"
    return True, "ok"


# ----------------- VERDICTS -----------------

class Verdict:
    """What bot.py should do about one message."""

    def __init__(self, action="none", reason="", score=0, reasons=None,
                 timeout_minutes=0, purge=False):
        self.action = action              # none | delete | warn | timeout | ban
        self.reason = reason
        self.score = score
        self.reasons = reasons or []
        self.timeout_minutes = timeout_minutes
        self.purge = purge

    def __bool__(self):
        return self.action != "none"

    def __repr__(self):
        return "<Verdict %s score=%s reason=%r>" % (self.action, self.score, self.reason)


NO_ACTION = Verdict()


# ----------------- PER-USER HISTORY -----------------

class SpamTracker:
    """Recent message history per (guild, user).

    The old implementation leaked a deque per user forever; entries here are
    pruned on a timer and idle users are dropped wholesale.
    """

    def __init__(self, idle_ttl=900.0):
        self._history = defaultdict(lambda: deque(maxlen=40))
        # Images are indexed per guild, not per user: a referral raid is several
        # fresh accounts posting one saved screenshot, which a per-user view misses.
        self._images = defaultdict(lambda: deque(maxlen=400))
        self._scam_hits = {}
        self._idle_ttl = idle_ttl
        self._last_sweep = time.time()
        self._lock = threading.Lock()

    def record_images(self, guild_id, user_id, fingerprints, window=300.0,
                      distance=6, now=None):
        """Add this message's images to the guild index.

        Returns (repeats, accounts): how many times this member has posted the
        image, and how many distinct members have posted it, within `window`.
        """
        now = now if now is not None else time.time()
        fingerprints = [f for f in (fingerprints or ()) if f]
        if not fingerprints:
            return 0, 0

        with self._lock:
            log = self._images[guild_id]
            while log and now - log[0][0] > window:
                log.popleft()

            repeats = accounts = 0
            for fingerprint in fingerprints:
                matches = [e for e in log if images_match(fingerprint, e[2], distance)]
                repeats = max(repeats, 1 + sum(1 for e in matches if e[1] == user_id))
                accounts = max(accounts, len({e[1] for e in matches} | {user_id}))
                log.append((now, user_id, fingerprint))
            return repeats, accounts

    def record(self, guild_id, user_id, text, channel_id, now=None):
        now = now if now is not None else time.time()
        key = (guild_id, user_id)
        with self._lock:
            self._history[key].append((now, normalize(text)[:200], channel_id))
            self._sweep(now)
            return list(self._history[key])

    def _sweep(self, now):
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        for key in [k for k, v in self._history.items()
                    if not v or now - v[-1][0] > self._idle_ttl]:
            self._history.pop(key, None)
        for key in [k for k, t in self._scam_hits.items() if now - t > 86400]:
            self._scam_hits.pop(key, None)
        for key in [k for k, v in self._images.items()
                    if not v or now - v[-1][0] > self._idle_ttl]:
            self._images.pop(key, None)

    def clear(self, guild_id, user_id):
        with self._lock:
            self._history.pop((guild_id, user_id), None)

    def note_scam(self, guild_id, user_id, now=None):
        """Record a scam hit; returns True if this user has offended before."""
        key = (guild_id, user_id)
        now = now if now is not None else time.time()
        with self._lock:
            previous = self._scam_hits.get(key)
            self._scam_hits[key] = now
            return previous is not None and now - previous < 86400

    def recent_channels(self, guild_id, user_id, window=600.0, now=None):
        """Channel ids this user posted in recently -- where a purge should reach."""
        now = now if now is not None else time.time()
        with self._lock:
            entries = self._history.get((guild_id, user_id), ())
            return list({h[2] for h in entries if now - h[0] <= window})

    def stats(self):
        with self._lock:
            return {"tracked_users": len(self._history),
                    "flagged_users": len(self._scam_hits),
                    "tracked_images": sum(len(v) for v in self._images.values())}


_tracker = SpamTracker()


def tracker_stats():
    return _tracker.stats()


def recent_channels(guild_id, user_id, window=600.0):
    return _tracker.recent_channels(guild_id, user_id, window=window)


def reset_state():
    """Drop all tracked history (used by tests and `$automod reset`)."""
    global _tracker
    _tracker = SpamTracker()


# ----------------- EVALUATION -----------------

def evaluate(*, text, guild_id, user_id, channel_id, attachments=0,
             mention_count=0, mentions_everyone=False, account_age_days=None,
             join_age_hours=None, role_ids=(), images=(), ocr_text="",
             config=None, now=None):
    """Decide what to do about one message."""
    cfg = config or get_config()
    now = now if now is not None else time.time()

    if not cfg.get("enabled", True):
        return NO_ACTION
    if str(channel_id) in [str(c) for c in cfg.get("exempt_channels", [])]:
        return NO_ACTION
    exempt_roles = {str(r) for r in cfg.get("exempt_roles", [])}
    if exempt_roles and exempt_roles.intersection({str(r) for r in role_ids}):
        return NO_ACTION

    history = _tracker.record(guild_id, user_id, text, channel_id, now=now)

    # --- @everyone / mention storms ---
    if cfg.get("block_mass_mentions", True):
        limit = cfg.get("mention_limit", 5)
        if mentions_everyone or (limit and mention_count >= limit):
            what = "@everyone/@here" if mentions_everyone else "%d mentions" % mention_count
            return Verdict("timeout", "Mass mention (%s)" % what,
                           timeout_minutes=cfg.get("rate_timeout_minutes", 5))

    # --- Unsolicited server invites ---
    if cfg.get("block_invites", True) and INVITE_RE.search(text or ""):
        return Verdict("delete", "Server invite link")

    # --- Content scoring ---
    score, reasons = score_content(text, attachments=attachments, config=cfg)

    # Words read out of the image count as the poster's own words, but only when
    # they actually add something the caption did not already say.
    if ocr_text:
        combined, combined_reasons = score_content(
            "%s\n%s" % (text or "", ocr_text), attachments=attachments, config=cfg)
        if combined > score:
            score, reasons = combined, combined_reasons + ["text in image"]

    # Context the text alone cannot carry.
    if score > 0:
        if account_age_days is not None and account_age_days <= cfg.get("new_account_days", 14):
            score += 2
            reasons.append("account %dd old" % int(account_age_days))
        if join_age_hours is not None and join_age_hours <= cfg.get("new_member_hours", 72):
            score += 1
            reasons.append("joined recently")

    # --- Image reuse ---
    # Scored before the threshold check so a captionless screenshot and a worded
    # one reinforce each other instead of being judged separately.
    image_repeats = image_accounts = 0
    if cfg.get("image_checks", True) and images:
        # A moderator already called this picture scam: decisive on its own, the
        # way an admin-blocked domain is.
        known = match_blocked_image(guild_id, images,
                                    cfg.get("image_hash_distance", 6))
        if known:
            score += 6
            reasons.append("blocked image (%s)" % (known.get("note") or known["id"]))

        image_repeats, image_accounts = _tracker.record_images(
            guild_id, user_id, images,
            window=cfg.get("image_dupe_window", 300.0),
            distance=cfg.get("image_hash_distance", 6),
            now=now,
        )
        if image_accounts >= 2:
            score += 3
            reasons.append("image seen from %d accounts" % image_accounts)
        elif image_repeats >= 2:
            score += 2
            reasons.append("repeated image")

    recent = [h for h in history if now - h[0] < cfg.get("duplicate_window", 60.0)]
    fingerprint = normalize(text)[:200]
    same = [h for h in recent if h[1] == fingerprint and h[1]]
    channels = {h[2] for h in same}
    repeats = len(same)

    if len(channels) >= cfg.get("crosspost_limit", 3):
        score += 3
        reasons.append("posted in %d channels" % len(channels))

    detail = ", ".join(list(dict.fromkeys(reasons))[:4])
    actionable = _has_content_signal(reasons)

    if actionable and score >= cfg.get("scam_threshold", 5):
        repeat_offender = _tracker.note_scam(guild_id, user_id, now=now)
        purge = cfg.get("purge_on_scam", True)
        if repeat_offender and cfg.get("ban_on_repeat", True):
            return Verdict("ban", "Repeat scam/referral spam (%s)" % detail,
                           score=score, reasons=reasons, purge=True)

        action = str(cfg.get("scam_action", "timeout")).lower()
        if action not in ("warn", "timeout", "ban"):
            action = "timeout"
        reason = "Scam/referral spam (%s)" % detail
        if action == "ban":
            return Verdict("ban", reason, score=score, reasons=reasons, purge=True)
        if action == "warn":
            return Verdict("warn", reason, score=score, reasons=reasons, purge=purge)
        return Verdict("timeout", reason, score=score, reasons=reasons,
                       timeout_minutes=cfg.get("scam_timeout_minutes", 60),
                       purge=purge)

    # --- Image reuse, on its own ---
    # These stand apart from the scam score: a raid posts the picture with no
    # wording at all, so there is no content signal to require.
    if image_accounts >= cfg.get("image_raid_accounts", 3):
        return Verdict("timeout",
                       "Image raid (same image from %d accounts)" % image_accounts,
                       score=score, reasons=reasons,
                       timeout_minutes=cfg.get("scam_timeout_minutes", 60), purge=True)

    if image_repeats >= cfg.get("image_dupe_limit", 3):
        _tracker.clear(guild_id, user_id)
        return Verdict("timeout", "Repeated the same image %dx" % image_repeats,
                       score=score, reasons=reasons,
                       timeout_minutes=cfg.get("rate_timeout_minutes", 5), purge=True)

    # --- Duplicate flooding ---
    if fingerprint and repeats >= cfg.get("duplicate_limit", 3):
        _tracker.clear(guild_id, user_id)
        return Verdict("timeout", "Repeated the same message %dx" % repeats,
                       score=score, reasons=reasons,
                       timeout_minutes=cfg.get("rate_timeout_minutes", 5), purge=True)

    # --- Attachment flooding ---
    if attachments and attachments >= cfg.get("attachment_limit", 5):
        return Verdict("delete", "Attachment flood (%d files)" % attachments,
                       score=score, reasons=reasons)

    # --- Rate flooding (the original rule, with the leak fixed) ---
    window = cfg.get("rate_window", 6.0)
    burst = [h for h in history if now - h[0] < window]
    if len(burst) >= cfg.get("rate_limit", 5):
        _tracker.clear(guild_id, user_id)
        return Verdict("timeout", "Spam (%d messages in %gs)" % (len(burst), window),
                       score=score, reasons=reasons,
                       timeout_minutes=cfg.get("rate_timeout_minutes", 5))

    # Borderline content still loses the message even if it misses the threshold.
    soft = max(3, cfg.get("scam_threshold", 5) - 2)
    if actionable and score >= soft and (attachments or extract_domains(text)):
        return Verdict("delete", "Suspected advertising (%s)" % detail,
                       score=score, reasons=reasons)

    return NO_ACTION
