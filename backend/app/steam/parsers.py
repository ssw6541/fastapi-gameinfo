"""Transformation layer: raw Steam payloads -> stable internal shapes.

The frontend only ever sees the shapes produced here, so upstream format changes are absorbed in this file.
"""
import html
import re
from datetime import datetime, timezone

IMG_BASE = "https://cdn.cloudflare.steamstatic.com/steam/apps"

# Steam store tag ids that correspond to top-level genres (stable ids used by store search).
GENRE_TAGS: dict[int, tuple[str, str]] = {
    19: ("Action", "액션"),
    21: ("Adventure", "어드벤처"),
    122: ("RPG", "RPG"),
    9: ("Strategy", "전략"),
    599: ("Simulation", "시뮬레이션"),
    492: ("Indie", "인디"),
    597: ("Casual", "캐주얼"),
    701: ("Sports", "스포츠"),
    699: ("Racing", "레이싱"),
    128: ("Massively Multiplayer", "대규모 멀티플레이어"),
    113: ("Free to Play", "무료 플레이"),
    493: ("Early Access", "앞서 해보기"),
}

REVIEW_LANGUAGES = [
    "english", "koreana", "schinese", "tchinese", "japanese", "russian", "german", "french", "spanish",
    "latam", "brazilian", "portuguese", "turkish", "polish", "thai", "italian", "ukrainian", "czech",
    "dutch", "swedish", "vietnamese", "arabic", "hungarian", "romanian", "bulgarian", "danish", "finnish",
    "greek", "norwegian", "indonesian",
]


def header_image(appid: int) -> str:
    return f"{IMG_BASE}/{appid}/header.jpg"


def capsule_image(appid: int) -> str:
    return f"{IMG_BASE}/{appid}/capsule_231x87.jpg"


# ---------------------------------------------------------------- text helpers
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(?:p|div|h[1-6]|li|ul|ol|tr|table)[^>]*>|<br\s*/?>", re.I)


def html_to_text(src: str | None) -> str:
    """Strip HTML to plain text (never forward upstream HTML to the browser)."""
    if not src:
        return ""
    t = _BLOCK.sub("\n", src)
    t = _TAG.sub("", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


_BB_DROP = re.compile(r"\[(?:img|previewyoutube|video)[^\]]*\].*?\[/(?:img|previewyoutube|video)\]", re.I | re.S)
_BB_TAG = re.compile(r"\[/?(?:h[1-3]|b|i|u|strike|spoiler|quote|code|noparse|hr|table|tr|th|td|olist|url|list|p)(?:=[^\]]*)?\]", re.I)
_BB_LI = re.compile(r"\[\*\]")


def clean_review_text(t: str | None) -> str:
    if not t:
        return ""
    t = _BB_DROP.sub("", t)
    t = _BB_LI.sub("\n• ", t)
    t = _BB_TAG.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ---------------------------------------------------------------- dates
_EN_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_release_ts(text: str | None) -> int | None:
    if not text:
        return None
    text = text.strip()
    try:
        m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
        if m:
            y, mo, d = map(int, m.groups())
            return int(datetime(y, mo, d, tzinfo=timezone.utc).timestamp())
        m = re.match(r"(\d{1,2}) ([A-Za-z]{3})[a-z]*,? (\d{4})", text)
        if m:
            return int(datetime(int(m[3]), _EN_MONTHS[m[2][:3].title()], int(m[1]), tzinfo=timezone.utc).timestamp())
        m = re.match(r"([A-Za-z]{3})[a-z]* (\d{1,2}), (\d{4})", text)
        if m:
            return int(datetime(int(m[3]), _EN_MONTHS[m[1][:3].title()], int(m[2]), tzinfo=timezone.utc).timestamp())
        m = re.match(r"(\d{4})년\s*(\d{1,2})월", text)
        if m:
            return int(datetime(int(m[1]), int(m[2]), 1, tzinfo=timezone.utc).timestamp())
    except (ValueError, KeyError):
        return None
    return None


# ---------------------------------------------------------------- search page (HTML rows)
_ROW = re.compile(r'<a href="[^"]*"\s+data-ds-appid="(\d+)"(.*?)</a>', re.S)


def parse_search_html(page: str) -> list[dict]:
    rows = []
    for m in _ROW.finditer(page or ""):
        appid, body = int(m[1]), m[2]
        # bundles/packages use comma-separated ids ("123,456") and do not match \d+ followed by quote
        title = re.search(r'<span class="title">(.*?)</span>', body, re.S)
        if not title:
            continue
        tags = re.search(r'data-ds-tagids="\[([\d,\s]*)\]"', body)
        cap = re.search(r'search_capsule"><img src="([^"]+)"', body)
        rel = re.search(r'search_released[^>]*>\s*(.*?)\s*</div>', body, re.S)
        price = re.search(r'data-price-final="(\d+)"', body)
        disc = re.search(r'data-discount="(-?\d+)"', body)
        rev = re.search(r'search_review_summary[^"]*"\s+data-tooltip-html="([^"]*)"', body)
        pct = cnt = None
        if rev:
            tip = html.unescape(rev[1])
            pm = re.search(r"(\d{1,3})\s*%", tip)
            if pm:
                pct = int(pm[1])
                rest = tip.replace(pm[0], " ")
                nums = re.findall(r"\d[\d,]*", rest)
                cnt = int(nums[0].replace(",", "")) if nums else None
        release_text = html.unescape(rel[1]).strip() if rel else None
        rows.append({
            "appid": appid,
            "title": html.unescape(title[1]).strip(),
            "capsule_url": html.unescape(cap[1]) if cap and cap[1].startswith("https://") else None,
            "tag_ids": [int(x) for x in tags[1].split(",") if x.strip()] if tags else [],
            "release_date": release_text or None,
            "release_ts": parse_release_ts(release_text),
            "price_final": int(price[1]) if price else None,
            "discount_percent": int(disc[1]) if disc else 0,
            "review_pct": pct,
            "review_count": cnt,
        })
    return rows


# ---------------------------------------------------------------- appdetails
def normalize_details(ko: dict, en: dict | None = None) -> dict:
    """Merge Korean (primary) and English app details into one internal document."""
    appid = int(ko["steam_appid"])
    po = ko.get("price_overview") or None
    rel = ko.get("release_date") or {}
    plats = ko.get("platforms") or {}
    return {
        "appid": appid,
        "type": ko.get("type"),
        "name": ko.get("name"),
        "name_en": (en or ko).get("name") if en else None,
        "short_description": html_to_text(ko.get("short_description")),
        "about": html_to_text(ko.get("about_the_game") or ko.get("detailed_description")),
        "header_image": ko.get("header_image") or header_image(appid),
        "background": ko.get("background_raw") or ko.get("background"),
        "website": ko.get("website"),
        "is_free": bool(ko.get("is_free")),
        "price": ({
            "currency": po.get("currency"),
            "initial": po.get("initial", 0) / 100,
            "final": po.get("final", 0) / 100,
            "discount_percent": po.get("discount_percent", 0),
            "final_formatted": po.get("final_formatted"),
        } if po else None),
        "release_date": rel.get("date") or None,
        "coming_soon": bool(rel.get("coming_soon")),
        "developers": ko.get("developers") or [],
        "publishers": [p for p in (ko.get("publishers") or []) if p],
        "genres": [g.get("description") for g in ko.get("genres") or [] if g.get("description")],
        "categories": [c.get("description") for c in ko.get("categories") or [] if c.get("description")],
        "platforms": {"windows": bool(plats.get("windows")), "mac": bool(plats.get("mac")), "linux": bool(plats.get("linux"))},
        "supported_languages": html_to_text(ko.get("supported_languages")).replace("*", ""),
        "metacritic": ((ko.get("metacritic") or {}).get("score")),
        "recommendations": ((ko.get("recommendations") or {}).get("total")),
        "screenshots": [s.get("path_full") for s in ko.get("screenshots") or [] if s.get("path_full")][:12],
        "movies": [
            {"name": m.get("name"), "thumbnail": m.get("thumbnail"),
             "url": (m.get("mp4") or {}).get("480") or (m.get("webm") or {}).get("480"),
             "hls": m.get("hls_h264")}
            for m in (ko.get("movies") or [])[:3] if (m.get("mp4") or m.get("webm") or m.get("hls_h264"))
        ],
        "store_url": f"https://store.steampowered.com/app/{appid}",
    }


# ---------------------------------------------------------------- reviews
def normalize_review(r: dict, appid: int) -> dict | None:
    rid = r.get("recommendationid")
    if not rid:
        return None
    a = r.get("author") or {}
    return {
        "id": str(rid),
        "language": r.get("language"),
        "text": clean_review_text(r.get("review")),
        "voted_up": bool(r.get("voted_up")),
        "votes_up": int(r.get("votes_up") or 0),
        "votes_funny": int(r.get("votes_funny") or 0),
        "helpful_score": float(r.get("weighted_vote_score") or 0),
        "comment_count": int(r.get("comment_count") or 0),
        "created_at": int(r.get("timestamp_created") or 0),
        "updated_at": int(r.get("timestamp_updated") or 0),
        "playtime_forever_min": int(a.get("playtime_forever") or 0),
        "playtime_at_review_min": int(a.get("playtime_at_review") or 0),
        "author_num_reviews": int(a.get("num_reviews") or 0),
        "steam_purchase": bool(r.get("steam_purchase")),
        "received_for_free": bool(r.get("received_for_free")),
        "early_access": bool(r.get("written_during_early_access")),
        "url": f"https://steamcommunity.com/profiles/{a['steamid']}/recommended/{appid}/" if str(a.get("steamid", "")).isdigit() else None,
    }


def normalize_summary(q: dict) -> dict:
    pos, neg = int(q.get("total_positive") or 0), int(q.get("total_negative") or 0)
    total = int(q.get("total_reviews") or pos + neg)
    return {
        "score_desc": q.get("review_score_desc"),
        "score": q.get("review_score"),
        "total_positive": pos,
        "total_negative": neg,
        "total_reviews": total,
        "positive_ratio": round(pos / (pos + neg), 4) if pos + neg else None,
    }
