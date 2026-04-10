# Internal Feed Service

This service is the minimal internal backend for timely, reviewable featured updates.

## What it does

- serves the static Entertainers Exchange site from the repo root
- exposes approved featured items at `/api/featured-news`
- keeps a small internal review queue with pending, approved, and rejected items
- stores data in `internal-feed/data/featured-news-store.json`

## Run it

Preferred in this workspace:

```bash
python3 internal-feed/server.py
```

Alternative if you already have Node installed:

```bash
node internal-feed/server.js
```

Then open:

```text
http://127.0.0.1:8787/
```

Admin screen:

```text
http://127.0.0.1:8787/internal-feed/admin.html
```

## API

### Public feed

- `GET /api/featured-news`

### Internal review endpoints

- `GET /api/admin/featured-news`
- `GET /api/admin/featured-news?status=pending`
- `POST /api/admin/featured-news`
- `POST /api/admin/featured-news/:id/approve`
- `POST /api/admin/featured-news/:id/reject`
- `PATCH /api/admin/featured-news/:id`

### Example draft item

```json
{
  "entertainer": "Drake",
  "headline": "Verified release announcement renewed attention",
  "summary": "A trusted source confirmed the release timing and moved the story back into active discussion.",
  "source": "Official Announcement",
  "sourceUrl": "https://drakerelated.com/",
  "publishedAt": "2026-04-09T18:00:00.000Z",
  "tag": "release",
  "confidence": 0.93,
  "whyItMatters": "Confirmed release timing often creates a clear short-term momentum catalyst."
}
```

Items stay out of the homepage feed until approved.
