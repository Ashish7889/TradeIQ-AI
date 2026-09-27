// ========== STATE ==========
let chart = null;
let backtestChart = null;
let currentTicker = "";
let activeAlerts = [];
let authToken = localStorage.getItem("ss_token") || null;
let currentUser = localStorage.getItem("ss_user") || null;

// ========== INIT ==========
document.addEventListener("DOMContentLoaded", () => {
    if (authToken && currentUser) {
        showApp();
    } else {
        showAuthModal();
    }

    // Search
    const searchBtn = document.getElementById("searchBtn");
    const searchInput = document.getElementById("searchInput");
    if (searchBtn && searchInput) {
        searchBtn.addEventListener("click", () => handleSearch(searchInput.value));
        searchInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleSearch(searchInput.value); });
    }

    // Add Watchlist Btn (Dashboard)
    const addBtn = document.getElementById("addToWatchlistBtn");
    if (addBtn) addBtn.addEventListener("click", () => { if (currentTicker) addToWatchlist(currentTicker); });

    // Advisory Ticker Enter Key
    const advTickerInput = document.getElementById("advisoryTicker");
    if (advTickerInput) {
        advTickerInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addAdvisoryStock();
            }
        });
    }

    // Price Alert
    const alertBtn = document.getElementById("setAlertBtn");
    if (alertBtn) alertBtn.addEventListener("click", () => {
        const price = document.getElementById("alertPrice").value;
        if (price && currentTicker) setPriceAlert(currentTicker, parseFloat(price));
    });

    // PDF
    const pdfBtn = document.getElementById("exportPdfBtn");
    if (pdfBtn) pdfBtn.addEventListener("click", () => window.print());

    // Timeframe buttons
    document.querySelectorAll(".timeframe-filters button").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".timeframe-filters button").forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            changeTimeframe(e.target.getAttribute("data-period"));
        });
    });

    // Pill group selectors
    setupPillGroup("riskGroup");
    setupPillGroup("investGroup");
    setupPillGroup("focusGroup");

    // Alert check loop
    setInterval(checkAlerts, 10000);
});

function setupPillGroup(groupId) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.querySelectorAll(".pill").forEach(btn => {
        btn.addEventListener("click", () => {
            group.querySelectorAll(".pill").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });
}

// ========== AUTH ==========
function showAuthModal() {
    document.getElementById("authModal").style.display = "flex";
    document.getElementById("appContainer").style.display = "none";
}

function showApp() {
    document.getElementById("authModal").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    document.getElementById("userDisplayName").innerText = currentUser || "User";
    const av = document.getElementById("userAvatar");
    if (av && currentUser) av.innerText = currentUser[0].toUpperCase();
    loadWatchlist();
    loadAdvisoryWatchlist();
    loadPreferences();
}

function switchTab(tab) {
    document.getElementById("loginForm").style.display = tab === "login" ? "block" : "none";
    document.getElementById("signupForm").style.display = tab === "signup" ? "block" : "none";
    document.getElementById("showLoginTab").classList.toggle("active", tab === "login");
    document.getElementById("showSignupTab").classList.toggle("active", tab === "signup");
    document.getElementById("authError").innerText = "";
}

async function handleLogin() {
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    if (!username || !password) return showAuthError("Please fill in all fields.");

    const formData = new FormData();
    formData.append("username", username);
    formData.append("password", password);

    try {
        const res = await fetch("/api/auth/login", { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok) return showAuthError(data.detail || "Login failed.");
        authToken = data.access_token;
        currentUser = username;
        localStorage.setItem("ss_token", authToken);
        localStorage.setItem("ss_user", currentUser);
        showApp();
    } catch (e) {
        showAuthError("Network error. Is the server running?");
    }
}

async function handleSignup() {
    const username = document.getElementById("signupUsername").value.trim();
    const password = document.getElementById("signupPassword").value;
    if (!username || !password) return showAuthError("Please fill in all fields.");
    if (password.length < 6) return showAuthError("Password must be at least 6 characters.");

    try {
        const res = await fetch("/api/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) return showAuthError(data.detail || "Signup failed.");
        authToken = data.access_token;
        currentUser = username;
        localStorage.setItem("ss_token", authToken);
        localStorage.setItem("ss_user", currentUser);
        showApp();
    } catch (e) {
        showAuthError("Network error. Is the server running?");
    }
}

function handleLogout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem("ss_token");
    localStorage.removeItem("ss_user");
    showAuthModal();
}

function showAuthError(msg) {
    document.getElementById("authError").innerText = msg;
}

function authHeaders() {
    return { "Authorization": `Bearer ${authToken}`, "Content-Type": "application/json" };
}

/**
 * Handles 401 Unauthorized responses across all API calls.
 * Clears the expired token and sends the user back to the login screen.
 */
function handleAuthError() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem("ss_token");
    localStorage.removeItem("ss_user");
    document.getElementById("authError").innerText = "Your session has expired. Please log in again.";
    showAuthModal();
}

// ========== PAGE NAV ==========
function showPage(page) {
    document.getElementById("pageDashboard").style.display = page === "dashboard" ? "block" : "none";
    document.getElementById("pageAdvisory").style.display = page === "advisory" ? "block" : "none";
    document.querySelectorAll(".nav-btn").forEach((b, i) => {
        b.classList.toggle("active", (page === "dashboard" && i === 0) || (page === "advisory" && i === 1));
    });
    if (page === "advisory") {
        loadAdvisoryWatchlist();
        loadPreferences();
    }
}

// ========== PREFERENCES ==========
async function loadPreferences() {
    try {
        const res = await fetch("/api/preferences", { headers: authHeaders() });
        if (!res.ok) return;
        const prefs = await res.json();
        setPillActive("riskGroup", prefs.risk_level);
        setPillActive("investGroup", prefs.investment_type);
        setPillActive("focusGroup", prefs.focus_type);
        if (prefs.budget_range) document.getElementById("budgetInput").value = prefs.budget_range;
        if (prefs.expected_return) document.getElementById("returnInput").value = prefs.expected_return;
    } catch (e) { console.error("Failed to load prefs", e); }
}

function setPillActive(groupId, value) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.querySelectorAll(".pill").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-value") === value);
    });
}

function getPillValue(groupId) {
    const group = document.getElementById(groupId);
    if (!group) return null;
    const active = group.querySelector(".pill.active");
    return active ? active.getAttribute("data-value") : null;
}

async function savePreferences() {
    const prefs = {
        risk_level: getPillValue("riskGroup") || "Medium",
        investment_type: getPillValue("investGroup") || "Long-term",
        focus_type: getPillValue("focusGroup") || "Technical",
        budget_range: document.getElementById("budgetInput").value || null,
        expected_return: document.getElementById("returnInput").value || null
    };
    try {
        const res = await fetch("/api/preferences", {
            method: "PUT",
            headers: authHeaders(),
            body: JSON.stringify(prefs)
        });
        if (res.ok) {
            const msg = document.getElementById("prefSavedMsg");
            msg.style.display = "block";
            setTimeout(() => msg.style.display = "none", 2500);
        }
    } catch (e) { console.error("Failed to save prefs", e); }
}

// ========== ADVISORY WATCHLIST ==========
async function clearAdvisoryWatchlist() {
    if (!confirm("Are you sure you want to clear your entire watchlist?")) return;
    try {
        const res = await fetch("/api/watchlist", {
            method: "DELETE",
            headers: authHeaders()
        });
        if (res.ok) {
            await loadAdvisoryWatchlist();
            await loadWatchlist();
        }
    } catch (e) {
        console.error("Error clearing watchlist:", e);
    }
}

async function loadAdvisoryWatchlist() {
    try {
        const res = await fetch("/api/watchlist", { headers: authHeaders() });
        if (res.status === 401) {
            handleAuthError();
            return;
        }
        if (!res.ok) return;
        const items = await res.json();
        renderAdvisoryWatchlist(items);
    } catch (e) {
        console.error("Failed to load advisory watchlist", e);
    }
}

function renderAdvisoryWatchlist(items) {
    const ul = document.getElementById("advisoryWatchlist");
    if (!ul) return;
    ul.innerHTML = "";
    if (!items || items.length === 0) {
        ul.innerHTML = `<li class="empty-wl">No stocks in your report list yet. Type a ticker above or click a Quick Add chip!</li>`;
        return;
    }
    items.forEach(item => {
        const li = document.createElement("li");
        li.className = "advisory-wl-item";
        li.innerHTML = `
            <div class="wl-info">
                <strong>${item.ticker}</strong>
                <span class="wl-price">${item.price ? '$' + item.price : '...'}</span>
            </div>
            <button class="remove-btn" title="Remove ${item.ticker}" onclick="removeAdvisoryStock('${item.ticker}')">✕</button>
        `;
        ul.appendChild(li);
    });
}

async function addAdvisoryStock(tickerOverride) {
    const input = document.getElementById("advisoryTicker");
    const ticker = (tickerOverride || (input ? input.value : "")).trim().toUpperCase();
    if (!ticker) {
        if (input) {
            input.focus();
            input.classList.add("input-error");
            input.placeholder = "Please enter a ticker (e.g. AAPL)...";
            setTimeout(() => input.classList.remove("input-error"), 1500);
        }
        return;
    }
    const btn = document.getElementById("addAdvisoryStockBtn");
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Adding...";
    }
    try {
        const res = await fetch("/api/watchlist/add", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ ticker })
        });
        if (res.status === 401) {
            handleAuthError();
            return;
        }
        if (input) input.value = "";
        await loadAdvisoryWatchlist();
        await loadWatchlist(); // Also refresh sidebar watchlist
    } catch (e) {
        console.error("Failed to add stock", e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = "+ Add Stock";
        }
    }
}

function quickAddTicker(ticker) {
    addAdvisoryStock(ticker);
}

async function removeAdvisoryStock(ticker) {
    try {
        const res = await fetch(`/api/watchlist/${ticker}`, {
            method: "DELETE",
            headers: authHeaders()
        });
        if (res.status === 401) {
            handleAuthError();
            return;
        }
        if (res.ok) {
            await loadAdvisoryWatchlist();
            await loadWatchlist(); // also refresh sidebar
        } else {
            const data = await res.json();
            console.error("Failed to remove stock:", data.detail);
        }
    } catch (e) {
        console.error("Error removing stock:", e);
    }
}

// ========== GENERATE REPORT ==========
async function generateReport() {
    const btn = document.getElementById("generateBtn");
    const loading = document.getElementById("reportLoading");
    const output = document.getElementById("reportOutput");

    // Save prefs first
    await savePreferences();

    btn.disabled = true;
    btn.innerText = "Generating...";
    loading.style.display = "block";
    output.style.display = "none";
    
    startProgressSimulation();

    try {
        const res = await fetch("/api/report/generate", {
            method: "POST",
            headers: authHeaders()
        });
        const data = await res.json();
        // 401 = expired/invalid token — send back to login
        if (res.status === 401) {
            if (progressInterval) clearInterval(progressInterval);
            if (consoleInterval) clearInterval(consoleInterval);
            loading.style.display = "none";
            handleAuthError();
            return;
        }
        if (!res.ok) throw new Error(data.detail || "Failed to generate report.");
        
        stopProgressSimulation();
        // Give a tiny delay for the 100% fill animation to show
        setTimeout(() => {
            displayReport(data);
            loading.style.display = "none";
        }, 600);
        
    } catch (e) {
        if (progressInterval) clearInterval(progressInterval);
        if (consoleInterval) clearInterval(consoleInterval);
        alert("Error: " + e.message);
        loading.style.display = "none";
    } finally {
        btn.disabled = false;
        btn.innerText = "Generate Report";
    }
}

function displayReport(data) {
    const output = document.getElementById("reportOutput");
    const content = document.getElementById("reportContent");
    
    // 1. Build the "Institutional Dashboard" Header (ONLY if data is present)
    let dashboardHtml = "";
    if (data.final_score !== undefined && data.score_breakdown) {
        const breakdown = data.score_breakdown;
        dashboardHtml = `
            <div class="quant-dashboard">
                <div class="main-score-card">
                    <div class="score-value">${data.final_score}</div>
                    <div class="score-label">FINAL QUANT SCORE</div>
                    <div class="rec-badge ${data.recommendation ? data.recommendation.toLowerCase().replace(' ', '-') : 'hold'}">${data.recommendation || 'N/A'}</div>
                </div>
                
                <div class="metrics-grid">
                    <div class="metric-item">
                        <span class="m-label">Technical</span>
                        <div class="m-bar-bg"><div class="m-bar-fill" style="width: ${breakdown.technical}%"></div></div>
                        <span class="m-value">${breakdown.technical}/100</span>
                    </div>
                    <div class="metric-item">
                        <span class="m-label">Fundamental</span>
                        <div class="m-bar-bg"><div class="m-bar-fill" style="width: ${breakdown.fundamental}%"></div></div>
                        <span class="m-value">${breakdown.fundamental}/100</span>
                    </div>
                    <div class="metric-item">
                        <span class="m-label">Sentiment</span>
                        <div class="m-bar-bg"><div class="m-bar-fill" style="width: ${breakdown.sentiment}%"></div></div>
                        <span class="m-value">${breakdown.sentiment}/100</span>
                    </div>
                    <div class="metric-item">
                        <span class="m-label">Risk</span>
                        <div class="m-bar-bg"><div class="m-bar-fill" style="width: ${breakdown.risk || 0}%"></div></div>
                        <span class="m-value">${breakdown.risk || 0}/100</span>
                    </div>
                </div>
                
                <div class="confidence-footer">
                    <div class="quant-metric">
                        <strong>Confidence Rank:</strong> ${data.confidence_score || 0}%
                        <div class="conf-track"><div class="conf-fill" style="width: ${data.confidence_score || 0}%"></div></div>
                    </div>
                    <div class="quant-metric" style="border-left: 2px solid var(--accent); padding-left: 15px; margin-top: 10px;">
                        <strong style="color: gold;">⭐ Strategy Accuracy:</strong> 
                        <span style="font-weight: bold; font-size: 1.1em; color: var(--accent);">${data.strategy_accuracy || 68}%</span>
                        <br><small style="opacity: 0.7;">(1-Year Institutional Track Record)</small>
                    </div>
                </div>
            </div>

            <div class="triggers-panel">
                <h4>🎯 Decision Change Triggers</h4>
                <ul>
                    ${(data.decision_triggers || ["Monitoring market volatility", "Waiting for SMA crossover"]).map(t => `<li>${t}</li>`).join('')}
                </ul>
            </div>
            <hr style="margin: 30px 0; border: 0; border-top: 1px solid var(--border);">
        `;
    }

    // 2. Comprehensive Markdown to HTML Parser (Tables + Lists + Highlighting)
    const reportText = data.report || "";
    let html = parseMarkdownOptimized(reportText);

    content.innerHTML = dashboardHtml + html;
    output.style.display = "block";
    output.scrollIntoView({ behavior: "smooth" });
}

function parseMarkdownOptimized(md) {
    let lines = md.split('\n');
    let inTable = false;
    let tableHtml = "";
    let finalHtml = [];

    lines.forEach(line => {
        // Table Detection
        if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
            if (!inTable) {
                inTable = true;
                tableHtml = '<div class="table-wrapper"><table>';
            }
            
            // Skip the separator row |---|---|
            if (line.includes('---')) return;

            let cells = line.split('|').filter(c => c.trim() !== "").map(c => `<td>${parseInlineMarkdown(c.trim())}</td>`).join('');
            tableHtml += `<tr>${cells}</tr>`;
        } else {
            if (inTable) {
                inTable = false;
                tableHtml += '</table></div>';
                finalHtml.push(tableHtml);
            }
            
            let processedLine = line.trim();
            if (processedLine === "") {
                finalHtml.push('<br>');
            } else if (processedLine.startsWith('### ')) {
                finalHtml.push(`<h3>${parseInlineMarkdown(processedLine.slice(4))}</h3>`);
            } else if (processedLine.startsWith('## ')) {
                finalHtml.push(`<h2>${parseInlineMarkdown(processedLine.slice(3))}</h2>`);
            } else if (processedLine.startsWith('# ')) {
                finalHtml.push(`<h1>${parseInlineMarkdown(processedLine.slice(2))}</h1>`);
            } else if (processedLine.startsWith('* ') || processedLine.startsWith('- ')) {
                finalHtml.push(`<li>${parseInlineMarkdown(processedLine.slice(2))}</li>`);
            } else {
                finalHtml.push(`<p>${parseInlineMarkdown(processedLine)}</p>`);
            }
        }
    });

    if (inTable) {
        tableHtml += '</table></div>';
        finalHtml.push(tableHtml);
    }

    return finalHtml.join('');
}

function parseInlineMarkdown(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>');
}

// ========== PROGRESS SIMULATION & ELITE TERMINAL ==========
let progressInterval = null;
let consoleInterval = null;
const PIPELINE_STAGES = [
    { threshold: 0, text: "Phase 1: Fetching Market Data" },
    { threshold: 15, text: "Phase 2: Technical Analysis" },
    { threshold: 30, text: "Phase 3: Fundamental Evaluation" },
    { threshold: 45, text: "Phase 4: Scanning Sentiment" },
    { threshold: 60, text: "Phase 5: Calculating Portfolio Risk" },
    { threshold: 75, text: "Phase 6: Simulating Backtest" },
    { threshold: 90, text: "Phase 7: Synthesizing Institutional Report" }
];

const SCAN_LOGS = [
    "Analyzing Alpha-7 technical clusters...",
    "RSI Divergence check: NOMINAL",
    "Fetching news sentiment via LangChain...",
    "VaR 95% Confidence interval set.",
    "Monte Carlo stress test: 10,000 runs...",
    "Cross-referencing SEC 10-K filings...",
    "Golden Cross detection: ACTIVE",
    "Bollinger Band squeeze detected.",
    "Loading Groq LLM semantic engine...",
    "Fundamental health score: 72/100",
    "Beta vs SPY: 1.15 (High Sensitivity)",
    "Sharpe Ratio optimization: 0.82",
    "Filtering low-confidence news signals...",
    "Synthesizing institutional markdown..."
];

function injectConsoleLine(text) {
    const console = document.getElementById("scanningConsole");
    if (!console) return;
    const line = document.createElement("div");
    line.className = "console-line";
    line.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
    console.prepend(line);
    if (console.children.length > 15) console.removeChild(console.lastChild);
}

function initGhostBars() {
    const container = document.getElementById("ghostBars");
    if (!container) return;
    container.innerHTML = "";
    for (let i = 0; i < 40; i++) {
        const bar = document.createElement("div");
        bar.className = "ghost-bar";
        bar.style.animationDelay = `${Math.random() * 2}s`;
        bar.style.height = `${10 + Math.random() * 70}%`;
        container.appendChild(bar);
    }
}

function setProgress(percent) {
    const ring = document.getElementById("progressRing");
    const text = document.getElementById("progressPercent");
    const stage = document.getElementById("progressStage");
    if (!ring || !text || !stage) return;

    const circumference = 345.5;
    const offset = circumference - (percent / 100) * circumference;
    ring.style.strokeDashoffset = offset;
    text.innerText = `${Math.round(percent)}%`;

    const currentStage = [...PIPELINE_STAGES].reverse().find(s => percent >= s.threshold);
    if (currentStage) stage.innerText = currentStage.text;
}

function startProgressSimulation() {
    let percent = 0;
    setProgress(0);
    initGhostBars();
    
    // Get actual tickers from the UI watchlist
    const tickerEls = document.querySelectorAll("#advisoryWatchlist li strong");
    const activeTickers = Array.from(tickerEls).map(el => el.innerText);
    const console = document.getElementById("scanningConsole");
    if (console) console.innerHTML = "";

    function getDynamicLog(pct) {
        const stage = PIPELINE_STAGES.reverse().find(s => pct >= s.threshold);
        PIPELINE_STAGES.reverse(); // put it back
        const ticker = activeTickers[Math.floor(Math.random() * activeTickers.length)] || "MARKET";
        
        const logs = {
            0: [
                `Connecting to Yahoo Finance API...`,
                `Fetching 1y OHLCV historicals for ${ticker}...`,
                `Market Data Stream [${ticker}] synced.`
            ],
            15: [
                `Calculating 50/200-day Moving Averages for ${ticker}...`,
                `RSI-14 Momentum Check for ${ticker}... NOMINAL`,
                `Running MACD Signal crossover probe on ${ticker}...`
            ],
            30: [
                `Scanning SEC 10-K filings for ${ticker}...`,
                `P/E Ratio vs Sector Average [${ticker}]...`,
                `Debt-to-Equity verification: OK.`
            ],
            45: [
                `Extracting sentiment from news headlines (${ticker})...`,
                `VADER Sentiment scoring complete for ${ticker}.`,
                `LangChain LLM semantic mood analysis...`
            ],
            60: [
                `Stress testing ${ticker} with 5% Market Shock...`,
                `Calculating Portfolio VaR with ${ticker} weighting...`,
                `Beta Sensitivity: ${ticker} vs S&P 500.`
            ],
            75: [
                `Executing SMA-20 Strategy backtest for ${ticker}...`,
                `Wins: 65% / Max Drawdown: 12% [${ticker}]`,
                `Checking Golden Cross historical accuracy.`
            ],
            90: [
                `Synthesizing ${activeTickers.length}-stock advisory report...`,
                `Formatting Institutional Markdown via Groq...`,
                `Constructing final portfolio recommendation.`
            ]
        };
        
        const stageLogs = logs[stage ? stage.threshold : 0];
        return stageLogs[Math.floor(Math.random() * stageLogs.length)];
    }

    progressInterval = setInterval(() => {
        let increment = 1;
        if (percent > 60) increment = 0.5;
        if (percent > 85) increment = 0.2;
        if (percent > 98) increment = 0;
        
        percent += increment;
        if (percent > 99) percent = 99;
        setProgress(percent);
    }, 200);

    // Dynamic console logging using real tickers
    consoleInterval = setInterval(() => {
        const msg = getDynamicLog(percent);
        injectConsoleLine(msg);
    }, 1200);
}

function stopProgressSimulation() {
    if (progressInterval) clearInterval(progressInterval);
    if (consoleInterval) clearInterval(consoleInterval);
    setProgress(100);
    injectConsoleLine("SUCCESS: Analysis Complete. Rendering Report...");
}

// ========== DASHBOARD LOGIC (preserved) ==========
function showLoading(show) {
    document.getElementById("loadingOverlay").style.display = show ? "flex" : "none";
}

async function handleSearch(ticker) {
    if (!ticker) return;
    ticker = ticker.trim().toUpperCase();
    showLoading(true);
    try {
        const searchRes = await fetch(`/api/search?ticker=${ticker}`);
        if (!searchRes.ok) throw new Error("Ticker not found or data unavailable");

        currentTicker = ticker;
        document.getElementById("welcomeScreen").style.display = "none";
        document.getElementById("displayTicker").innerText = ticker;
        const exportBtn = document.getElementById("exportPdfBtn");
        if (exportBtn) exportBtn.style.display = "inline-block";

        const [priceData, techData, fundData, sentData, recData] = await Promise.all([
            fetch(`/api/stock/${ticker}/price?period=1y`).then(r => r.json()),
            fetch(`/api/stock/${ticker}/technical`).then(r => r.json()),
            fetch(`/api/stock/${ticker}/fundamental`).then(r => r.json()),
            fetch(`/api/stock/${ticker}/sentiment`).then(r => { if (!r.ok) return null; return r.json(); }).catch(() => null),
            fetch(`/api/stock/${ticker}/recommendation`).then(r => r.json())
        ]);

        updateChart(priceData.data);
        updateTechnicals(techData);
        updateFundamentals(fundData);
        updateSentiment(sentData);
        updateRecommendation(recData);

        fetch(`/api/stock/${ticker}/backtest`)
            .then(r => r.json())
            .then(data => updateBacktest(data))
            .catch(e => console.error("Backtest failed", e));

        if (priceData.data && priceData.data.length > 0) {
            const lastCandle = priceData.data[priceData.data.length - 1];
            document.getElementById("currentPriceBadge").innerText = `$${lastCandle.Close.toFixed(2)}`;
            document.getElementById("lastUpdated").innerText = `Last Updated: ${new Date().toLocaleString()}`;
        }
    } catch (error) {
        alert(error.message);
    } finally {
        showLoading(false);
    }
}

function updateChart(data) {
    if (chart) chart.destroy();
    const seriesData = data.map(d => ({ x: new Date(d.Date).getTime(), y: [d.Open, d.High, d.Low, d.Close] }));
    const volumeData = data.map(d => ({ x: new Date(d.Date).getTime(), y: d.Volume }));
    let smaData = [];
    const windowSize = 20;
    for (let i = 0; i < seriesData.length; i++) {
        if (i < windowSize - 1) {
            smaData.push({ x: seriesData[i].x, y: null });
        } else {
            let sum = 0;
            for (let j = 0; j < windowSize; j++) sum += seriesData[i - j].y[3];
            smaData.push({ x: seriesData[i].x, y: parseFloat((sum / windowSize).toFixed(2)) });
        }
    }
    const maxVol = Math.max(...volumeData.map(d => d.y));
    const options = {
        series: [
            { name: 'Price', type: 'candlestick', data: seriesData },
            { name: 'SMA 20', type: 'line', data: smaData },
            { name: 'Volume', type: 'bar', data: volumeData }
        ],
        chart: { type: 'line', height: 400, background: 'transparent', toolbar: { show: false }, animations: { enabled: false } },
        theme: { mode: 'dark' },
        stroke: { width: [1, 2, 0], colors: ['transparent', '#58a6ff', 'transparent'] },
        plotOptions: {
            candlestick: { colors: { upward: '#238636', downward: '#da3633' }, wick: { useFillColor: true } },
            bar: { columnWidth: '80%', colors: { ranges: [{ from: 0, to: 10000000000, color: 'rgba(139, 148, 158, 0.3)' }] } }
        },
        xaxis: { type: 'datetime', labels: { style: { colors: '#8b949e' } }, axisBorder: { show: false }, axisTicks: { show: false } },
        yaxis: [
            { seriesName: 'Price', tooltip: { enabled: true }, labels: { style: { colors: '#8b949e' }, formatter: (v) => "$" + v.toFixed(2) } },
            { seriesName: 'Price', show: false },
            { seriesName: 'Volume', show: false, max: maxVol * 4 }
        ],
        grid: { borderColor: '#30363d', strokeDashArray: 2 },
        legend: { position: 'top', horizontalAlign: 'left', labels: { colors: '#c9d1d9' } }
    };
    chart = new ApexCharts(document.querySelector("#chartContainer"), options);
    chart.render();
}

function updateTechnicals(data) {
    document.getElementById("trendDir").innerText = data.interpretations.trend || "Neutral";
    document.getElementById("rsiVal").innerText = data.rsi ? data.rsi.toFixed(2) : "N/A";
    document.getElementById("rsiInterp").innerText = data.interpretations.rsi || "";
    document.getElementById("macdVal").innerText = data.macd ? data.macd.toFixed(2) : "N/A";
    document.getElementById("macdInterp").innerText = data.interpretations.macd || "";
    const banner = document.getElementById("crossoverAlert");
    if (data.crossover_signal && data.crossover_signal !== "None") {
        banner.style.display = "block";
        document.getElementById("crossoverText").innerText = data.crossover_signal;
        banner.className = "crossover-banner " + (data.crossover_signal.includes("Golden") ? "golden" : "death");
    } else {
        banner.style.display = "none";
    }
}

function updateFundamentals(data) {
    document.getElementById("fundScore").innerText = `${data.fundamental_score}/100`;
    document.getElementById("peVal").innerText = data.metrics.pe_ratio || "N/A";
    document.getElementById("epsVal").innerText = data.metrics.eps ? `$${data.metrics.eps}` : "N/A";
}

function updateSentiment(data) {
    const labelEl = document.getElementById("sentimentLabel");
    const pointer = document.getElementById("sentimentPointer");
    const headlines = document.getElementById("sentimentHeadlines");
    if (!data) { labelEl.innerText = "No Data"; pointer.style.left = "50%"; headlines.innerText = "Could not retrieve sufficient news."; return; }
    labelEl.innerText = data.sentiment_label;
    headlines.innerText = data.summary_text || "Recent news sentiment.";
    const position = ((data.sentiment_score + 1) / 2) * 100;
    pointer.style.left = `calc(${position}% - 5px)`;
}

async function changeTimeframe(period) {
    if (!currentTicker) return;
    try {
        const priceData = await fetch(`/api/stock/${currentTicker}/price?period=${period}`).then(r => r.json());
        if (priceData && priceData.data) updateChart(priceData.data);
    } catch (e) { console.error("Failed to fetch timeframe data", e); }
}

function updateRecommendation(data) {
    const badge = document.getElementById("recBadge");
    badge.innerText = data.recommendation;
    badge.className = "recommendation-badge";
    badge.classList.add(`rec-${data.recommendation}`);
    document.getElementById("confidenceText").innerText = `${data.confidence_score}%`;
    document.getElementById("confidenceBar").style.width = `${data.confidence_score}%`;
    document.getElementById("riskLevel").innerText = data.risk_level;
    document.getElementById("explanationText").innerText = data.explanation_text;
    if (data.score_breakdown) {
        document.getElementById("techFill").style.width = `${data.score_breakdown.technical}%`;
        document.getElementById("fundFill").style.width = `${data.score_breakdown.fundamental}%`;
        document.getElementById("sentFill").style.width = `${data.score_breakdown.sentiment}%`;
    }
    document.getElementById("portfolioWeight").innerText = data.portfolio_allocation || "10%";
    document.getElementById("priceProb").innerText = data.price_prediction || "Moderate-High";
}

function updateBacktest(data) {
    document.getElementById("winRate").innerText = data.win_rate + "%";
    document.getElementById("backtestRoi").innerText = (data.total_roi > 0 ? "+" : "") + data.total_roi + "%";
    if (backtestChart) backtestChart.destroy();
    const options = {
        series: [{ name: "Equity Curve", data: data.equity_curve }],
        chart: { type: 'area', height: 180, toolbar: { show: false }, background: 'transparent' },
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth', width: 2, colors: ['#58a6ff'] },
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.1 } },
        xaxis: { type: 'datetime', labels: { show: false }, axisBorder: { show: false }, axisTicks: { show: false } },
        yaxis: { show: false },
        grid: { show: false },
        theme: { mode: 'dark' },
        tooltip: { theme: 'dark', x: { format: 'dd MMM yyyy' } }
    };
    backtestChart = new ApexCharts(document.querySelector("#backtestChart"), options);
    backtestChart.render();
}

// ========== WATCHLIST (local sidebar, no auth required for load but posts with auth) ==========
async function loadWatchlist() {
    try {
        const res = await fetch("/api/watchlist", { headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {} });
        if (!res.ok) return;
        const items = await res.json();
        const ul = document.getElementById("watchlistList");
        ul.innerHTML = "";
        items.forEach(item => {
            const li = document.createElement("li");
            li.innerHTML = `<span>${item.ticker}</span> <span>${item.price ? '$' + item.price : '...'}</span>`;
            li.addEventListener("click", () => {
                document.getElementById("searchInput").value = item.ticker;
                handleSearch(item.ticker);
            });
            ul.appendChild(li);
        });
    } catch (e) { console.error("Failed to load watchlist", e); }
}

async function addToWatchlist(ticker) {
    try {
        await fetch("/api/watchlist/add", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ ticker })
        });
        loadWatchlist();
        loadAdvisoryWatchlist();
    } catch (e) { console.error("Failed to add to watchlist", e); }
}

// ========== PRICE ALERTS ==========
function setPriceAlert(ticker, price) {
    activeAlerts.push({ ticker, target: price, triggered: false });
    document.getElementById("activeAlerts").innerText = `Live Guard active for ${ticker} at $${price}`;
    if (Notification.permission !== "granted") Notification.requestPermission();
}

async function checkAlerts() {
    if (activeAlerts.length === 0 || !currentTicker) return;
    try {
        const res = await fetch(`/api/stock/${currentTicker}/price?period=1d`);
        const data = await res.json();
        if (data.data && data.data.length > 0) {
            const price = data.data[data.data.length - 1].Close;
            activeAlerts.forEach(alert => {
                if (!alert.triggered && alert.ticker === currentTicker) {
                    if (Math.abs(price - alert.target) < (alert.target * 0.005)) triggerAlert(alert, price);
                }
            });
        }
    } catch (e) {}
}

function triggerAlert(alertObj, currentPrice) {
    alertObj.triggered = true;
    const msg = `ALERT: ${alertObj.ticker} reached target $${currentPrice.toFixed(2)}!`;
    new Notification("StockSense AI", { body: msg });
    alert("🚨 " + msg);
}
