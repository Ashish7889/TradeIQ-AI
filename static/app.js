// ========== SECURITY HELPERS ==========
function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ========== FORMATTING HELPERS ==========
const priceFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
});

function fmtPrice(val) {
    if (val == null || isNaN(val)) return "—";
    return priceFormatter.format(Number(val));
}

function fmtChange(pct) {
    if (pct == null || isNaN(pct)) {
        return { text: "—", className: "neutral", sign: "" };
    }
    const num = Number(pct);
    const isUp = num >= 0;
    return {
        text: `${isUp ? "+" : ""}${num.toFixed(2)}%`,
        className: isUp ? "up" : "down",
        sign: isUp ? "+" : ""
    };
}

// ========== STATE ==========
let chart = null;
let backtestChart = null;
let currentTicker = "";
let activeAlerts = [];
let currentChartType = "area";
let currentPriceHistory = [];
let authToken = null;
let currentUser = null;
let currentTheme = "light";

try {
    authToken = localStorage.getItem("ss_token") || sessionStorage.getItem("ss_token") || null;
    currentUser = localStorage.getItem("ss_user") || sessionStorage.getItem("ss_user") || null;
    currentTheme = localStorage.getItem("tradeiq_theme") || "light";
} catch (e) {
    currentTheme = "light";
}

// ========== LAZY LOAD APEXCHARTS ==========
let apexChartsPromise = null;
function loadApexCharts() {
    if (window.ApexCharts) {
        return Promise.resolve(window.ApexCharts);
    }
    if (apexChartsPromise) {
        return apexChartsPromise;
    }
    apexChartsPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/apexcharts@7.1.0/dist/apexcharts.min.js";
        script.onload = () => resolve(window.ApexCharts);
        script.onerror = (err) => {
            apexChartsPromise = null;
            reject(err);
        };
        document.head.appendChild(script);
    });
    return apexChartsPromise;
}

const COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
    "META": "Meta Platforms, Inc.",
    "AMD": "Advanced Micro Devices",
    "PLTR": "Palantir Technologies",
    "NFLX": "Netflix, Inc.",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "BTC-USD": "Bitcoin USD"
};

function getCompanyName(ticker) {
    return COMPANY_NAMES[ticker] || `${ticker} Corporation`;
}

function getAvatarColor(char) {
    const colors = [
        { bg: "#eef2ff", text: "#4f46e5" }, // Indigo
        { bg: "#ecfdf5", text: "#059669" }, // Emerald
        { bg: "#f0fdf4", text: "#16a34a" }, // Green
        { bg: "#eff6ff", text: "#2563eb" }, // Blue
        { bg: "#faf5ff", text: "#7c3aed" }, // Purple
        { bg: "#fff7ed", text: "#ea580c" }  // Orange
    ];
    const code = (char || "A").charCodeAt(0);
    return colors[code % colors.length];
}

// ========== THEME MANAGEMENT (Default Light, Dark Toggle) ==========
function applyTheme(theme) {
    currentTheme = theme;
    try {
        localStorage.setItem("tradeiq_theme", theme);
    } catch (e) {
        console.warn("localStorage write failed:", e);
    }
    document.documentElement.setAttribute("data-theme", theme);

    const sunIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`;
    const moonIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

    const btn1 = document.getElementById("themeToggleBtn");
    const btn2 = document.getElementById("mobileThemeToggleBtn");
    if (btn1) btn1.innerHTML = theme === "dark" ? sunIcon : moonIcon;
    if (btn2) btn2.innerHTML = theme === "dark" ? sunIcon : moonIcon;

    if (chart && chart.w && chart.w.config) {
        chart.updateOptions({
            theme: { mode: theme },
            grid: { borderColor: theme === "dark" ? "rgba(255, 255, 255, 0.07)" : "#e5e7eb" }
        });
    }
}

function toggleTheme() {
    applyTheme(currentTheme === "dark" ? "light" : "dark");
}

function toggleSidebarCollapse() {
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.toggle("collapsed");
}

function scrollToWatchlist() {
    showPage('dashboard');
    const el = document.getElementById("watchlistFullCard");
    if (el) el.scrollIntoView({ behavior: 'smooth' });
}

function toggleAccountMenu() {
    const userBar = document.getElementById("userInfoBar");
    if (userBar) userBar.scrollIntoView({ behavior: 'smooth' });
}

function toggleSummaryClamp() {
    const el = document.getElementById("explanationText");
    const btn = document.getElementById("readMoreBtn");
    if (!el || !btn) return;
    const isClamped = el.classList.toggle("clamped");
    btn.innerText = isClamped ? "Read more" : "Read less";
}

// ========== INIT ==========
document.addEventListener("DOMContentLoaded", () => {
    applyTheme(currentTheme);

    const themeBtn = document.getElementById("themeToggleBtn");
    if (themeBtn) themeBtn.addEventListener("click", toggleTheme);
    const mobileThemeBtn = document.getElementById("mobileThemeToggleBtn");
    if (mobileThemeBtn) mobileThemeBtn.addEventListener("click", toggleTheme);

    const collapseBtn = document.getElementById("sidebarCollapseBtn");
    if (collapseBtn) collapseBtn.addEventListener("click", toggleSidebarCollapse);

    if (authToken && currentUser) {
        showApp();
    } else {
        showAuthModal();
    }

    // Auth Form submit handlers
    const loginFormEl = document.getElementById("loginForm");
    if (loginFormEl) loginFormEl.addEventListener("submit", handleSignInStep1Submit);
    const loginPasswordFormEl = document.getElementById("loginPasswordForm");
    if (loginPasswordFormEl) loginPasswordFormEl.addEventListener("submit", handleSignInStep2Submit);
    const signupFormEl = document.getElementById("signupForm");
    if (signupFormEl) signupFormEl.addEventListener("submit", handleSignUpStep1Submit);
    const signupPasswordFormEl = document.getElementById("signupPasswordForm");
    if (signupPasswordFormEl) signupPasswordFormEl.addEventListener("submit", handleSignUpStep2Submit);

    // Escape key navigates back to step 1
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            const step2Login = document.getElementById("signInStep2");
            const step2Signup = document.getElementById("signUpStep2");
            if (step2Login && step2Login.style.display !== "none") {
                backToSignInStep1();
            } else if (step2Signup && step2Signup.style.display !== "none") {
                backToSignUpStep1();
            }
        }
    });

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

    // Timeframe buttons (1W / 1M / 3M / 6M / 1Y)
    document.querySelectorAll(".timeframe-filters button").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".timeframe-filters button").forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            changeTimeframe(e.target.getAttribute("data-period"));
        });
    });

    // Setup ResizeObserver for responsive chart (Item 7)
    const chartBox = document.getElementById("chartContainer");
    if (chartBox && window.ResizeObserver) {
        const ro = new ResizeObserver(() => {
            if (chart && typeof chart.resize === "function") {
                chart.resize();
            }
        });
        ro.observe(chartBox);
    }

    // Pill group selectors
    setupPillGroup("riskGroup");
    setupPillGroup("investGroup");
    setupPillGroup("focusGroup");

    // Account Dashboard Pill group selectors
    setupPillGroup("accountRiskGroup");
    setupPillGroup("accountInvestGroup");
    setupPillGroup("accountFocusGroup");

    // Account Add Ticker Enter key
    const accTickerInput = document.getElementById("accountAddTickerInput");
    if (accTickerInput) {
        accTickerInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addAccountWatchlistStock();
            }
        });
    }

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
    const modal = document.getElementById("authModal");
    const app = document.getElementById("appContainer");
    if (modal) modal.style.display = "flex";
    if (app) app.style.display = "none";
    if (typeof switchAuthFlow === "function") {
        switchAuthFlow("signin");
    }
}

function updateUserDisplays(username) {
    if (!username || username === "undefined") username = "User";
    currentUser = username;
    try {
        localStorage.setItem("ss_user", username);
    } catch (e) {}

    const userDisplay = document.getElementById("userDisplayName");
    if (userDisplay) userDisplay.innerText = username;

    const av = document.getElementById("userAvatar");
    if (av) {
        av.innerText = username.charAt(0).toUpperCase();
        const avColor = getAvatarColor(username.charAt(0));
        av.style.backgroundColor = avColor.bg;
        av.style.color = avColor.text;
    }

    const headerEl = document.getElementById("accountHeaderUser");
    if (headerEl) headerEl.innerText = username;

    const heroUserEl = document.getElementById("accountHeroUsername");
    if (heroUserEl) heroUserEl.innerText = username;

    const heroAv = document.getElementById("accountHeroAvatar");
    if (heroAv) {
        heroAv.innerText = username.charAt(0).toUpperCase();
        const avColor = getAvatarColor(username.charAt(0));
        heroAv.style.backgroundColor = avColor.bg;
        heroAv.style.color = avColor.text;
    }
}

function showApp() {
    document.getElementById("authModal").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    updateUserDisplays(currentUser || "User");

    loadApexCharts();
    loadWatchlist();
    loadPreferences();
    loadAdvisoryWatchlist();
    loadAccountDashboard();
}

function switchAuthFlow(flow) {
    const isSignIn = flow === "signin";
    const signInStep1 = document.getElementById("signInStep1");
    const signInStep2 = document.getElementById("signInStep2");
    const signUpStep1 = document.getElementById("signUpStep1");
    const signUpStep2 = document.getElementById("signUpStep2");

    if (signInStep1) signInStep1.style.display = isSignIn ? "block" : "none";
    if (signInStep2) signInStep2.style.display = "none";
    if (signUpStep1) signUpStep1.style.display = !isSignIn ? "block" : "none";
    if (signUpStep2) signUpStep2.style.display = "none";

    clearAuthErrors();

    if (isSignIn) {
        const u = document.getElementById("loginUsername");
        if (u) {
            u.focus();
            u.select();
        }
    } else {
        const u = document.getElementById("signupUsername");
        if (u) {
            u.focus();
            u.select();
        }
    }
}

function backToSignInStep1() {
    const s1 = document.getElementById("signInStep1");
    const s2 = document.getElementById("signInStep2");
    if (s1) s1.style.display = "block";
    if (s2) s2.style.display = "none";
    clearAuthErrors();
    const u = document.getElementById("loginUsername");
    if (u) {
        u.focus();
        u.select();
    }
}

function backToSignUpStep1() {
    const s1 = document.getElementById("signUpStep1");
    const s2 = document.getElementById("signUpStep2");
    if (s1) s1.style.display = "block";
    if (s2) s2.style.display = "none";
    clearAuthErrors();
    const u = document.getElementById("signupUsername");
    if (u) {
        u.focus();
        u.select();
    }
}

function clearAuthErrors() {
    ["signInError1", "signInError2", "signUpError1", "signUpError2"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerText = "";
    });
}

function handleSignInStep1Submit(e) {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    clearAuthErrors();
    const usernameInput = document.getElementById("loginUsername");
    const username = usernameInput ? usernameInput.value.trim() : "";
    if (!username) {
        const errEl = document.getElementById("signInError1");
        if (errEl) errEl.innerText = "Enter a valid username or email address.";
        if (usernameInput) usernameInput.focus();
        return;
    }
    const displayEl = document.getElementById("signInDisplayUser");
    if (displayEl) displayEl.innerText = username;

    const s1 = document.getElementById("signInStep1");
    const s2 = document.getElementById("signInStep2");
    if (s1) s1.style.display = "none";
    if (s2) s2.style.display = "block";

    const passInput = document.getElementById("loginPassword");
    if (passInput) {
        passInput.value = "";
        passInput.focus();
    }
}

async function handleSignInStep2Submit(e) {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    clearAuthErrors();
    const username = (document.getElementById("loginUsername")?.value || "").trim();
    const password = document.getElementById("loginPassword")?.value || "";

    if (!password) {
        const errEl = document.getElementById("signInError2");
        if (errEl) errEl.innerText = "Please enter your password.";
        document.getElementById("loginPassword")?.focus();
        return;
    }

    const btn = document.getElementById("btnSignInSubmit");
    const origText = btn ? btn.innerText : "Sign in";
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Signing in...";
    }

    try {
        const formData = new URLSearchParams();
        formData.append("username", username);
        formData.append("password", password);

        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString()
        });
        const data = await res.json();
        if (!res.ok) {
            const errEl = document.getElementById("signInError2");
            if (errEl) {
                errEl.innerText = "That username or password isn't right. Check and try again.";
            }
            const passInput = document.getElementById("loginPassword");
            if (passInput) {
                passInput.focus();
                passInput.select();
            }
            return;
        }
        setAuth(data.access_token, data.username || username);
    } catch (err) {
        const errEl = document.getElementById("signInError2");
        if (errEl) errEl.innerText = "Network error. Please try again.";
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = origText;
        }
    }
}

function handleSignUpStep1Submit(e) {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    clearAuthErrors();
    const usernameInput = document.getElementById("signupUsername");
    const username = usernameInput ? usernameInput.value.trim() : "";

    if (!username || username.length < 3) {
        const errEl = document.getElementById("signUpError1");
        if (errEl) errEl.innerText = "Username must be at least 3 characters long.";
        if (usernameInput) usernameInput.focus();
        return;
    }
    if (username.length > 30) {
        const errEl = document.getElementById("signUpError1");
        if (errEl) errEl.innerText = "Username cannot exceed 30 characters.";
        if (usernameInput) usernameInput.focus();
        return;
    }

    const displayEl = document.getElementById("signUpDisplayUser");
    if (displayEl) displayEl.innerText = username;

    const s1 = document.getElementById("signUpStep1");
    const s2 = document.getElementById("signUpStep2");
    if (s1) s1.style.display = "none";
    if (s2) s2.style.display = "block";

    validateLivePassword();
    const passInput = document.getElementById("signupPassword");
    if (passInput) {
        passInput.value = "";
        passInput.focus();
    }
}

async function handleSignUpStep2Submit(e) {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    clearAuthErrors();
    const username = (document.getElementById("signupUsername")?.value || "").trim();
    const password = document.getElementById("signupPassword")?.value || "";

    if (!password) {
        const errEl = document.getElementById("signUpError2");
        if (errEl) errEl.innerText = "Please enter a password.";
        document.getElementById("signupPassword")?.focus();
        return;
    }
    if (password.length < 8) {
        const errEl = document.getElementById("signUpError2");
        if (errEl) errEl.innerText = "Password must be at least 8 characters long.";
        document.getElementById("signupPassword")?.focus();
        return;
    }

    const btn = document.getElementById("btnSignUpSubmit");
    const origText = btn ? btn.innerText : "Create account";
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Creating account...";
    }

    try {
        const res = await fetch("/api/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) {
            const errEl = document.getElementById("signUpError2");
            if (errEl) errEl.innerText = data.detail || "Registration failed. Try a different username.";
            return;
        }

        const formData = new URLSearchParams();
        formData.append("username", username);
        formData.append("password", password);
        const loginRes = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString()
        });
        const loginData = await loginRes.json();
        if (loginRes.ok) {
            setAuth(loginData.access_token, loginData.username || username);
        } else {
            switchAuthFlow("signin");
            const errEl = document.getElementById("signInError1");
            if (errEl) errEl.innerText = "Registration complete. Please sign in.";
        }
    } catch (err) {
        const errEl = document.getElementById("signUpError2");
        if (errEl) errEl.innerText = "Network error. Please try again.";
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = origText;
        }
    }
}

function validateLivePassword() {
    const pass = document.getElementById("signupPassword")?.value || "";
    const ruleLength = document.getElementById("ruleLength");
    if (!ruleLength) return;

    if (pass.length >= 8) {
        ruleLength.classList.add("valid");
        ruleLength.innerHTML = `<svg class="hint-bullet" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg> Minimum 8 characters`;
    } else {
        ruleLength.classList.remove("valid");
        ruleLength.innerHTML = `<svg class="hint-bullet" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><circle cx="12" cy="12" r="6"/></svg> Minimum 8 characters`;
    }
}

function togglePasswordVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (!input) return;

    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";

    const btn = input.parentElement ? input.parentElement.querySelector(".auth-eye-btn") : null;
    if (btn) {
        btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
    }

    if (icon) {
        if (isPassword) {
            icon.innerHTML = `<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>`;
        } else {
            icon.innerHTML = `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>`;
        }
    }
}

function handleForgotPassword() {
    const errBox = document.getElementById("signInError2");
    if (errBox) {
        errBox.innerText = "Password reset is coming soon. Please contact your system administrator or support@tradeiq.ai.";
    }
}

function showAuthError(msg) {
    const errEl = document.getElementById("signInError2") || document.getElementById("signInError1");
    if (errEl) errEl.innerText = msg;
}

function setAuth(token, username) {
    authToken = token;
    currentUser = username;
    const keepSignedInEl = document.getElementById("keepSignedIn");
    const remember = keepSignedInEl ? keepSignedInEl.checked : true;

    try {
        if (remember) {
            localStorage.setItem("ss_token", token);
            localStorage.setItem("ss_user", username);
            sessionStorage.removeItem("ss_token");
            sessionStorage.removeItem("ss_user");
        } else {
            sessionStorage.setItem("ss_token", token);
            sessionStorage.setItem("ss_user", username);
            localStorage.removeItem("ss_token");
            localStorage.removeItem("ss_user");
        }
    } catch (e) {
        console.warn("Storage write failed:", e);
    }
    updateUserDisplays(username);
    showApp();
}

function handleLogout() {
    authToken = null;
    currentUser = null;
    try {
        localStorage.removeItem("ss_token");
        localStorage.removeItem("ss_user");
        sessionStorage.removeItem("ss_token");
        sessionStorage.removeItem("ss_user");
    } catch (e) {}

    const pass1 = document.getElementById("loginPassword");
    if (pass1) pass1.value = "";
    const pass2 = document.getElementById("signupPassword");
    if (pass2) pass2.value = "";

    showAuthModal();
}

function handleAuthError() {
    handleLogout();
    const err = document.getElementById("signInError1");
    if (err) err.innerText = "Your session has expired. Please sign in again.";
}

// Backward-compatibility wrappers & Global exports
function switchTab(tab) {
    switchAuthFlow(tab === "signup" ? "signup" : "signin");
}
function handleLoginFormSubmit(e) { handleSignInStep1Submit(e); }
function handleSignupFormSubmit(e) { handleSignUpStep1Submit(e); }
function handleLogin(e) { handleSignInStep2Submit(e); }
function handleSignup(e) { handleSignUpStep2Submit(e); }

window.switchAuthFlow = switchAuthFlow;
window.backToSignInStep1 = backToSignInStep1;
window.backToSignUpStep1 = backToSignUpStep1;
window.handleSignInStep1Submit = handleSignInStep1Submit;
window.handleSignInStep2Submit = handleSignInStep2Submit;
window.handleSignUpStep1Submit = handleSignUpStep1Submit;
window.handleSignUpStep2Submit = handleSignUpStep2Submit;
window.validateLivePassword = validateLivePassword;
window.togglePasswordVisibility = togglePasswordVisibility;
window.handleForgotPassword = handleForgotPassword;
window.switchTab = switchTab;
window.showAuthError = showAuthError;
window.setAuth = setAuth;
window.handleLogout = handleLogout;

function authHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${authToken}`
    };
}

// ========== NAVIGATION ==========
function showPage(page) {
    const pageDash = document.getElementById("pageDashboard");
    const pageAdv = document.getElementById("pageAdvisory");
    const pageAcc = document.getElementById("pageAccount");
    if (pageDash) pageDash.style.display = page === "dashboard" ? "block" : "none";
    if (pageAdv) pageAdv.style.display = page === "advisory" ? "block" : "none";
    if (pageAcc) pageAcc.style.display = page === "account" ? "block" : "none";

    const navDash = document.getElementById("navTerminalBtn");
    const navAdv = document.getElementById("navAdvisoryBtn");
    const navAcc = document.getElementById("navAccountBtn");
    if (navDash) navDash.classList.toggle("active", page === "dashboard");
    if (navAdv) navAdv.classList.toggle("active", page === "advisory");
    if (navAcc) navAcc.classList.toggle("active", page === "account");

    const mobDash = document.getElementById("mobileTabTerminal");
    const mobAdv = document.getElementById("mobileTabAdvisory");
    const mobAcc = document.getElementById("mobileTabAccount");
    if (mobDash) mobDash.classList.toggle("active", page === "dashboard");
    if (mobAdv) mobAdv.classList.toggle("active", page === "advisory");
    if (mobAcc) mobAcc.classList.toggle("active", page === "account");

    if (page === "account") {
        loadAccountDashboard();
    }
}

// ========== USER ACCOUNT DASHBOARD ==========
async function loadAccountDashboard() {
    if (!authToken) return;
    try {
        const res = await fetch("/api/user/profile", { headers: authHeaders() });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) return;
        const profile = await res.json();

        // 1. User Header, Hero, and Sidebar sync
        const username = profile.username || currentUser || "User";
        updateUserDisplays(username);
        const heroIdEl = document.getElementById("accountHeroId");
        if (heroIdEl) heroIdEl.innerText = `#${profile.id}`;


        // 2. KPIs
        const kpiAssets = document.getElementById("accountKpiAssets");
        if (kpiAssets) kpiAssets.innerText = profile.watchlist_count || 0;
        const wlBadge = document.getElementById("accountWlCountBadge");
        if (wlBadge) wlBadge.innerText = profile.watchlist_count || 0;

        const prefs = profile.preferences || {};
        const kpiRisk = document.getElementById("accountKpiRisk");
        if (kpiRisk) kpiRisk.innerText = prefs.risk_level || "Medium";
        const kpiHorizon = document.getElementById("accountKpiHorizon");
        if (kpiHorizon) kpiHorizon.innerText = prefs.investment_type || "Long-term";

        // 3. Preference controls
        if (prefs.risk_level) setPillValue("accountRiskGroup", prefs.risk_level);
        if (prefs.investment_type) setPillValue("accountInvestGroup", prefs.investment_type);
        if (prefs.focus_type) setPillValue("accountFocusGroup", prefs.focus_type);
        if (prefs.budget_range) document.getElementById("accountBudgetInput").value = prefs.budget_range;
        if (prefs.expected_return) document.getElementById("accountReturnInput").value = prefs.expected_return;

        // 4. Render Saved Watchlist in Account Dashboard
        renderAccountWatchlist();

    } catch (e) {
        console.error("Failed to load account dashboard", e);
    }
}

async function renderAccountWatchlist() {
    try {
        const res = await fetch("/api/watchlist", { headers: authHeaders() });
        if (!res.ok) return;
        const items = await res.json();
        const listEl = document.getElementById("accountWatchlistList");
        if (!listEl) return;
        listEl.innerHTML = "";

        if (!items || items.length === 0) {
            listEl.innerHTML = `<li style="font-size: 12px; color: var(--text-muted); padding: 12px 0; text-align: center;">No assets in your account watchlist yet. Add one above!</li>`;
            return;
        }

        items.forEach(item => {
            const li = document.createElement("li");
            li.className = "account-wl-item";

            const leftDiv = document.createElement("div");
            leftDiv.className = "account-wl-left";

            const av = document.createElement("div");
            av.className = "letter-avatar";
            const avColor = getAvatarColor(item.ticker[0]);
            av.style.backgroundColor = avColor.bg;
            av.style.color = avColor.text;
            av.textContent = (item.ticker[0] || "A").toUpperCase();

            const metaDiv = document.createElement("div");
            metaDiv.className = "account-wl-meta";

            const tickerSpan = document.createElement("span");
            tickerSpan.className = "account-wl-ticker";
            tickerSpan.textContent = item.ticker;

            const companySpan = document.createElement("span");
            companySpan.className = "account-wl-company";
            companySpan.textContent = getCompanyName(item.ticker);

            metaDiv.appendChild(tickerSpan);
            metaDiv.appendChild(companySpan);

            leftDiv.appendChild(av);
            leftDiv.appendChild(metaDiv);

            const rightDiv = document.createElement("div");
            rightDiv.className = "account-wl-right";

            const priceSpan = document.createElement("span");
            priceSpan.className = "tabular";
            priceSpan.style.fontWeight = "600";
            priceSpan.textContent = item.price ? fmtPrice(item.price) : "—";

            const changeInfo = fmtChange(item.change_pct);
            const changePill = document.createElement("span");
            changePill.className = `price-change-pill ${changeInfo.className}`;
            changePill.textContent = changeInfo.text;

            const analyzeBtn = document.createElement("button");
            analyzeBtn.className = "account-wl-action-btn";
            analyzeBtn.textContent = "Analyze";
            analyzeBtn.title = `Analyze ${item.ticker} in Terminal`;
            analyzeBtn.addEventListener("click", () => {
                showPage('dashboard');
                const searchInput = document.getElementById("searchInput");
                if (searchInput) searchInput.value = item.ticker;
                handleSearch(item.ticker);
            });

            const removeBtn = document.createElement("button");
            removeBtn.className = "remove-btn";
            removeBtn.title = `Remove ${item.ticker}`;
            removeBtn.textContent = "✕";
            removeBtn.addEventListener("click", async () => {
                await removeAdvisoryStock(item.ticker);
                loadAccountDashboard();
            });

            rightDiv.appendChild(priceSpan);
            rightDiv.appendChild(changePill);
            rightDiv.appendChild(analyzeBtn);
            rightDiv.appendChild(removeBtn);

            li.appendChild(leftDiv);
            li.appendChild(rightDiv);
            listEl.appendChild(li);
        });
    } catch (e) {
        console.error("Failed to render account watchlist", e);
    }
}

async function addAccountWatchlistStock() {
    const input = document.getElementById("accountAddTickerInput");
    if (!input) return;
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;

    if (!/^[A-Z0-9.\-]{1,10}$/.test(ticker)) {
        alert("Invalid ticker format. Please enter 1-10 uppercase alphanumeric characters.");
        return;
    }

    const btn = document.getElementById("accountAddTickerBtn");
    if (btn) btn.disabled = true;

    try {
        const res = await fetch("/api/watchlist/add", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ ticker })
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Could not add ticker.");
            return;
        }
        input.value = "";
        await loadWatchlist();
        await loadAdvisoryWatchlist();
        await loadAccountDashboard();
    } catch (e) {
        console.error("Failed to add account stock", e);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function saveAccountPreferences() {
    const payload = {
        risk_level: getPillValue("accountRiskGroup"),
        investment_type: getPillValue("accountInvestGroup"),
        focus_type: getPillValue("accountFocusGroup"),
        budget_range: document.getElementById("accountBudgetInput").value || null,
        expected_return: document.getElementById("accountReturnInput").value || null
    };

    try {
        const res = await fetch("/api/preferences", {
            method: "PUT",
            headers: authHeaders(),
            body: JSON.stringify(payload)
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.ok) {
            // Sync with Advisory page
            setPillValue("riskGroup", payload.risk_level);
            setPillValue("investGroup", payload.investment_type);
            setPillValue("focusGroup", payload.focus_type);
            const advBudget = document.getElementById("budgetInput");
            if (advBudget) advBudget.value = payload.budget_range || "";
            const advReturn = document.getElementById("returnInput");
            if (advReturn) advReturn.value = payload.expected_return || "";

            const kpiRisk = document.getElementById("accountKpiRisk");
            if (kpiRisk) kpiRisk.innerText = payload.risk_level || "Medium";
            const kpiHorizon = document.getElementById("accountKpiHorizon");
            if (kpiHorizon) kpiHorizon.innerText = payload.investment_type || "Long-term";

            const msg = document.getElementById("accountPrefSavedMsg");
            if (msg) {
                msg.style.display = "block";
                setTimeout(() => { msg.style.display = "none"; }, 3000);
            }
        }
    } catch (e) {
        console.error("Failed to save account preferences", e);
    }
}

async function handleAccountChangePassword() {
    const curPwd = document.getElementById("currentPasswordInput").value;
    const newPwd = document.getElementById("newPasswordInput").value;
    const msg = document.getElementById("accountPwdMsg");

    if (!curPwd || !newPwd) {
        if (msg) {
            msg.style.display = "block";
            msg.style.color = "var(--danger)";
            msg.innerText = "Please provide both current and new password.";
        }
        return;
    }
    if (newPwd.length < 8) {
        if (msg) {
            msg.style.display = "block";
            msg.style.color = "var(--danger)";
            msg.innerText = "New password must be at least 8 characters long.";
        }
        return;
    }

    try {
        const res = await fetch("/api/user/change-password", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ current_password: curPwd, new_password: newPwd })
        });
        const data = await res.json();
        if (!res.ok) {
            if (msg) {
                msg.style.display = "block";
                msg.style.color = "var(--danger)";
                msg.innerText = data.detail || "Password update failed.";
            }
            return;
        }

        if (msg) {
            msg.style.display = "block";
            msg.style.color = "var(--success)";
            msg.innerText = "Password updated successfully.";
            document.getElementById("currentPasswordInput").value = "";
            document.getElementById("newPasswordInput").value = "";
            setTimeout(() => { msg.style.display = "none"; }, 4000);
        }
    } catch (e) {
        if (msg) {
            msg.style.display = "block";
            msg.style.color = "var(--danger)";
            msg.innerText = "Network error. Please try again.";
        }
    }
}


// ========== ADVISORY PREFERENCES ==========
async function loadPreferences() {
    try {
        const res = await fetch("/api/preferences", { headers: authHeaders() });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) return;
        const prefs = await res.json();
        if (prefs.risk_tolerance) setPillValue("riskGroup", prefs.risk_tolerance);
        if (prefs.investment_horizon) setPillValue("investGroup", prefs.investment_horizon);
        if (prefs.focus_area) setPillValue("focusGroup", prefs.focus_area);
        if (prefs.budget_range) document.getElementById("budgetInput").value = prefs.budget_range;
        if (prefs.expected_return) document.getElementById("returnInput").value = prefs.expected_return;
    } catch (e) {
        console.error("Failed to load preferences", e);
    }
}

function setPillValue(groupId, value) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.querySelectorAll(".pill").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-value") === value);
    });
}

function getPillValue(groupId) {
    const group = document.getElementById(groupId);
    if (!group) return "";
    const active = group.querySelector(".pill.active");
    return active ? active.getAttribute("data-value") : "";
}

async function savePreferences() {
    const payload = {
        risk_tolerance: getPillValue("riskGroup"),
        investment_horizon: getPillValue("investGroup"),
        focus_area: getPillValue("focusGroup"),
        budget_range: document.getElementById("budgetInput").value || null,
        expected_return: document.getElementById("returnInput").value || null
    };
    try {
        const res = await fetch("/api/preferences", {
            method: "PUT",
            headers: authHeaders(),
            body: JSON.stringify(payload)
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.ok) {
            const msg = document.getElementById("prefSavedMsg");
            msg.style.display = "block";
            setTimeout(() => { msg.style.display = "none"; }, 3000);
        }
    } catch (e) {
        console.error("Failed to save preferences", e);
    }
}

// ========== ADVISORY WATCHLIST ==========
async function clearAdvisoryWatchlist() {
    if (!confirm("Are you sure you want to clear your entire advisory basket?")) return;
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
        if (res.status === 401) { handleAuthError(); return; }
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
        ul.innerHTML = `<li style="font-size: 12px; color: var(--text-muted); padding: 8px 0;">No candidate tickers added yet. Type a ticker above or click a Quick Add chip!</li>`;
        return;
    }
    items.forEach(item => {
        const li = document.createElement("li");
        li.className = "advisory-wl-item";

        const infoDiv = document.createElement("div");
        infoDiv.style.display = "flex";
        infoDiv.style.alignItems = "center";
        infoDiv.style.gap = "8px";

        const av = document.createElement("div");
        av.className = "letter-avatar";
        const avColor = getAvatarColor(item.ticker[0]);
        av.style.backgroundColor = avColor.bg;
        av.style.color = avColor.text;
        av.textContent = (item.ticker[0] || "A").toUpperCase();

        const strong = document.createElement("strong");
        strong.textContent = item.ticker;

        const span = document.createElement("span");
        span.className = "wl-price tabular";
        span.textContent = item.price ? fmtPrice(item.price) : "—";

        infoDiv.appendChild(av);
        infoDiv.appendChild(strong);
        infoDiv.appendChild(span);

        const btn = document.createElement("button");
        btn.className = "remove-btn";
        btn.title = `Remove ${item.ticker}`;
        btn.textContent = "✕";
        btn.addEventListener("click", () => removeAdvisoryStock(item.ticker));

        li.appendChild(infoDiv);
        li.appendChild(btn);
        ul.appendChild(li);
    });
}

async function addAdvisoryStock(tickerOverride) {
    const input = document.getElementById("advisoryTicker");
    const rawVal = tickerOverride || (input ? input.value : "");
    const ticker = rawVal.trim().toUpperCase();
    if (!ticker) return;

    if (!/^[A-Z0-9.\-]{1,10}$/.test(ticker)) {
        alert("Invalid ticker format. Please enter 1-10 uppercase alphanumeric characters.");
        return;
    }

    const btn = document.getElementById("addAdvisoryStockBtn");
    if (btn) btn.disabled = true;

    try {
        const res = await fetch("/api/watchlist/add", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ ticker })
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Could not add ticker.");
            return;
        }
        if (input) input.value = "";
        await loadAdvisoryWatchlist();
        await loadWatchlist();
    } catch (e) {
        console.error("Failed to add advisory stock", e);
    } finally {
        if (btn) btn.disabled = false;
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
        if (res.status === 401) { handleAuthError(); return; }
        await loadAdvisoryWatchlist();
        await loadWatchlist();
    } catch (e) {
        console.error("Failed to remove advisory stock", e);
    }
}

// ========== AI REPORT GENERATION ==========
let progressInterval = null;
let consoleInterval = null;

const PIPELINE_STAGES = [
    { threshold: 0, text: "Stage 1: Ingesting Real-Time Market Data" },
    { threshold: 20, text: "Stage 2: Calculating Moving Averages & Volatility" },
    { threshold: 40, text: "Stage 3: Screening Fundamentals & Valuation Ratios" },
    { threshold: 60, text: "Stage 4: Sentiment Mining & NLP Mood Analysis" },
    { threshold: 80, text: "Stage 5: Strategy Simulation & Backtesting" },
    { threshold: 90, text: "Stage 6: Synthesizing Executive Memorandum via LLM" }
];

async function generateReport() {
    const btn = document.getElementById("generateBtn");
    const loading = document.getElementById("reportLoading");
    const output = document.getElementById("reportOutput");

    btn.disabled = true;
    loading.style.display = "block";
    output.style.display = "none";

    startProgressSimulation();

    try {
        const res = await fetch("/api/report/generate", {
            method: "POST",
            headers: authHeaders()
        });
        if (res.status === 401) {
            handleAuthError();
            return;
        }
        const data = await res.json();
        if (!res.ok) {
            alert(data.detail || "Report generation failed.");
            return;
        }

        stopProgressSimulation();
        renderExecutiveReport(data);
    } catch (e) {
        console.error("Report generation failed", e);
        stopProgressSimulation();
        alert("An error occurred while generating the tactical report.");
    } finally {
        btn.disabled = false;
        loading.style.display = "none";
    }
}

function renderExecutiveReport(data) {
    const output = document.getElementById("reportOutput");
    const content = document.getElementById("reportContent");
    if (!content || !output) return;

    // 1. Memo Header Meta (Item 4: "Generated <local time>", tickers covered, model name if returned)
    const currentTimeStr = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const genTime = data.generated_at || currentTimeStr;

    let tickersList = [];
    if (Array.isArray(data.tickers) && data.tickers.length > 0) {
        tickersList = data.tickers;
    } else if (typeof data.tickers === "string" && data.tickers.trim()) {
        tickersList = [data.tickers.trim()];
    } else if (data.full_data && data.full_data.length > 0) {
        tickersList = data.full_data.map(d => d.ticker).filter(Boolean);
    } else if (data.portfolio_ticker) {
        tickersList = [data.portfolio_ticker];
    }
    const tickersText = tickersList.join(", ");
    const modelText = data.model ? escapeHtml(data.model) : "";

    const headerMetaHtml = `
        <div class="memo-header-meta">
            <div class="memo-meta-main">
                <span class="memo-meta-time">Generated ${escapeHtml(genTime)}, data as of today</span>
                ${tickersText ? `<span class="memo-meta-dot">•</span><span class="memo-meta-tickers">Covered: <strong>${escapeHtml(tickersText)}</strong></span>` : ''}
            </div>
            ${modelText ? `<div class="memo-meta-model"><span class="memo-model-badge">${modelText}</span></div>` : ''}
        </div>
    `;

    // 2. Optional Dashboard Snapshot (if full_data)
    let dashboardHtml = "";
    if (data.full_data && data.full_data.length > 0) {
        const primary = data.full_data[0];
        const breakdown = primary.score_breakdown || {};
        const techVal = breakdown.technical != null ? Number(breakdown.technical).toFixed(0) : "N/A";
        const fundVal = breakdown.fundamental != null ? Number(breakdown.fundamental).toFixed(0) : "N/A";
        const sentVal = breakdown.sentiment != null ? Number(breakdown.sentiment).toFixed(0) : "N/A";

        dashboardHtml = `
            <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border-subtle); padding-bottom: 12px; margin-bottom: 16px;">
                <div>
                    <h3 style="font-size: 16px; font-weight: 700; color: var(--text-primary); margin: 0 0 2px;">${escapeHtml(data.portfolio_ticker || primary.ticker)}</h3>
                    <span style="font-size: 12px; color: var(--text-secondary);">${getCompanyName(data.portfolio_ticker || primary.ticker)}</span>
                </div>
                <div style="font-size: 12.5px; font-weight: 700; color: var(--accent);">Confidence: ${Number(data.confidence_score) || 0}%</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px;">
                <div style="background: var(--bg-surface-elevated); padding: 10px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">Technical Score</div>
                    <div style="font-size: 14px; font-weight: 700;" class="tabular">${techVal}/100</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 10px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">Fundamental Score</div>
                    <div style="font-size: 14px; font-weight: 700;" class="tabular">${fundVal}/100</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 10px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">Sentiment Score</div>
                    <div style="font-size: 14px; font-weight: 700;" class="tabular">${sentVal}/100</div>
                </div>
            </div>
        `;
    }

    // 3. Parse Markdown with Table Enhancements and Extract Table of Contents
    const reportText = data.report || "";
    const { html: parsedHtml, toc } = parseMarkdownOptimized(reportText);

    // 4. Desktop Sticky Table of Contents (Item 6)
    let tocHtml = "";
    if (toc && toc.length > 0) {
        tocHtml = `
            <aside class="memo-toc" id="memoToc" aria-label="Table of contents">
                <div class="memo-toc-title">Contents</div>
                <nav class="memo-toc-nav">
                    ${toc.map(item => `<a href="#${item.id}" class="memo-toc-link" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</a>`).join('')}
                </nav>
            </aside>
        `;
    }

    // 5. Footer Note (Item 5: Educational research only. Not financial advice.)
    const footerDisclaimerHtml = `
        <footer class="memo-footer-disclaimer">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span>Educational research only. Not financial advice.</span>
        </footer>
    `;

    // Assemble complete memo
    content.innerHTML = `
        <div class="memo-wrapper">
            ${headerMetaHtml}
            <div class="memo-layout">
                <article class="memo-main-col">
                    ${dashboardHtml}
                    <div class="memo-prose">
                        ${parsedHtml}
                    </div>
                    ${footerDisclaimerHtml}
                </article>
                ${tocHtml}
            </div>
        </div>
    `;

    output.style.display = "block";
    output.scrollIntoView({ behavior: "smooth" });
}

function parseMarkdownOptimized(md) {
    const lines = md.split('\n');
    let inTable = false;
    let tableHeaders = [];
    let tableRows = [];
    const finalBlocks = [];
    const toc = [];
    let inList = false;
    let listItems = [];

    function flushList() {
        if (inList && listItems.length > 0) {
            finalBlocks.push(`<ul>${listItems.join('')}</ul>`);
            listItems = [];
            inList = false;
        }
    }

    function flushTable() {
        if (!inTable) return;
        let html = '<div class="memo-table-container"><table class="memo-table">';
        if (tableHeaders.length > 0) {
            html += '<thead><tr>';
            tableHeaders.forEach(col => {
                const signalClass = col.type === 'signal' ? ' class="col-signal"' : '';
                html += `<th${signalClass}>${escapeHtml(col.title)}</th>`;
            });
            html += '</tr></thead>';
        }
        if (tableRows.length > 0) {
            html += '<tbody>';
            tableRows.forEach(row => {
                html += '<tr>';
                row.forEach((cell, idx) => {
                    const col = tableHeaders[idx] || { type: 'text' };
                    if (col.type === 'rec') {
                        const cleanRec = cell.replace(/\*/g, '').trim().toUpperCase();
                        let badgeClass = 'rec-pill rec-pill-neutral';
                        if (cleanRec.includes('BUY')) badgeClass = 'rec-pill rec-pill-buy';
                        else if (cleanRec.includes('SELL')) badgeClass = 'rec-pill rec-pill-sell';
                        else if (cleanRec.includes('HOLD')) badgeClass = 'rec-pill rec-pill-hold';
                        html += `<td><span class="${badgeClass}">${escapeHtml(cleanRec)}</span></td>`;
                    } else if (col.type === 'score') {
                        const cleanVal = cell.replace(/\*/g, '').trim();
                        const num = parseFloat(cleanVal.replace(/[^0-9.]/g, ''));
                        if (!isNaN(num)) {
                            const pct = Math.min(100, Math.max(0, num));
                            html += `
                                <td>
                                    <div class="table-score-wrap">
                                        <span class="table-score-val tabular">${num}</span>
                                        <div class="table-score-track">
                                            <div class="table-score-bar" style="width: ${pct}%;"></div>
                                        </div>
                                    </div>
                                </td>
                            `;
                        } else {
                            html += `<td>${parseInlineMarkdown(cell)}</td>`;
                        }
                    } else if (col.type === 'ticker') {
                        const cleanTicker = cell.replace(/\*/g, '').trim();
                        html += `<td><strong class="memo-ticker-highlight">${escapeHtml(cleanTicker)}</strong></td>`;
                    } else if (col.type === 'signal') {
                        html += `<td class="col-signal">${parseInlineMarkdown(cell)}</td>`;
                    } else {
                        html += `<td>${parseInlineMarkdown(cell)}</td>`;
                    }
                });
                html += '</tr>';
            });
            html += '</tbody>';
        }
        html += '</table></div>';
        finalBlocks.push(html);
        inTable = false;
        tableHeaders = [];
        tableRows = [];
    }

    lines.forEach(rawLine => {
        const trimmed = rawLine.trim();

        // Table line detection: starts and ends with |
        if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
            flushList();
            if (!inTable) {
                inTable = true;
                tableHeaders = [];
                tableRows = [];
                // First row is header row
                const rawCols = trimmed.split('|').slice(1, -1).map(c => c.trim());
                tableHeaders = rawCols.map(colText => {
                    let title = colText.replace(/\*/g, '').trim();
                    // Item 3: Rename "Accuracy" column to "Backtest win rate"
                    if (/^accuracy$/i.test(title)) {
                        title = "Backtest win rate";
                    }
                    let type = 'text';
                    if (/rec|recommendation|rating/i.test(title)) type = 'rec';
                    else if (/score/i.test(title)) type = 'score';
                    else if (/signal/i.test(title)) type = 'signal';
                    else if (/ticker|symbol/i.test(title)) type = 'ticker';
                    else if (/win rate|accuracy|backtest/i.test(title)) type = 'win_rate';
                    return { title, type };
                });
                return;
            }

            // Divider row check
            if (trimmed.includes('---')) {
                return;
            }

            // Data row
            const cells = trimmed.split('|').slice(1, -1).map(c => c.trim());
            tableRows.push(cells);
            return;
        }

        // Exiting table
        if (inTable) {
            flushTable();
        }

        // Bullet lists
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            inList = true;
            listItems.push(`<li>${parseInlineMarkdown(trimmed.slice(2))}</li>`);
            return;
        } else {
            flushList();
        }

        if (trimmed === "") {
            return; // Tighten spacing: do not emit double <br> tags
        } else if (trimmed.startsWith('### ')) {
            const hText = trimmed.slice(4).trim();
            finalBlocks.push(`<h3>${parseInlineMarkdown(hText)}</h3>`);
        } else if (trimmed.startsWith('## ')) {
            const hText = trimmed.slice(3).trim();
            const cleanText = hText.replace(/\*/g, '').replace(/^[0-9.]+\s*/, '').trim();
            const slug = "sec-" + cleanText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
            toc.push({ id: slug, title: cleanText });
            finalBlocks.push(`<h2 id="${slug}">${parseInlineMarkdown(hText)}</h2>`);
        } else if (trimmed.startsWith('# ')) {
            const hText = trimmed.slice(2).trim();
            const cleanText = hText.replace(/\*/g, '').replace(/^[0-9.]+\s*/, '').trim();
            const slug = "sec-" + cleanText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
            toc.push({ id: slug, title: cleanText });
            finalBlocks.push(`<h2 id="${slug}">${parseInlineMarkdown(hText)}</h2>`);
        } else {
            finalBlocks.push(`<p>${parseInlineMarkdown(trimmed)}</p>`);
        }
    });

    flushList();
    if (inTable) {
        flushTable();
    }

    return { html: finalBlocks.join(''), toc };
}

function parseInlineMarkdown(text) {
    if (!text) return "";
    return escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code style="background: var(--bg-surface-elevated); padding: 2px 4px; border-radius: 4px; font-size: 11px;">$1</code>');
}


function setProgress(percent) {
    const text = document.getElementById("progressPercent");
    const stage = document.getElementById("progressStage");
    if (text) text.innerText = `${Math.round(percent)}%`;

    const currentStage = [...PIPELINE_STAGES].reverse().find(s => percent >= s.threshold);
    if (stage && currentStage) stage.innerText = currentStage.text;
}

function startProgressSimulation() {
    let percent = 0;
    setProgress(0);
    const consoleEl = document.getElementById("scanningConsole");
    if (consoleEl) consoleEl.innerHTML = "<div>[SYSTEM] Pipeline initialized...</div>";

    progressInterval = setInterval(() => {
        if (percent < 90) {
            percent += Math.random() * 8 + 3;
            if (percent > 90) percent = 90;
            setProgress(percent);
        }
    }, 800);
}

function stopProgressSimulation() {
    if (progressInterval) clearInterval(progressInterval);
    if (consoleInterval) clearInterval(consoleInterval);
    setProgress(100);
}

// ========== DASHBOARD LOGIC ==========
function showLoading(show) {
    document.getElementById("loadingOverlay").style.display = show ? "flex" : "none";
}

function setChartType(type) {
    currentChartType = type;
    const areaBtn = document.getElementById("chartTypeArea");
    const candleBtn = document.getElementById("chartTypeCandle");
    if (areaBtn) areaBtn.classList.toggle("active", type === "area");
    if (candleBtn) candleBtn.classList.toggle("active", type === "candlestick");
    if (currentPriceHistory && currentPriceHistory.length > 0) {
        updateChart(currentPriceHistory);
    }
}

async function handleSearch(ticker) {
    if (!ticker) return;
    ticker = ticker.trim().toUpperCase();
    showLoading(true);
    try {
        const reqHeaders = authToken ? { "Authorization": `Bearer ${authToken}` } : {};
        const searchRes = await fetch(`/api/search?ticker=${ticker}`, { headers: reqHeaders });
        if (!searchRes.ok) throw new Error("Ticker not found or data unavailable");

        currentTicker = ticker;
        document.getElementById("welcomeScreen").style.display = "none";
        document.getElementById("displayTicker").innerText = ticker;
        const compEl = document.getElementById("displayCompanyName");
        if (compEl) compEl.innerText = getCompanyName(ticker);

        const exportBtn = document.getElementById("exportPdfBtn");
        if (exportBtn) exportBtn.style.display = "inline-flex";

        const [priceData, techData, fundData, sentData, recData] = await Promise.all([
            fetch(`/api/stock/${ticker}/price?period=1y`, { headers: reqHeaders }).then(r => r.json()),
            fetch(`/api/stock/${ticker}/technical`, { headers: reqHeaders }).then(r => r.json()),
            fetch(`/api/stock/${ticker}/fundamental`, { headers: reqHeaders }).then(r => r.json()),
            fetch(`/api/stock/${ticker}/sentiment`, { headers: reqHeaders }).then(r => { if (!r.ok) return null; return r.json(); }).catch(() => null),
            fetch(`/api/stock/${ticker}/recommendation`, { headers: reqHeaders }).then(r => {
                if (r.status === 401) {
                    handleAuthError();
                    return null;
                }
                return r.json();
            })
        ]);

        updateChart(priceData.data);
        updateTechnicals(techData);
        updateFundamentals(fundData);
        updateSentiment(sentData);
        if (recData) updateRecommendation(recData);

        fetch(`/api/stock/${ticker}/backtest`, { headers: reqHeaders })
            .then(r => r.json())
            .then(data => updateBacktest(data))
            .catch(e => console.error("Backtest failed", e));

        if (priceData.data && priceData.data.length > 0) {
            const lastCandle = priceData.data[priceData.data.length - 1];
            const prevCandle = priceData.data.length > 1 ? priceData.data[priceData.data.length - 2] : null;
            document.getElementById("currentPriceBadge").innerText = fmtPrice(lastCandle.Close);
            document.getElementById("lastUpdated").innerText = `Last updated: ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

            // Single unified change calculation
            let pctChange = null;
            if (prevCandle && prevCandle.Close) {
                pctChange = ((lastCandle.Close - prevCandle.Close) / prevCandle.Close) * 100;
            }
            const changeInfo = fmtChange(pctChange);
            const pill = document.getElementById("priceChangePill");
            const signEl = document.getElementById("priceChangeSign");
            const pctEl = document.getElementById("priceChangePercent");
            if (pill && pctEl) {
                pill.style.display = "inline-flex";
                pill.className = `price-change-pill ${changeInfo.className}`;
                if (signEl) signEl.innerText = changeInfo.sign;
                pctEl.innerText = changeInfo.text;
            }
        }
    } catch (error) {
        alert(error.message);
    } finally {
        showLoading(false);
    }
}

// ========== SECTION A: PRICE CHART FIX ==========
// Cause of bug: dataLabels was not disabled, causing ApexCharts to print raw float coordinates on every data point.
// Solution: dataLabels explicitly disabled; clean recreation on render; fmtPrice on axis/tooltip; at most ONE last-price pill annotation.
async function updateChart(data) {
    if (!data || !Array.isArray(data) || data.length === 0) return;
    await loadApexCharts();
    if (!window.ApexCharts) return;
    currentPriceHistory = data;

    // Dispose old chart cleanly so annotations/markers never accumulate (Item 2)
    if (chart) {
        chart.destroy();
        chart = null;
    }

    const isDark = currentTheme === "dark";
    const areaData = data.map(d => ({ x: new Date(d.Date).getTime(), y: d.Close }));
    const candleData = data.map(d => ({ x: new Date(d.Date).getTime(), y: [d.Open, d.High, d.Low, d.Close] }));

    // Compute SMA 20
    let smaData = [];
    const windowSize = 20;
    for (let i = 0; i < data.length; i++) {
        if (i < windowSize - 1) {
            smaData.push({ x: new Date(data[i].Date).getTime(), y: null });
        } else {
            let sum = 0;
            for (let j = 0; j < windowSize; j++) sum += data[i - j].Close;
            smaData.push({ x: new Date(data[i].Date).getTime(), y: parseFloat((sum / windowSize).toFixed(2)) });
        }
    }

    const lastPrice = data[data.length - 1].Close;

    let series = [];
    let stroke = {};
    let fill = {};

    if (currentChartType === "area") {
        series = [
            { name: 'Price', type: 'area', data: areaData }
        ];
        stroke = {
            curve: 'smooth',
            width: 2,
            colors: ['#4f46e5']
        };
        fill = {
            type: 'gradient',
            gradient: {
                shadeIntensity: 1,
                opacityFrom: isDark ? 0.35 : 0.22,
                opacityTo: 0.02,
                stops: [0, 95, 100]
            }
        };
    } else {
        series = [
            { name: 'Price', type: 'candlestick', data: candleData },
            { name: 'SMA 20', type: 'line', data: smaData }
        ];
        stroke = {
            width: [1, 2],
            colors: ['transparent', '#4f46e5']
        };
        fill = { type: 'solid' };
    }

    // At most ONE label on the right axis (last price), styled as a small accent-color pill (Item 4)
    const annotations = {
        yaxis: (lastPrice != null) ? [{
            y: lastPrice,
            borderColor: '#4f46e5',
            strokeDashArray: 2,
            label: {
                borderColor: '#4f46e5',
                style: {
                    color: '#ffffff',
                    background: '#4f46e5',
                    fontSize: '11px',
                    fontFamily: 'Inter',
                    fontWeight: 600,
                    padding: { left: 6, right: 6, top: 3, bottom: 3 }
                },
                text: fmtPrice(lastPrice),
                position: 'right',
                textAnchor: 'start'
            }
        }] : []
    };

    const options = {
        series: series,
        chart: {
            type: currentChartType === "area" ? "area" : "candlestick",
            height: 360,
            background: 'transparent',
            toolbar: { show: false },
            animations: {
                enabled: true,
                easing: 'easeout',
                speed: 600,
                animateGradually: { enabled: false },
                dynamicAnimation: { enabled: false }
            }
        },
        theme: { mode: isDark ? 'dark' : 'light' },
        // CRITICAL FIX: Explicitly disable per-point data labels (Item 1)
        dataLabels: {
            enabled: false
        },
        markers: {
            size: 0,
            hover: {
                size: 4,
                sizeOffset: 2
            }
        },
        stroke: stroke,
        fill: fill,
        annotations: annotations,
        plotOptions: {
            candlestick: {
                colors: { upward: '#10b981', downward: '#ef4444' },
                wick: { useFillColor: true }
            }
        },
        xaxis: {
            type: 'datetime',
            tickAmount: 6, // About 6 x-axis labels (Item 5)
            labels: {
                datetimeUTC: false,
                format: 'MMM dd',
                style: { colors: isDark ? '#94a3b8' : '#64748b', fontSize: '11px', fontFamily: 'Inter' }
            },
            axisBorder: { show: false },
            axisTicks: { show: false }
        },
        yaxis: {
            opposite: true, // Right axis (Item 5)
            labels: {
                style: { colors: isDark ? '#94a3b8' : '#64748b', fontSize: '11px', fontFamily: 'Inter' },
                formatter: (v) => fmtPrice(v) // Tabular 2 decimals via fmtPrice (Item 3)
            }
        },
        grid: {
            borderColor: isDark ? 'rgba(255, 255, 255, 0.07)' : '#e5e7eb',
            strokeDashArray: 2
        },
        tooltip: {
            enabled: true,
            shared: false,
            intersect: false,
            theme: isDark ? 'dark' : 'light',
            x: { format: 'dd MMM yyyy' },
            y: {
                formatter: (v) => fmtPrice(v)
            }
        },
        legend: {
            show: currentChartType === "candlestick",
            position: 'top',
            horizontalAlign: 'left',
            labels: { colors: isDark ? '#f8fafc' : '#0f172a' }
        }
    };

    chart = new ApexCharts(document.querySelector("#chartContainer"), options);
    chart.render();
}

// Period buttons 1W/1M/3M/6M/1Y change both request and visible range (Item 6)
async function changeTimeframe(period) {
    if (!currentTicker) return;
    try {
        const reqHeaders = authToken ? { "Authorization": `Bearer ${authToken}` } : {};
        const priceData = await fetch(`/api/stock/${currentTicker}/price?period=${period}`, { headers: reqHeaders }).then(r => r.json());
        if (priceData && priceData.data && priceData.data.length > 0) {
            updateChart(priceData.data);
        }
    } catch (e) {
        console.error("Failed to fetch timeframe data", e);
    }
}

function updateTechnicals(data) {
    if (!data || !data.available) {
        document.getElementById("trendDir").innerText = "Neutral";
        document.getElementById("rsiVal").innerText = "—";
        document.getElementById("rsiInterp").innerText = "";
        document.getElementById("macdVal").innerText = "—";
        document.getElementById("macdInterp").innerText = "";
        const banner = document.getElementById("crossoverAlert");
        if (banner) banner.style.display = "none";
        return;
    }
    const interp = data.interpretations || {};
    document.getElementById("trendDir").innerText = interp.trend || "Neutral";
    document.getElementById("rsiVal").innerText = data.rsi != null ? Number(data.rsi).toFixed(2) : "—";
    document.getElementById("rsiInterp").innerText = interp.rsi || "";
    document.getElementById("macdVal").innerText = data.macd != null ? Number(data.macd).toFixed(2) : "—";
    document.getElementById("macdInterp").innerText = interp.macd || "";

    const banner = document.getElementById("crossoverAlert");
    if (banner && (interp.crossover === "Golden Cross" || interp.crossover === "Death Cross")) {
        banner.style.display = "block";
        document.getElementById("crossoverText").innerText = `${interp.crossover} Active`;
        document.getElementById("crossoverIcon").innerText = interp.crossover === "Golden Cross" ? "⚡" : "⚠️";
    } else if (banner) {
        banner.style.display = "none";
    }
}

function updateFundamentals(data) {
    if (!data || !data.available || !data.metrics) {
        document.getElementById("fundScore").innerText = "—";
        document.getElementById("peVal").innerText = "—";
        document.getElementById("epsVal").innerText = "—";
        return;
    }
    document.getElementById("fundScore").innerText = data.fundamental_score != null ? `${data.fundamental_score}/100` : "—";
    document.getElementById("peVal").innerText = data.metrics.pe_ratio != null ? Number(data.metrics.pe_ratio).toFixed(2) : "—";
    document.getElementById("epsVal").innerText = data.metrics.eps != null ? fmtPrice(data.metrics.eps) : "—";
}

function updateSentiment(data) {
    const labelEl = document.getElementById("sentimentLabel");
    const pointer = document.getElementById("sentimentPointer");
    const briefEl = document.getElementById("sentimentSummaryBrief");
    if (!data) {
        if (labelEl) labelEl.innerText = "No Data";
        if (pointer) pointer.style.left = "50%";
        if (briefEl) briefEl.innerText = "Could not retrieve sufficient news.";
        updateNewsList(null);
        return;
    }
    if (labelEl) labelEl.innerText = data.sentiment_label || "Neutral";
    if (briefEl) briefEl.innerText = data.summary_text ? "Real-time news headlines synthesized." : "No active news.";
    const position = ((data.sentiment_score + 1) / 2) * 100;
    if (pointer) pointer.style.left = `${Math.min(100, Math.max(0, position))}%`;

    updateNewsList(data);
}

// ========== SECTION B: NEWS / SENTIMENT FIX ==========
// Item 8 & 9: Split on "|" only, trim, drop empties, up to 5 rows with 2-line clamp.
// Remove all invented source names and timestamps!
function updateNewsList(data) {
    const container = document.getElementById("sentimentHeadlines");
    if (!container) return;

    if (!data || !data.summary_text) {
        container.innerHTML = `<p style="font-size: 12px; color: var(--text-muted); padding: 8px 0;">No active headlines available.</p>`;
        return;
    }

    const headlines = data.summary_text
        .split("|")
        .map(h => h.trim())
        .filter(h => h.length > 0)
        .slice(0, 5);

    if (headlines.length === 0) {
        container.innerHTML = `<p style="font-size: 12px; color: var(--text-muted); padding: 8px 0;">No active headlines available.</p>`;
        return;
    }

    let html = `<ul class="news-list" id="newsListContainer">`;
    headlines.forEach(headline => {
        html += `
            <li class="news-item">
                <span class="news-title">${escapeHtml(headline)}</span>
            </li>
        `;
    });
    html += `</ul>`;
    container.innerHTML = html;
}

function updateRecommendation(data) {
    if (!data) return;
    const badge = document.getElementById("recBadge");
    if (badge) {
        badge.innerText = data.recommendation || "HOLD";
        badge.className = `decision-badge rec-${data.recommendation || 'HOLD'}`;
    }
    document.getElementById("confidenceText").innerText = `${data.confidence_score || 0}%`;
    document.getElementById("confidenceBar").style.width = `${data.confidence_score || 0}%`;
    document.getElementById("riskLevel").innerText = data.risk_level || "Medium";

    // Item 15: Clamp summary and show read more toggle if long
    const explEl = document.getElementById("explanationText");
    const readMoreBtn = document.getElementById("readMoreBtn");
    if (explEl) {
        explEl.innerText = data.explanation_text || "";
        if (readMoreBtn) {
            readMoreBtn.style.display = (data.explanation_text && data.explanation_text.length > 200) ? "inline-block" : "none";
            readMoreBtn.innerText = "Read more";
            explEl.classList.add("clamped");
        }
    }

    if (data.score_breakdown) {
        const b = data.score_breakdown;
        document.getElementById("techFill").style.width = `${b.technical || 0}%`;
        document.getElementById("fundFill").style.width = `${b.fundamental || 0}%`;
        document.getElementById("sentFill").style.width = `${b.sentiment || 0}%`;
        const tLabel = document.getElementById("techScoreLabel");
        const fLabel = document.getElementById("fundScoreLabel");
        const sLabel = document.getElementById("sentScoreLabel");
        if (tLabel) tLabel.innerText = `${b.technical || 0}/100`;
        if (fLabel) fLabel.innerText = `${b.fundamental || 0}/100`;
        if (sLabel) sLabel.innerText = `${b.sentiment || 0}/100`;
    }
    document.getElementById("portfolioWeight").innerText = data.portfolio_allocation || "10%";
    document.getElementById("priceProb").innerText = data.price_prediction || "Moderate-High";
}

// ========== SECTION D: BACKTEST FIX ==========
// Item 12: Read real fields: available, accuracy, win_rate, total_signals, period.
// Item 13: Win rate uses neutral text color.
function updateBacktest(data) {
    const winRateEl = document.getElementById("winRate");
    const roiEl = document.getElementById("backtestRoi");
    const chartContainer = document.getElementById("backtestChart");

    if (backtestChart) {
        backtestChart.destroy();
        backtestChart = null;
    }

    if (!data || !data.available) {
        if (winRateEl) {
            winRateEl.innerText = "—";
            winRateEl.style.color = "var(--text-primary)";
        }
        if (roiEl) {
            roiEl.innerText = "—";
            roiEl.style.color = "var(--text-secondary)";
        }
        if (chartContainer) {
            chartContainer.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 140px; text-align: center; color: var(--text-muted); font-size: 12px; gap: 6px;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    <span>Insufficient historical data to simulate RSI + SMA50 signals for this asset.</span>
                </div>
            `;
        }
        return;
    }

    // Win rate uses neutral text color (Item 13)
    if (winRateEl) {
        winRateEl.innerText = `${Number(data.win_rate).toFixed(1)}%`;
        winRateEl.style.color = "var(--text-primary)"; // Neutral text color
    }

    // Signals count and evaluation
    if (roiEl) {
        roiEl.innerText = `${data.total_signals} signals (${data.period || "1 Year"})`;
        roiEl.style.color = "var(--text-secondary)";
    }

    // Trades summary rendered cleanly in container (Item 12)
    if (chartContainer) {
        chartContainer.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 20px 0; text-align: center;">
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Simulation Period</div>
                    <div style="font-size: 15px; font-weight: 600; color: var(--text-primary);">${escapeHtml(data.period || "1 Year")}</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Total Signals Evaluated</div>
                    <div style="font-size: 15px; font-weight: 600; color: var(--text-primary);" class="tabular">${data.total_signals}</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Hit Rate / Accuracy</div>
                    <div style="font-size: 15px; font-weight: 600; color: var(--text-primary);" class="tabular">${Number(data.win_rate).toFixed(1)}%</div>
                </div>
            </div>
        `;
    }
}

// ========== SECTION C: REAL DATA IN WATCHLIST & TICKER TAPE ==========
// Item 10: Compute daily % from real API data in ONE helper used by hero, ticker tape, sidebar and watchlist table.
// No mock formulas or hardcoded values!
async function loadWatchlist() {
    try {
        const res = await fetch("/api/watchlist", { headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {} });
        if (!res.ok) return;
        const items = await res.json();

        // 1. Sidebar watchlist list
        const sidebarUl = document.getElementById("watchlistList");
        if (sidebarUl) {
            sidebarUl.innerHTML = "";
            items.forEach(item => {
                const li = document.createElement("li");
                li.className = "sidebar-wl-item";

                const leftDiv = document.createElement("div");
                leftDiv.className = "sidebar-wl-left";

                const av = document.createElement("div");
                av.className = "letter-avatar";
                const avColor = getAvatarColor(item.ticker[0]);
                av.style.backgroundColor = avColor.bg;
                av.style.color = avColor.text;
                av.textContent = (item.ticker[0] || "A").toUpperCase();

                const strong = document.createElement("strong");
                strong.textContent = item.ticker;

                leftDiv.appendChild(av);
                leftDiv.appendChild(strong);

                const spanPrice = document.createElement("span");
                spanPrice.className = "price-val tabular";
                spanPrice.textContent = item.price ? fmtPrice(item.price) : "—";

                li.appendChild(leftDiv);
                li.appendChild(spanPrice);

                li.addEventListener("click", () => {
                    const searchInput = document.getElementById("searchInput");
                    if (searchInput) searchInput.value = item.ticker;
                    handleSearch(item.ticker);
                });
                sidebarUl.appendChild(li);
            });
        }

        // 2. Main Watchlist Table Body
        const tbody = document.getElementById("watchlistTableBody");
        if (tbody) {
            tbody.innerHTML = "";
            items.forEach(item => {
                const tr = document.createElement("tr");
                tr.className = "wl-row";

                // Cell 1: Letter Avatar + Ticker
                const tdTicker = document.createElement("td");
                const tickerCellDiv = document.createElement("div");
                tickerCellDiv.className = "wl-ticker-cell";
                const av = document.createElement("div");
                av.className = "letter-avatar";
                const avColor = getAvatarColor(item.ticker[0]);
                av.style.backgroundColor = avColor.bg;
                av.style.color = avColor.text;
                av.textContent = (item.ticker[0] || "A").toUpperCase();
                const tickerSpan = document.createElement("strong");
                tickerSpan.textContent = item.ticker;
                tickerCellDiv.appendChild(av);
                tickerCellDiv.appendChild(tickerSpan);
                tdTicker.appendChild(tickerCellDiv);

                // Cell 2: Company Name
                const tdCompany = document.createElement("td");
                tdCompany.style.color = "var(--text-secondary)";
                tdCompany.textContent = getCompanyName(item.ticker);

                // Cell 3: Price
                const tdPrice = document.createElement("td");
                tdPrice.className = "tabular";
                tdPrice.style.fontWeight = "600";
                tdPrice.textContent = item.price ? fmtPrice(item.price) : "—";

                // Cell 4: Daily % Change (Real data from API via fmtChange helper)
                const tdChange = document.createElement("td");
                const changeInfo = fmtChange(item.change_pct);
                const changePill = document.createElement("span");
                changePill.className = `price-change-pill ${changeInfo.className}`;
                changePill.textContent = changeInfo.text;
                tdChange.appendChild(changePill);

                // Cell 5: Hover-only Remove Button
                const tdAction = document.createElement("td");
                tdAction.style.textAlign = "right";
                const removeBtn = document.createElement("button");
                removeBtn.className = "wl-remove-btn";
                removeBtn.title = `Remove ${item.ticker}`;
                removeBtn.textContent = "✕";
                removeBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    await removeAdvisoryStock(item.ticker);
                    loadWatchlist();
                });
                tdAction.appendChild(removeBtn);

                tr.appendChild(tdTicker);
                tr.appendChild(tdCompany);
                tr.appendChild(tdPrice);
                tr.appendChild(tdChange);
                tr.appendChild(tdAction);

                tr.addEventListener("click", () => {
                    const searchInput = document.getElementById("searchInput");
                    if (searchInput) searchInput.value = item.ticker;
                    handleSearch(item.ticker);
                });

                tbody.appendChild(tr);
            });
        }

        // 3. Render Ticker Tape
        renderTickerTape(items);

    } catch (e) {
        console.error("Failed to load watchlist", e);
    }
}

// Ticker tape: rendered strictly from real watchlist data, or clean message if empty
function renderTickerTape(items) {
    const track = document.getElementById("tickerTapeTrack");
    if (!track) return;
    track.innerHTML = "";

    if (!items || items.length === 0) {
        track.innerHTML = `<span style="font-size: 11px; color: var(--text-muted); padding: 0 16px;">Add assets to your watchlist to monitor real-time prices</span>`;
        return;
    }

    // Duplicate list to create a seamless infinite loop
    const doubleList = [...items, ...items];

    doubleList.forEach(item => {
        const changeInfo = fmtChange(item.change_pct);

        const span = document.createElement("div");
        span.className = "tape-item";
        span.innerHTML = `
            <span class="tape-symbol">${escapeHtml(item.ticker)}</span>
            <span class="tape-price tabular">${fmtPrice(item.price)}</span>
            <span class="tape-change ${changeInfo.className} tabular">${changeInfo.text}</span>
        `;
        span.addEventListener("click", () => {
            const searchInput = document.getElementById("searchInput");
            if (searchInput) searchInput.value = item.ticker;
            handleSearch(item.ticker);
        });
        track.appendChild(span);
    });
}

async function addToWatchlist(ticker) {
    const cleanTicker = (ticker || "").trim().toUpperCase();
    if (!cleanTicker) return;
    try {
        await fetch("/api/watchlist/add", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ ticker: cleanTicker })
        });
        loadWatchlist();
        loadAdvisoryWatchlist();
    } catch (e) {
        console.error("Failed to add to watchlist", e);
    }
}

// ========== PRICE ALERTS ==========
function setPriceAlert(ticker, price) {
    activeAlerts.push({ ticker, target: price, triggered: false });
    const alertsEl = document.getElementById("activeAlerts");
    if (alertsEl) alertsEl.innerText = `Live alert active for ${ticker} at ${fmtPrice(price)}`;
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
    const msg = `ALERT: ${alertObj.ticker} reached target ${fmtPrice(currentPrice)}!`;
    if (Notification.permission === "granted") {
        new Notification("TradeIQ AI", { body: msg });
    }
    alert("🚨 " + msg);
}
