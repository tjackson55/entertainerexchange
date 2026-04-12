from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import json
import re

REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "EntertainersExchangeProfileEnrichment/1.0"
MAX_NEWS_ITEMS = 4
MAX_PROJECT_ITEMS = 4
MAX_EVENT_ITEMS = 4
NOISE_KEYWORDS = {
    "trial", "lawsuit", "legal", "court", "battle", "wedding", "dating", "rumor", "rumour"
}
NOISY_SOURCES = {
    "tmz", "page six", "daily mail", "pinkvilla", "aol.com", "the independent"
}
PREFERRED_SOURCE_ORDER = {
    "variety": 0,
    "deadline": 1,
    "the hollywood reporter": 2,
    "billboard": 3,
    "rolling stone": 4,
    "espn": 5,
    "nba": 6,
    "nfl": 7,
    "mlb": 8,
    "fifa": 9,
    "vogue.com": 10,
    "people.com": 11,
}

CATEGORY_PROJECT_KEYWORDS = {
    "musician": {"album", "single", "ep", "release", "soundtrack", "track", "mixtape", "catalog"},
    "actor": {"film", "movie", "series", "season", "casting", "cast", "role", "production", "premiere", "trailer"},
    "tv": {"series", "season", "episode", "show", "premiere", "renewed", "renewal", "special"},
    "athlete": {"contract", "season", "trade", "playoffs", "schedule", "injury", "return", "finals"},
    "comedian": {"special", "tour", "show", "series", "podcast", "stand-up"},
    "creator": {"series", "podcast", "collab", "campaign", "drop", "launch", "video", "season"},
}

CATEGORY_EVENT_KEYWORDS = {
    "musician": {"tour", "festival", "concert", "residency", "dates", "tickets", "show"},
    "actor": {"premiere", "festival", "opening night", "screening", "release date"},
    "tv": {"premiere", "finale", "release date", "screening", "panel"},
    "athlete": {"match", "playoff", "final", "semifinal", "schedule", "season opener", "fixture"},
    "comedian": {"tour", "show", "tickets", "festival", "set"},
    "creator": {"appearance", "event", "panel", "festival", "drop"},
}

CATEGORY_PREFERRED_SOURCES = {
    "musician": {"billboard", "rolling stone", "variety", "deadline", "apple music", "spotify"},
    "actor": {"variety", "deadline", "the hollywood reporter", "imdb", "tmdb", "vogue.com"},
    "tv": {"variety", "deadline", "the hollywood reporter", "imdb", "tmdb"},
    "athlete": {"espn", "nba", "nfl", "mlb", "fifa"},
    "comedian": {"variety", "deadline", "rolling stone", "youtube"},
    "creator": {"variety", "deadline", "youtube", "spotify"},
}

STOPWORDS = {
    "a", "an", "and", "at", "for", "from", "in", "of", "on", "or", "the", "to", "with"
}


def _http_get_json(url: str) -> dict | list | None:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _http_get_text(url: str) -> str | None:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _google_news_rss(query: str) -> list[dict]:
    feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    body = _http_get_text(feed_url)
    if not body:
        return []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []

    items: list[dict] = []
    for item in root.findall("./channel/item")[:10]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "Google News").strip()
        pub_date = _parse_rss_date(item.findtext("pubDate"))
        if title and link:
            items.append({
                "title": title,
                "url": link,
                "source": source or "Google News",
                "publishedAt": pub_date,
            })
    return items


def _source_priority(source: object) -> int:
    normalized = str(source or "").strip().lower()
    return PREFERRED_SOURCE_ORDER.get(normalized, 50)


def _normalize_source(source: object) -> str:
    return str(source or "").strip().lower()


def _published_timestamp(value: object) -> float:
    candidate = str(value or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).timestamp()
    except ValueError:
        return 0.0


def _category_keywords(category: str, keyword_map: dict[str, set[str]]) -> set[str]:
    return keyword_map.get(category, keyword_map.get("creator", set()))


def _is_noise_headline(title: str, source: object) -> bool:
    lowered = title.lower()
    normalized_source = _normalize_source(source)
    return any(word in lowered for word in NOISE_KEYWORDS) or normalized_source in NOISY_SOURCES


def _relevance_score(title: str, category: str, source: object) -> int:
    lowered = title.lower()
    normalized_source = _normalize_source(source)
    score = 0

    preferred_sources = CATEGORY_PREFERRED_SOURCES.get(category, set())
    if normalized_source in preferred_sources:
        score += 5
    if normalized_source in PREFERRED_SOURCE_ORDER:
        score += 3

    project_keywords = _category_keywords(category, CATEGORY_PROJECT_KEYWORDS)
    event_keywords = _category_keywords(category, CATEGORY_EVENT_KEYWORDS)
    score += sum(2 for keyword in project_keywords if keyword in lowered)
    score += sum(2 for keyword in event_keywords if keyword in lowered)

    if "official" in normalized_source:
        score += 4
    if _is_noise_headline(title, source):
        score -= 8

    return score


def _sort_headlines(items: list[dict], category: str) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            _source_priority(item.get("source")),
            -_relevance_score(str(item.get("title", "")), category, item.get("source")),
            -_published_timestamp(item.get("publishedAt")),
        ),
    )


def _filter_news_items(headlines: list[dict], category: str) -> list[dict]:
    ranked = _sort_headlines(headlines, category)
    strong_items = [
        item for item in ranked
        if not _is_noise_headline(str(item.get("title", "")), item.get("source"))
        and _relevance_score(str(item.get("title", "")), category, item.get("source")) >= 3
    ]
    return strong_items[:MAX_NEWS_ITEMS] if len(strong_items) >= 2 else ranked[:MAX_NEWS_ITEMS]


def _parse_rss_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clean_headline(title: str) -> str:
    cleaned = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
    return cleaned or title.strip()


def _dedupe_by_title(items: list[dict], key: str = "title") -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        value = str(item.get(key, "")).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(item)
    return deduped


def _extract_candidate_labels(name: str, category: str, headlines: list[dict]) -> tuple[list[dict], list[dict]]:
    project_items: list[dict] = []
    event_items: list[dict] = []
    project_keywords = _category_keywords(category, CATEGORY_PROJECT_KEYWORDS)
    event_keywords = _category_keywords(category, CATEGORY_EVENT_KEYWORDS)

    for item in headlines:
        title = _clean_headline(str(item.get("title", "")))
        url = str(item.get("url", "")).strip()
        if not title or not url:
            continue

        lowered = title.lower()
        source = str(item.get("source", "Google News"))
        published_at = item.get("publishedAt") or ""

        if _is_noise_headline(title, source):
            continue

        if any(word in lowered for word in event_keywords) and _relevance_score(title, category, source) >= 3:
            event_items.append({
                "title": title,
                "date": published_at[:10] if published_at else "Current",
                "link": url,
                "source": source,
            })

        if any(word in lowered for word in project_keywords) and _relevance_score(title, category, source) >= 3:
            project_items.append({
                "title": title,
                "link": url,
                "source": source,
            })

    return _dedupe_by_title(project_items)[:MAX_PROJECT_ITEMS], _dedupe_by_title(event_items)[:MAX_EVENT_ITEMS]


def _music_projects(name: str) -> list[dict]:
    url = f"https://itunes.apple.com/search?term={quote_plus(name)}&entity=album&limit=6"
    payload = _http_get_json(url)
    if not isinstance(payload, dict):
        return []

    results: list[dict] = []
    for item in payload.get("results", []):
        collection_name = str(item.get("collectionName", "")).strip()
        collection_url = str(item.get("collectionViewUrl", "")).strip()
        artist_name = str(item.get("artistName", "")).strip().lower()
        if not collection_name or not collection_url:
            continue
        if artist_name and name.lower() not in artist_name:
            continue
        results.append({
            "title": collection_name,
            "link": collection_url,
            "source": "Apple Music",
        })
    return _dedupe_by_title(results)[:MAX_PROJECT_ITEMS]


def _fallback_project_sources(name: str, category: str) -> list[dict]:
    encoded_name = quote_plus(name)
    if category == "musician":
        return [
            {"title": "Spotify Catalog", "link": f"https://open.spotify.com/search/{encoded_name}", "source": "Spotify"},
            {"title": "Apple Music Releases", "link": f"https://music.apple.com/us/search?term={encoded_name}", "source": "Apple Music"},
        ]
    if category in {"actor", "tv"}:
        return [
            {"title": "IMDb Credits", "link": f"https://www.imdb.com/find/?q={encoded_name}&ref_=nv_sr_sm", "source": "IMDb"},
            {"title": "Industry Coverage", "link": f"https://deadline.com/?s={encoded_name}", "source": "Deadline"},
        ]
    if category == "athlete":
        return [
            {"title": "ESPN Coverage", "link": f"https://www.espn.com/search/_/q/{encoded_name}", "source": "ESPN"},
            {"title": "Schedule Search", "link": f"https://www.google.com/search?q={encoded_name}+schedule", "source": "Google"},
        ]
    return [
        {"title": "Current Coverage", "link": f"https://news.google.com/search?q={encoded_name}", "source": "Google News"},
        {"title": "Video Coverage", "link": f"https://www.youtube.com/results?search_query={encoded_name}", "source": "YouTube"},
    ]


def _fallback_event_sources(name: str, category: str) -> list[dict]:
    encoded_name = quote_plus(name)
    if category == "musician":
        return [
            {"title": f"{name} live dates", "date": "Live lookup", "link": f"https://www.songkick.com/search?query={encoded_name}", "source": "Songkick"},
            {"title": f"{name} tickets", "date": "Live lookup", "link": f"https://www.ticketmaster.com/search?q={encoded_name}", "source": "Ticketmaster"},
        ]
    if category == "athlete":
        return [
            {"title": f"{name} upcoming schedule", "date": "Live lookup", "link": f"https://www.espn.com/search/_/q/{encoded_name}", "source": "ESPN"},
        ]
    return [
        {"title": f"{name} upcoming appearances", "date": "Live lookup", "link": f"https://www.google.com/search?q={encoded_name}+upcoming", "source": "Google"},
    ]


def _fallback_news_sources(name: str, category: str) -> list[dict]:
    encoded_name = quote_plus(name)
    if category == "musician":
        return [
            {"kind": "trade", "badge": "Trade", "title": f"{name} in Billboard coverage", "source": "Billboard", "url": f"https://www.billboard.com/?s={encoded_name}", "publishedAt": None},
            {"kind": "trade", "badge": "Trade", "title": f"{name} in Rolling Stone coverage", "source": "Rolling Stone", "url": f"https://www.rollingstone.com/search/{encoded_name}/", "publishedAt": None},
        ]
    if category in {"actor", "tv"}:
        return [
            {"kind": "trade", "badge": "Trade", "title": f"{name} in Variety coverage", "source": "Variety", "url": f"https://variety.com/?s={encoded_name}", "publishedAt": None},
            {"kind": "trade", "badge": "Trade", "title": f"{name} in Deadline coverage", "source": "Deadline", "url": f"https://deadline.com/?s={encoded_name}", "publishedAt": None},
        ]
    if category == "athlete":
        return [
            {"kind": "coverage", "badge": "Coverage", "title": f"{name} in ESPN coverage", "source": "ESPN", "url": f"https://www.espn.com/search/_/q/{encoded_name}", "publishedAt": None},
            {"kind": "coverage", "badge": "Coverage", "title": f"{name} in current sports coverage", "source": "Google News", "url": f"https://news.google.com/search?q={encoded_name}", "publishedAt": None},
        ]
    return [
        {"kind": "coverage", "badge": "Coverage", "title": f"{name} in current coverage", "source": "Google News", "url": f"https://news.google.com/search?q={encoded_name}", "publishedAt": None},
        {"kind": "trade", "badge": "Trade", "title": f"{name} in Variety coverage", "source": "Variety", "url": f"https://variety.com/?s={encoded_name}", "publishedAt": None},
    ]


def build_profile_enrichment(name: str, category: str) -> dict:
    cleaned_name = (name or "").strip()
    cleaned_category = (category or "creator").strip().lower()
    if not cleaned_name:
        return {"projects": [], "upcomingEvents": [], "news": [], "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z")}

    headlines = _filter_news_items(_google_news_rss(cleaned_name), cleaned_category)
    news = [
        {
            "kind": "coverage",
            "badge": "Coverage",
            "title": _clean_headline(item["title"]),
            "source": item["source"],
            "url": item["url"],
            "publishedAt": item.get("publishedAt"),
        }
        for item in headlines[:MAX_NEWS_ITEMS]
    ]
    if len(news) < MAX_NEWS_ITEMS:
        news = _dedupe_by_title(news + _fallback_news_sources(cleaned_name, cleaned_category))[:MAX_NEWS_ITEMS]

    extracted_projects, extracted_events = _extract_candidate_labels(cleaned_name, cleaned_category, headlines)
    music_projects = _music_projects(cleaned_name) if cleaned_category == "musician" else []

    projects = _dedupe_by_title(music_projects + extracted_projects + _fallback_project_sources(cleaned_name, cleaned_category))[:MAX_PROJECT_ITEMS]
    upcoming_events = _dedupe_by_title(extracted_events + _fallback_event_sources(cleaned_name, cleaned_category))[:MAX_EVENT_ITEMS]

    return {
        "projects": projects,
        "upcomingEvents": upcoming_events,
        "news": news,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
