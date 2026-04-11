from __future__ import annotations

import argparse
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parent.parent
ENTERTAINER_FILE = ROOT_DIR / "entertainers" / "entertainer_list.json"
USER_AGENT = "EntertainersExchangeAutoDraft/1.0 (+local-only)"
REQUEST_TIMEOUT_SECONDS = 12
DEFAULT_LIMIT = 6
DEFAULT_LOOKBACK_HOURS = 96

FEED_SOURCES = (
    {"id": "variety", "name": "Variety", "url": "https://variety.com/feed/", "trust": "high", "confidence": 0.91},
    {"id": "deadline", "name": "Deadline", "url": "https://deadline.com/feed/", "trust": "high", "confidence": 0.89},
)

TAG_RULES = (
    ("tour", ("tour", "dates", "concert", "festival", "residency")),
    ("casting", ("cast", "casting", "joins", "role", "series regular")),
    ("award", ("award", "oscar", "grammy", "emmy", "nomination", "won ")),
    ("production", ("production", "filming", "shoot", "wrap", "director", "trailer")),
    ("release", ("release", "album", "single", "debut", "drop", "premiere")),
    ("appearance", ("appearance", "hosting", "interview", "performance", "cameo")),
    ("creator", ("youtube", "creator", "stream", "podcast", "channel")),
)

WHY_IT_MATTERS = {
    "tour": "Live-event news often creates an immediate and understandable attention catalyst.",
    "casting": "Casting and role confirmations usually give audiences a clear reason to reprice momentum.",
    "award": "Awards recognition can drive a clean short-term spike in attention and search interest.",
    "production": "Production milestones usually create a concrete reason for renewed audience attention.",
    "release": "Release timing updates often create a direct short-term momentum trigger.",
    "appearance": "A fresh public appearance can quickly put an entertainer back into active coverage.",
    "creator": "New creator activity tends to move attention quickly when it is tied to a clear release or platform event.",
    "update": "A timely verified update can move the conversation back toward this entertainer.",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = ascii_value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def dedupe_key(value: str) -> str:
    return normalize_text(value)


def infer_tag(text: str, profession: str = "") -> str:
    haystack = normalize_text(f"{text} {profession}")
    for tag, keywords in TAG_RULES:
        if any(keyword in haystack for keyword in keywords):
            return tag
    return "update"


def make_summary(entertainer: str, headline: str, source_name: str, profession: str, tag: str) -> str:
    profession_label = profession.lower() if profession else "entertainer"
    if tag == "tour":
        return f"{source_name} reported a live-event update tied to {entertainer}, keeping this {profession_label} in active conversation."
    if tag == "casting":
        return f"{source_name} linked {entertainer} to a fresh role or casting move, renewing attention around this {profession_label}."
    if tag == "award":
        return f"{source_name} highlighted a recognition milestone for {entertainer}, putting this {profession_label} back into the awards conversation."
    if tag == "production":
        return f"{source_name} reported a production milestone connected to {entertainer}, which can quickly restore audience momentum."
    if tag == "release":
        return f"{source_name} surfaced a release-related update for {entertainer}, giving audiences a concrete reason to pay attention now."
    if tag == "appearance":
        return f"{source_name} flagged a fresh public-facing moment for {entertainer}, pushing this {profession_label} back into active coverage."
    if tag == "creator":
        return f"{source_name} noted a creator-focused update for {entertainer}, which can move digital attention quickly when the story is timely."
    return f"{source_name} reported a timely update involving {entertainer}, putting this {profession_label} back into the current news cycle."


@dataclass(frozen=True)
class Entertainer:
    name: str
    profession: str
    normalized_name: str


def load_entertainers() -> list[Entertainer]:
    raw = json.loads(ENTERTAINER_FILE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    entertainers: list[Entertainer] = []
    for item in raw:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        normalized_name = normalize_text(name)
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        entertainers.append(
            Entertainer(
                name=name,
                profession=str(item.get("profession") or item.get("bio") or "entertainer").strip(),
                normalized_name=normalized_name,
            )
        )
    return entertainers


def match_entertainer(text: str, entertainers: Iterable[Entertainer]) -> Entertainer | None:
    normalized_text = normalize_text(text)
    best_match: Entertainer | None = None
    for entertainer in entertainers:
        pattern = rf"(^|\s){re.escape(entertainer.normalized_name)}(\s|$)"
        if re.search(pattern, normalized_text):
            if best_match is None or len(entertainer.normalized_name) > len(best_match.normalized_name):
                best_match = entertainer
    return best_match


def fetch_feed_xml(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def extract_entries(feed_xml: bytes) -> list[dict]:
    root = ET.fromstring(feed_xml)
    entries: list[dict] = []

    for item in root.findall("./channel/item"):
        source_node = item.find("source")
        entries.append(
            {
                "title": strip_html(item.findtext("title", default="")),
                "link": (item.findtext("link", default="") or "").strip(),
                "description": strip_html(item.findtext("description", default="")),
                "publishedAt": item.findtext("pubDate", default=""),
                "source": strip_html(source_node.text if source_node is not None else ""),
            }
        )

    if entries:
        return entries

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("./atom:entry", namespace):
        link_node = entry.find("atom:link", namespace)
        entries.append(
            {
                "title": strip_html(entry.findtext("atom:title", default="", namespaces=namespace)),
                "link": (link_node.attrib.get("href", "") if link_node is not None else "").strip(),
                "description": strip_html(entry.findtext("atom:summary", default="", namespaces=namespace)),
                "publishedAt": entry.findtext("atom:updated", default="", namespaces=namespace),
                "source": "",
            }
        )
    return entries


def is_recent(entry: dict, lookback_hours: int) -> bool:
    parsed = parse_iso(entry.get("publishedAt"))
    if parsed is None:
        return True
    return utc_now() - parsed <= timedelta(hours=lookback_hours)


def existing_keys(store: dict) -> set[str]:
    keys: set[str] = set()
    for item in store.get("items", []):
        if item.get("sourceUrl"):
            keys.add(f"url:{dedupe_key(str(item['sourceUrl']))}")
        keys.add(
            "headline:" + dedupe_key(f"{item.get('entertainer', '')}|{item.get('headline', '')}|{item.get('source', '')}")
        )
    return keys


def build_pending_item(entry: dict, entertainer: Entertainer, source: dict) -> dict:
    tag = infer_tag(f"{entry.get('title', '')} {entry.get('description', '')}", entertainer.profession)
    published_at = parse_iso(entry.get("publishedAt"))
    normalized_published = (published_at or utc_now()).isoformat().replace("+00:00", "Z")
    return {
        "id": str(uuid.uuid4()),
        "entertainer": entertainer.name,
        "headline": entry.get("title") or f"{entertainer.name} update requires review",
        "summary": make_summary(entertainer.name, entry.get("title", ""), source["name"], entertainer.profession, tag),
        "source": source["name"],
        "sourceUrl": entry.get("link", ""),
        "publishedAt": normalized_published,
        "tag": tag,
        "confidence": source["confidence"],
        "status": "pending",
        "pinned": False,
        "whyItMatters": WHY_IT_MATTERS.get(tag, WHY_IT_MATTERS["update"]),
        "createdAt": iso_now(),
        "updatedAt": iso_now(),
        "reviewedAt": None,
    }


def generate_drafts(store: dict, limit: int = DEFAULT_LIMIT, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> tuple[list[dict], list[str]]:
    limit = max(1, min(12, int(limit)))
    entertainers = load_entertainers()
    known_keys = existing_keys(store)
    drafted: list[dict] = []
    warnings: list[str] = []

    for source in FEED_SOURCES:
        if len(drafted) >= limit:
            break
        try:
            entries = extract_entries(fetch_feed_xml(source["url"]))
        except (HTTPError, URLError, TimeoutError, ET.ParseError) as error:
            warnings.append(f"{source['name']}: {error}")
            continue

        for entry in entries:
            if len(drafted) >= limit:
                break
            if not entry.get("title") or not entry.get("link"):
                continue
            if not is_recent(entry, lookback_hours):
                continue
            entertainer = match_entertainer(
                f"{entry.get('title', '')} {entry.get('description', '')}",
                entertainers,
            )
            if entertainer is None:
                continue

            url_key = f"url:{dedupe_key(entry['link'])}"
            headline_key = "headline:" + dedupe_key(f"{entertainer.name}|{entry['title']}|{source['name']}")
            if url_key in known_keys or headline_key in known_keys:
                continue

            item = build_pending_item(entry, entertainer, source)
            drafted.append(item)
            known_keys.add(url_key)
            known_keys.add(headline_key)

    return drafted, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pending internal-feed drafts from trusted RSS feeds.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum number of pending drafts to add.")
    parser.add_argument("--dry-run", action="store_true", help="Print drafts instead of writing them to the local store.")
    parser.add_argument(
        "--data-file",
        default=str(Path(__file__).resolve().parent / "data" / "featured-news-store.json"),
        help="Path to the featured-news store file.",
    )
    args = parser.parse_args()

    data_file = Path(args.data_file)
    store = json.loads(data_file.read_text(encoding="utf-8"))
    drafts, warnings = generate_drafts(store, limit=args.limit)

    if args.dry_run:
        print(json.dumps({"items": drafts, "warnings": warnings}, indent=2))
        return 0

    if drafts:
        store.setdefault("items", []).extend(drafts)
        data_file.write_text(json.dumps(store, indent=2), encoding="utf-8")

    print(json.dumps({"created": len(drafts), "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())