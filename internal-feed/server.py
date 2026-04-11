from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from auto_draft import generate_drafts


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "featured-news-store.json"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))
DEFAULT_FRESHNESS_HOURS = 72

DEFAULT_STORE = {
    "sources": [
        {"id": "variety", "name": "Variety", "trust": "high"},
        {"id": "deadline", "name": "Deadline", "trust": "high"},
        {"id": "official", "name": "Official Announcement", "trust": "high"},
    ],
    "items": [
        {
            "id": "sample-approved-1",
            "entertainer": "Taylor Swift",
            "headline": "Tour dates extended after sustained demand",
            "summary": "Official updates signaled another round of added dates, keeping attention elevated this week.",
            "source": "Official Announcement",
            "sourceUrl": "https://www.taylorswift.com/",
            "publishedAt": "2026-04-08T14:30:00.000Z",
            "tag": "tour",
            "confidence": 0.97,
            "status": "approved",
            "pinned": True,
            "whyItMatters": "Major live-event demand tends to reinforce short-term momentum.",
            "createdAt": "2026-04-08T14:35:00.000Z",
            "updatedAt": "2026-04-08T14:35:00.000Z",
            "reviewedAt": "2026-04-08T14:36:00.000Z",
        },
        {
            "id": "sample-approved-2",
            "entertainer": "Zendaya",
            "headline": "New production update renewed audience attention",
            "summary": "A verified trade report tied Zendaya to a fresh production milestone and pushed the story back into active coverage.",
            "source": "Variety",
            "sourceUrl": "https://variety.com/",
            "publishedAt": "2026-04-08T18:00:00.000Z",
            "tag": "production",
            "confidence": 0.91,
            "status": "approved",
            "pinned": False,
            "whyItMatters": "Production milestones usually create a clean, understandable reason for momentum changes.",
            "createdAt": "2026-04-08T18:05:00.000Z",
            "updatedAt": "2026-04-08T18:05:00.000Z",
            "reviewedAt": "2026-04-08T18:10:00.000Z",
        },
        {
            "id": "sample-pending-1",
            "entertainer": "MrBeast",
            "headline": "Pending review example",
            "summary": "This item stays out of the homepage feed until it is approved.",
            "source": "Deadline",
            "sourceUrl": "https://deadline.com/",
            "publishedAt": "2026-04-08T20:00:00.000Z",
            "tag": "creator",
            "confidence": 0.62,
            "status": "pending",
            "pinned": False,
            "whyItMatters": "Example review-queue item for internal testing.",
            "createdAt": "2026-04-08T20:01:00.000Z",
            "updatedAt": "2026-04-08T20:01:00.000Z",
        },
    ],
}

CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(DEFAULT_STORE, indent=2), encoding="utf-8")


def read_store() -> dict:
    ensure_store()
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def write_store(store: dict) -> None:
    DATA_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def is_fresh(item: dict) -> bool:
    if item.get("pinned"):
        return True
    published_at = parse_iso(item.get("publishedAt"))
    if published_at is None:
        return False
    return utc_now() - published_at <= timedelta(hours=DEFAULT_FRESHNESS_HOURS)


def sort_featured(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            0 if item.get("pinned") else 1,
            -(parse_iso(item.get("publishedAt")) or utc_now()).timestamp(),
        ),
    )


def public_item(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "entertainer": item.get("entertainer"),
        "headline": item.get("headline"),
        "summary": item.get("summary"),
        "source": item.get("source"),
        "sourceUrl": item.get("sourceUrl"),
        "publishedAt": item.get("publishedAt"),
        "tag": item.get("tag"),
        "confidence": item.get("confidence"),
        "pinned": bool(item.get("pinned")),
        "whyItMatters": item.get("whyItMatters"),
    }


def trusted_source_names(store: dict) -> set[str]:
    return {sanitize_text(source.get("name")) for source in store.get("sources", []) if sanitize_text(source.get("name"))}


def validate_item(item: dict, store: dict) -> str | None:
    if not item.get("sourceUrl"):
        return "sourceUrl is required so every featured item has a traceable source."
    if len(item.get("headline", "")) < 12:
        return "headline should be at least 12 characters so the feed stays descriptive."
    if not item.get("whyItMatters"):
        return "whyItMatters is required so the item has a clear reason to appear in the feed."
    if item.get("status") == "approved" and float(item.get("confidence", 0)) < 0.7:
        return "approved items must have confidence of at least 0.70."
    if item.get("pinned") and item.get("status") != "approved":
        return "only approved items can be pinned."

    known_sources = trusted_source_names(store)
    source_name = sanitize_text(item.get("source"))
    if source_name and known_sources and source_name not in known_sources and float(item.get("confidence", 0)) < 0.85:
        return "unlisted sources need confidence of at least 0.85 before they can be saved."

    return None


def sanitize_text(value: object, fallback: str = "") -> str:
    if isinstance(value, str):
      return value.strip()
    return fallback


def sanitize_url(value: object) -> str:
    candidate = sanitize_text(value)
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return ""


def sanitize_confidence(value: object, fallback: float = 0.75) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, numeric))


def sanitize_status(value: object, fallback: str = "pending") -> str:
    return value if value in {"pending", "approved", "rejected"} else fallback


def sanitize_iso_date(value: object) -> str:
    candidate = sanitize_text(value)
    parsed = parse_iso(candidate)
    return (parsed or utc_now()).isoformat().replace("+00:00", "Z")


def sanitize_item_input(payload: dict, existing: dict | None = None) -> dict:
    current = existing or {}
    entertainer = sanitize_text(payload.get("entertainer"), current.get("entertainer", ""))
    headline = sanitize_text(payload.get("headline"), current.get("headline", ""))
    source = sanitize_text(payload.get("source"), current.get("source", "Verified Source"))
    if not entertainer or not headline or not source:
        return {"error": "entertainer, headline, and source are required."}

    status = sanitize_status(payload.get("status"), current.get("status", "pending"))
    pinned = bool(payload.get("pinned", current.get("pinned", False))) if status == "approved" else False

    return {
        "id": current.get("id", str(uuid.uuid4())),
        "entertainer": entertainer,
        "headline": headline,
        "summary": sanitize_text(payload.get("summary"), current.get("summary", "")),
        "source": source,
        "sourceUrl": sanitize_url(payload.get("sourceUrl") or current.get("sourceUrl", "")),
        "publishedAt": sanitize_iso_date(payload.get("publishedAt") or current.get("publishedAt")),
        "tag": sanitize_text(payload.get("tag"), current.get("tag", "update")),
        "confidence": sanitize_confidence(payload.get("confidence"), current.get("confidence", 0.75)),
        "status": status,
        "pinned": pinned,
        "whyItMatters": sanitize_text(payload.get("whyItMatters"), current.get("whyItMatters", "")),
        "createdAt": current.get("createdAt", iso_now()),
        "updatedAt": iso_now(),
        "reviewedAt": current.get("reviewedAt"),
    }


class FeedHandler(BaseHTTPRequestHandler):
    server_version = "InternalFeed/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers("application/json; charset=utf-8")
        self.end_headers()

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") or parsed.path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_common_headers("application/json; charset=utf-8")
            self.end_headers()
            return
        self.serve_static(parsed.path, head_only=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": "internal-featured-feed-python"})
            return

        if parsed.path == "/api/featured-news":
            store = read_store()
            limit = max(1, min(12, int(query.get("limit", ["6"])[0])))
            items = [public_item(item) for item in sort_featured(store["items"]) if item.get("status") == "approved" and is_fresh(item)]
            self.send_json(HTTPStatus.OK, {"items": items[:limit], "generatedAt": iso_now()})
            return

        if parsed.path == "/api/admin/featured-news":
            store = read_store()
            status = query.get("status", [None])[0]
            items = store["items"] if status is None else [item for item in store["items"] if item.get("status") == status]
            self.send_json(HTTPStatus.OK, {"items": sort_featured(items), "sources": store.get("sources", [])})
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/admin/featured-news":
            payload = self.read_json_body()
            if payload is None:
                return
            store = read_store()
            next_item = sanitize_item_input(payload)
            if next_item.get("error"):
                self.send_json(HTTPStatus.BAD_REQUEST, next_item)
                return
            validation_error = validate_item(next_item, store)
            if validation_error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": validation_error})
                return
            store["items"].append(next_item)
            write_store(store)
            self.send_json(HTTPStatus.CREATED, {"item": next_item})
            return

        if parsed.path == "/api/admin/featured-news/auto-draft":
            payload = self.read_json_body()
            if payload is None:
                return
            store = read_store()
            limit = max(1, min(12, int(payload.get("limit", 6))))
            drafts, warnings = generate_drafts(store, limit=limit)
            if drafts:
                store["items"].extend(drafts)
                write_store(store)
            self.send_json(
                HTTPStatus.OK,
                {
                    "items": drafts,
                    "created": len(drafts),
                    "warnings": warnings,
                    "message": "No new drafts were created." if not drafts else f"Created {len(drafts)} pending draft(s).",
                },
            )
            return

        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) == 5 and segments[:4] == ["api", "admin", "featured-news", segments[3]] and segments[4] in {"approve", "reject"}:
            item_id = segments[3]
            action = segments[4]
            store = read_store()
            item = next((candidate for candidate in store["items"] if candidate.get("id") == item_id), None)
            if item is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Item not found."})
                return
            item["status"] = "approved" if action == "approve" else "rejected"
            if item["status"] != "approved":
                item["pinned"] = False
            item["reviewedAt"] = iso_now()
            item["updatedAt"] = item["reviewedAt"]
            write_store(store)
            self.send_json(HTTPStatus.OK, {"item": item})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) == 4 and segments[:3] == ["api", "admin", "featured-news"]:
            item_id = segments[3]
            payload = self.read_json_body()
            if payload is None:
                return
            store = read_store()
            index = next((i for i, item in enumerate(store["items"]) if item.get("id") == item_id), -1)
            if index == -1:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Item not found."})
                return
            next_item = sanitize_item_input(payload, store["items"][index])
            if next_item.get("error"):
                self.send_json(HTTPStatus.BAD_REQUEST, next_item)
                return
            validation_error = validate_item(next_item, store)
            if validation_error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": validation_error})
                return
            store["items"][index] = next_item
            write_store(store)
            self.send_json(HTTPStatus.OK, {"item": next_item})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def read_json_body(self) -> dict | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length."})
            return None
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Malformed JSON body."})
            return None

    def serve_static(self, request_path: str, head_only: bool = False) -> None:
        relative_path = "/index.html" if request_path == "/" else request_path
        file_path = (ROOT_DIR / relative_path.lstrip("/")).resolve()
        if ROOT_DIR not in file_path.parents and file_path != ROOT_DIR:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden."})
            return
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if not file_path.exists() or not file_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        body = file_path.read_bytes()
        content_type = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_common_headers(content_type)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_common_headers("application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def send_common_headers(self, content_type: str) -> None:
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", content_type)


if __name__ == "__main__":
    ensure_store()
    with ThreadingHTTPServer((HOST, PORT), FeedHandler) as server:
        print(f"Internal feed server running at http://{HOST}:{PORT}")
        server.serve_forever()