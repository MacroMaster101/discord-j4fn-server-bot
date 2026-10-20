"""Checks for the auto-mod detection engine.

Run with `python test_automod.py` -- no test framework needed, so it works in the
same slim container the bot ships in.
"""

import os
import sys
import time

import automod

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


def fresh(**overrides):
    """A config built from defaults, so a local data/automod.json cannot skew results."""
    cfg = dict(automod.DEFAULTS)
    cfg.update(overrides)
    return cfg


def verdict_for(text, *, user=1, channel=10, t=1000.0, cfg=None, **kwargs):
    return automod.evaluate(
        text=text, guild_id=1, user_id=user, channel_id=channel,
        config=cfg or fresh(), now=t, **kwargs
    )


# ----------------- scoring -----------------

print("\nScam samples are caught")
automod.reset_state()

SCAM = [
    ("mrbeast casino", "I am giving away $3,500 to everyone who registers on my new "
                       "crypto casino. Claim your reward at fabwin.com", 4),
    ("promo code", "use promo code CASH for a free bonus at luckywin.vip", 1),
    ("rakeback proof", "Rakeback bonus! Withdrawal success $3700 -> payday.top", 2),
    ("nitro phish", "FREE NITRO GIVEAWAY https://discord-nitro.ru/claim", 0),
    ("obfuscated", "fr33 m0ney c a s i n o pr0mo c0de at luckywin.vip", 2),
    ("telegram bait", "Easy money daily profit, dm me on telegram, usdt payouts "
                      "https://cutt.ly/abc", 1),
]
for name, text, atts in SCAM:
    automod.reset_state()
    v = verdict_for(text, attachments=atts)
    check(name, v.action in ("timeout", "ban", "delete"),
          "-> %r" % (v,))


print("\nOrdinary chat is left alone")
LEGIT = [
    ("plain chat", "hey guys anyone up for valorant tonight?", 0),
    ("clip link", "check out this clip https://medal.tv/clips/123", 0),
    ("money talk", "I lost $50 betting on that match lol", 0),
    ("screenshots", "here are my screenshots from the tournament", 4),
    ("youtube", "watch this https://youtube.com/watch?v=abc", 0),
    ("own blog", "wrote it up here https://someblog.dev/post with a screenshot", 1),
    ("shortener only", "short link https://bit.ly/abc", 0),
    ("casual money", "that skin costs 20 usd now", 0),
    ("github", "PR is up https://github.com/me/repo/pull/3", 0),
]
for name, text, atts in LEGIT:
    automod.reset_state()
    v = verdict_for(text, attachments=atts)
    check(name, not v, "-> %r" % (v,))


# ----------------- discrete rules -----------------

print("\nDiscrete rules")
automod.reset_state()
v = verdict_for("join my server https://discord.gg/abc123")
check("invite deleted", v.action == "delete", "-> %r" % (v,))

automod.reset_state()
v = verdict_for("@everyone free stuff", mentions_everyone=True)
check("@everyone timed out", v.action == "timeout", "-> %r" % (v,))

automod.reset_state()
v = verdict_for("hi all", mention_count=6)
check("mention storm timed out", v.action == "timeout", "-> %r" % (v,))

automod.reset_state()
v = verdict_for("hello", attachments=6)
check("attachment flood deleted", v.action == "delete", "-> %r" % (v,))


# ----------------- flood rules -----------------

print("\nFlood rules")
automod.reset_state()
last = None
for i in range(5):
    last = verdict_for("message %d" % i, t=1000.0 + i * 0.5)
check("rate flood timed out", last.action == "timeout", "-> %r" % (last,))

automod.reset_state()
last = None
for i in range(3):
    last = verdict_for("buy my stuff", t=1000.0 + i * 5)
check("duplicate flood timed out", last.action == "timeout", "-> %r" % (last,))

automod.reset_state()
last = None
for i, ch in enumerate((10, 11, 12)):
    last = verdict_for("check my page someshop.xyz", channel=ch, t=1000.0 + i * 5,
                       attachments=1)
check("cross-posting escalates", last.action in ("timeout", "delete", "ban"),
      "-> %r" % (last,))


# ----------------- context signals -----------------

print("\nContext signals")
automod.reset_state()
borderline = "check out luckywin.vip for free spins"
old = verdict_for(borderline, user=2, attachments=0, account_age_days=900,
                  join_age_hours=9000)
automod.reset_state()
new = verdict_for(borderline, user=3, attachments=0, account_age_days=1,
                  join_age_hours=2)
check("new accounts score higher", new.score > old.score,
      "old=%d new=%d" % (old.score, new.score))


# ----------------- escalation -----------------

print("\nEscalation")
automod.reset_state()
scam = "giving away free money, use promo code WIN at fabwin.com"
first = verdict_for(scam, user=7, t=1000.0, attachments=1)
second = verdict_for(scam, user=7, channel=11, t=1200.0, attachments=1)
check("first scam hit times out", first.action == "timeout", "-> %r" % (first,))
check("repeat scam hit bans", second.action == "ban", "-> %r" % (second,))


# ----------------- first-hit action -----------------

print("\nFirst-hit action is configurable")
automod.reset_state()
v = verdict_for(scam, user=11, attachments=1, cfg=fresh(scam_action="warn"))
check("warn mode warns", v.action == "warn", "-> %r" % (v,))

automod.reset_state()
v = verdict_for(scam, user=12, attachments=1, cfg=fresh(scam_action="ban"))
check("ban mode bans on first hit", v.action == "ban", "-> %r" % (v,))

automod.reset_state()
v = verdict_for(scam, user=13, attachments=1, cfg=fresh(scam_action="nonsense"))
check("unknown mode falls back to timeout", v.action == "timeout", "-> %r" % (v,))

automod.reset_state()
cfg = fresh(scam_action="warn")
first = verdict_for(scam, user=14, t=1000.0, attachments=1, cfg=cfg)
second = verdict_for(scam, user=14, channel=11, t=1200.0, attachments=1, cfg=cfg)
check("warn mode still bans a repeat", second.action == "ban", "-> %r" % (second,))

check("save_config rejects a bad action",
      automod.save_config({"scam_action": "explode"})["scam_action"] in
      ("warn", "timeout", "ban"))


# ----------------- signal toggles -----------------

print("\nSignal categories can be switched off")
automod.reset_state()
gambling = "join this casino and use promo code WIN at somewhere.xyz"
on = verdict_for(gambling, user=21, attachments=1)
automod.reset_state()
off = verdict_for(gambling, user=22, attachments=1,
                  cfg=fresh(disabled_signals=["gambling"]))
check("disabling gambling lowers the score", off.score < on.score,
      "on=%d off=%d" % (on.score, off.score))
check("disabled label is gone", "gambling" not in off.reasons,
      "-> %r" % (off.reasons,))

automod.reset_state()
v = verdict_for("I won $3,500 last night", user=23,
                cfg=fresh(disabled_signals=["money amount"]))
check("disabling money amounts zeroes it", v.score == 0, "-> %r" % (v,))

automod.reset_state()
crypto = "usdt airdrop, dm me to claim your reward at payday.top"
full = verdict_for(crypto, user=24)
automod.reset_state()
trimmed = verdict_for(crypto, user=25,
                      cfg=fresh(disabled_signals=["crypto bait", "dm bait"]))
check("disabling two categories compounds", trimmed.score < full.score,
      "full=%d trimmed=%d" % (full.score, trimmed.score))

check("every toggleable signal has a weight",
      all(isinstance(w, int) and w > 0 for _, w in automod.TOGGLEABLE_SIGNALS),
      "-> %r" % (automod.TOGGLEABLE_SIGNALS,))
check("keyword categories are all toggleable",
      automod.KEYWORD_LABELS.issubset({l for l, _ in automod.TOGGLEABLE_SIGNALS}))


# ----------------- image reuse -----------------

print("\nImage reuse")


def make_png(seed, size=64):
    """A deterministic test image; different seeds look clearly different."""
    if not automod.PIL_AVAILABLE:
        return None
    from PIL import Image
    import io as _io
    img = Image.new("L", (size, size))
    img.putdata([(x * seed + y * (seed + 3)) % 256
                 for y in range(size) for x in range(size)])
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def shot(seed):
    """Fingerprint for a test image, whichever backend is available."""
    data = make_png(seed)
    if data is not None:
        return automod.fingerprint_image(data)
    return automod.fingerprint_meta(1000 + seed, 64, 64)


automod.reset_state()
one = shot(1)
last = None
for i in range(3):
    last = verdict_for("", user=31, channel=10 + i, t=1000.0 + i * 5, images=[one])
check("same image 3x is caught", last.action == "timeout", "-> %r" % (last,))

automod.reset_state()
last = None
for i, uid in enumerate((41, 42, 43)):
    last = verdict_for("", user=uid, channel=10 + i, t=1000.0 + i * 5, images=[one])
check("image raid across accounts is caught", last.action == "timeout",
      "-> %r" % (last,))
check("raid reason names the accounts", "accounts" in last.reason,
      "-> %r" % (last.reason,))

automod.reset_state()
last = None
for i in range(3):
    last = verdict_for("", user=51, channel=10 + i, t=1000.0 + i * 5,
                       images=[shot(i + 10)])
check("different images are left alone", not last, "-> %r" % (last,))

automod.reset_state()
first = verdict_for("", user=61, t=1000.0, images=[one])
check("a single image is fine", not first, "-> %r" % (first,))

automod.reset_state()
stale = verdict_for("", user=71, t=1000.0, images=[one])
fresh_again = verdict_for("", user=71, t=1000.0 + 10000, images=[one])
check("the window expires old images", not fresh_again, "-> %r" % (fresh_again,))

automod.reset_state()
off = fresh(image_checks=False)
last = None
for i in range(4):
    last = verdict_for("", user=81, channel=10 + i, t=1000.0 + i * 5,
                       images=[one], cfg=off)
check("image checks can be switched off", not last, "-> %r" % (last,))

automod.reset_state()
captioned = verdict_for("claim your reward", user=91, t=1000.0, images=[one])
captioned2 = verdict_for("claim your reward", user=92, channel=11, t=1005.0,
                         images=[one])
check("a reused image raises the text score", captioned2.score > captioned.score,
      "%d -> %d" % (captioned.score, captioned2.score))


print("\nBlocked image list")
# Point the store at a scratch file so a real data/blocked_images.json is untouched.
_real_store = automod.BLOCKED_IMAGES_FILE
automod.BLOCKED_IMAGES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "_test_blocked.json")
if os.path.exists(automod.BLOCKED_IMAGES_FILE):
    os.remove(automod.BLOCKED_IMAGES_FILE)
automod.reset_blocked_cache()

scam_shot = shot(77)
entry = automod.add_blocked_image(1, scam_shot, note="mrbeast casino", moderator="mod")
check("an image can be blocked", entry is not None and entry["id"], "-> %r" % (entry,))
check("blocking is idempotent",
      automod.add_blocked_image(1, scam_shot, note="again") is None)
check("the block is listed", len(automod.blocked_images(1)) == 1)
check("other guilds are unaffected", automod.blocked_images(2) == [])

automod.reset_state()
v = verdict_for("", user=101, t=1000.0, images=[scam_shot])
check("a blocked image is caught on the FIRST post", v.action == "timeout",
      "-> %r" % (v,))
check("the reason names the note", "mrbeast casino" in v.reason, "-> %r" % (v.reason,))

automod.reset_state()
v = verdict_for("", user=102, t=1000.0, images=[shot(78)])
check("an unrelated image still passes", not v, "-> %r" % (v,))

automod.reset_state()
v = automod.evaluate(text="", guild_id=2, user_id=103, channel_id=10,
                     images=[scam_shot], now=1000.0, config=fresh())
check("the block does not leak across guilds", not v, "-> %r" % (v,))

check("it survives a reload", (automod.reset_blocked_cache() or
                               len(automod.blocked_images(1))) == 1)

if automod.PIL_AVAILABLE:
    import io as _io2
    from PIL import Image as _Img2
    buf = _io2.BytesIO()
    with _Img2.open(_io2.BytesIO(make_png(77))) as im:
        im.convert("RGB").save(buf, format="JPEG", quality=70)
    automod.reset_state()
    v = verdict_for("", user=104, t=1000.0,
                    images=[automod.fingerprint_image(buf.getvalue())])
    check("a re-encoded copy is still blocked", v.action == "timeout", "-> %r" % (v,))

check("an entry can be removed",
      automod.remove_blocked_image(1, entry["id"]) is True)
check("removing twice reports nothing",
      automod.remove_blocked_image(1, entry["id"]) is False)

automod.reset_state()
v = verdict_for("", user=105, t=1000.0, images=[scam_shot])
check("an unblocked image passes again", not v, "-> %r" % (v,))

try:
    os.remove(automod.BLOCKED_IMAGES_FILE)
except OSError:
    pass
automod.BLOCKED_IMAGES_FILE = _real_store
automod.reset_blocked_cache()


print("\nCloud OCR gating")
_real_ocr_cache = automod.OCR_CACHE_FILE
automod.OCR_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "_test_ocr.json")
if os.path.exists(automod.OCR_CACHE_FILE):
    os.remove(automod.OCR_CACHE_FILE)
automod.reset_ocr_cache()

on = fresh(ocr_enabled=True)
pic = [shot(5)]

check("off by default", automod.DEFAULTS["ocr_enabled"] is False)
check("disabled means never",
      automod.should_ocr(text_score=0, images=pic, config=fresh())[0] is False)
check("no images means never",
      automod.should_ocr(text_score=0, images=[], config=on)[0] is False)

ok, why = automod.should_ocr(text_score=0, images=pic, has_roles=False,
                             account_age_days=1, join_age_hours=1, config=on)
check("a fresh account with images is read", ok, "-> %s" % why)

ok, why = automod.should_ocr(text_score=9, images=pic, has_roles=False,
                             account_age_days=1, config=on)
check("already-damning text skips the call", not ok, "-> %s" % why)

ok, why = automod.should_ocr(text_score=0, images=pic, has_roles=True,
                             account_age_days=900, join_age_hours=9000, config=on)
check("an established member is skipped", not ok, "-> %s" % why)

ok, why = automod.should_ocr(text_score=0, images=pic, has_roles=True,
                             account_age_days=1, join_age_hours=1, config=on)
check("a role does not excuse a brand-new account", ok, "-> %s" % why)

ok, _ = automod.should_ocr(text_score=0, images=pic, has_roles=True,
                           account_age_days=900, join_age_hours=9000,
                           config=fresh(ocr_enabled=True, ocr_only_untrusted=False))
check("the trust gate can be switched off", ok)

print("\nOCR budget")
automod.reset_ocr_cache()
capped = fresh(ocr_enabled=True, ocr_max_per_hour=3)
check("budget starts full", automod.ocr_budget_left(capped) == 3)
for _ in range(3):
    automod.ocr_note_call()
check("budget is consumed", automod.ocr_budget_left(capped) == 0)
check("a spent budget blocks the call",
      automod.should_ocr(text_score=0, images=pic, account_age_days=1,
                         config=capped)[0] is False)
check("the budget is hourly, not forever",
      automod.ocr_budget_left(capped, now=time.time() + 3700) == 3)

print("\nOCR cache")
automod.reset_ocr_cache()
one_shot = shot(31)
check("an unseen image is a miss", automod.ocr_cache_get(one_shot) is None)
automod.ocr_cache_put(one_shot, "claim your reward at fabwin.com")
check("a stored read comes back",
      automod.ocr_cache_get(one_shot) == "claim your reward at fabwin.com")
check("an expired read is ignored",
      automod.ocr_cache_get(one_shot, max_age_days=1,
                            now=time.time() + 3 * 86400) is None)
check("an unrelated image is still a miss",
      automod.ocr_cache_get(shot(32)) is None)

if automod.PIL_AVAILABLE:
    import io as _io3
    from PIL import Image as _Img3
    buf = _io3.BytesIO()
    with _Img3.open(_io3.BytesIO(make_png(31))) as im:
        im.convert("RGB").save(buf, format="JPEG", quality=70)
    check("a re-encoded repost hits the cache (no second call)",
          automod.ocr_cache_get(automod.fingerprint_image(buf.getvalue())) is not None)

print("\nOCR text reaches the verdict")
automod.reset_state()
silent = verdict_for("", user=201, t=1000.0, images=pic, cfg=on)
check("a captionless image alone is not enough", not silent, "-> %r" % (silent,))

automod.reset_state()
read = automod.evaluate(
    text="", guild_id=1, user_id=202, channel_id=10, attachments=1, images=pic,
    ocr_text="I am giving away $3,500 — claim your reward at fabwin.com",
    account_age_days=1, join_age_hours=1, config=on, now=1000.0)
check("words read from the image catch it", read.action in ("timeout", "ban"),
      "-> %r" % (read,))
check("the verdict says it came from the image",
      "text in image" in read.reasons, "-> %r" % (read.reasons,))

automod.reset_state()
harmless = automod.evaluate(
    text="", guild_id=1, user_id=203, channel_id=10, attachments=1, images=pic,
    ocr_text="Welcome to the server, read the rules in #info",
    account_age_days=1, config=on, now=1000.0)
check("innocent image text changes nothing", not harmless, "-> %r" % (harmless,))

try:
    os.remove(automod.OCR_CACHE_FILE)
except OSError:
    pass
automod.OCR_CACHE_FILE = _real_ocr_cache
automod.reset_ocr_cache()


print("\nOCR word-joining is handled")
# RapidOCR output from the benchmark: spaces lost between words.
joined = "WithdrawalSuccess! YourWithdrawalof wassuccessfully claimyourreward"
check("despacing recovers joined phrases",
      automod.score_content(joined)[0] > 0,
      "-> %r" % (automod.score_content(joined),))
check("despacing does not fire on ordinary chat",
      automod.score_content("anyone up for a game tonight")[0] == 0)
check("short phrases are not despace-matched",
      "gamble" not in automod.score_content("gam ble")[1])


print("\nFingerprint helpers")
check("metadata fingerprints match on identical files",
      automod.images_match(automod.fingerprint_meta(5000, 1170, 2532),
                           automod.fingerprint_meta(5000, 1170, 2532)))
check("metadata fingerprints differ on different files",
      not automod.images_match(automod.fingerprint_meta(5000, 1170, 2532),
                               automod.fingerprint_meta(5001, 1170, 2532)))
check("empty metadata is rejected", automod.fingerprint_meta(0) is None)
check("garbage bytes do not raise", automod.fingerprint_image(b"not an image")
      is not None)
check("garbage bytes have no perceptual hash",
      automod.fingerprint_image(b"not an image")["perceptual"] is None)
check("empty bytes are rejected", automod.fingerprint_image(b"") is None)
check("hamming tolerance is respected",
      automod.images_match({"exact": "a", "perceptual": 0},
                           {"exact": "b", "perceptual": 0b1111}, distance=6))
check("distant hashes do not match",
      not automod.images_match({"exact": "a", "perceptual": 0},
                               {"exact": "b", "perceptual": (1 << 40) - 1},
                               distance=6))

if automod.PIL_AVAILABLE:
    png = make_png(1)
    check("dhash is deterministic", automod.dhash(png) == automod.dhash(png))
    check("dhash is 64 bits", 0 <= automod.dhash(png) < (1 << 64))
    check("different images hash differently",
          automod.dhash(make_png(1)) != automod.dhash(make_png(9)))

    # Re-encoding as JPEG is what a reposted screenshot actually goes through.
    from PIL import Image as _Img
    import io as _io
    buf = _io.BytesIO()
    with _Img.open(_io.BytesIO(png)) as im:
        im.convert("RGB").save(buf, format="JPEG", quality=72)
    requantised = buf.getvalue()
    check("a re-encoded image still matches",
          automod.images_match(automod.fingerprint_image(png),
                               automod.fingerprint_image(requantised),
                               distance=automod.DEFAULTS["image_hash_distance"]),
          "distance=%d" % bin(automod.dhash(png) ^ automod.dhash(requantised)).count("1"))

    buf = _io.BytesIO()
    with _Img.open(_io.BytesIO(png)) as im:
        im.resize((im.width // 2, im.height // 2)).save(buf, format="PNG")
    check("a resized image still matches",
          automod.images_match(automod.fingerprint_image(png),
                               automod.fingerprint_image(buf.getvalue()),
                               distance=automod.DEFAULTS["image_hash_distance"]))
else:
    print("  SKIP  Pillow not installed; perceptual hashing not exercised")


# ----------------- exemptions -----------------

print("\nExemptions")
automod.reset_state()
v = verdict_for(scam, cfg=fresh(enabled=False), attachments=2)
check("disabled filter does nothing", not v, "-> %r" % (v,))

automod.reset_state()
v = verdict_for(scam, channel=99, cfg=fresh(exempt_channels=["99"]), attachments=2)
check("exempt channel skipped", not v, "-> %r" % (v,))

automod.reset_state()
v = automod.evaluate(text=scam, guild_id=1, user_id=5, channel_id=10, attachments=2,
                     role_ids=[42], config=fresh(exempt_roles=["42"]), now=1000.0)
check("exempt role skipped", not v, "-> %r" % (v,))


# ----------------- admin lists -----------------

print("\nAdmin lists")
automod.reset_state()
v = verdict_for("my page is at neutralsite.com",
                cfg=fresh(block_domains=["neutralsite.com"]))
check("blocked domain caught", v.action in ("timeout", "delete"), "-> %r" % (v,))

automod.reset_state()
v = verdict_for("free money at goodsite.com, dm me",
                cfg=fresh(allow_domains=["goodsite.com"], scam_threshold=7))
check("allowed domain lowers score", v.score < 7, "-> %r" % (v,))

automod.reset_state()
v = verdict_for("selling cheap vbucks here shop.xyz",
                cfg=fresh(extra_keywords=["vbucks"]), attachments=1)
check("custom keyword caught", bool(v), "-> %r" % (v,))


# ----------------- helpers -----------------

print("\nHelpers")
check("normalize flattens leetspeak",
      "casino" in automod.normalize("C A S I N O"), automod.normalize("C A S I N O"))
check("normalize strips zero width",
      automod.normalize("fr​ee") == "free", automod.normalize("fr​ee"))
check("domains extracted",
      automod.extract_domains("go to https://Fabwin.com/ref/9 now") == ["fabwin.com"],
      automod.extract_domains("go to https://Fabwin.com/ref/9 now"))

print("\n%d checks failed" % len(FAILURES))
if FAILURES:
    for name in FAILURES:
        print("  - %s" % name)
sys.exit(1 if FAILURES else 0)
