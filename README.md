# Entertainers Exchange

A browser-based fantasy stock market where you buy and sell entertainer shares while prices move in real time.

## Run locally

1. Open `index.html` in a browser (or serve the folder with a static web server).
2. Start trading from the market cards.
3. In local mode, the app simulates market events on an interval.

## Internal featured-news flow

If you want timely, reviewable featured updates without turning the site into a news product, run the internal feed server:

```bash
node internal-feed/server.js
```

Then open:

```text
http://127.0.0.1:8787/
```

Internal admin screen:

```text
http://127.0.0.1:8787/internal-feed/admin.html
```

What this changes:

- the homepage fetches approved featured items from `/api/featured-news`
- featured items appear first in the Momentum Feed
- local roster activity still appears underneath as fallback/context
- review state is stored in `internal-feed/data/featured-news-store.json`

Internal endpoints:

- `GET /api/featured-news`
- `GET /api/admin/featured-news`
- `POST /api/admin/featured-news`
- `POST /api/admin/featured-news/:id/approve`
- `POST /api/admin/featured-news/:id/reject`
- `PATCH /api/admin/featured-news/:id`

## Realtime mode (live backend)

Enable realtime mode with query params:

- `realtime=1`
- `ws=wss://your-stream-endpoint`

Example:

`https://your-domain.example/index.html?realtime=1&ws=wss://stream.your-domain.example/market`

When realtime mode is enabled:

- Local random simulation is disabled.
- Buy/sell/limit actions are sent as server intents over WebSocket.
- Server `snapshot` and `patch` messages drive market state.
- UI updates are throttled to avoid excessive re-renders under high event rates.

## Required backend architecture for millions of users

This frontend is now realtime-ready, but internet-scale reliability depends on backend design. Recommended production topology:

1. Edge + API Gateway:
Global Anycast/edge termination (Cloudflare/Akamai/Fastly/AWS Global Accelerator).
WebSocket-aware L7 gateway with sticky-free routing.

2. Stateless realtime fanout tier:
Horizontally scaled WebSocket/SSE nodes.
Connection registry in-memory + shard map.
Backpressure controls per connection.

3. Event backbone:
Kafka/Pulsar/Kinesis for durable ordered event streams.
Separate topics for `market-prices`, `portfolio-events`, `alerts`, `leaderboards`.

4. Market engine + risk service:
Authoritative pricing/trade matching service.
Idempotent intent handling (request IDs).
Anti-abuse/rate limiting and account-level risk checks.

5. Data stores:
Redis/KeyDB for hot state and fanout caches.
Postgres/CockroachDB for durable accounts/trades.
Object storage + warehouse for analytics/history.

6. Compute strategy:
Partition by entertainer symbol or user region.
Deterministic shard assignment.
Blue/green deploy with protocol versioning.

7. Reliability + SLOs:
Multi-region active-active.
Circuit breakers and graceful degradation (snapshot-only mode).
Target p95 update latency < 250ms and p99 reconnect < 5s.

8. Observability:
End-to-end tracing of intent -> match -> fanout.
High-cardinality metrics: fanout lag, dropped frames, queue depth.
Replayable audit log for incident forensics.

## Files

- `index.html` - page markup, game logic, realtime client wiring
- `style.css` - page styling

## Non-Expiring URL (No Tunnels)

This repo now includes GitHub Pages auto-deploy workflow at `.github/workflows/pages.yml`.
The workflow publishes only the public static site. It does not publish the internal feed backend or the internal admin screen.

### Publish once

1. Create a GitHub repo and push this project to the `main` branch.
2. In GitHub: `Settings -> Pages -> Source: GitHub Actions`.
3. Wait for workflow `Deploy Static Site to GitHub Pages` to finish.
4. Your permanent URL will be:

`https://<your-github-username>.github.io/<repo-name>/`

### What GitHub Pages includes

- public homepage and static pages
- market UI, rankings, profiles, styles, and images

### What GitHub Pages does not include

- `internal-feed/server.py`
- `internal-feed/server.js`
- `internal-feed/admin.html`
- `/api/featured-news` and the internal review endpoints

If you publish with GitHub Pages, the site itself will be reachable from anywhere, but the internal featured-news backend still needs a separate host if you want that system to work outside your local machine.

### Private access note

Static hosting cannot be truly private by itself. Your app currently has token-gated access in the URL (`?access=...`).
For identity-level private access (only your account/email), front it with Cloudflare Access, Firebase Auth, or another auth gateway.
