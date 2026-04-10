const entertainers = (window.ENTERTAINERS_EXCHANGE_CATALOG || []).map((entertainer) => ({
    ...entertainer,
    history: Array.isArray(entertainer.history) && entertainer.history.length > 0 ? entertainer.history.slice() : [Number(entertainer.price) || 0]
}));

const STORAGE_KEY = "entertainers-exchange-state";
const STORAGE_BACKUP_KEY = "entertainers-exchange-state-backup";
const PERMANENT_TRADES_KEY = "entertainers-exchange-trades";
const STARTING_MONEY = 1500;
const TRADE_HISTORY_LIMIT = 5000;

function getLiveEntertainers() {
    const state = loadSharedState();
    const savedByName = new Map((Array.isArray(state.entertainers) ? state.entertainers : []).map((item) => [item.name, item]));

    return entertainers.map((entertainer) => {
        const saved = savedByName.get(entertainer.name);
        return {
            ...entertainer,
            price: saved && typeof saved.price === "number" ? saved.price : entertainer.price,
            history: saved && Array.isArray(saved.history) && saved.history.length > 0 ? saved.history.slice() : entertainer.history.slice()
        };
    });
}

function rankEntertainers() {
    return getLiveEntertainers().sort((left, right) => (right.popularity + right.price) - (left.popularity + left.price));
}

function formatCompactNumber(value) {
    const safeValue = Number(value || 0);
    const absValue = Math.abs(safeValue);
    if (absValue >= 1000000000) return `${(safeValue / 1000000000).toFixed(absValue >= 10000000000 ? 0 : 1)}B`;
    if (absValue >= 1000000) return `${(safeValue / 1000000).toFixed(absValue >= 10000000 ? 0 : 1)}M`;
    if (absValue >= 1000) return `${(safeValue / 1000).toFixed(absValue >= 100000 ? 0 : 1)}K`;
    return `${Math.round(safeValue)}`;
}

function formatCompactCurrency(value) {
    return `$${formatCompactNumber(value)}`;
}

function formatCurrency(value) {
    return `$${Number(value || 0).toFixed(2)}`;
}

function safeParseJson(rawValue) {
    if (typeof rawValue !== "string" || !rawValue) {
        return null;
    }

    try {
        return JSON.parse(rawValue);
    } catch (error) {
        return null;
    }
}

function getTradeSignature(trade) {
    if (!trade || typeof trade !== "object") {
        return "";
    }

    return `${Number(trade.ts) || 0}|${String(trade.name || "")}|${String(trade.action || "")}|${Number(trade.qty) || 0}|${Number(trade.price) || 0}`;
}

function mergeTradeHistory() {
    const seen = new Set();
    const merged = [];

    Array.from(arguments).forEach((source) => {
        if (!Array.isArray(source)) {
            return;
        }

        source.forEach((trade) => {
            const signature = getTradeSignature(trade);
            if (!signature || seen.has(signature)) {
                return;
            }
            seen.add(signature);
            merged.push(trade);
        });
    });

    merged.sort((left, right) => (Number(right.ts) || 0) - (Number(left.ts) || 0));
    return merged.slice(0, TRADE_HISTORY_LIMIT);
}

function loadSharedState() {
    const parsed = safeParseJson(localStorage.getItem(STORAGE_KEY)) || safeParseJson(localStorage.getItem(STORAGE_BACKUP_KEY)) || {};
    const permanentTrades = safeParseJson(localStorage.getItem(PERMANENT_TRADES_KEY));

    return {
        entertainers: Array.isArray(parsed.entertainers) ? parsed.entertainers : entertainers.map((entertainer) => ({
            name: entertainer.name,
            price: entertainer.price,
            history: Array.isArray(entertainer.history) ? entertainer.history.slice() : [entertainer.price]
        })),
        portfolio: parsed.portfolio && typeof parsed.portfolio === "object" ? parsed.portfolio : {},
        money: typeof parsed.money === "number" ? parsed.money : STARTING_MONEY,
        tradeHistory: mergeTradeHistory(parsed.tradeHistory, Array.isArray(permanentTrades) ? permanentTrades : []),
        exchangeScore: typeof parsed.exchangeScore === "number" ? parsed.exchangeScore : 0,
        newsFeed: Array.isArray(parsed.newsFeed) ? parsed.newsFeed : []
    };
}

function saveSharedState(state) {
    const existing = safeParseJson(localStorage.getItem(STORAGE_KEY)) || safeParseJson(localStorage.getItem(STORAGE_BACKUP_KEY)) || {};
    const next = {
        ...existing,
        entertainers: state.entertainers,
        portfolio: state.portfolio,
        money: state.money,
        tradeHistory: state.tradeHistory,
        exchangeScore: state.exchangeScore,
        newsFeed: state.newsFeed
    };
    const serialized = JSON.stringify(next);
    localStorage.setItem(STORAGE_KEY, serialized);
    localStorage.setItem(STORAGE_BACKUP_KEY, serialized);
    localStorage.setItem(PERMANENT_TRADES_KEY, JSON.stringify(Array.isArray(state.tradeHistory) ? state.tradeHistory.slice(0, TRADE_HISTORY_LIMIT) : []));
}

function getHolding(state, name) {
    if (!state.portfolio[name]) {
        state.portfolio[name] = { shares: 0, totalCost: 0 };
    }
    return state.portfolio[name];
}

function getStateEntertainer(state, entertainer) {
    const existing = Array.isArray(state.entertainers)
        ? state.entertainers.find((item) => item && item.name === entertainer.name)
        : null;

    if (existing) {
        if (typeof existing.price !== "number") {
            existing.price = entertainer.price;
        }
        if (!Array.isArray(existing.history) || existing.history.length === 0) {
            existing.history = [existing.price];
        }
        return existing;
    }

    const created = { name: entertainer.name, price: entertainer.price, history: [entertainer.price] };
    state.entertainers.push(created);
    return created;
}

function getCirculatingShares(popularity, id) {
    return Math.round((1400000 + (Number(popularity || 0) * 12000) + (Number(id || 0) * 15000)) / 50000) * 50000;
}

function calculateVolatilityPercent(entertainer) {
    const history = Array.isArray(entertainer.history) ? entertainer.history.filter((value) => Number.isFinite(value) && value > 0) : [];
    if (history.length < 3) return 0;
    const returns = [];
    for (let index = 1; index < history.length; index += 1) {
        const previous = history[index - 1];
        const current = history[index];
        if (previous > 0) returns.push((current - previous) / previous);
    }
    if (returns.length < 2) return 0;
    const meanReturn = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.reduce((sum, value) => sum + Math.pow(value - meanReturn, 2), 0) / returns.length;
    return Math.sqrt(variance) * 100;
}

function getEntertainerMetrics(entertainer, tradeHistoryOverride) {
    const circulatingShares = getCirculatingShares(entertainer.popularity, entertainer.id);
    const since = Date.now() - (24 * 60 * 60 * 1000);
    const sourceTrades = Array.isArray(tradeHistoryOverride) ? tradeHistoryOverride : loadSharedState().tradeHistory;
    const recentTrades = sourceTrades.filter((trade) => trade.name === entertainer.name && Number(trade.ts) >= since);
    const volume24h = recentTrades.reduce((sum, trade) => sum + ((trade.qty || 0) * (trade.price || 0)), 0);
    const shareVolume24h = recentTrades.reduce((sum, trade) => sum + (trade.qty || 0), 0);
    const marketCap = entertainer.price * circulatingShares;
    const turnover = shareVolume24h / Math.max(1, circulatingShares);
    const volatilityPct = calculateVolatilityPercent(entertainer);
    const history = Array.isArray(entertainer.history) && entertainer.history.length > 1 ? entertainer.history : [entertainer.price];
    const start = history[Math.max(0, history.length - 7)] || entertainer.price;
    const end = history[history.length - 1] || entertainer.price;
    const priceChangePct = start > 0 ? ((end - start) / start) * 100 : 0;
    const liquidityScore = Math.max(18, Math.min(98, Math.round((Math.log10(1 + Math.max(volume24h, 1)) * 12) + (Math.log10(circulatingShares) * 5.5) + Math.min(18, turnover * 8500))));
    const momentum = Math.max(-99, Math.min(99, Math.round((priceChangePct * 0.62) + (Math.min(2, volume24h / Math.max(1, marketCap * 0.004)) * 18) + ((entertainer.popularity - 75) * 0.28))));

    return { circulatingShares, volume24h, shareVolume24h, marketCap, turnover, volatilityPct, liquidityScore, momentum };
}

function calculateStats(state) {
    const priceMap = new Map();
    (Array.isArray(state.entertainers) ? state.entertainers : []).forEach((entertainer) => {
        if (entertainer && typeof entertainer.name === "string") {
            priceMap.set(entertainer.name, typeof entertainer.price === "number" ? entertainer.price : 0);
        }
    });

    let portfolioValue = 0;
    let openPositions = 0;

    Object.entries(state.portfolio).forEach(([name, holding]) => {
        if (!holding || holding.shares <= 0) {
            return;
        }
        openPositions += 1;
        portfolioValue += (priceMap.get(name) || 0) * holding.shares;
    });

    return {
        openPositions,
        portfolioValue,
        netWorth: state.money + portfolioValue
    };
}

function updateBalanceSummary(state) {
    const moneyNode = document.getElementById("money");
    const netWorthNode = document.getElementById("net-worth");
    const openPositionsNode = document.getElementById("open-positions");
    const scoreNode = document.getElementById("score-value");
    const stats = calculateStats(state);

    if (moneyNode) moneyNode.innerText = formatCurrency(state.money);
    if (netWorthNode) netWorthNode.innerText = formatCurrency(stats.netWorth);
    if (openPositionsNode) openPositionsNode.innerText = String(stats.openPositions);
    if (scoreNode) scoreNode.innerText = String(state.exchangeScore || 0);
}

function setPageFeedback(message, isError) {
    const feedback = document.getElementById("page-feedback");
    if (!feedback) {
        return;
    }
    feedback.innerText = message;
    feedback.classList.toggle("negative-text", Boolean(isError));
    feedback.classList.toggle("positive-text", !isError);
}

function recordTrade(state, entertainer, action, qty, price) {
    const trade = { ts: Date.now(), name: entertainer.name, action, qty, price: Number(price.toFixed(2)) };
    state.tradeHistory = mergeTradeHistory([trade], state.tradeHistory);
    state.newsFeed = Array.isArray(state.newsFeed) ? state.newsFeed : [];
    state.newsFeed.push(`${action.toUpperCase()} ${qty} ${entertainer.name} @ ${formatCurrency(price)}`);
    state.newsFeed = state.newsFeed.slice(-64);
}

function rerenderRankedPages() {
    renderGrid("entertainers-11-30", 10, 30, 11);
    renderGrid("entertainers-31-50", 30, 50, 31);
    updateBalanceSummary(loadSharedState());
}

function buyEntertainer(entertainer) {
    const state = loadSharedState();
    const marketEntry = getStateEntertainer(state, entertainer);
    const holding = getHolding(state, entertainer.name);
    const purchasePrice = Number(marketEntry.price || entertainer.price);

    if (state.money < purchasePrice) {
        updateBalanceSummary(state);
        setPageFeedback(`Not enough cash to buy ${entertainer.name}.`, true);
        return;
    }

    state.money -= purchasePrice;
    holding.shares += 1;
    holding.totalCost += purchasePrice;
    marketEntry.price = Number((purchasePrice * 1.05).toFixed(2));
    marketEntry.history = Array.isArray(marketEntry.history) ? marketEntry.history.concat(marketEntry.price).slice(-14) : [purchasePrice, marketEntry.price];
    state.exchangeScore = (state.exchangeScore || 0) + 12;
    recordTrade(state, entertainer, "buy", 1, purchasePrice);
    saveSharedState(state);
    rerenderRankedPages();
    setPageFeedback(`Bought 1 share of ${entertainer.name} for ${formatCurrency(purchasePrice)}.`, false);
}

function sellEntertainer(entertainer) {
    const state = loadSharedState();
    const holding = getHolding(state, entertainer.name);
    const marketEntry = getStateEntertainer(state, entertainer);
    const salePrice = Number(marketEntry.price || entertainer.price);

    if (holding.shares <= 0) {
        updateBalanceSummary(state);
        setPageFeedback(`No shares of ${entertainer.name} available to sell.`, true);
        return;
    }

    const averageCost = holding.totalCost / holding.shares;
    state.money += salePrice;
    holding.shares -= 1;
    holding.totalCost = Math.max(0, holding.totalCost - averageCost);
    marketEntry.price = Number((salePrice * 0.95).toFixed(2));
    marketEntry.history = Array.isArray(marketEntry.history) ? marketEntry.history.concat(marketEntry.price).slice(-14) : [salePrice, marketEntry.price];
    state.exchangeScore = Math.max(0, (state.exchangeScore || 0) + 8);
    recordTrade(state, entertainer, "sell", 1, salePrice);
    saveSharedState(state);
    rerenderRankedPages();
    setPageFeedback(`Sold 1 share of ${entertainer.name} for ${formatCurrency(salePrice)}.`, false);
}

function tradeEntertainer(entertainer) {
    const state = loadSharedState();
    const holding = getHolding(state, entertainer.name);
    const suggestedAction = holding.shares > 0 ? "sell" : "buy";
    const response = window.prompt(`Trade ${entertainer.name}: type buy or sell`, suggestedAction);
    if (!response) {
        return;
    }
    const action = response.trim().toLowerCase();
    if (action === "buy") {
        buyEntertainer(entertainer);
        return;
    }
    if (action === "sell") {
        sellEntertainer(entertainer);
        return;
    }
    updateBalanceSummary(state);
    setPageFeedback(`Trade action "${response}" was not recognized. Use buy or sell.`, true);
}

function handleCardAction(action, id) {
    const entertainer = entertainers.find((item) => item.id === Number(id));
    if (!entertainer) {
        return;
    }

    if (action === "buy") {
        buyEntertainer(entertainer);
        return;
    }
    if (action === "sell") {
        sellEntertainer(entertainer);
        return;
    }
    tradeEntertainer(entertainer);
}

function getInitials(name) {
    return String(name || "")
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part.charAt(0))
        .join("")
        .toUpperCase();
}

function formatCategoryLabel(category) {
    const labels = {
        musician: "Musician",
        athlete: "Athlete",
        actor: "Actor",
        comedian: "Comedian",
        tv: "TV Personality",
        creator: "Creator"
    };
    return labels[category] || "Entertainer";
}

function createCardMarkup(entertainer, rank) {
    return `
        <div class="card-img" style="margin-bottom:10px;text-align:center;">
            <span class="artist-photo avatar-badge avatar-${entertainer.category || "creator"}" aria-hidden="true">${getInitials(entertainer.name)}</span>
        </div>
        <div class="card-content">
            <div class="card-topline">
                <h3 class="card-title">#${rank} ${entertainer.name}</h3>
                <span class="category-badge category-${entertainer.category || "creator"}">${formatCategoryLabel(entertainer.category)}</span>
            </div>
            <div class="card-meta">
                <span class="card-price">Price: ${formatCurrency(entertainer.price)}</span><br>
                <span class="card-popularity">Popularity: ${entertainer.popularity}</span>
            </div>
            <div class="card-actions entertainer-actions" style="margin-top:10px;display:flex;gap:8px;justify-content:center;">
                <button class="buy" data-id="${entertainer.id}" type="button">Add</button>
                <button class="sell" data-id="${entertainer.id}" type="button">Trim</button>
                <button class="trade" data-id="${entertainer.id}" type="button">Adjust</button>
            </div>
            <a class="card-link" href="profile.html?id=${entertainer.id}">View Profile</a>
        </div>
    `;
}

function renderGrid(containerId, start, end, rankOffset) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }

    const ranked = rankEntertainers().slice(start, end);
    container.innerHTML = "";

    ranked.forEach((entertainer, index) => {
        const card = document.createElement("div");
        card.className = "entertainer-card";
        card.innerHTML = createCardMarkup(entertainer, rankOffset + index);
        container.appendChild(card);
    });

    if (!container.dataset.transactionBound) {
        container.addEventListener("click", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }

            if (target.matches(".buy, .sell, .trade")) {
                const action = target.classList.contains("buy") ? "buy" : target.classList.contains("sell") ? "sell" : "trade";
                handleCardAction(action, target.getAttribute("data-id"));
            }
        });
        container.dataset.transactionBound = "true";
    }
}

document.addEventListener("DOMContentLoaded", function() {
    rerenderRankedPages();
});
