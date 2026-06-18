(function () {
  const THEME_KEY = "uptick-theme";

  function getTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
  }

  function setTheme(theme) {
    if (theme !== "light" && theme !== "dark") return;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    syncThemeControls(theme);
  }

  function syncThemeControls(theme) {
    document.querySelectorAll(".theme-btn, .theme-option").forEach((el) => {
      el.classList.toggle("active", el.dataset.theme === theme);
    });
  }

  syncThemeControls(getTheme());

  document.querySelectorAll(".theme-btn, .theme-option").forEach((el) => {
    el.addEventListener("click", () => setTheme(el.dataset.theme));
  });

  // SVG gradient defs
  const svgDefs = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svgDefs.setAttribute("width", "0");
  svgDefs.setAttribute("height", "0");
  svgDefs.style.position = "absolute";
  svgDefs.innerHTML = `
    <defs>
      <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#10b981"/>
        <stop offset="50%" stop-color="#f59e0b"/>
        <stop offset="100%" stop-color="#f43f5e"/>
      </linearGradient>
      <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#06b6d4"/>
        <stop offset="100%" stop-color="#8b5cf6"/>
      </linearGradient>
    </defs>
  `;
  document.body.appendChild(svgDefs);

  // Animate risk gauge
  const gauge = document.querySelector(".risk-gauge");
  const fill = document.getElementById("gauge-fill");
  if (gauge && fill) {
    const risk = parseInt(gauge.dataset.risk || "50", 10);
    const circumference = 327;
    const offset = circumference - (risk / 100) * circumference;
    requestAnimationFrame(() => {
      fill.style.strokeDashoffset = String(offset);
    });
  }

  // Animate KPI bars and region bars on load
  document.querySelectorAll(".region-fill, .kpi-bar div").forEach((el) => {
    const w = el.style.width;
    el.style.width = "0";
    requestAnimationFrame(() => {
      setTimeout(() => { el.style.width = w; }, 100);
    });
  });

  // Run agent button
  const btn = document.getElementById("run-now");
  btn?.addEventListener("click", async () => {
    btn.disabled = true;
    btn.classList.add("loading");
    btn.querySelector(".btn-text").textContent = "Analyzing…";
    try {
      const res = await fetch("/api/run-now", { method: "POST" });
      if (!res.ok) throw new Error("Run failed");
      location.reload();
    } catch {
      alert("Agent run failed. Check terminal logs.");
      btn.disabled = false;
      btn.classList.remove("loading");
      btn.querySelector(".btn-text").textContent = "Run Scan";
    }
  });

  const cryptoBtn = document.getElementById("refresh-crypto");
  cryptoBtn?.addEventListener("click", async () => {
    cryptoBtn.disabled = true;
    cryptoBtn.textContent = "…";
    try {
      const res = await fetch("/api/crypto-pulse/refresh", { method: "POST" });
      if (!res.ok) throw new Error("Refresh failed");
      location.reload();
    } catch {
      alert("Crypto pulse refresh failed.");
      cryptoBtn.disabled = false;
      cryptoBtn.textContent = "↻ Refresh";
    }
  });

  async function refreshIndia(btn) {
    if (!btn) return;
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "…";
    try {
      const res = await fetch("/api/india-desk/refresh", { method: "POST" });
      if (!res.ok) throw new Error("Refresh failed");
      location.reload();
    } catch {
      alert("India desk refresh failed.");
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  document.getElementById("refresh-india")?.addEventListener("click", (e) => refreshIndia(e.currentTarget));
  document.querySelectorAll("[data-refresh-india]").forEach((btn) => {
    btn.addEventListener("click", () => refreshIndia(btn));
  });

  const globalBtn = document.getElementById("refresh-global");
  globalBtn?.addEventListener("click", async () => {
    globalBtn.disabled = true;
    globalBtn.textContent = "…";
    try {
      const res = await fetch("/api/global-desk/refresh", { method: "POST" });
      if (!res.ok) throw new Error("Refresh failed");
      location.reload();
    } catch {
      alert("Global desk refresh failed.");
      globalBtn.disabled = false;
      globalBtn.textContent = "↻ Refresh Global Desk";
    }
  });

  const crBtn = document.getElementById("crypto-research-btn");
  const crInput = document.getElementById("crypto-research-input");
  const crOut = document.getElementById("crypto-research-out");
  async function runCryptoResearch() {
    const sym = (crInput?.value || "").trim();
    if (!sym || !crOut) return;
    crOut.textContent = "Loading…";
    try {
      const res = await fetch(`/api/crypto-research/${encodeURIComponent(sym)}`);
      const data = await res.json();
      if (!res.ok) {
        crOut.textContent = data.status === "not_found" ? `No CoinGecko data for ${sym.toUpperCase()}.` : "Request failed.";
        return;
      }
      const lines = [
        `${data.header}`,
        `${data.token} (${data.ticker}) · Tier ${data.risk_tier} · ${data.bias}`,
        `Price $${data.price} · Rank #${data.rank || "—"} · MCap $${(data.market_cap_usd / 1e9).toFixed(2)}B`,
        `7D ${data.momentum_7d_pct != null ? data.momentum_7d_pct + "%" : "—"} · Support $${data.support} · Resistance $${data.resistance}`,
        data.risk_tier >= 10 ? data.desk_note : `Targets: bull $${data.bull_case} · base $${data.base_case} · bear $${data.bear_case}`,
        `Sizing: balanced ${data.size_balanced_pct}% · aggressive ${data.size_aggressive_pct}%`,
        `Desk: ${data.desk_note}`,
      ];
      crOut.textContent = lines.join("\n");
    } catch {
      crOut.textContent = "Crypto research fetch failed.";
    }
  }
  crBtn?.addEventListener("click", runCryptoResearch);
  crInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runCryptoResearch();
  });

  // Live track record (async — avoids blocking page load)
  function fmtPct(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const n = Number(v);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(Math.abs(n) < 1 ? 2 : 1)}%`;
  }

  function pctClass(v) {
    if (v == null) return "";
    if (v > 0.05) return "pct-up";
    if (v < -0.05) return "pct-down";
    return "flat";
  }

  async function loadTrackRecord(refresh = false) {
    const list = document.getElementById("tr-open-list");
    const updated = document.getElementById("tr-updated-at");
    const countEl = document.getElementById("tr-open-count");
    const pnlEl = document.getElementById("tr-open-pnl");
    const winEl = document.getElementById("tr-open-win");
    if (!list) return;

    try {
      const url = refresh ? "/api/track-record?refresh=true" : "/api/track-record";
      const res = await fetch(url);
      if (!res.ok) throw new Error("track record failed");
      const data = await res.json();
      const live = data.live_open || {};

      if (countEl) countEl.textContent = live.count ?? 0;
      if (pnlEl) {
        pnlEl.textContent = fmtPct(live.avg_return_pct);
        pnlEl.className = "track-value " + pctClass(live.avg_return_pct);
      }
      if (winEl) {
        winEl.textContent = live.win_rate_pct != null ? `${live.win_rate_pct}%` : "—";
      }

      if (updated) {
        const t = live.updated_at ? new Date(live.updated_at).toLocaleTimeString() : "";
        updated.textContent = t ? `Updated ${t}` : "";
      }

      list.innerHTML = "";
      if (!live.items || !live.items.length) {
        list.innerHTML = `<li class="track-empty">${live.failed_symbols?.length ? "Quote fetch failed — retry shortly." : "No open calls logged yet — run Global Desk."}</li>`;
        return;
      }

      live.items.forEach((item) => {
        const li = document.createElement("li");
        const ret = item.return_pct;
        const priceNote =
          item.entry_price != null && item.current_price != null
            ? ` · ${item.entry_price}→${item.current_price}`
            : "";
        li.innerHTML = `
          <span><strong>${item.symbol}</strong> <small>${item.rating || ""}</small></span>
          <span class="${pctClass(ret)}">${fmtPct(ret)}</span>
          <small>${item.age_label || ""}${priceNote} · ${item.source}</small>
        `;
        list.appendChild(li);
      });
    } catch {
      if (list) list.innerHTML = `<li class="track-error">Could not load live P&amp;L — check network and refresh.</li>`;
      if (updated) updated.textContent = "Load failed";
    }
  }

  loadTrackRecord(false);
  setInterval(() => loadTrackRecord(false), 3 * 60 * 1000);

  // Investor return target
  function renderTargetBand(minPct, maxPct) {
    const a = Math.round(Number(minPct));
    const b = Math.round(Number(maxPct));
    const header = document.querySelector("#target-chip .target-band-display");
    const brief = document.querySelector("#target-chip-brief .target-band-display");
    const kpi = document.querySelector(".kpi-amber .target-band-display");
    document.querySelectorAll(".target-band-display").forEach((el) => {
      if (el.closest(".kpi-amber")) {
        el.innerHTML = `${a}–${b}<small>%</small>`;
      } else if (el.closest("#target-chip") && el.closest("#target-chip").id === "target-chip") {
        el.textContent = `${a}–${b}%`;
      } else if (el.closest("#target-chip-brief")) {
        el.textContent = `${a}–${b}% / yr`;
      } else if (el.closest(".settings-card") || el.closest(".app-footer")) {
        el.textContent = `${a}–${b}`;
      } else {
        el.textContent = `${a}–${b}`;
      }
    });
    const minIn = document.getElementById("target-min-input");
    const maxIn = document.getElementById("target-max-input");
    if (minIn) minIn.value = a;
    if (maxIn) maxIn.value = b;
  }

  async function saveTarget(minPct, maxPct, rerank = false) {
    const res = await fetch("/api/investor-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_min_pct: minPct, target_max_pct: maxPct, rerank }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    renderTargetBand(data.target_min_pct, data.target_max_pct);
    return data;
  }

  function showRerankOverlay(show, msg) {
    const overlay = document.getElementById("rerank-overlay");
    const msgEl = document.getElementById("rerank-overlay-msg");
    if (!overlay) return;
    if (msgEl && msg) msgEl.textContent = msg;
    overlay.hidden = !show;
  }

  function setRerankBanner(show, minPct, maxPct) {
    const banner = document.getElementById("rerank-banner");
    if (!banner) return;
    if (show && minPct != null && maxPct != null) {
      const text = banner.querySelector(".rerank-banner-text");
      if (text) {
        text.textContent = `Picks were ranked for a different return target. Re-rank to match your ${Math.round(minPct)}–${Math.round(maxPct)}% goal.`;
      }
    }
    banner.hidden = !show;
  }

  async function rerankPicks(full = false) {
    showRerankOverlay(true, full ? "Running full scan for your target…" : "Re-ranking global and India picks…");
    try {
      const res = await fetch("/api/re-rank", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Re-rank failed");
      location.reload();
    } catch (err) {
      showRerankOverlay(false);
      alert(err.message || "Re-rank failed. Check terminal logs.");
    }
  }

  async function saveTargetAndRerank(minPct, maxPct) {
    showRerankOverlay(true, `Re-ranking picks for ${Math.round(minPct)}–${Math.round(maxPct)}% target…`);
    try {
      await saveTarget(minPct, maxPct, true);
      location.reload();
    } catch (err) {
      showRerankOverlay(false);
      alert(err.message || "Could not save and re-rank picks");
    }
  }

  document.getElementById("rerank-now-btn")?.addEventListener("click", () => rerankPicks(false));

  function openTargetDialog() {
    const dlg = document.getElementById("target-dialog");
    const minIn = document.getElementById("target-dialog-min");
    const maxIn = document.getElementById("target-dialog-max");
    const curMin = document.getElementById("target-min-input")?.value || "{{ target_min }}";
    const curMax = document.getElementById("target-max-input")?.value || "{{ target_max }}";
    if (minIn) minIn.value = curMin;
    if (maxIn) maxIn.value = curMax;
    dlg?.showModal();
  }

  document.querySelectorAll(".target-chip-edit").forEach((el) => {
    el.addEventListener("click", openTargetDialog);
  });

  document.getElementById("target-dialog-cancel")?.addEventListener("click", () => {
    document.getElementById("target-dialog")?.close();
  });

  document.getElementById("target-dialog-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const minPct = parseFloat(document.getElementById("target-dialog-min")?.value || "12");
    const maxPct = parseFloat(document.getElementById("target-dialog-max")?.value || "15");
    try {
      await saveTargetAndRerank(minPct, maxPct);
      document.getElementById("target-dialog")?.close();
    } catch (err) {
      alert(err.message || "Could not save target");
    }
  });

  document.getElementById("target-profile-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("target-save-msg");
    const minPct = parseFloat(document.getElementById("target-min-input")?.value || "12");
    const maxPct = parseFloat(document.getElementById("target-max-input")?.value || "15");
    try {
      await saveTargetAndRerank(minPct, maxPct);
    } catch (err) {
      if (msg) msg.textContent = "";
      alert(err.message || "Could not save target");
    }
  });

  // Tab active state on scroll/click
  const mcTabs = document.querySelectorAll(".mc-tab");
  mcTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      mcTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
    });
  });

  // Smooth scroll for nav
  document.querySelectorAll('.mc-tab[href^="#"], .nav-item[href^="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const id = link.getAttribute("href");
      if (id && id.length > 1) {
        e.preventDefault();
        document.querySelector(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  // Deep link tab highlight (e.g. email → #morning-brief)
  const hash = window.location.hash;
  if (hash) {
    const tab = document.querySelector(`.mc-tab[href="${hash}"]`);
    if (tab) {
      mcTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
    }
  }

  // Onboarding (first visit)
  const ONBOARD_KEY = "uptick-onboarded";
  const onboarding = document.getElementById("onboarding");
  const onboardingDone = document.getElementById("onboarding-done");
  if (onboarding && !localStorage.getItem(ONBOARD_KEY)) {
    onboarding.hidden = false;
  }
  onboardingDone?.addEventListener("click", () => {
    localStorage.setItem(ONBOARD_KEY, "1");
    if (onboarding) onboarding.hidden = true;
    document.getElementById("morning-brief")?.scrollIntoView({ behavior: "smooth" });
    mcTabs.forEach((t) => t.classList.remove("active"));
    document.querySelector('.mc-tab[href="#morning-brief"]')?.classList.add("active");
  });

  // Watchlist (localStorage)
  const WATCH_KEY = "uptick-watchlist";
  const watchInput = document.getElementById("watchlist-input");
  const watchAdd = document.getElementById("watchlist-add");
  const watchList = document.getElementById("watchlist-items");

  function loadWatchlist() {
    try {
      return JSON.parse(localStorage.getItem(WATCH_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function saveWatchlist(items) {
    localStorage.setItem(WATCH_KEY, JSON.stringify(items));
  }

  function normalizeSymbol(s) {
    return s.trim().toUpperCase().replace(/\s+/g, "");
  }

  function renderWatchlist() {
    if (!watchList) return;
    const items = loadWatchlist();
    watchList.innerHTML = "";
    items.forEach((sym) => {
      const li = document.createElement("li");
      li.textContent = sym;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.setAttribute("aria-label", `Remove ${sym}`);
      rm.textContent = "×";
      rm.addEventListener("click", () => {
        saveWatchlist(loadWatchlist().filter((x) => x !== sym));
        renderWatchlist();
        highlightWatchlistHits();
      });
      li.appendChild(rm);
      watchList.appendChild(li);
    });
    highlightWatchlistHits();
  }

  function highlightWatchlistHits() {
    const items = loadWatchlist();
    document.querySelectorAll(".day-pick-item[data-symbol], .day-pick-item").forEach((el) => {
      const sym = el.dataset.symbol || el.querySelector("strong")?.textContent || "";
      const hit = items.some(
        (w) => sym.toUpperCase().includes(w) || w.includes(sym.toUpperCase())
      );
      el.classList.toggle("watchlist-hit", hit);
    });
  }

  function addWatchSymbol() {
    const sym = normalizeSymbol(watchInput?.value || "");
    if (!sym || sym.length < 2) return;
    const items = loadWatchlist();
    if (!items.includes(sym)) items.push(sym);
    saveWatchlist(items.slice(0, 12));
    if (watchInput) watchInput.value = "";
    renderWatchlist();
  }

  watchAdd?.addEventListener("click", addWatchSymbol);
  watchInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addWatchSymbol();
  });
  renderWatchlist();
})();
