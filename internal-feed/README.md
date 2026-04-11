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
- `POST /api/admin/featured-news/auto-draft`
- `POST /api/admin/featured-news/:id/approve`
- `POST /api/admin/featured-news/:id/reject`
- `PATCH /api/admin/featured-news/:id`

## Local auto-draft worker

This repo now includes a local-only draft generator that pulls recent stories from trusted RSS feeds, matches them against entertainers already in the catalog, and adds new items as `pending` only.

What it does:

- reads trusted feeds from Variety and Deadline
- matches headlines to entertainers already in `entertainers/entertainer_list.json`
- generates short internal summaries and `whyItMatters` text
- writes new items into the review queue as `pending`
- never auto-approves or pins items
- skips generic roundup, gallery, recap, and weak one-line feed items

Run it directly:

```bash
python3 internal-feed/auto_draft.py
```

Dry run without writing:

```bash
python3 internal-feed/auto_draft.py --dry-run
```

From the admin screen, use the new `Generate Drafts` button to run the same local-only workflow through the server.

Notes:

- it needs an internet connection to reach the trusted RSS feeds
- it skips likely duplicates based on source URL and entertainer/headline/source combinations
- it only creates drafts for entertainers already present in the site catalog
- it prefers entertainment-story URLs over generic feed clutter when scanning source feeds

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
