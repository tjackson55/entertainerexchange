const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");

const ROOT_DIR = path.resolve(__dirname, "..");
const DATA_DIR = path.join(__dirname, "data");
const DATA_FILE = path.join(DATA_DIR, "featured-news-store.json");
const PORT = Number(process.env.PORT || 8787);
const HOST = process.env.HOST || "127.0.0.1";
const DEFAULT_FRESHNESS_HOURS = 72;

const DEFAULT_STORE = {
  sources: [
    { id: "variety", name: "Variety", trust: "high" },
    { id: "deadline", name: "Deadline", trust: "high" },
    { id: "official", name: "Official Announcement", trust: "high" }
  ],
  items: [
    {
      id: "sample-approved-1",
      entertainer: "Taylor Swift",
      headline: "Tour dates extended after sustained demand",
      summary: "Official updates signaled another round of added dates, keeping attention elevated this week.",
      source: "Official Announcement",
      sourceUrl: "https://www.taylorswift.com/",
      publishedAt: "2026-04-08T14:30:00.000Z",
      tag: "tour",
      confidence: 0.97,
      status: "approved",
      pinned: true,
      whyItMatters: "Major live-event demand tends to reinforce short-term momentum.",
      createdAt: "2026-04-08T14:35:00.000Z",
      updatedAt: "2026-04-08T14:35:00.000Z",
      reviewedAt: "2026-04-08T14:36:00.000Z"
    },
    {
      id: "sample-approved-2",
      entertainer: "Zendaya",
      headline: "New production update renewed audience attention",
      summary: "A verified trade report tied Zendaya to a fresh production milestone and pushed the story back into active coverage.",
      source: "Variety",
      sourceUrl: "https://variety.com/",
      publishedAt: "2026-04-08T18:00:00.000Z",
      tag: "production",
      confidence: 0.91,
      status: "approved",
      pinned: false,
      whyItMatters: "Production milestones usually create a clean, understandable reason for momentum changes.",
      createdAt: "2026-04-08T18:05:00.000Z",
      updatedAt: "2026-04-08T18:05:00.000Z",
      reviewedAt: "2026-04-08T18:10:00.000Z"
    },
    {
      id: "sample-pending-1",
      entertainer: "MrBeast",
      headline: "Pending review example",
      summary: "This item stays out of the homepage feed until it is approved.",
      source: "Deadline",
      sourceUrl: "https://deadline.com/",
      publishedAt: "2026-04-08T20:00:00.000Z",
      tag: "creator",
      confidence: 0.62,
      status: "pending",
      pinned: false,
      whyItMatters: "Example review-queue item for internal testing.",
      createdAt: "2026-04-08T20:01:00.000Z",
      updatedAt: "2026-04-08T20:01:00.000Z"
    }
  ]
};

const CONTENT_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".webp": "image/webp"
};

async function ensureStore() {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(DATA_FILE);
  } catch {
    await fs.writeFile(DATA_FILE, JSON.stringify(DEFAULT_STORE, null, 2));
  }
}

async function readStore() {
  await ensureStore();
  const raw = await fs.readFile(DATA_FILE, "utf8");
  return JSON.parse(raw);
}

async function writeStore(store) {
  await fs.writeFile(DATA_FILE, JSON.stringify(store, null, 2));
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8"
  });
  response.end(JSON.stringify(payload, null, 2));
}

function sendText(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "text/plain; charset=utf-8"
  });
  response.end(payload);
}

function normalizePathname(pathname) {
  if (pathname === "/") {
    return "/index.html";
  }
  return pathname;
}

function isFresh(item) {
  if (item.pinned) {
    return true;
  }
  const publishedMs = Date.parse(item.publishedAt || "");
  if (Number.isNaN(publishedMs)) {
    return false;
  }
  return Date.now() - publishedMs <= DEFAULT_FRESHNESS_HOURS * 60 * 60 * 1000;
}

function toPublicItem(item) {
  return {
    id: item.id,
    entertainer: item.entertainer,
    headline: item.headline,
    summary: item.summary,
    source: item.source,
    sourceUrl: item.sourceUrl,
    publishedAt: item.publishedAt,
    tag: item.tag,
    confidence: item.confidence,
    pinned: Boolean(item.pinned),
    whyItMatters: item.whyItMatters
  };
}

function sortFeatured(items) {
  return [...items].sort((left, right) => {
    if (Boolean(left.pinned) !== Boolean(right.pinned)) {
      return left.pinned ? -1 : 1;
    }
    return Date.parse(right.publishedAt || "") - Date.parse(left.publishedAt || "");
  });
}

function sanitizeText(value, fallback = "") {
  return typeof value === "string" ? value.trim() : fallback;
}

function sanitizeUrl(value) {
  const candidate = sanitizeText(value);
  if (!candidate) {
    return "";
  }
  try {
    const parsed = new URL(candidate);
    return parsed.toString();
  } catch {
    return "";
  }
}

function sanitizeIsoDate(value) {
  const candidate = sanitizeText(value);
  const parsed = Date.parse(candidate);
  if (Number.isNaN(parsed)) {
    return new Date().toISOString();
  }
  return new Date(parsed).toISOString();
}

function sanitizeConfidence(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 0.75;
  }
  return Math.max(0, Math.min(1, numeric));
}

function sanitizeStatus(value) {
  const allowed = new Set(["pending", "approved", "rejected"]);
  return allowed.has(value) ? value : "pending";
}

function sanitizeItemInput(input, existingItem = {}) {
  const entertainer = sanitizeText(input.entertainer, existingItem.entertainer || "");
  const headline = sanitizeText(input.headline, existingItem.headline || "");
  const source = sanitizeText(input.source, existingItem.source || "Verified Source");

  if (!entertainer || !headline || !source) {
    return { error: "entertainer, headline, and source are required." };
  }

  return {
    id: existingItem.id || crypto.randomUUID(),
    entertainer,
    headline,
    summary: sanitizeText(input.summary, existingItem.summary || ""),
    source,
    sourceUrl: sanitizeUrl(input.sourceUrl || existingItem.sourceUrl || ""),
    publishedAt: sanitizeIsoDate(input.publishedAt || existingItem.publishedAt || new Date().toISOString()),
    tag: sanitizeText(input.tag, existingItem.tag || "update"),
    confidence: sanitizeConfidence(input.confidence ?? existingItem.confidence ?? 0.75),
    status: sanitizeStatus(input.status || existingItem.status || "pending"),
    pinned: Boolean(input.pinned ?? existingItem.pinned),
    whyItMatters: sanitizeText(input.whyItMatters, existingItem.whyItMatters || ""),
    createdAt: existingItem.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    reviewedAt: existingItem.reviewedAt || null
  };
}

function parseJsonBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("Request body too large."));
      }
    });
    request.on("end", () => {
      if (!body) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(body));
      } catch {
        reject(new Error("Malformed JSON body."));
      }
    });
    request.on("error", reject);
  });
}

async function handleApi(request, response, pathname, searchParams) {
  const store = await readStore();

  if (request.method === "GET" && pathname === "/api/featured-news") {
    const limit = Math.max(1, Math.min(12, Number(searchParams.get("limit")) || 6));
    const items = sortFeatured(store.items.filter((item) => item.status === "approved" && isFresh(item)))
      .slice(0, limit)
      .map(toPublicItem);
    sendJson(response, 200, { items, generatedAt: new Date().toISOString() });
    return;
  }

  if (request.method === "GET" && pathname === "/api/admin/featured-news") {
    const status = searchParams.get("status");
    const items = status ? store.items.filter((item) => item.status === status) : store.items;
    sendJson(response, 200, { items: sortFeatured(items) });
    return;
  }

  if (request.method === "POST" && pathname === "/api/admin/featured-news") {
    const body = await parseJsonBody(request);
    const nextItem = sanitizeItemInput(body);
    if (nextItem.error) {
      sendJson(response, 400, { error: nextItem.error });
      return;
    }

    store.items.push(nextItem);
    await writeStore(store);
    sendJson(response, 201, { item: nextItem });
    return;
  }

  const itemActionMatch = pathname.match(/^\/api\/admin\/featured-news\/([^/]+)\/(approve|reject)$/);
  if (request.method === "POST" && itemActionMatch) {
    const [, itemId, action] = itemActionMatch;
    const item = store.items.find((candidate) => candidate.id === itemId);
    if (!item) {
      sendJson(response, 404, { error: "Item not found." });
      return;
    }
    item.status = action === "approve" ? "approved" : "rejected";
    item.reviewedAt = new Date().toISOString();
    item.updatedAt = item.reviewedAt;
    await writeStore(store);
    sendJson(response, 200, { item });
    return;
  }

  const itemEditMatch = pathname.match(/^\/api\/admin\/featured-news\/([^/]+)$/);
  if (request.method === "PATCH" && itemEditMatch) {
    const [, itemId] = itemEditMatch;
    const body = await parseJsonBody(request);
    const itemIndex = store.items.findIndex((candidate) => candidate.id === itemId);
    if (itemIndex === -1) {
      sendJson(response, 404, { error: "Item not found." });
      return;
    }

    const nextItem = sanitizeItemInput(body, store.items[itemIndex]);
    if (nextItem.error) {
      sendJson(response, 400, { error: nextItem.error });
      return;
    }

    store.items[itemIndex] = nextItem;
    await writeStore(store);
    sendJson(response, 200, { item: nextItem });
    return;
  }

  if (request.method === "GET" && pathname === "/health") {
    sendJson(response, 200, { ok: true, service: "internal-featured-feed" });
    return;
  }

  sendJson(response, 404, { error: "Not found." });
}

async function serveStatic(response, pathname) {
  const normalized = normalizePathname(pathname);
  const resolved = path.resolve(ROOT_DIR, `.${normalized}`);
  if (!resolved.startsWith(ROOT_DIR)) {
    sendText(response, 403, "Forbidden");
    return;
  }

  try {
    const stat = await fs.stat(resolved);
    const filePath = stat.isDirectory() ? path.join(resolved, "index.html") : resolved;
    const fileBuffer = await fs.readFile(filePath);
    const extension = path.extname(filePath).toLowerCase();
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Type": CONTENT_TYPES[extension] || "application/octet-stream"
    });
    response.end(fileBuffer);
  } catch {
    sendText(response, 404, "Not found");
  }
}

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${request.headers.host || `${HOST}:${PORT}`}`);

    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
        "Access-Control-Allow-Origin": "*"
      });
      response.end();
      return;
    }

    if (url.pathname.startsWith("/api/") || url.pathname === "/health") {
      await handleApi(request, response, url.pathname, url.searchParams);
      return;
    }

    await serveStatic(response, url.pathname);
  } catch (error) {
    sendJson(response, 500, { error: error.message || "Internal server error." });
  }
});

ensureStore()
  .then(() => {
    server.listen(PORT, HOST, () => {
      console.log(`Internal feed server running at http://${HOST}:${PORT}`);
    });
  })
  .catch((error) => {
    console.error("Failed to initialize internal feed server:", error);
    process.exitCode = 1;
  });