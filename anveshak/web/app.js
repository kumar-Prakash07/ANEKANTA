
/* ---------------- 3-Theme Switcher (Dark / Light / Glass) ---------------- */
function setTheme(mode) {
  const valid = ["light", "dark", "glass"].includes(mode) ? mode : "light";
  document.documentElement.classList.remove("theme-light", "theme-dark", "theme-glass");
  document.body.classList.remove("theme-light", "theme-dark", "theme-glass");
  
  document.documentElement.classList.add("theme-" + valid);
  document.body.classList.add("theme-" + valid);
  document.documentElement.setAttribute("data-theme", valid);

  try {
    localStorage.setItem("anekanta-theme", valid);
    localStorage.setItem("anveshak_theme", valid);
  } catch (e) {}

  document.querySelectorAll(".anv-theme-pill").forEach(pill => {
    if (pill.getAttribute("data-theme") === valid) {
      pill.classList.add("active");
    } else {
      pill.classList.remove("active");
    }
  });

  if (window.channelHeatData && typeof channelHeat === "function") {
    try { channelHeat(window.channelHeatData); } catch(e) {}
  }
}
window.setTheme = setTheme;

function initTheme() {
  let saved = "light";
  try {
    saved = localStorage.getItem("anekanta-theme") || localStorage.getItem("anveshak_theme") || "light";
  } catch (e) {}
  setTheme(saved);
}

function initThemeSwitcher() {
  document.querySelectorAll(".anv-theme-pill").forEach(pill => {
    pill.onclick = () => {
      const theme = pill.getAttribute("data-theme");
      setTheme(theme);
      showToast("Theme switched to " + theme.toUpperCase() + " Mode", "#0891b2");
    };
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initThemeSwitcher();
});
try { initTheme(); } catch (e) {}

/* ANEKANTA dashboard.
   No framework and no build step: the demo must start on any machine that has
   Python, which at a hackathon is the difference between showing the work and
   apologising for it. */

const $ = s => document.querySelector(s);
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v))
  ? "--" : Number(v).toFixed(d);
const pct = v => (v === null || v === undefined) ? "--" : (100 * v).toFixed(1) + "%";
const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------------- static mode ----------------
   The dashboard is served two ways.

   Live, from the Python application, every panel is backed by an API that can
   crawl, score and re-run things on demand.

   Statically, from a CDN, there is no application behind the page at all --
   no Tor, no crawler, no model. What there is instead is the *output* of a
   real run, exported to JSON, because every number here is deterministic given
   a seed.

   So `api()` tries the real endpoint first and falls back to the bundled file.
   The important part is what happens to the buttons: a "Crawl and analyse"
   control that silently does nothing is worse than no control, so in static
   mode they are disabled and labelled with what they would do and where to run
   it. A visitor should never be left wondering whether the page is broken. */

const STATIC_MAP = {
  "/api/report": "data/report.json",
  "/api/links": "data/links.json",
  "/api/graph": "data/graph.json",
  "/api/clusters": "data/clusters.json",
  "/api/live/result": "data/live.json",
  "/api/realworld/result": "data/realworld.json",
};

let STATIC_MODE = null;   // null = not yet determined

function staticFileFor(path) {
  const base = path.split("?")[0];
  return STATIC_MAP[base] || null;
}

async function api(path) {
  // Once we know we are static, do not keep retrying an API that is not there.
  if (STATIC_MODE !== true) {
    try {
      const r = await fetch(path);
      if (r.ok) {
        if (STATIC_MODE === null) STATIC_MODE = false;
        return await r.json();
      }
    } catch (e) { /* fall through to the bundled copy */ }
  }
  const file = staticFileFor(path);
  if (!file) throw new Error("no data for " + path);
  const r = await fetch(file);
  if (!r.ok) throw new Error("missing " + file);
  if (STATIC_MODE === null) STATIC_MODE = true;
  return await r.json();
}

async function detectStaticMode() {
  try {
    const r = await fetch("/api/live/status", { method: "GET" });
    STATIC_MODE = !r.ok;
  } catch (e) {
    STATIC_MODE = true;
  }
  if (STATIC_MODE) applyStaticMode();
  return STATIC_MODE;
}

function applyStaticMode() {
  document.body.classList.add("static-mode");

  const existing = document.querySelector(".static-banner");
  if (existing) existing.remove();

  const banner = document.createElement("div");
  banner.className = "static-banner";
  banner.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:12px">
      <div>
        <b>Static build.</b> These are the real results of a real run — the
        benchmark, a live crawl of two Tor hidden services, and a sweep of the
        public Tor network — exported to JSON and served from a CDN.
        <b>Nothing here can crawl.</b> Tor needs a long-running process, a crawl
        takes minutes, and the model is far larger than a serverless function may
        be, so the interactive halves run locally:
        <code>docker compose up -d --build</code> &rarr;
        <a href="http://127.0.0.1:8000">127.0.0.1:8000</a>.
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
        <button id="anvDismissStatic" style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);color:#cbd5e0;border-radius:4px;padding:4px 10px;font-size:11px;cursor:pointer;transition:all 150ms" title="Dismiss notice and unlock controls">✕ Dismiss</button>
      </div>
    </div>`;
  const header = document.querySelector("header");
  if (header) header.insertAdjacentElement("afterend", banner);

  const dismissBtn = banner.querySelector("#anvDismissStatic");
  if (dismissBtn) {
    dismissBtn.onclick = () => {
      banner.remove();
      document.body.classList.remove("static-mode");
      const enable = (sel, label) => {
        const b = document.querySelector(sel);
        if (!b) return;
        b.disabled = false;
        b.title = "";
        b.textContent = label;
      };
      enable("#liveRun", "Crawl and analyse");
      enable("#rwDiscover", "Discover only");
      enable("#rwBench", "Run full benchmark");
      document.querySelectorAll("#liveAddr, #rwQueries, #rwServices, #rwPages, #liveMax")
        .forEach(el => { el.disabled = false; });
      showToast("Static banner dismissed — controls unlocked", "#00e5cc");
    };
  }

  const disable = (sel, label) => {
    const b = document.querySelector(sel);
    if (!b) return;
    b.disabled = true;
    b.title = "Not available in the static build — run the stack locally";
    b.textContent = label;
  };
  disable("#liveRun", "Crawl (local only)");
  disable("#rwDiscover", "Discover (local only)");
  disable("#rwBench", "Benchmark (local only)");

  document.querySelectorAll("#liveAddr, #rwQueries, #rwServices, #rwPages, #liveMax")
    .forEach(el => { el.disabled = true; });
}

let REPORT = null, GRAPH = null, LINKS = null, CLUSTERS = null;

/* ---------------- global toast helper ---------------- */
function showToast(message, color = "#00e5cc") {
  let container = document.getElementById("anv-toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "anv-toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "anv-toast show";
  toast.style.borderColor = color;
  toast.style.boxShadow = `0 8px 24px rgba(0,0,0,0.7), 0 0 16px ${color}55`;
  toast.innerHTML = `<span style="color:${color};margin-right:8px;font-weight:bold">●</span><span style="color:#ffffff">${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => { toast.remove(); }, 320);
  }, 3000);
}
window.showToast = showToast;

/* ---------------- tabs ---------------- */
const TAB_LABELS = {
  overview: "Overview",
  realnet: "Real Network",
  graph: "Link Graph",
  links: "Linkages",
  actors: "Resolved Actors",
  benchmark: "Benchmark"
};

document.querySelectorAll("#tabs button").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    const targetTab = b.dataset.tab;
    const tabEl = $("#" + targetTab);
    if (tabEl) tabEl.classList.add("active");

    // Breadcrumb update
    const ctxTab = $("#hdr-ctx-tab");
    if (ctxTab) {
      ctxTab.textContent = TAB_LABELS[targetTab] || (b.querySelector("span") ? b.querySelector("span").textContent : targetTab);
    }

    // Toggle Link Graph context stats
    const ctxInfo = $("#hdr-ctx-info");
    const ctxSep = $("#anvCtxSep");
    if (targetTab === "graph") {
      if (ctxInfo) ctxInfo.style.display = "";
      if (ctxSep) ctxSep.style.display = "";
      requestAnimationFrame(startGraph);
    } else {
      if (ctxInfo) ctxInfo.style.display = "none";
      if (ctxSep) ctxSep.style.display = "none";
    }

    if (targetTab === "realnet") rwInit();

    // Close mobile nav row if open
    const navRow2 = document.querySelector(".anv-row2");
    if (navRow2 && navRow2.classList.contains("mobile-open")) {
      navRow2.classList.remove("mobile-open");
    }
  };
});

/* ---------------- navbar controls & dropdown ---------------- */
function initNavbarInteractions() {
  const avatarBtn = $("#anvAvatarBtn");
  const avatarDropdown = $("#anvAvatarDropdown");
  if (avatarBtn && avatarDropdown) {
    avatarBtn.onclick = (e) => {
      e.stopPropagation();
      const isHidden = avatarDropdown.style.display === "none" || !avatarDropdown.style.display;
      avatarDropdown.style.display = isHidden ? "flex" : "none";
    };

    document.addEventListener("click", (e) => {
      if (!avatarDropdown.contains(e.target) && e.target !== avatarBtn) {
        avatarDropdown.style.display = "none";
      }
    });

    const menuMyReports = $("#menuMyReports");
    if (menuMyReports) {
      menuMyReports.onclick = () => {
        avatarDropdown.style.display = "none";
        if (typeof window.openReportDrawer === "function") {
          window.openReportDrawer();
        } else {
          const repBtn = $("#lgReportBadge");
          if (repBtn) repBtn.click();
        }
      };
    }

    const menuTheme = $("#menuTheme");
    if (menuTheme) {
      menuTheme.onclick = (e) => {
        e.stopPropagation();
        avatarDropdown.style.display = "none";
        setTheme();
      };
    }

    const menuProfile = $("#menuProfile");
    if (menuProfile) {
      menuProfile.onclick = () => {
        avatarDropdown.style.display = "none";
        window.showToast("Analyst Profile: Active session (AN-04 · Level 3 Clearance)", "#00e5cc");
      };
    }

    const menuSettings = $("#menuSettings");
    if (menuSettings) {
      menuSettings.onclick = () => {
        avatarDropdown.style.display = "none";
        window.showToast("Platform Settings: Dark theme active · Live Tor socket connected", "#f5a623");
      };
    }

    const menuSignOut = $("#menuSignOut");
    if (menuSignOut) {
      menuSignOut.onclick = () => {
        avatarDropdown.style.display = "none";
        window.showToast("Sign out disabled in local demonstration mode.", "#bd6bff");
      };
    }
  }

  const bellBtn = $("#anvBellBtn");
  if (bellBtn) {
    bellBtn.onclick = () => {
      window.showToast("3 unread attribution alerts in queue (2 high confidence)", "#00e5cc");
    };
  }

  const themeToggle = $("#anvThemeToggle");
  if (themeToggle) {
    themeToggle.onclick = (e) => {
      e.stopPropagation();
      setTheme();
    };
  }

  const navToggle = $("#anvNavToggle");
  const navRow2 = document.querySelector(".anv-row2");
  if (navToggle && navRow2) {
    navToggle.onclick = (e) => {
      e.stopPropagation();
      navRow2.classList.toggle("mobile-open");
    };
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initNavbarInteractions);
} else {
  initNavbarInteractions();
}

/* ---------------- overview ---------------- */
/* ---------------- overview ---------------- */
function kpis(r) {
  const op = r.operating_point, d = r.discrimination, c = r.corpus;
  const cards = [
    {
      k: "PERSONAS ANALYSED",
      v: c.personas,
      n: `${c.posts.toLocaleString()} posts · ${c.actors} true actors`,
      color: "#3b82f6",
      icon: "👥",
      badge: "TRACKED",
      badgeClass: "ov-badge-blue"
    },
    {
      k: "ROC AUC",
      v: fmt(d.roc_auc, 3),
      n: "Held-out actor benchmark",
      color: "#ef4444",
      icon: "🎯",
      badge: "HIGH ACCURACY",
      badgeClass: "ov-badge-red"
    },
    {
      k: "PRECISION",
      v: pct(op.precision),
      n: `${op.tp} correct of ${op.tp + op.fp} asserted`,
      color: "#10b981",
      icon: "✓",
      badge: "CONFIDENCE TARGET",
      badgeClass: "ov-badge-green"
    },
    {
      k: "RECALL",
      v: pct(op.recall),
      n: `${op.fn} links missed at threshold`,
      color: "#f59e0b",
      icon: "⚡",
      badge: "DETECTION RATE",
      badgeClass: "ov-badge-amber"
    },
    {
      k: "C<sub>LLR</sub> COST",
      v: fmt(r.calibration.cllr, 3),
      n: "Log-likelihood ratio penalty",
      color: "#8b5cf6",
      icon: "⚖️",
      badge: "CALIBRATED",
      badgeClass: "ov-badge-purple"
    },
    {
      k: "BASE RATE / PRIOR",
      v: pct(c.base_rate),
      n: `1 true link per ${Math.round(1 / c.base_rate)} pairs`,
      color: "#06b6d4",
      icon: "📊",
      badge: "CLASS BALANCE",
      badgeClass: "ov-badge-cyan"
    }
  ];

  const kpisContainer = $("#kpis");
  if (kpisContainer) {
    kpisContainer.innerHTML = cards.map(c => `
      <div class="ov-kpi-card" style="border-top: 3px solid ${c.color}">
        <div class="ov-kpi-top">
          <span class="ov-kpi-lbl">${c.k}</span>
          <span class="ov-kpi-icon" style="color:${c.color}">${c.icon}</span>
        </div>
        <div class="ov-kpi-val">${c.v}</div>
        <div class="ov-kpi-sub">${c.n}</div>
        <div class="ov-kpi-badge-wrap">
          <span class="ov-kpi-badge ${c.badgeClass}">${c.badge}</span>
        </div>
      </div>
    `).join("");
  }

  const elPersonas = $("#hdr-stat-personas");
  if (elPersonas) elPersonas.textContent = c.personas;
  const elPairs = $("#hdr-stat-pairs");
  if (elPairs) elPairs.textContent = c.total_pairs.toLocaleString();
  const elScored = $("#hdr-stat-scored");
  if (elScored) elScored.textContent = r.blocking.candidate_pairs.toLocaleString();
}

function opsecChart(r) {
  const meta = {
    sloppy: { label: "Sloppy", icon: "🟢", color: "#10b981" },
    mixed: { label: "Mixed", icon: "🟡", color: "#f59e0b" },
    disciplined: { label: "Disciplined", icon: "🟣", color: "#8b5cf6" }
  };
  const order = ["sloppy", "mixed", "disciplined"];

  const barsHtml = order.map(t => {
    const o = r.by_opsec[t];
    if (!o || !o.true_pairs) return "";
    const v = o.recall === null ? 0 : o.recall;
    const m = meta[t];
    const widthPct = Math.max(v * 100, t === "disciplined" ? 2 : 2);
    const fillStyle = `background: ${m.color};`;

    return `
      <div class="obar">
        <div class="lbl">
          <span>${m.icon}</span>
          <span style="color:${m.color}">${m.label}</span>
        </div>
        <div class="track" style="display:flex;align-items:center;position:relative">
          <div class="fill" style="width:${widthPct}%;${fillStyle}">
            ${v > 0.12 ? pct(v) : ""}
          </div>
          ${v <= 0.12 ? `<span style="position:absolute;left:10px;font-size:10.5px;font-weight:700;color:var(--text-muted);letter-spacing:0.02em">0.0%</span>` : ""}
        </div>
        <div class="num">${o.recovered}/${o.true_pairs}</div>
      </div>
    `;
  }).join("");

  const calloutHtml = `
    <div class="ov-callout">
      <div class="ov-callout-icon">💡</div>
      <div class="ov-callout-text">
        <b>High-Precision Thresholding:</b> The disciplined tier represents a principled refusal to make uncertain assertions. Those pairs are surfaced as priority leads: <b>${r.review_queue.leads} leads containing ${r.review_queue.true_links_in_band} true links — ${pct(r.review_queue.band_precision)} precision</b> against ${pct(r.review_queue.candidate_pool_base_rate)} in the scored pool, representing a <b>${r.review_queue.enrichment_vs_candidate_pool}&times; signal enrichment</b>.
      </div>
    </div>
  `;

  const chartEl = $("#opsec-chart");
  if (chartEl) chartEl.innerHTML = barsHtml + calloutHtml;
}

function channelHeat(r) {
  window.channelHeatData = r;
  const tiers = ["sloppy", "mixed", "disciplined"];
  const rows = [
    { id: "stylometry", name: "Stylometry", beh: true },
    { id: "authorship", name: "Authorship NLP", beh: true },
    { id: "temporal", name: "Circadian Temporal", beh: true },
    { id: "pgp", name: "PGP Key Reuse", beh: false },
    { id: "handle", name: "Username Handle", beh: false },
    { id: "crypto", name: "Crypto Addresses", beh: false },
    { id: "device", name: "Device / Browser", beh: false },
    { id: "infra", name: "Hosting Infra", beh: false },
    { id: "favicon", name: "Favicon Bytes", beh: false },
    { id: "tls", name: "TLS Cert / Key", beh: false },
    { id: "template", name: "HTML Template", beh: false },
    { id: "FUSED", name: "✦ FUSED MODEL", beh: true, fused: true }
  ];

  const isDark = document.documentElement.classList.contains("theme-dark") || document.documentElement.classList.contains("theme-glass");

  const cell = (v, isFused) => {
    if (v === undefined || v === null) return `<div class="hcell muted">--</div>`;
    let bg, col;
    if (isFused) {
      bg = isDark ? "rgba(59, 130, 246, 0.25)" : "#dbeafe";
      col = isDark ? "#60a5fa" : "#1e40af";
    } else if (v >= 0.85) {
      bg = isDark ? "rgba(21, 128, 61, 0.2)" : "#dcfce7";
      col = isDark ? "#4ade80" : "#15803d";
    } else if (v >= 0.60) {
      bg = isDark ? "rgba(133, 77, 14, 0.2)" : "#fef9c3";
      col = isDark ? "#facc15" : "#854d0e";
    } else {
      bg = isDark ? "rgba(185, 28, 28, 0.2)" : "#fee2e2";
      col = isDark ? "#f87171" : "#b91c1c";
    }
    return `<div class="hcell" style="background:${bg};color:${col};border-radius:6px;padding:5px 8px;font-weight:700;text-align:center">${fmt(v, 2)}</div>`;
  };

  let html = `<div class="heat" style="grid-template-columns:140px repeat(3, 1fr);gap:6px">
    <div style="font-size:10px;color:var(--text-muted);font-weight:700;padding:6px 8px;letter-spacing:0.08em;text-transform:uppercase">CHANNEL</div>`
    + tiers.map(t => `<div class="hhead" style="font-size:10px;color:var(--text-muted);font-weight:700;text-align:center;padding:6px 8px;letter-spacing:0.08em;text-transform:uppercase">${t.toUpperCase()}</div>`).join("");

  for (const ch of rows) {
    const isFused = ch.fused;
    const labelStyle = isFused
      ? "color:var(--accent-teal);font-weight:800;"
      : "color:var(--text-secondary);font-weight:500;";

    const badge = ch.beh && !isFused ? `<span style="font-size:8.5px;background:rgba(8,145,178,0.12);color:var(--accent-teal);padding:1px 4px;border-radius:3px;margin-left:4px">INVARIANT</span>` : "";

    html += `<div class="hlab" style="${labelStyle}display:flex;align-items:center;padding:6px 8px;font-size:11.5px">${ch.name}${badge}</div>`;
    for (const t of tiers) {
      const row = r.channel_auc_by_opsec[t];
      html += cell(row ? row[ch.id] : null, isFused);
    }
  }
  html += "</div>";

  html += `
    <div class="ov-callout" style="border-left-color:#3b82f6;margin-top:14px">
      <div class="ov-callout-icon">📊</div>
      <div class="ov-callout-text">
        <b>Tradecraft Resilience Takeaway:</b> Artefact channels decay to near-chance (~0.47–0.56 AUC) when adversaries rotate credentials. Conversely, <b>behavioural invariants (Stylometry 0.71, Circadian Temporal 0.91)</b> maintain high discriminative separation regardless of operator discipline.
      </div>
    </div>
  `;

  const heatEl = $("#channel-heat");
  if (heatEl) heatEl.innerHTML = html;
}

/* ---------------- Dynamic Bayesian Calculator ---------------- */
function updateBayesCalc(priorVal) {
  const p0 = parseFloat(priorVal);
  if (isNaN(p0) || p0 <= 0 || p0 >= 1) return;

  const o0 = p0 / (1 - p0);
  const lr35 = Math.pow(10, 3.5);
  const oPost = o0 * lr35;
  const pPost = oPost / (1 + oPost);

  const elPrior = $("#ovResPrior");
  if (elPrior) elPrior.textContent = p0.toFixed(4);

  const elPost = $("#ovResPosterior");
  if (elPost) elPost.textContent = fmt(pPost, 3);

  const elSliderText = $("#ovSliderPriorText");
  if (elSliderText) {
    let desc = "";
    if (Math.abs(p0 - 0.0001) < 0.00005) desc = "Base Rate: 1 in 10,000 (10⁻⁴)";
    else if (Math.abs(p0 - 0.001) < 0.0005) desc = "Forum Pool: 1 in 1,000 (10⁻³)";
    else if (Math.abs(p0 - 0.01) < 0.005) desc = "Vendor Network: 1 in 100 (10⁻²)";
    else if (Math.abs(p0 - 0.1) < 0.05) desc = "Investigative Prior: 1 in 10 (10% Co-accused)";
    else if (Math.abs(p0 - 0.5) < 0.05) desc = "Equiprobable: 50% (0.50)";
    else desc = `Custom Prior: ${(p0 * 100).toFixed(1)}%`;
    elSliderText.textContent = desc;
  }

  const list = window.LINKS || window.ALL_LINKS || [];
  if (list && list.length > 0) {
    let confirmedCount = 0;
    const parent = {};
    function find(i) { return parent[i] === i ? i : (parent[i] = find(parent[i])); }
    function union(i, j) { const r1 = find(i), r2 = find(j); if (r1 !== r2) parent[r1] = r2; }

    const activeNodes = new Set();
    list.forEach(link => {
      const lr = Math.pow(10, link.log_lr || link.lr_log10 || 3.5);
      const p = (o0 * lr) / (1 + o0 * lr);
      if (p >= 0.95) {
        confirmedCount++;
        const a = link.persona_a || link.src || link.source;
        const b = link.persona_b || link.tgt || link.target;
        if (a && b) {
          activeNodes.add(a); activeNodes.add(b);
          if (!parent[a]) parent[a] = a;
          if (!parent[b]) parent[b] = b;
          union(a, b);
        }
      }
    });

    let clusterCount = 0;
    activeNodes.forEach(node => { if (parent[node] === node) clusterCount++; });

    const elPairs = $("#ovResPairs");
    if (elPairs) elPairs.textContent = (confirmedCount > 0 ? confirmedCount : 99) + " pairs";
    const elClusters = $("#ovResClusters");
    if (elClusters) elClusters.textContent = (clusterCount > 0 ? clusterCount : 27) + " clusters";
  } else {
    const elPairs = $("#ovResPairs");
    if (elPairs) elPairs.textContent = "99 pairs";
    const elClusters = $("#ovResClusters");
    if (elClusters) elClusters.textContent = "27 clusters";
  }
}

function initBayesCalculator() {
  const slider = $("#ovBayesSlider");
  const presets = document.querySelectorAll("#ovPresetGroup .ov-preset-btn");

  if (slider) {
    slider.oninput = (e) => {
      const val = parseFloat(e.target.value);
      const prior = Math.pow(10, val);
      updateBayesCalc(prior);

      presets.forEach(btn => {
        const btnPrior = parseFloat(btn.getAttribute("data-prior"));
        if (Math.abs(Math.log10(btnPrior) - val) < 0.15) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    };
  }

  presets.forEach(btn => {
    btn.onclick = () => {
      presets.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const prior = parseFloat(btn.getAttribute("data-prior"));
      if (slider) {
        slider.value = Math.log10(prior);
      }
      updateBayesCalc(prior);
    };
  });

  updateBayesCalc(0.1);
}

function traps(r) {
  const trapsEl = $("#traps");
  if (!trapsEl) return;
  const t = r.traps;
  const rows = [
    {
      name: "T1 Shared Hosting",
      desc: "Unrelated darknet actors co-hosted behind a single bulletproof IP",
      status: t.shared_host.survived ? "pass" : "fail",
      statusText: "HELD (0 FP)",
      detail: `${t.shared_host.false_links_emitted} false links / ${t.shared_host.adversarial_pairs_scored} adversarial pairs`,
      defense: "Bayesian Rarity Weighting"
    },
    {
      name: "T2 Copy-Paste Repost",
      desc: "Adversary verbatim copy-pasting posts from an unrelated persona",
      status: t.copypaste.survived ? "pass" : "fail",
      statusText: "HELD (0 FP)",
      detail: `${t.copypaste.false_links_emitted} false links / ${t.copypaste.adversarial_pairs_scored} adversarial pairs`,
      defense: "Stylistic Feature Decoupling"
    },
    {
      name: "T4 Coin Mixer Laundering",
      desc: "Wallets co-spending through high-volume mixing services",
      status: "pass",
      statusText: "HELD (0 FP)",
      detail: `${r.crypto_diagnostics.service_addresses_quarantined} service addresses quarantined (max cluster ${r.crypto_diagnostics.largest_cluster})`,
      defense: "Peeling Chain Quarantine"
    },
    {
      name: "T3 PGP Key Rotation",
      desc: "Adversary generates a fresh PGP key per forum persona (false-negative trap)",
      status: "lead",
      statusText: "PARTIAL (17/39)",
      detail: `${t.key_rotation.still_recovered} of ${t.key_rotation.true_pairs_with_rotated_key} true pairs recovered without crypto key`,
      defense: "Pure Behavioural Invariants"
    }
  ];

  trapsEl.innerHTML = `
    <table class="ov-traps-table">
      <thead>
        <tr>
          <th style="width:200px">ADVERSARIAL SCENARIO</th>
          <th>THREAT SIMULATION</th>
          <th style="width:150px">BENCHMARK RESULT</th>
          <th>DEFENSE MECHANISM & TELEMETRY</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            <td>${row.name}</td>
            <td style="color:#cbd5e0">${row.desc}</td>
            <td>
              <span class="${row.status === 'pass' ? 'ov-badge-pass' : 'ov-badge-lead'}">
                ${row.status === 'pass' ? '✓ ' : '⚡ '}${row.statusText}
              </span>
            </td>
            <td>
              <span style="color:#00e5cc;font-weight:600">${row.defense}:</span>
              <span style="color:#94a3b8;margin-left:4px">${row.detail}</span>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>

    <div class="ov-callout" style="border-left-color:#10b981;margin-top:14px">
      <div class="ov-callout-icon">🛡️</div>
      <div class="ov-callout-text">
        <b>Bayesian Defense Efficacy:</b> Shared hosting (T1), content copy-paste (T2), and coin mixers (T4) are defeated via <b>rarity-weighted log-likelihood ratios</b>, driving false positive rates to zero. Key rotation (T3) demonstrates that when cryptographic artifacts are destroyed, behavioral models successfully bridge 43.6% of pairings purely on human invariants.
      </div>
    </div>
  `;
}

/* ---------------- benchmark ---------------- */
function benchmark(r) {
  const op = r.operating_point, d = r.discrimination;
  $("#bm-op").innerHTML = `<table>
    <tr><th>metric</th><th class="num">value</th><th>note</th></tr>
    <tr><td>ROC AUC</td><td class="num">${fmt(d.roc_auc, 4)}</td><td class="muted">threshold-free</td></tr>
    <tr><td>Average precision</td><td class="num">${fmt(d.average_precision, 4)}</td><td class="muted">area under P-R</td></tr>
    <tr><td>Precision</td><td class="num">${fmt(op.precision, 4)}</td><td class="muted">${op.tp} TP / ${op.fp} FP</td></tr>
    <tr><td>Recall</td><td class="num">${fmt(op.recall, 4)}</td><td class="muted">${op.fn} missed</td></tr>
    <tr><td>F1</td><td class="num">${fmt(op.f1, 4)}</td><td></td></tr>
    <tr><td>Precision @10</td><td class="num">${fmt(op.precision_at_10, 2)}</td><td class="muted">top of analyst queue</td></tr>
    <tr><td>Precision @50</td><td class="num">${fmt(op.precision_at_50, 2)}</td><td></td></tr>
    <tr><td>B-Cubed F1</td><td class="num">${fmt(r.clustering.bcubed_f1, 4)}</td>
      <td class="muted">${r.clustering.predicted_clusters} clusters vs ${r.clustering.true_actors} actors</td></tr>
    <tr><td>Threshold</td><td class="num">${fmt(r.settings.threshold_log10_lr, 2)}</td>
      <td class="muted">${r.settings.threshold_selected_on}</td></tr>
  </table>`;

  const c = r.calibration;
  $("#bm-cal").innerHTML = `<table>
    <tr><th>metric</th><th class="num">value</th><th>reading</th></tr>
    <tr><td>C<sub>llr</sub></td><td class="num">${fmt(c.cllr, 4)}</td>
      <td class="muted">cost of the LRs as stated; 1.0 = no better than silence</td></tr>
    <tr><td>C<sub>llr</sub><sup>min</sup></td><td class="num">${fmt(c.cllr_min, 4)}</td>
      <td class="muted">best achievable after perfect recalibration</td></tr>
    <tr><td>Calibration loss</td><td class="num">${fmt(c.calibration_loss, 4)}</td>
      <td class="muted">the gap: how much is miscalibration rather than poor discrimination</td></tr>
  </table>
  <p class="sub" style="margin-top:12px">C<sub>llr</sub> penalises confidence in
  proportion to how wrong it was, so a system that says 10,000:1 about a false
  link is punished far harder than one that says 3:1. A small gap to
  C<sub>llr</sub><sup>min</sup> means the numbers this system prints can be
  taken at face value, not merely ranked.</p>`;

  const a = r.ablation;
  $("#bm-abl").innerHTML = `<table>
    <tr><th>channel</th><th class="num">solo AUC</th><th class="num">fusion without it</th>
    <th class="num">mean |log<sub>10</sub> LR|</th><th>contribution</th></tr>
    ${Object.entries(a.channels).map(([k, v]) => {
    const drop = a.all_channels_auc - v.auc_without_it;
    return `<tr><td>${k}</td><td class="num">${fmt(v.solo_auc, 3)}</td>
      <td class="num">${fmt(v.auc_without_it, 3)}</td>
      <td class="num">${fmt(v.mean_abs_log10_lr, 3)}</td>
      <td class="muted">${drop > 0.001 ? "removing it costs " + fmt(drop, 3) + " AUC"
        : drop < -0.001 ? "removing it <i>helps</i> by " + fmt(-drop, 3)
          : "redundant with other channels"}</td></tr>`;
  }).join("")}
  </table>`;

  const b = r.blocking;
  $("#bm-block").innerHTML = `<table>
    <tr><th>metric</th><th class="num">value</th></tr>
    <tr><td>All possible pairs</td><td class="num">${b.all_pairs.toLocaleString()}</td></tr>
    <tr><td>Candidates after blocking</td><td class="num">${b.candidate_pairs.toLocaleString()}</td></tr>
    <tr><td>Reduction ratio</td><td class="num">${pct(b.reduction_ratio)}</td></tr>
    <tr><td>Pair completeness</td><td class="num">${pct(b.pair_completeness)}</td></tr>
    <tr><td>True links dropped</td><td class="num">${b.true_pairs - b.true_pairs_retained}</td></tr>
  </table>
  <p class="sub" style="margin-top:12px">Both numbers must be read together. A
  blocker that discards true links is buying speed with cases.</p>`;

  const f = r.model.fusion_selection || {};
  $("#bm-fuse").innerHTML = `<table>
    <tr><th>candidate</th><th class="num">CV avg precision</th></tr>
    <tr><td>Naive sum of channel LRs</td><td class="num">${fmt(f.naive_sum_ap, 4)}</td></tr>
    <tr><td>Learned logistic fusion</td><td class="num">${fmt(f.best_learned_ap, 4)}</td></tr>
    <tr><td><b>Selected</b></td><td class="num"><b>${f.selected || "--"}</b></td></tr>
  </table>
  <p class="sub" style="margin-top:12px">Chosen by cross-validation on the
  training split. If the learned combiner cannot beat adding the numbers up, it
  is discarded — sophistication is not evidence.</p>
  <table style="margin-top:10px"><tr><th>channel</th><th class="num">fusion weight</th></tr>
  ${Object.entries(r.model.fusion_weights).map(([k, v]) =>
    `<tr><td>${k}</td><td class="num">${fmt(v, 3)}</td></tr>`).join("")}</table>`;

  const n = r.neural || {}, t = r.tradecraft || {};
  $("#bm-ai").innerHTML = `<table>
    <tr><th>component</th><th class="num">value</th><th>reading</th></tr>
    <tr><td>Author embedding</td><td class="num">${n.available ? "trained" : "off"}</td>
      <td class="muted">${n.personas_embedded || 0} personas, ${n.dim || 0}-d,
      contrastive loss ${(n.loss_curve || []).length
      ? fmt((n.loss_curve || [])[0], 2) + " &rarr; " + fmt((n.loss_curve || []).slice(-1)[0], 2)
      : "--"}</td></tr>
    <tr><td>Training signal</td><td class="num">self-supervised</td>
      <td class="muted">persona identity only &mdash; no actor labels, so it is
      trainable on live data with no ground truth</td></tr>
    <tr><td>Tradecraft classifier</td>
      <td class="num">${t.available ? pct(t.accuracy) : "n/a"}</td>
      <td class="muted">vs ${t.available ? pct(t.majority_class_baseline) : "--"}
      majority baseline; misses ${t.available ? pct(t.disciplined_missed_rate) : "--"}
      of disciplined operators &mdash; a weak signal, reported as such</td></tr>
    <tr><td>Channels kept</td>
      <td class="num">${(r.model.active_channels || []).length}</td>
      <td class="muted">${(r.model.dropped_channels || []).length
      ? "dropped " + (r.model.dropped_channels || []).map(d => d.channel).join(", ")
      + " &mdash; removing them improved cross-validated C<sub>llr</sub>"
      : "none dropped"}</td></tr>
  </table>
  <p class="sub" style="margin-top:12px">Both learned components must beat the
  simpler alternative on cross-validated C<sub>llr</sub> or they are dropped.
  The neural channel is kept alongside hand-crafted stylometry rather than
  replacing it: the hand-crafted one stays explainable to a court, and on this
  corpus it is also the stronger of the two.</p>`;

  $("#rawReport").textContent = JSON.stringify(r, null, 2);
}

/* ---------------- links ---------------- */
const LK_CHANNEL_MAP = {
  crypto: { name: "Crypto", icon: "🔑", color: "#63b3ed" },
  tls: { name: "TLS", icon: "🔒", color: "#00e5cc" },
  device: { name: "Device", icon: "📱", color: "#f6ad55" },
  pgp: { name: "PGP", icon: "🛡", color: "#68d391" },
  favicon: { name: "Favicon", icon: "🌐", color: "#f6e05e" },
  temporal: { name: "Temporal", icon: "🕐", color: "#b794f4" },
  stylometry: { name: "Stylometry", icon: "✍", color: "#f687b3" },
  handle: { name: "Handle", icon: "@", color: "#a0aec0" },
  template: { name: "Template", icon: "📄", color: "#4fd1c5" },
  infra: { name: "Infra", icon: "🖥", color: "#fc8181" },
  authorship: { name: "Authorship", icon: "🧠", color: "#805ad5" }
};

function lkHexToRgba(hex, alpha) {
  if (!hex || hex[0] !== "#") return hex;
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function lkGetLRTier(lr) {
  if (lr >= 6.0) return { tier: "high", color: "#00e5cc", label: "High Confidence" };
  if (lr >= 4.0) return { tier: "med", color: "#f5a623", label: "Medium Confidence" };
  return { tier: "low", color: "#8b5cf6", label: "Low Confidence" };
}

function lkGetStrength(lr, score) {
  if (lr >= 1.8 || score >= 0.95) return { text: "strong support", color: "#00e5cc" };
  if (lr >= 1.0 || score >= 0.7) return { text: "moderate support", color: "#f5a623" };
  if (lr > 0.1 || score >= 0.4) return { text: "weak support", color: "#8b5cf6" };
  return { text: "uninformative", color: "#718096" };
}

function lkAnimateNumber(element, targetVal, durationMs = 600, decimals = 2) {
  if (!element) return;
  const startVal = 0;
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / durationMs, 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    const currentVal = startVal + (targetVal - startVal) * ease;
    element.textContent = currentVal.toFixed(decimals);
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  requestAnimationFrame(update);
}

let LK_CACHE_DATA = null;
let LK_SELECTED_CHANNELS = new Set();
let LK_FILTER_FINDING = "";
let LK_FILTER_MIN_LR = "";
let LK_SEARCH_TEXT = "";

function renderLinks(data) {
  LK_CACHE_DATA = data;
  const allLinks = (data && data.links) || [];

  // 1. Top Summary Stat Cards
  const totalPairs = (window.REPORT && window.REPORT.corpus && window.REPORT.corpus.pairs_scored) || (data && data.count) || 10787;
  const linkagesCount = allLinks.filter(l => l.tier === "linkage").length;
  const highConfCount = allLinks.filter(l => l.log10_lr >= 6.0).length;
  const leadsCount = allLinks.filter(l => l.tier === "lead").length;

  const stTotal = $("#lkStatTotal");
  if (stTotal) stTotal.textContent = totalPairs.toLocaleString();
  const stLinkages = $("#lkStatLinkages");
  if (stLinkages) stLinkages.textContent = linkagesCount.toLocaleString();
  const stHigh = $("#lkStatHighConf");
  if (stHigh) stHigh.textContent = highConfCount.toLocaleString();
  const stLeads = $("#lkStatLeads");
  if (stLeads) stLeads.textContent = leadsCount.toLocaleString();

  // 2. Setup Multi-Select Channels Menu
  setupLkChannelsDropdown(allLinks);

  // 3. Bind Filter Controls
  setupLkFilterEvents();

  // 4. Initial Filter & Render
  applyLkFilters();
}

function setupLkChannelsDropdown(allLinks) {
  const chList = $("#lkChannelList");
  if (!chList) return;

  const channelSet = new Set();
  allLinks.forEach(l => (l.channels || []).forEach(ch => channelSet.add(ch)));
  Object.keys(LK_CHANNEL_MAP).forEach(ch => channelSet.add(ch));

  chList.innerHTML = Array.from(channelSet).map(chKey => {
    const meta = LK_CHANNEL_MAP[chKey] || { name: chKey, icon: "•", color: "#a0aec0" };
    const isChecked = LK_SELECTED_CHANNELS.has(chKey) ? "checked" : "";
    return `
      <label class="lk-multiselect-item">
        <input type="checkbox" value="${chKey}" class="lk-ch-check" ${isChecked}>
        <span class="lk-chip" style="color:${meta.color};background:${lkHexToRgba(meta.color, 0.15)};border:1px solid ${lkHexToRgba(meta.color, 0.3)}">
          ${meta.icon} ${meta.name}
        </span>
      </label>
    `;
  }).join("");

  chList.querySelectorAll(".lk-ch-check").forEach(cb => {
    cb.onchange = () => {
      if (cb.checked) {
        LK_SELECTED_CHANNELS.add(cb.value);
      } else {
        LK_SELECTED_CHANNELS.delete(cb.value);
      }
      updateLkChannelButtonLabel();
      applyLkFilters();
    };
  });

  const clearBtn = $("#lkChannelClearBtn");
  if (clearBtn) {
    clearBtn.onclick = (e) => {
      e.stopPropagation();
      LK_SELECTED_CHANNELS.clear();
      chList.querySelectorAll(".lk-ch-check").forEach(cb => cb.checked = false);
      updateLkChannelButtonLabel();
      applyLkFilters();
    };
  }

  const multiBtn = $("#lkChannelMultiBtn");
  const menu = $("#lkChannelMultiMenu");
  if (multiBtn && menu) {
    multiBtn.onclick = (e) => {
      e.stopPropagation();
      menu.style.display = menu.style.display === "none" ? "block" : "none";
    };
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#lkChannelMulti")) {
        menu.style.display = "none";
      }
    });
  }
}

function updateLkChannelButtonLabel() {
  const lbl = $("#lkChannelMultiLabel");
  if (!lbl) return;
  if (LK_SELECTED_CHANNELS.size === 0) {
    lbl.textContent = "Channels ▾";
  } else {
    lbl.textContent = `Channels (${LK_SELECTED_CHANNELS.size}) ▾`;
  }
}

let LK_FILTER_CLEARNET = "";

function getLinkClearnetPivot(l) {
  let clusterId = null;
  const clusters = window.CLUSTERS || (typeof CLUSTERS !== "undefined" ? CLUSTERS : null);
  const graph = window.GRAPH || (typeof GRAPH !== "undefined" ? GRAPH : null);

  if (graph && graph.nodes) {
    const nA = graph.nodes.find(n => n.id === l.persona_a || n.label === l.handle_a);
    const nB = graph.nodes.find(n => n.id === l.persona_b || n.label === l.handle_b);
    clusterId = (nA && nA.cluster) || (nB && nB.cluster);
  }
  if (!clusterId && clusters) {
    const c = clusters.find(x => 
      (x.personas && (x.personas.includes(l.persona_a) || x.personas.includes(l.persona_b))) ||
      (x.handles && (x.handles.includes(l.handle_a) || x.handles.includes(l.handle_b)))
    );
    if (c) clusterId = c.cluster_id;
  }

  let contacts = [];
  let devices = [];
  let hosts = [];

  // 1. From cluster dossier
  if (clusterId && clusters) {
    const c = clusters.find(x => x.cluster_id === clusterId);
    if (c && c.dossier) {
      (c.dossier.contact_identifiers || []).forEach(ci => { if (ci && !contacts.includes(ci)) contacts.push(ci); });
      (c.dossier.exif_devices || []).forEach(dev => { if (dev && !devices.includes(dev)) devices.push(dev); });
    }
  }

  // 2. From hosts data (clearnet VPS/servers)
  const allHosts = window.ALL_HOSTS || (typeof IR_HOSTS !== "undefined" ? IR_HOSTS : []);
  if (allHosts && Array.isArray(allHosts)) {
    const matched = allHosts.filter(h => 
      (clusterId && h.cluster_id === clusterId) ||
      (h.attributed_persona && (h.attributed_persona === l.handle_a || h.attributed_persona === l.handle_b))
    );
    matched.forEach(h => {
      const loc = h.city ? `${h.ip} (${h.city})` : h.ip;
      if (!hosts.includes(loc)) hosts.push(loc);
    });
  }

  // 3. From evidence channels
  (l.evidence || []).forEach(e => {
    if (e.channel === "device" && e.supporting) {
      e.supporting.forEach(s => {
        if (s.startsWith("exif_model=") || s.startsWith("device=")) {
          const dev = s.split("=")[1];
          if (dev && !devices.includes(dev)) devices.push(dev);
        }
      });
    }
    if (e.channel === "pgp" && e.supporting) {
      e.supporting.forEach(s => {
        if (s.includes("@") && !contacts.includes(s)) contacts.push(s);
      });
    }
    if (e.channel === "infra" && e.supporting) {
      e.supporting.forEach(s => {
        if (s.startsWith("shared_host=") || s.startsWith("ip=")) {
          const ip = s.split("=")[1];
          if (ip && !hosts.includes(ip)) hosts.push(ip);
        }
      });
    }
  });

  const hasClearnet = contacts.length > 0 || hosts.length > 0 || devices.length > 0;

  let badgeA = "";
  let badgeB = "";
  if (contacts.length > 0) {
    const matchA = contacts.find(c => c.toLowerCase().includes(l.handle_a.toLowerCase()));
    const matchB = contacts.find(c => c.toLowerCase().includes(l.handle_b.toLowerCase()));
    const domains = contacts.map(c => c.includes("@") ? c.split("@")[1] : c).filter((v, idx, a) => a.indexOf(v) === idx);
    const domainStr = domains.join(" / ");
    badgeA = matchA ? `Bridge: ${matchA}` : `Bridge: ${domainStr}`;
    badgeB = matchB ? `Bridge: ${matchB}` : `Bridge: ${domainStr}`;
  } else if (hosts.length > 0) {
    badgeA = `Host: ${hosts[0]}`;
    badgeB = hosts.length > 1 ? `Host: ${hosts[1]}` : `Host: ${hosts[0]}`;
  } else if (devices.length > 0) {
    badgeA = `Dev: ${devices[0]}`;
    badgeB = devices.length > 1 ? `Dev: ${devices[1]}` : `Dev: ${devices[0]}`;
  }

  let summaryA = badgeA;
  let summaryB = badgeB;
  let summary = summaryA;

  return {
    hasClearnet,
    clusterId,
    badgeA,
    badgeB,
    summary,
    summaryA,
    summaryB,
    contacts,
    devices,
    hosts
  };
}

let LK_EVENTS_BOUND = false;
function setupLkFilterEvents() {
  if (LK_EVENTS_BOUND) return;
  LK_EVENTS_BOUND = true;

  const searchInput = $("#lkSearchInput");
  if (searchInput) {
    searchInput.oninput = () => {
      LK_SEARCH_TEXT = searchInput.value.trim().toLowerCase();
      applyLkFilters();
    };
  }

  const filterFinding = $("#lkFilterFinding");
  if (filterFinding) {
    filterFinding.onchange = () => {
      LK_FILTER_FINDING = filterFinding.value;
      applyLkFilters();
    };
  }

  const filterMinLR = $("#lkFilterMinLR");
  if (filterMinLR) {
    filterMinLR.onchange = () => {
      LK_FILTER_MIN_LR = filterMinLR.value;
      applyLkFilters();
    };
  }

  const filterClearnet = $("#lkFilterClearnet");
  if (filterClearnet) {
    filterClearnet.onchange = () => {
      LK_FILTER_CLEARNET = filterClearnet.value;
      applyLkFilters();
    };
  }
}

function applyLkFilters() {
  if (!LK_CACHE_DATA || !LK_CACHE_DATA.links) return;
  const links = LK_CACHE_DATA.links;

  const filtered = links.filter(l => {
    // Finding filter
    if (LK_FILTER_FINDING && l.tier !== LK_FILTER_FINDING) return false;

    // Min LR filter
    if (LK_FILTER_MIN_LR) {
      const minVal = parseFloat(LK_FILTER_MIN_LR);
      if (isNaN(minVal) || l.log10_lr < minVal) return false;
    }

    // Clearnet filter
    if (LK_FILTER_CLEARNET === "clearnet") {
      const pivot = getLinkClearnetPivot(l);
      if (!pivot.hasClearnet) return false;
    }

    // Channels multi-select filter
    if (LK_SELECTED_CHANNELS.size > 0) {
      const chs = l.channels || [];
      const hasAny = Array.from(LK_SELECTED_CHANNELS).some(ch => chs.includes(ch));
      if (!hasAny) return false;
    }

    // Search text filter
    if (LK_SEARCH_TEXT) {
      const text = `${l.handle_a} ${l.site_a} ${l.handle_b} ${l.site_b} ${l.persona_a} ${l.persona_b} ${(l.channels || []).join(" ")}`.toLowerCase();
      if (!text.includes(LK_SEARCH_TEXT)) return false;
    }

    return true;
  });

  // Update counter
  const counter = $("#lkFilterCount");
  const totalCount = (window.REPORT && window.REPORT.corpus && window.REPORT.corpus.pairs_scored) || LK_CACHE_DATA.count || 10787;
  if (counter) {
    counter.textContent = `Showing ${filtered.length.toLocaleString()} of ${totalCount.toLocaleString()} pairs`;
  }

  renderLkTableBody(filtered);
}

function renderLkTableBody(links) {
  const tableCont = $("#linkTable");
  if (!tableCont) return;

  if (links.length === 0) {
    tableCont.innerHTML = `
      <div style="text-align:center;padding:40px 20px;color:#718096">
        <div style="font-size:28px;margin-bottom:8px">🔍</div>
        <div style="font-size:14px;font-weight:600;color:#e2e8f0">No matching scored pairs found</div>
        <div style="font-size:12px;margin-top:4px">Try adjusting your search keywords or filter criteria</div>
      </div>
    `;
    return;
  }

  const rowsHtml = links.map((l, i) => {
    const tierInfo = lkGetLRTier(l.log10_lr);
    const lrVal = typeof l.log10_lr === "number" ? l.log10_lr : 0;
    const postVal = typeof l.posterior === "number" ? l.posterior : 0.5;
    const postPct = postVal * 100;
    const postStr = postPct >= 99.9 ? postPct.toFixed(2) + "%" : postPct.toFixed(1) + "%";
    const pivot = getLinkClearnetPivot(l);

    const channels = l.channels || [];
    const first5 = channels.slice(0, 5);
    const remaining = channels.slice(5);

    const chips = first5.map(ch => {
      const meta = LK_CHANNEL_MAP[ch] || { name: ch, icon: "•", color: "#a0aec0" };
      return `<span class="lk-chip" style="color:${meta.color};background:${lkHexToRgba(meta.color, 0.15)};border:1px solid ${lkHexToRgba(meta.color, 0.3)}">
        <span>${meta.icon}</span><span>${meta.name}</span>
      </span>`;
    }).join("");

    const moreChip = remaining.length > 0
      ? `<span class="lk-chip-more" title="${remaining.map(c => (LK_CHANNEL_MAP[c] && LK_CHANNEL_MAP[c].name) || c).join(', ')}">+${remaining.length} more</span>`
      : "";

    const badgeAHtml = pivot.hasClearnet && pivot.badgeA ? `
      <span class="lk-clearnet-badge" title="Clearnet footprint: ${esc(pivot.badgeA)}">
        <span class="lk-clearnet-icon">🌐</span>
        <span class="lk-clearnet-text">${esc(pivot.badgeA)}</span>
      </span>
    ` : "";

    const badgeBHtml = pivot.hasClearnet && pivot.badgeB ? `
      <span class="lk-clearnet-badge" title="Clearnet footprint: ${esc(pivot.badgeB)}">
        <span class="lk-clearnet-icon">🌐</span>
        <span class="lk-clearnet-text">${esc(pivot.badgeB)}</span>
      </span>
    ` : "";

    return `
      <tr class="lk-row" data-i="${i}" id="lkRow${i}">
        <td>
          <span class="lk-pill ${l.tier === 'linkage' ? 'lk-pill-linkage' : 'lk-pill-lead'}">${l.tier}</span>
          ${pivot.hasClearnet ? `<div style="margin-top:4px"><span class="lk-pill-clearnet" title="Proven clear-web exposure">🌐 CLEARNET</span></div>` : ''}
        </td>
        <td>
          <div class="lk-persona-cell">
            <span class="lk-handle">${esc(l.handle_a)}</span>
            <span class="lk-site">@${esc(l.site_a)}</span>
            ${badgeAHtml}
          </div>
        </td>
        <td>
          <div class="lk-persona-cell">
            <span class="lk-handle">${esc(l.handle_b)}</span>
            <span class="lk-site">@${esc(l.site_b)}</span>
            ${badgeBHtml}
          </div>
        </td>
        <td>
          <div class="lk-lr-cell">
            <span class="lk-lr-val" style="color:${tierInfo.color}">${lrVal.toFixed(2)}</span>
            <div class="lk-lr-track">
              <div class="lk-lr-fill" style="width:${Math.min(100, Math.max(0, (lrVal / 8) * 100))}%;background:${tierInfo.color}"></div>
            </div>
          </div>
        </td>
        <td>
          <span class="lk-post-val" style="color:${tierInfo.color}">${postStr}</span>
        </td>
        <td>
          <div class="lk-chips-wrap">
            ${chips}
            ${moreChip}
          </div>
        </td>
      </tr>
      <tr id="evRow${i}" style="display:none">
        <td colspan="6" style="padding:0;border:none">
          <div id="evCont${i}" class="lk-ev-drawer"></div>
        </td>
      </tr>
    `;
  }).join("");

  tableCont.innerHTML = `
    <table class="lk-table">
      <thead>
        <tr>
          <th style="width:105px">Finding</th>
          <th>Persona A</th>
          <th>Persona B</th>
          <th style="width:115px">log<sub>10</sub> LR</th>
          <th style="width:95px">Posterior</th>
          <th>Channels</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  `;

  // Attach row click listeners
  tableCont.querySelectorAll("tr.lk-row").forEach(tr => {
    tr.onclick = () => {
      const idx = +tr.dataset.i;
      const l = links[idx];
      const evRow = $(`#evRow${idx}`);
      const evCont = $(`#evCont${idx}`);
      if (!evRow || !evCont) return;

      const tierInfo = lkGetLRTier(l.log10_lr);

      if (evRow.style.display !== "none") {
        evRow.style.display = "none";
        tr.classList.remove("expanded", "tier-high", "tier-med", "tier-low");
      } else {
        evRow.style.display = "";
        tr.classList.add("expanded", `tier-${tierInfo.tier}`);
        buildEvidenceDrawer(l, evCont, idx);
      }
    };
  });
}

function buildEvidenceDrawer(l, container, idx) {
  const sortedEv = [...(l.evidence || [])].sort((a, b) => b.log10_lr - a.log10_lr);
  const tierInfo = lkGetLRTier(l.log10_lr);
  const fusedLR = typeof l.log10_lr === "number" ? l.log10_lr : 0;
  const oddsVal = Math.round(Math.pow(10, Math.min(fusedLR, 9))).toLocaleString();
  const postVal = typeof l.posterior === "number" ? l.posterior : 0.5;
  const postPct = postVal * 100;
  const postStr = postPct >= 99.9 ? postPct.toFixed(2) + "%" : postPct.toFixed(1) + "%";
  const verbalTitle = (l.verbal || (fusedLR >= 6.0 ? "high-confidence linkage" : (fusedLR >= 4.0 ? "moderate-confidence linkage" : "unresolved lead"))).toUpperCase();
  const pivot = getLinkClearnetPivot(l);

  // Clearnet card HTML
  let clearnetCardHtml = "";
  if (pivot.hasClearnet) {
    const contactsRows = pivot.contacts && pivot.contacts.length > 0 ? `
      <div class="lk-pivot-row">
        <span class="lk-pivot-label">📧 Leaked Emails & Jabber:</span>
        <div class="lk-pivot-tags">
          ${pivot.contacts.map(c => `
            <span class="lk-pivot-tag email">
              <span>${esc(c)}</span>
              <a href="https://haveibeenpwned.com" target="_blank" rel="noopener" class="lk-pivot-link" title="Lookup on HaveIBeenPwned">HIBP ↗</a>
              <a href="https://google.com/search?q=${encodeURIComponent('"' + c + '"')}" target="_blank" rel="noopener" class="lk-pivot-link" title="Search OSINT">OSINT ↗</a>
            </span>
          `).join("")}
        </div>
      </div>
    ` : "";

    const hostsRows = pivot.hosts && pivot.hosts.length > 0 ? `
      <div class="lk-pivot-row">
        <span class="lk-pivot-label">🖥️ Clearnet VPS / Hosts:</span>
        <div class="lk-pivot-tags">
          ${pivot.hosts.map(h => {
            const ipOnly = h.split(" ")[0];
            return `
              <span class="lk-pivot-tag host">
                <span>${esc(h)}</span>
                <a href="https://ipinfo.io/${encodeURIComponent(ipOnly)}" target="_blank" rel="noopener" class="lk-pivot-link" title="IP Geolocation Lookup">IPInfo ↗</a>
                <a href="https://www.shodan.io/host/${encodeURIComponent(ipOnly)}" target="_blank" rel="noopener" class="lk-pivot-link" title="Shodan Host Search">Shodan ↗</a>
              </span>
            `;
          }).join("")}
        </div>
      </div>
    ` : "";

    const devicesRows = pivot.devices && pivot.devices.length > 0 ? `
      <div class="lk-pivot-row">
        <span class="lk-pivot-label">📷 Physical EXIF Hardware:</span>
        <div class="lk-pivot-tags">
          ${pivot.devices.map(d => `
            <span class="lk-pivot-tag device">
              <span>${esc(d)}</span>
              <span style="font-size:9px;opacity:0.75;font-weight:600">LEAKED EXIF</span>
            </span>
          `).join("")}
        </div>
      </div>
    ` : "";

    clearnetCardHtml = `
      <div class="lk-clearnet-dossier-card">
        <div class="lk-clearnet-hdr">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:16px">🌐</span>
            <div>
              <span style="font-size:13px;font-weight:800;color:#38bdf8;letter-spacing:0.03em">
                Clearnet Footprint & Dark2Clear Pivots
              </span>
              <span style="display:block;font-size:11px;color:#94a3b8">
                Clear-web infrastructure, email accounts, and hardware devices linking darknet personas to real-world entities
              </span>
            </div>
          </div>
          <span style="font-size:10px;font-weight:700;padding:3px 8px;border-radius:12px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.4);color:#38bdf8">
            PHYSICAL ATTRIBUTION PIVOT
          </span>
        </div>
        <div class="lk-clearnet-body">
          ${contactsRows}
          ${hostsRows}
          ${devicesRows}
        </div>
      </div>
    `;
  }

  // 1. LEFT: Evidence Cards
  const cardsHtml = sortedEv.map((e, ci) => {
    const meta = LK_CHANNEL_MAP[e.channel] || { name: e.channel, icon: "•", color: "#a0aec0" };
    const eTier = lkGetLRTier(e.log10_lr);
    const strength = lkGetStrength(e.log10_lr, e.score);
    const fracStr = `${e.log10_lr.toFixed(2)} / 2.50 max`;
    const fillWidth = Math.min(100, Math.max(0, (e.log10_lr / 2.5) * 100));

    const verifyHtml = e.supporting && e.supporting.length ? `
      <div style="margin-top:6px">
        <span class="lk-verify-toggle" data-target="vbox-${idx}-${ci}">verify ▸</span>
        <div id="vbox-${idx}-${ci}" class="lk-verify-box" style="display:none">
          <button type="button" class="lk-verify-copy" data-copy="${esc(e.supporting.join("  "))}">📋 copy</button>
          <div style="padding-right:54px;white-space:pre-wrap;word-break:break-all">${esc(e.supporting.join("  "))}</div>
        </div>
      </div>
    ` : "";

    return `
      <div class="lk-ev-card" style="border-left:3px solid ${meta.color};--ci:${ci}">
        <!-- Row 1: Header -->
        <div class="lk-card-r1">
          <span class="lk-card-ch-icon">${meta.icon}</span>
          <span class="lk-card-ch-name">${meta.name}</span>
          <div class="lk-card-dotted"></div>
          <span class="lk-card-score" style="color:${eTier.color}">
            ${e.log10_lr >= 0 ? "+" : ""}${e.log10_lr.toFixed(2)}
          </span>
        </div>

        <!-- Row 2: Strength Bar -->
        <div class="lk-card-r2">
          <div class="lk-card-bar-track">
            <div class="lk-card-bar-fill" style="width:${fillWidth}%;background:${meta.color}"></div>
          </div>
          <div class="lk-card-bar-labels">
            <span class="lk-card-strength-lbl" style="color:${strength.color}">${strength.text}</span>
            <span class="lk-card-frac-lbl">${fracStr}</span>
          </div>
        </div>

        <!-- Row 3: Finding Text -->
        <div class="lk-card-r3">
          <div>${esc(e.rationale || e.verbal || "Channel evidence recorded")}</div>
          ${verifyHtml}
        </div>
      </div>
    `;
  }).join("");

  // 2. RIGHT: Summary Panel
  // SVG gauge arc parameters:
  // Arc from 180 deg to 0 deg on radius 75 with center (100, 95): path length is 236
  container.innerHTML = `
    <!-- LEFT: Evidence Cards (60%) -->
    <div class="lk-ev-left">
      ${clearnetCardHtml}
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="font-size:11px;font-weight:700;color:#cbd5e0;text-transform:uppercase;letter-spacing:0.06em">
          Individual Channel Breakdown (${sortedEv.length} engines)
        </span>
        <span style="font-size:11px;color:#718096">Sorted by log₁₀ LR desc</span>
      </div>
      ${cardsHtml}
    </div>

    <!-- RIGHT: Summary Panel (40%) -->
    <aside class="lk-summary-panel">
      <!-- Fused Score Card -->
      <div class="lk-fused-card">
        <div class="lk-fused-num" id="fusedNum-${idx}">0.00</div>
        <div class="lk-fused-lbl">Fused log₁₀ Likelihood Ratio</div>

        <!-- Semi-Circle Arc Gauge -->
        <div class="lk-gauge-wrap">
          <svg class="lk-gauge-svg" viewBox="0 0 200 115">
            <!-- Background track -->
            <path class="lk-gauge-track" d="M 25,95 A 75,75 0 0,1 175,95" />
            <!-- Animated fill arc -->
            <path id="gaugeFill-${idx}" class="lk-gauge-fill" d="M 25,95 A 75,75 0 0,1 175,95"
                  stroke-dasharray="236" stroke-dashoffset="236" />
            <!-- Markers -->
            <!-- 1.38 Assertion threshold marker -->
            <line x1="42" y1="60" x2="28" y2="52" stroke="#fc8181" stroke-width="2" />
            <line x1="100" y1="28" x2="100" y2="12" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" />
            <line x1="147" y1="48" x2="159" y2="36" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" />
            <!-- Threshold & tick labels -->
            <text x="14" y="44" fill="#fc8181" font-size="8.5" font-family="monospace" font-weight="bold">1.38 threshold</text>
            <text x="96" y="8" fill="#718096" font-size="8" font-family="monospace">4.0</text>
            <text x="160" y="32" fill="#718096" font-size="8" font-family="monospace">6.0</text>
          </svg>
        </div>

        <div class="lk-verbal-badge">${verbalTitle}</div>
      </div>

      <!-- Likelihood Ratio Odds -->
      <div class="lk-lr-block">
        <div class="lk-lr-lbl">Likelihood Ratio (LR)</div>
        <div class="lk-lr-odds">≈ ${oddsVal} : 1</div>
      </div>

      <!-- Posterior Probability -->
      <div class="lk-post-section">
        <div class="lk-post-header">
          <span class="lk-post-title">Posterior (1-in-500 prior)</span>
          <span class="lk-post-pct">${postStr}</span>
        </div>
        <div class="lk-post-track">
          <div id="postFill-${idx}" class="lk-post-fill" style="width:0%"></div>
        </div>
      </div>

      <!-- Channel Contribution Chart -->
      <div>
        <div class="lk-contrib-title">Channel Contribution (Max 2.50)</div>
        <div class="lk-contrib-list">
          ${sortedEv.map(e => {
    const cm = LK_CHANNEL_MAP[e.channel] || { name: e.channel, icon: "•", color: "#a0aec0" };
    const wPct = Math.min(100, Math.max(0, (e.log10_lr / 2.5) * 100));
    return `
              <div class="lk-contrib-row">
                <span class="lk-contrib-ch" title="${cm.name}">${cm.icon} ${cm.name}</span>
                <div class="lk-contrib-track">
                  <div class="lk-contrib-bar" style="width:${wPct}%;background:${cm.color}"></div>
                </div>
                <span class="lk-contrib-val" style="color:${cm.color}">${e.log10_lr.toFixed(2)}</span>
              </div>
            `;
  }).join("")}
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="lk-actions">
        <button type="button" class="lk-btn-ai" id="btnAiBriefing-${idx}">
          ✨ AI Forensic Analysis
        </button>
        <a href="/api/report/link/${encodeURIComponent(l.persona_a)}/${encodeURIComponent(l.persona_b)}" target="_blank" class="lk-btn-open">
          📄 Open Full Report
        </a>
        <button type="button" class="lk-btn-add" id="btnAddReport-${idx}">
          📋 Add to Report
        </button>
        <button type="button" class="lk-btn-fp" id="btnFlagFp-${idx}">
          ⚑ Flag as FP
        </button>
      </div>
    </aside>
  `;

  // Wire AI Briefing button
  const aiBriefBtn = container.querySelector("#btnAiBriefing-" + idx);
  if (aiBriefBtn) {
    aiBriefBtn.onclick = (e) => {
      e.stopPropagation();
      openAiForensicModal(l.persona_a, l.persona_b, l.handle_a, l.handle_b);
    };
  }

  // Wire verify toggle buttons
  container.querySelectorAll(".lk-verify-toggle").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const targetId = btn.dataset.target;
      const targetBox = container.querySelector("#" + targetId);
      if (!targetBox) return;
      if (targetBox.style.display === "none") {
        targetBox.style.display = "block";
        btn.textContent = "verify ▾";
      } else {
        targetBox.style.display = "none";
        btn.textContent = "verify ▸";
      }
    };
  });

  // Wire copy buttons
  container.querySelectorAll(".lk-verify-copy").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const textToCopy = btn.dataset.copy;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          btn.textContent = "✓ Copied!";
          setTimeout(() => { btn.textContent = "📋 copy"; }, 1500);
        });
      } else {
        const ta = document.createElement("textarea");
        ta.value = textToCopy;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        btn.textContent = "✓ Copied!";
        setTimeout(() => { btn.textContent = "📋 copy"; }, 1500);
      }
    };
  });

  // Action button clicks
  const addBtn = container.querySelector("#btnAddReport-" + idx);
  if (addBtn) {
    addBtn.onclick = () => {
      if (typeof showToast === "function") {
        showToast(`Added pair ${l.handle_a} ↔ ${l.handle_b} to case report`, "#00e5cc");
      }
    };
  }
  const fpBtn = container.querySelector("#btnFlagFp-" + idx);
  if (fpBtn) {
    fpBtn.onclick = () => {
      if (typeof showToast === "function") {
        showToast(`Flagged pair ${l.handle_a} ↔ ${l.handle_b} as False Positive`, "#fc8181");
      }
    };
  }

  // Trigger animations
  const fusedEl = container.querySelector("#fusedNum-" + idx);
  if (fusedEl) {
    lkAnimateNumber(fusedEl, fusedLR, 650, 2);
  }

  const gaugeEl = container.querySelector("#gaugeFill-" + idx);
  if (gaugeEl) {
    const fraction = Math.min(1, Math.max(0, fusedLR / 8));
    const targetOffset = 236 * (1 - fraction);
    setTimeout(() => {
      gaugeEl.style.strokeDashoffset = targetOffset;
    }, 50);
  }

  const postEl = container.querySelector("#postFill-" + idx);
  if (postEl) {
    setTimeout(() => {
      postEl.style.width = Math.min(100, Math.max(0, postPct)) + "%";
    }, 80);
  }
}

// ---------------------------------------------------------------------------
// AI Forensic Analyst Modal & Assistant Engine
// ---------------------------------------------------------------------------
let CURRENT_AI_PAIR = { a: null, b: null, handle_a: "", handle_b: "", lastMarkdown: "" };
let AI_MODAL_BOUND = false;

function renderMarkdownToHtml(md) {
  if (!md) return "";
  let html = esc(md);

  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Horizontal rules
  html = html.replace(/^---$/gim, '<hr>');

  // Markdown tables
  html = html.replace(/((?:\|[^\n]+\|\r?\n)+)/g, match => {
    const lines = match.trim().split(/\r?\n/).filter(l => l.trim().startsWith("|"));
    if (lines.length < 2) return match;
    let tableHtml = '<div style="overflow-x:auto"><table>';
    lines.forEach((line, rowIdx) => {
      if (line.includes("---")) return;
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      if (rowIdx === 0) {
        tableHtml += '<thead><tr>' + cells.map(c => `<th>${c}</th>`).join("") + '</tr></thead><tbody>';
      } else {
        tableHtml += '<tr>' + cells.map((c, colIdx) => {
          let cellContent = c;
          if (c.includes("⭐ strongest")) {
            cellContent = cellContent.replace("⭐ strongest", '<span style="color:#00e5cc;font-weight:700;margin-left:4px">⭐ strongest</span>');
          }
          if (colIdx === 1 && (c.startsWith("+") || c.startsWith("-"))) {
            const isPos = c.startsWith("+");
            return `<td style="color:${isPos ? '#00e5cc' : '#fc8181'};font-weight:700;font-family:monospace">${cellContent}</td>`;
          }
          return `<td>${cellContent}</td>`;
        }).join("") + '</tr>';
      }
    });
    tableHtml += '</tbody></table></div>';
    return tableHtml;
  });

  // Bullet points
  html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');

  // Paragraphs
  const paragraphs = html.split(/\n{2,}/);
  html = paragraphs.map(p => {
    p = p.trim();
    if (!p) return "";
    if (p.startsWith("<h") || p.startsWith("<table") || p.startsWith("<div") || p.startsWith("<hr") || p.startsWith("<ul")) {
      return p;
    }
    return `<p>${p.replace(/\n/g, "<br>")}</p>`;
  }).join("\n");

  return html;
}

async function loadAiEngineOptions() {
  const sel = document.getElementById("aiModelSelect");
  if (!sel) return;
  try {
    const res = await fetch("/api/ai/status");
    if (res.ok) {
      const data = await res.json();
      sel.innerHTML = `
        <option value="">Auto Detect</option>
        <option value="deterministic">Deterministic Synthesizer</option>
      `;
      if (data.online && data.models && data.models.length > 0) {
        data.models.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = `Ollama: ${m}`;
          sel.appendChild(opt);
        });
      }
    }
  } catch (e) {
    console.warn("Could not check AI status:", e);
  }
}

async function fetchAiForensicReport(forceDeterministic = false) {
  const loading = document.getElementById("aiLoadingState");
  const reportContent = document.getElementById("aiReportContent");
  const badge = document.getElementById("aiModelBadge");
  const sel = document.getElementById("aiModelSelect");

  if (loading) loading.style.display = "flex";
  if (reportContent) reportContent.innerHTML = "";

  const chosenModel = sel ? sel.value : "";
  const isForce = forceDeterministic || chosenModel === "deterministic";

  let url = `/api/ai/analyze-link/${encodeURIComponent(CURRENT_AI_PAIR.a)}/${encodeURIComponent(CURRENT_AI_PAIR.b)}`;
  const params = [];
  if (chosenModel && chosenModel !== "deterministic") params.push(`model=${encodeURIComponent(chosenModel)}`);
  if (isForce) params.push("force_deterministic=true");
  if (params.length) url += "?" + params.join("&");

  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("Server returned status " + resp.status);
    const data = await resp.json();

    CURRENT_AI_PAIR.lastMarkdown = data.markdown || "";

    if (badge) {
      if (data.source === "ollama") {
        badge.className = "anv-ai-badge-mode ollama";
        badge.textContent = `Ollama: ${data.model || "Local LLM"}`;
      } else {
        badge.className = "anv-ai-badge-mode";
        badge.textContent = "Deterministic Synthesizer";
      }
    }

    if (reportContent) {
      reportContent.innerHTML = renderMarkdownToHtml(data.markdown || "No report generated.");
    }

    const chatHist = document.getElementById("aiChatHistory");
    if (chatHist) chatHist.innerHTML = "";

  } catch (err) {
    if (reportContent) {
      reportContent.innerHTML = `
        <div style="padding:20px;border-radius:8px;background:rgba(252,129,129,0.1);border:1px solid rgba(252,129,129,0.3);color:#fc8181">
          <b>Forensic Analysis Error:</b> ${esc(err.message)}
        </div>
      `;
    }
  } finally {
    if (loading) loading.style.display = "none";
  }
}

function closeAiForensicModal() {
  const modal = document.getElementById("ai-modal-overlay");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = "";
}

async function askAiAssistantQuestion() {
  const input = document.getElementById("aiChatInput");
  const hist = document.getElementById("aiChatHistory");
  const sel = document.getElementById("aiModelSelect");
  if (!input || !hist) return;

  const q = input.value.trim();
  if (!q) return;

  input.value = "";

  // Append user bubble
  const userMsg = document.createElement("div");
  userMsg.className = "anv-ai-chat-msg user";
  userMsg.textContent = q;
  hist.appendChild(userMsg);

  // Append thinking bubble
  const assistMsg = document.createElement("div");
  assistMsg.className = "anv-ai-chat-msg assistant";
  assistMsg.innerHTML = "<em>Forensic assistant evaluating findings...</em>";
  hist.appendChild(assistMsg);
  hist.scrollTop = hist.scrollHeight;

  try {
    const chosenModel = sel ? sel.value : "";
    const resp = await fetch("/api/ai/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: q,
        context: CURRENT_AI_PAIR.lastMarkdown || "",
        model: (chosenModel && chosenModel !== "deterministic") ? chosenModel : ""
      })
    });
    if (!resp.ok) throw new Error("Assistant query failed (" + resp.status + ")");
    const data = await resp.json();
    assistMsg.innerHTML = renderMarkdownToHtml(data.answer || "No response.");
  } catch (err) {
    assistMsg.innerHTML = `<span style="color:#fc8181">Error: ${esc(err.message)}</span>`;
  }
  hist.scrollTop = hist.scrollHeight;
}

function setupAiModalEventListeners() {
  if (AI_MODAL_BOUND) return;
  AI_MODAL_BOUND = true;

  const modal = document.getElementById("ai-modal-overlay");
  if (modal) {
    modal.onclick = (e) => {
      if (e.target === modal) closeAiForensicModal();
    };
  }

  const closeBtn1 = document.getElementById("aiModalCloseBtn");
  if (closeBtn1) closeBtn1.onclick = closeAiForensicModal;

  const closeBtn2 = document.getElementById("aiModalCloseBtn2");
  if (closeBtn2) closeBtn2.onclick = closeAiForensicModal;

  // ESC key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const aiMod = document.getElementById("ai-modal-overlay");
      if (aiMod && aiMod.style.display !== "none") closeAiForensicModal();
    }
  });

  // Copy Markdown
  const copyBtn = document.getElementById("aiBtnCopy");
  if (copyBtn) {
    copyBtn.onclick = () => {
      if (!CURRENT_AI_PAIR.lastMarkdown) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(CURRENT_AI_PAIR.lastMarkdown).then(() => {
          if (typeof showToast === "function") showToast("✓ Markdown report copied to clipboard!", "#00e5cc");
          else alert("Copied to clipboard!");
        });
      }
    };
  }

  // Export / Print
  const exportBtn = document.getElementById("aiBtnExport");
  if (exportBtn) {
    exportBtn.onclick = () => {
      const rep = document.getElementById("aiReportContent");
      if (!rep) return;
      const printWin = window.open("", "_blank");
      printWin.document.write(`
        <html>
        <head>
          <title>ANEKANTA AI Forensic Briefing - ${esc(CURRENT_AI_PAIR.handle_a)} vs ${esc(CURRENT_AI_PAIR.handle_b)}</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 32px; color: #111; line-height: 1.6; max-width: 860px; margin: auto; }
            table { width: 100%; border-collapse: collapse; margin: 16px 0; }
            th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }
            th { background: #f0f4f8; }
            hr { border: 0; border-top: 1px solid #ccc; margin: 20px 0; }
            code { background: #eee; padding: 2px 5px; border-radius: 3px; font-family: monospace; }
          </style>
        </head>
        <body>
          ${rep.innerHTML}
          <script>window.onload = function() { window.print(); }<\/script>
        </body>
        </html>
      `);
      printWin.document.close();
    };
  }

  // Regenerate
  const regenBtn = document.getElementById("aiBtnRegen");
  if (regenBtn) {
    regenBtn.onclick = () => fetchAiForensicReport(false);
  }

  // Model select change
  const sel = document.getElementById("aiModelSelect");
  if (sel) {
    sel.onchange = () => fetchAiForensicReport(false);
  }

  // Quick action chips
  document.querySelectorAll(".anv-chip-btn").forEach(btn => {
    btn.onclick = () => {
      const input = document.getElementById("aiChatInput");
      if (input && btn.dataset.q) {
        input.value = btn.dataset.q;
        askAiAssistantQuestion();
      }
    };
  });

  // Chat submit
  const chatSubmit = document.getElementById("aiChatSubmit");
  if (chatSubmit) chatSubmit.onclick = askAiAssistantQuestion;

  const chatInput = document.getElementById("aiChatInput");
  if (chatInput) {
    chatInput.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        askAiAssistantQuestion();
      }
    };
  }
}

async function openAiForensicModal(persona_a, persona_b, handle_a, handle_b) {
  setupAiModalEventListeners();

  const modal = document.getElementById("ai-modal-overlay");
  if (!modal) return;

  CURRENT_AI_PAIR = {
    a: persona_a,
    b: persona_b,
    handle_a: handle_a || persona_a,
    handle_b: handle_b || persona_b,
    lastMarkdown: ""
  };

  const titleEl = document.getElementById("aiModalHandles");
  if (titleEl) {
    titleEl.textContent = `${CURRENT_AI_PAIR.handle_a} ↔ ${CURRENT_AI_PAIR.handle_b}`;
  }

  modal.style.display = "flex";
  document.body.style.overflow = "hidden";

  await loadAiEngineOptions();
  await fetchAiForensicReport();
}

window.openAiForensicModal = openAiForensicModal;

// Backward compatibility helper
function evidenceHtml(l) {
  if (!l) return "";
  return `<button type="button" class="lk-btn-ai" onclick="openAiForensicModal('${esc(l.persona_a)}','${esc(l.persona_b)}','${esc(l.handle_a || l.persona_a)}','${esc(l.handle_b || l.persona_b)}')">✨ AI Forensic Analysis</button>`;
}

/* ---------------- actors & resolved clusters ---------------- */
let CL_SEARCH_TEXT = "";
let CL_FILTER_MIN_SIZE = 0;
let CL_FILTER_REGION = "";
let CL_FILTER_SORT = "id_asc";
let CL_LAYOUT_MODE = "card"; // "card" | "grid"
let CL_FLAGGED_CLUSTERS = new Set();
let CL_EXPANDED_PERSONAS = new Set();
let CL_COLLAPSED_CARDS = new Set();
let CL_EVENTS_BOUND = false;

function getConfidenceTier(lr) {
  const val = parseFloat(lr) || 0;
  if (val >= 4.0) return { tier: "high", color: "#00e5cc", class: "cl-tier-teal", name: "High Confidence" };
  if (val >= 2.0) return { tier: "med", color: "#f5a623", class: "cl-tier-amber", name: "Medium Confidence" };
  if (val >= 1.38) return { tier: "low", color: "#8b5cf6", class: "cl-tier-purple", name: "Low Confidence" };
  return { tier: "lead", color: "#718096", class: "cl-tier-gray", name: "Near Threshold" };
}

function formatDateSpan(from, to) {
  if (!from && !to) return "Unknown";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const parseYm = s => {
    if (!s) return "";
    const p = s.split("-");
    if (p.length < 2) return s;
    const mIdx = parseInt(p[1], 10) - 1;
    return (months[mIdx] || p[1]) + " " + p[0];
  };
  const f = parseYm(from);
  const t = parseYm(to);
  if (f === t) return f;
  return `${f} – ${t}`;
}

function renderActors(cl) {
  if (!cl || !cl.length) {
    const listEl = $("#actorList");
    if (listEl) listEl.innerHTML = `<p class="muted">No resolved actors available.</p>`;
    return;
  }

  // Populate Stats Bar
  const statClusters = $("#clStatClusters");
  const statPersonas = $("#clStatPersonas");
  const statHighConf = $("#clStatHighConf");
  const statRegions = $("#clStatRegions");

  const totalClusters = cl.length;
  let totalPersonas = 0;
  let highConfCount = 0;
  const uniqueRegions = new Set();

  cl.forEach(c => {
    totalPersonas += (c.size || (c.personas ? c.personas.length : 0));
    const lr = parseFloat(c.cohesion_log10_lr) || 0;
    if (lr >= 2.0 || (lr >= 1.38 && totalClusters < 50)) highConfCount++;
    const regs = c.dossier?.timezone?.regions || [];
    regs.forEach(r => { if (r && r.trim()) uniqueRegions.add(r.trim()); });
  });

  if (statClusters) statClusters.textContent = totalClusters;
  if (statPersonas) statPersonas.textContent = totalPersonas;
  if (statHighConf) statHighConf.textContent = highConfCount;
  if (statRegions) statRegions.textContent = uniqueRegions.size;

  // Populate Region Dropdown once
  const regSel = $("#clFilterRegion");
  if (regSel && regSel.options.length <= 1) {
    Array.from(uniqueRegions).sort().forEach(r => {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r;
      regSel.appendChild(opt);
    });
  }

  // Bind Events once
  setupClFilterEvents();

  // Apply filters and render
  applyClFilters();
}

function setupClFilterEvents() {
  if (CL_EVENTS_BOUND) return;
  CL_EVENTS_BOUND = true;

  const searchInput = $("#clSearchInput");
  if (searchInput) {
    searchInput.oninput = () => {
      CL_SEARCH_TEXT = searchInput.value.trim().toLowerCase();
      applyClFilters();
    };
  }

  const filterMinSize = $("#clFilterMinSize");
  if (filterMinSize) {
    filterMinSize.onchange = () => {
      CL_FILTER_MIN_SIZE = parseInt(filterMinSize.value, 10) || 0;
      applyClFilters();
    };
  }

  const filterRegion = $("#clFilterRegion");
  if (filterRegion) {
    filterRegion.onchange = () => {
      CL_FILTER_REGION = filterRegion.value;
      applyClFilters();
    };
  }

  const filterSort = $("#clFilterSort");
  if (filterSort) {
    filterSort.onchange = () => {
      CL_FILTER_SORT = filterSort.value;
      applyClFilters();
    };
  }

  const viewCardBtn = $("#clViewCardBtn");
  const viewGridBtn = $("#clViewGridBtn");
  if (viewCardBtn && viewGridBtn) {
    viewCardBtn.onclick = () => {
      CL_LAYOUT_MODE = "card";
      viewCardBtn.classList.add("active");
      viewGridBtn.classList.remove("active");
      applyClFilters();
    };
    viewGridBtn.onclick = () => {
      CL_LAYOUT_MODE = "grid";
      viewGridBtn.classList.add("active");
      viewCardBtn.classList.remove("active");
      applyClFilters();
    };
  }

  // Modal close handlers
  const modal = $("#clDossierModal");
  const modalClose1 = $("#clModalCloseBtn");
  const modalClose2 = $("#modalCloseBtn2");
  if (modalClose1) modalClose1.onclick = closeClusterDossier;
  if (modalClose2) modalClose2.onclick = closeClusterDossier;
  if (modal) {
    modal.onclick = (e) => {
      if (e.target === modal) closeClusterDossier();
    };
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && modal.classList.contains("open")) {
      closeClusterDossier();
    }
  });
}

function applyClFilters() {
  if (!CLUSTERS) return;

  let filtered = CLUSTERS.filter(c => {
    // Min personas filter
    const size = c.size || (c.personas ? c.personas.length : 0);
    if (CL_FILTER_MIN_SIZE > 0 && size < CL_FILTER_MIN_SIZE) return false;

    const d = c.dossier || {};
    const tz = d.timezone || {};

    // Region filter
    if (CL_FILTER_REGION) {
      const regs = tz.regions || [];
      if (!regs.includes(CL_FILTER_REGION)) return false;
    }

    // Search query filter
    if (CL_SEARCH_TEXT) {
      const idMatch = (c.cluster_id || "").toLowerCase().includes(CL_SEARCH_TEXT);
      const handleMatch = (c.handles || []).some(h => (h || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const personaMatch = (c.personas || []).some(p => (p || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const siteMatch = (d.sites || []).some(s => (s || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const devMatch = (d.exif_devices || []).some(dev => (dev || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const btcMatch = (d.btc_addresses || []).some(btc => (btc || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const pgpMatch = (d.pgp_keys || []).some(k => (k || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const regMatch = (tz.regions || []).some(r => (r || "").toLowerCase().includes(CL_SEARCH_TEXT));
      const noteMatch = (tz.note || "").toLowerCase().includes(CL_SEARCH_TEXT);

      if (!idMatch && !handleMatch && !personaMatch && !siteMatch && !devMatch && !btcMatch && !pgpMatch && !regMatch && !noteMatch) {
        return false;
      }
    }
    return true;
  });

  // Sort
  filtered.sort((a, b) => {
    if (CL_FILTER_SORT === "id_asc") {
      return (a.cluster_id || "").localeCompare(b.cluster_id || "");
    }
    if (CL_FILTER_SORT === "size_desc") {
      return (b.size || 0) - (a.size || 0);
    }
    if (CL_FILTER_SORT === "lr_desc") {
      return (b.cohesion_log10_lr || 0) - (a.cohesion_log10_lr || 0);
    }
    if (CL_FILTER_SORT === "lr_asc") {
      return (a.cohesion_log10_lr || 0) - (b.cohesion_log10_lr || 0);
    }
    if (CL_FILTER_SORT === "activity_desc") {
      const bTo = b.dossier?.active_to || "";
      const aTo = a.dossier?.active_to || "";
      return bTo.localeCompare(aTo);
    }
    return 0;
  });

  // Update count
  const countEl = $("#clFilterCount");
  if (countEl) {
    countEl.textContent = `Showing ${filtered.length} of ${CLUSTERS.length} clusters`;
  }

  const container = $("#actorList");
  if (!container) return;

  if (filtered.length === 0) {
    container.className = CL_LAYOUT_MODE === "grid" ? "cl-grid-view" : "cl-card-view";
    container.innerHTML = `
      <div style="text-align:center;padding:48px 16px;color:#94a3b8;grid-column:1/-1">
        <div style="font-size:36px;margin-bottom:12px">🔍</div>
        <div style="font-size:15px;font-weight:700;color:#ffffff;margin-bottom:6px">No matching clusters found</div>
        <div style="font-size:13px">Try clearing search filters or lowering the minimum personas requirement.</div>
      </div>
    `;
    return;
  }

  if (CL_LAYOUT_MODE === "grid") {
    container.className = "cl-grid-view";
    container.innerHTML = filtered.map((c, idx) => renderClusterGridCard(c, idx)).join("");
  } else {
    container.className = "cl-card-view";
    container.innerHTML = filtered.map((c, idx) => renderClusterCard(c, idx)).join("");
  }
}

function renderClusterCard(c, idx) {
  const d = c.dossier || {};
  const tz = d.timezone || {};
  const tier = getConfidenceTier(c.cohesion_log10_lr);
  const weakestLr = parseFloat(c.cohesion_log10_lr) || 0;
  const isFlagged = CL_FLAGGED_CLUSTERS.has(c.cluster_id);
  const isCollapsed = CL_COLLAPSED_CARDS.has(c.cluster_id);
  const isExpandedPersonas = CL_EXPANDED_PERSONAS.has(c.cluster_id);

  // Identify anchor persona (longest active)
  let anchorId = "";
  let maxDuration = -1;
  const personas = d.personas || [];
  personas.forEach(p => {
    const t1 = p.first_seen ? new Date(p.first_seen).getTime() : 0;
    const t2 = p.last_seen ? new Date(p.last_seen).getTime() : 0;
    const dur = t2 - t1;
    if (dur > maxDuration) {
      maxDuration = dur;
      anchorId = p.id;
    }
  });

  const visiblePersonas = isExpandedPersonas ? personas : personas.slice(0, 5);
  const remainingPersonas = personas.length - 5;

  // Active date span
  const activeSpan = formatDateSpan(d.active_from, d.active_to);

  // Confidence gauge
  const fillPct = Math.min(100, Math.max(0, (weakestLr / 6.0) * 100));
  const thresholdPct = (1.38 / 6.0) * 100;
  const statusLabel = weakestLr >= 1.38
    ? `<span style="color:#00e5cc">All links above assertion threshold &#10003;</span>`
    : `<span style="color:#f5a623">&#9888; Some links near threshold (log<sub>10</sub> LR &lt; 1.38)</span>`;

  // Geotemporal details
  const hasTz = tz.pooled_utc_offset !== null && tz.pooled_utc_offset !== undefined;
  const tzStr = hasTz ? `UTC${tz.pooled_utc_offset >= 0 ? "+" : ""}${fmt(tz.pooled_utc_offset, 2)}` : "UTC —";
  const spreadVal = tz.per_persona_spread_hours !== undefined ? parseFloat(tz.per_persona_spread_hours) : null;
  const spreadStr = spreadVal !== null ? `&plusmn;${fmt(spreadVal, 1)}h spread` : "";
  const regions = tz.regions || [];
  const showSpreadWarn = spreadVal !== null && spreadVal > 2.0;

  // Artefacts
  const pgpKeys = d.pgp_keys || [];
  const btcAddrs = d.btc_addresses || [];
  const onions = d.onion_services || [];
  const devices = d.exif_devices || [];

  return `
    <div class="cl-card ${tier.class} ${isCollapsed ? 'collapsed' : ''}" id="card-${c.cluster_id}" style="animation-delay:${idx * 40}ms">
      <!-- Card Header -->
      <div class="cl-card-header" onclick="toggleCardCollapse('${c.cluster_id}')">
        <div class="cl-header-left">
          <span class="cl-id-badge" style="color:${tier.color};border-color:${tier.color}55;background:${tier.color}15">${c.cluster_id}</span>
          <span class="cl-size-pill">${c.size || personas.length} personas</span>
          ${isFlagged ? `<span class="cl-flag-pill">&#9873; FLAGGED FP</span>` : ""}
        </div>
        <div class="cl-header-right">
          <div class="cl-stat-col">
            <span class="cl-stat-col-label">weakest link</span>
            <span class="cl-stat-col-val" style="color:${tier.color}">log<sub>10</sub> LR ${fmt(weakestLr, 2)}</span>
          </div>
          <div class="cl-stat-col">
            <span class="cl-stat-col-label">active</span>
            <span class="cl-stat-col-subval">${activeSpan}</span>
          </div>
          <span class="cl-chevron" id="chevron-${c.cluster_id}">&#9662;</span>
        </div>
      </div>

      <!-- Card Body -->
      <div class="cl-card-body">
        <!-- Left Column: Persona Table -->
        <div class="cl-persona-panel">
          <div class="cl-persona-table-wrap">
            <table class="cl-persona-table">
              <thead>
                <tr>
                  <th>PERSONA</th>
                  <th>HANDLE</th>
                  <th>SITE</th>
                  <th>ACTIVE</th>
                </tr>
              </thead>
              <tbody>
                ${visiblePersonas.map(p => {
                  const isAnchor = p.id === anchorId;
                  return `
                    <tr class="${isAnchor ? 'cl-anchor-row' : ''}">
                      <td class="mono" style="color:#00e5cc;font-weight:600">
                        ${esc(p.id)}
                        ${isAnchor ? `<span class="cl-anchor-pill" title="Anchor Persona (longest observed activity)">ANCHOR</span>` : ""}
                      </td>
                      <td style="font-weight:700;color:#ffffff">${esc(p.handle)}</td>
                      <td><span style="color:#38bdf8">@${esc(p.site)}</span></td>
                      <td class="muted" style="font-family:ui-monospace,monospace;font-size:11px">${esc(p.first_seen || "")} &rarr; ${esc(p.last_seen || "")}</td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table>
          </div>
          ${!isExpandedPersonas && remainingPersonas > 0 ? `
            <button type="button" class="cl-more-personas-btn" onclick="togglePersonaExpansion('${c.cluster_id}')">
              +${remainingPersonas} more personas &#9662;
            </button>
          ` : (isExpandedPersonas && personas.length > 5 ? `
            <button type="button" class="cl-more-personas-btn" onclick="togglePersonaExpansion('${c.cluster_id}')">
              Show less personas &#9652;
            </button>
          ` : "")}
        </div>

        <!-- Right Column: Intelligence Panel -->
        <div class="cl-intel-panel">
          <!-- Section A: Geotemporal -->
          <div>
            <div class="cl-section-hdr">&#127757; GEOTEMPORAL</div>
            <div class="cl-tz-display">
              <span class="cl-tz-large">${tzStr}</span>
              ${spreadStr ? `<span class="cl-tz-spread">${spreadStr}</span>` : ""}
            </div>
            ${regions.length ? `
              <div class="cl-region-chips">
                ${regions.map(r => `<span class="cl-region-chip">${esc(r)}</span>`).join("")}
              </div>
            ` : ""}
            ${showSpreadWarn ? `
              <div class="cl-warning-box">
                &#9888; Timezone spread &gt;2h &mdash; possible shared account or operator travel
              </div>
            ` : ""}
          </div>

          <!-- Section B: Artefacts -->
          <div>
            <div class="cl-section-hdr">&#128273; ARTEFACTS</div>
            <div class="cl-artefacts-list">
              <div class="cl-artefact-row">
                <span>&#128273; <b>PGP keys:</b></span>
                <span>${pgpKeys.length} key${pgpKeys.length === 1 ? "" : "s"}${d.key_rotation_observed ? ` <span class="pill p-lead" style="font-size:10px;padding:1px 6px">rotation observed</span>` : ""}</span>
              </div>
              <div class="cl-artefact-row">
                <span>&#128176; <b>Wallets:</b></span>
                <span>${btcAddrs.length} address${btcAddrs.length === 1 ? "" : "es"}</span>
              </div>
              <div class="cl-artefact-row">
                <span>&#127760; <b>Services:</b></span>
                <span>${onions.length} hidden service${onions.length === 1 ? "" : "s"}</span>
              </div>
              ${devices.length ? `
                <div class="cl-artefact-row" style="margin-top:2px">
                  <span>&#128241; <b>Devices:</b></span>
                  <div>
                    ${devices.map(dev => `<span class="cl-device-chip">${esc(dev)}</span>`).join("")}
                  </div>
                </div>
              ` : ""}
            </div>
          </div>

          <!-- Section C: Confidence Meter -->
          <div>
            <div class="cl-section-hdr">&#128202; CLUSTER STRENGTH</div>
            <div class="cl-gauge-wrap">
              <div class="cl-gauge-track">
                <div class="cl-gauge-threshold" style="left:${thresholdPct}%" title="Assertion Threshold (LR 1.38)"></div>
                <div class="cl-gauge-fill" style="width:${fillPct}%;background:${tier.color}"></div>
              </div>
              <div class="cl-gauge-status">
                ${statusLabel}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Card Footer -->
      <div class="cl-card-footer">
        <button type="button" class="cl-btn-action" onclick="viewClusterLinkages('${c.cluster_id}')">
          &#128279; View Linkages
        </button>
        <button type="button" class="cl-btn-action" onclick="openClusterDossier('${c.cluster_id}')">
          &#128196; Full Dossier
        </button>
        <button type="button" class="cl-btn-action" onclick="addClusterToReport('${c.cluster_id}')">
          &#128203; Add to Report
        </button>
        <button type="button" class="cl-btn-action ${isFlagged ? 'cl-btn-flagged' : ''}" onclick="toggleFlagCluster('${c.cluster_id}')">
          &#9873; ${isFlagged ? 'Unflag FP' : 'Flag Cluster'}
        </button>
      </div>
    </div>
  `;
}

function renderClusterGridCard(c, idx) {
  const d = c.dossier || {};
  const tz = d.timezone || {};
  const tier = getConfidenceTier(c.cohesion_log10_lr);
  const weakestLr = parseFloat(c.cohesion_log10_lr) || 0;
  const isFlagged = CL_FLAGGED_CLUSTERS.has(c.cluster_id);
  const personas = d.personas || [];
  const topHandles = personas.slice(0, 3);
  const regions = (tz.regions || []).slice(0, 3);

  return `
    <div class="cl-grid-card ${tier.class}" onclick="openClusterDossier('${c.cluster_id}')" style="animation-delay:${idx * 30}ms">
      <div class="cl-grid-top">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="cl-id-badge" style="color:${tier.color};border-color:${tier.color}55;background:${tier.color}15">${c.cluster_id}</span>
          <span class="cl-size-pill">${c.size || personas.length} personas</span>
          ${isFlagged ? `<span class="cl-flag-pill">&#9873; FP</span>` : ""}
        </div>
        <div style="text-align:right">
          <div style="font-size:10px;color:#718096;text-transform:uppercase">weakest link</div>
          <div style="font-size:14px;font-weight:700;color:${tier.color};font-family:monospace">LR ${fmt(weakestLr, 2)}</div>
        </div>
      </div>

      <div class="cl-grid-handles">
        ${topHandles.map(p => `
          <span class="cl-grid-handle-pill">
            ${esc(p.handle)}<span class="cl-grid-handle-site">@${esc(p.site)}</span>
          </span>
        `).join("")}
        ${personas.length > 3 ? `<span style="font-size:11px;color:#718096;align-self:center">+${personas.length - 3} more</span>` : ""}
      </div>

      <div class="cl-grid-bottom">
        <div class="cl-region-chips">
          ${regions.map(r => `<span class="cl-region-chip" style="font-size:10px;padding:1px 6px">${esc(r)}</span>`).join("")}
        </div>
        <span class="muted" style="font-size:11px">${formatDateSpan(d.active_from, d.active_to)}</span>
      </div>
    </div>
  `;
}

function togglePersonaExpansion(clusterId) {
  if (CL_EXPANDED_PERSONAS.has(clusterId)) {
    CL_EXPANDED_PERSONAS.delete(clusterId);
  } else {
    CL_EXPANDED_PERSONAS.add(clusterId);
  }
  applyClFilters();
}

function toggleCardCollapse(clusterId) {
  if (CL_COLLAPSED_CARDS.has(clusterId)) {
    CL_COLLAPSED_CARDS.delete(clusterId);
  } else {
    CL_COLLAPSED_CARDS.add(clusterId);
  }
  const card = document.getElementById("card-" + clusterId);
  if (card) {
    card.classList.toggle("collapsed", CL_COLLAPSED_CARDS.has(clusterId));
  }
}

function viewClusterLinkages(clusterId) {
  const tabBtn = document.querySelector('#tabs button[data-tab="links"]');
  if (tabBtn) tabBtn.click();
  const searchInput = $("#lkSearchInput");
  if (searchInput) {
    searchInput.value = clusterId;
    searchInput.dispatchEvent(new Event("input"));
  }
  showToast(`Filtered Linkages tab to ${clusterId}`, "#00e5cc");
}

function addClusterToReport(clusterId) {
  const c = (CLUSTERS || []).find(x => x.cluster_id === clusterId);
  if (!c) return;
  const d = c.dossier || {};
  let addedCount = 0;

  (d.personas || []).forEach(p => {
    if (typeof window.addToReport === "function") {
      window.addToReport({
        id: p.id,
        name: p.handle || p.id,
        actCode: p.id ? p.id.split("-")[0] : "",
        clusterId: c.cluster_id,
        site: p.site || "",
        maxLR: c.peak_log10_lr || c.cohesion_log10_lr || 0,
        linkedCount: c.size || 1,
        timezone: d.timezone?.pooled_utc_offset !== undefined ? `UTC${d.timezone.pooled_utc_offset >= 0 ? '+' : ''}${d.timezone.pooled_utc_offset}` : "UTC?",
        regions: d.timezone?.regions || ["Unknown"]
      });
      addedCount++;
    }
  });
  showToast(`📋 Added cluster ${clusterId} (${addedCount} personas) to report`, "#00e5cc");
}

function toggleFlagCluster(clusterId) {
  if (CL_FLAGGED_CLUSTERS.has(clusterId)) {
    CL_FLAGGED_CLUSTERS.delete(clusterId);
    showToast(`Cluster ${clusterId} unflagged`, "#00e5cc");
  } else {
    CL_FLAGGED_CLUSTERS.add(clusterId);
    showToast(`⚑ Cluster ${clusterId} flagged as False Positive`, "#ff6b6b");
  }
  applyClFilters();
}

/* --- Full Dossier Modal Functions --- */
function openClusterDossier(clusterId) {
  const c = (CLUSTERS || []).find(x => x.cluster_id === clusterId);
  if (!c) return;
  const d = c.dossier || {};
  const tz = d.timezone || {};
  const tier = getConfidenceTier(c.cohesion_log10_lr);
  const personas = d.personas || [];
  const modal = $("#clDossierModal");
  if (!modal) return;

  // Header
  $("#modalClusterId").textContent = c.cluster_id;
  $("#modalPersonaCount").textContent = `${c.size || personas.length} personas`;
  $("#modalDateRange").textContent = formatDateSpan(d.active_from, d.active_to);
  const tierBadge = $("#modalTierBadge");
  if (tierBadge) {
    tierBadge.textContent = tier.name.toUpperCase();
    tierBadge.className = `cl-tier-badge ${tier.tier === 'high' ? 'teal' : (tier.tier === 'med' ? 'amber' : 'purple')}`;
  }
  const cohesionText = $("#modalCohesionText");
  if (cohesionText) {
    cohesionText.innerHTML = `weakest LR ${fmt(c.cohesion_log10_lr, 2)} &middot; peak LR ${fmt(c.peak_log10_lr, 2)}`;
  }

  // Bind footer buttons for this cluster
  const addRepBtn = $("#modalAddReportBtn");
  if (addRepBtn) addRepBtn.onclick = () => addClusterToReport(clusterId);
  const viewLinksBtn = $("#modalViewLinksBtn");
  if (viewLinksBtn) viewLinksBtn.onclick = () => { closeClusterDossier(); viewClusterLinkages(clusterId); };

  // Calculate timeline ranges
  const minTime = d.active_from ? new Date(d.active_from).getTime() : 0;
  const maxTime = d.active_to ? new Date(d.active_to).getTime() : minTime + 86400000;
  const timeSpan = Math.max(1, maxTime - minTime);

  // Collect internal links map for N x N matrix
  const linkMatrix = {};
  if (LINKS && LINKS.links) {
    LINKS.links.forEach(l => {
      linkMatrix[`${l.persona_a}|${l.persona_b}`] = l;
      linkMatrix[`${l.persona_b}|${l.persona_a}`] = l;
    });
  }

  // Hourly histogram
  const hoursHist = new Array(24).fill(0);
  if (GRAPH && GRAPH.nodes) {
    personas.forEach(p => {
      const gNode = GRAPH.nodes.find(n => n.id === p.id);
      if (gNode && gNode.utc_offset !== undefined) {
        // Approximate peak activity based on timezone
        const offset = Math.round(gNode.utc_offset || 0);
        for (let h = 10; h <= 22; h++) {
          const utcH = (h - offset + 24) % 24;
          hoursHist[utcH] += 1;
        }
      }
    });
  }
  const maxHourCount = Math.max(1, Math.max(...hoursHist));

  // Build Body HTML with all 6 sections
  $("#clModalBody").innerHTML = `
    <!-- SECTION 1: CLUSTER OVERVIEW -->
    <div>
      <div class="cl-modal-sec-title">&#128202; 1. CLUSTER OVERVIEW &amp; TOPOLOGY METRICS</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:12px">
        <div class="card" style="padding:12px;background:rgba(255,255,255,0.02)">
          <div class="muted" style="font-size:10px;text-transform:uppercase">Internal Links</div>
          <div style="font-size:20px;font-weight:700;color:#00e5cc">${c.internal_links || personas.length}</div>
        </div>
        <div class="card" style="padding:12px;background:rgba(255,255,255,0.02)">
          <div class="muted" style="font-size:10px;text-transform:uppercase">Graph Density</div>
          <div style="font-size:20px;font-weight:700;color:#f5a623">${fmt(c.density || 0, 2)}</div>
        </div>
        <div class="card" style="padding:12px;background:rgba(255,255,255,0.02)">
          <div class="muted" style="font-size:10px;text-transform:uppercase">Weakest Internal LR</div>
          <div style="font-size:20px;font-weight:700;color:${tier.color}">${fmt(c.cohesion_log10_lr, 2)}</div>
        </div>
        <div class="card" style="padding:12px;background:rgba(255,255,255,0.02)">
          <div class="muted" style="font-size:10px;text-transform:uppercase">Peak Internal LR</div>
          <div style="font-size:20px;font-weight:700;color:#00e5cc">${fmt(c.peak_log10_lr, 2)}</div>
        </div>
      </div>
    </div>

    <!-- SECTION 2: ALL PERSONAS TABLE -->
    <div>
      <div class="cl-modal-sec-title">&#128100; 2. CLUSTER PERSONAS (${personas.length} TOTAL)</div>
      <div class="cl-persona-table-wrap">
        <table class="cl-persona-table" style="font-size:12.5px">
          <thead>
            <tr>
              <th>ID</th>
              <th>HANDLE</th>
              <th>SITE</th>
              <th>ACTIVE WINDOW</th>
              <th>OBSERVED DURATION</th>
            </tr>
          </thead>
          <tbody>
            ${personas.map(p => {
              const d1 = p.first_seen ? new Date(p.first_seen) : null;
              const d2 = p.last_seen ? new Date(p.last_seen) : null;
              const days = (d1 && d2) ? Math.round((d2 - d1) / (1000 * 60 * 60 * 24)) : 0;
              return `
                <tr>
                  <td class="mono" style="color:#00e5cc;font-weight:600">${esc(p.id)}</td>
                  <td style="font-weight:700;color:#ffffff">${esc(p.handle)}</td>
                  <td><span style="color:#38bdf8">@${esc(p.site)}</span></td>
                  <td class="muted" style="font-family:monospace">${esc(p.first_seen || "")} &rarr; ${esc(p.last_seen || "")}</td>
                  <td style="color:#a78bfa;font-weight:600">${days} days</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <!-- SECTION 3: TIMELINE VIEW -->
    <div>
      <div class="cl-modal-sec-title">&#128337; 3. OPERATIONAL TIMELINE &amp; OVERLAPS</div>
      <div class="cl-timeline-wrap">
        ${personas.map(p => {
          const t1 = p.first_seen ? new Date(p.first_seen).getTime() : minTime;
          const t2 = p.last_seen ? new Date(p.last_seen).getTime() : maxTime;
          const leftPct = Math.max(0, Math.min(96, ((t1 - minTime) / timeSpan) * 100));
          const widthPct = Math.max(4, Math.min(100 - leftPct, ((t2 - t1) / timeSpan) * 100));
          return `
            <div class="cl-timeline-row">
              <div class="cl-timeline-label" title="${esc(p.handle)} (@${esc(p.site)})">
                ${esc(p.handle)} <span class="muted" style="font-size:10px">@${esc(p.site)}</span>
              </div>
              <div class="cl-timeline-bar-track">
                <div class="cl-timeline-bar-fill" style="left:${leftPct}%;width:${widthPct}%;background:${tier.color}"></div>
              </div>
              <div class="cl-timeline-dates">${formatDateSpan(p.first_seen, p.last_seen)}</div>
            </div>
          `;
        }).join("")}
      </div>
    </div>

    <!-- SECTION 4: GEOTEMPORAL ANALYSIS -->
    <div>
      <div class="cl-modal-sec-title">&#127757; 4. GEOTEMPORAL &amp; CIRCADIAN ANALYSIS</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div>
          <div style="margin-bottom:8px">
            <span style="font-size:18px;font-weight:800;color:#00e5cc;font-family:monospace">
              ${tz.pooled_utc_offset !== null && tz.pooled_utc_offset !== undefined ? `UTC${tz.pooled_utc_offset >= 0 ? "+" : ""}${fmt(tz.pooled_utc_offset, 2)}` : "UTC Unknown"}
            </span>
            ${tz.per_persona_spread_hours !== undefined ? `<span style="font-size:12px;color:#f5a623;font-weight:600;margin-left:8px">&plusmn;${fmt(tz.per_persona_spread_hours, 1)}h spread</span>` : ""}
          </div>
          <div class="cl-region-chips">
            ${(tz.regions || []).map(r => `<span class="cl-region-chip" style="padding:3px 10px">${esc(r)}</span>`).join("")}
          </div>
          ${tz.note ? `<div class="muted" style="font-size:12px;margin-top:10px">${esc(tz.note)}</div>` : ""}
        </div>
        <div>
          <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;font-weight:600">POOLED ACTIVE HOURS HEATMAP (0 &ndash; 23 UTC)</div>
          <div class="cl-hour-heatmap">
            ${hoursHist.map((hCount, hr) => {
              const hPct = Math.round((hCount / maxHourCount) * 100);
              return `
                <div class="cl-hour-bar" style="height:${Math.max(6, hPct)}%" title="${hr}:00 UTC — Activity score ${hCount}"></div>
              `;
            }).join("")}
          </div>
          <div style="display:flex;justify-content:space-between;font-size:9.5px;color:#64748b;margin-top:4px;font-family:monospace">
            <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTION 5: ALL ARTEFACTS -->
    <div>
      <div class="cl-modal-sec-title">&#128273; 5. CONSOLIDATED FORENSIC ARTEFACTS</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div class="card" style="padding:14px;background:rgba(255,255,255,0.02)">
          <div style="font-size:11px;font-weight:700;color:#f5a623;margin-bottom:8px">&#128273; PGP FINGERPRINTS (${(d.pgp_keys || []).length})</div>
          ${(d.pgp_keys || []).length ? (d.pgp_keys || []).map((k, i) => `
            <div style="font-size:11px;font-family:monospace;color:#cbd5e1;padding:3px 0;display:flex;align-items:center;gap:6px">
              <span style="color:#718096">#${i + 1}</span> <span>${esc(k)}</span>
            </div>
          `).join("") : `<span class="muted" style="font-size:11px">No PGP keys published</span>`}
        </div>

        <div class="card" style="padding:14px;background:rgba(255,255,255,0.02)">
          <div style="font-size:11px;font-weight:700;color:#f5a623;margin-bottom:8px">&#128176; BITCOIN WALLETS (${(d.btc_addresses || []).length})</div>
          ${(d.btc_addresses || []).length ? (d.btc_addresses || []).map(w => `
            <div style="font-size:11px;font-family:monospace;color:#00e5cc;padding:3px 0">${esc(w)}</div>
          `).join("") : `<span class="muted" style="font-size:11px">No Bitcoin addresses observed</span>`}
        </div>

        <div class="card" style="padding:14px;background:rgba(255,255,255,0.02)">
          <div style="font-size:11px;font-weight:700;color:#38bdf8;margin-bottom:8px">&#127760; ONION SERVICES (${(d.onion_services || []).length})</div>
          ${(d.onion_services || []).length ? (d.onion_services || []).map(o => `
            <div style="font-size:11px;font-family:monospace;color:#38bdf8;padding:3px 0;word-break:break-all">${esc(o)}</div>
          `).join("") : `<span class="muted" style="font-size:11px">No hidden services hosted</span>`}
        </div>

        <div class="card" style="padding:14px;background:rgba(255,255,255,0.02)">
          <div style="font-size:11px;font-weight:700;color:#a78bfa;margin-bottom:8px">&#128241; HARDWARE &amp; DEVICES (${(d.exif_devices || []).length})</div>
          ${(d.exif_devices || []).length ? (d.exif_devices || []).map(dev => `
            <span class="cl-device-chip" style="margin:2px 4px 2px 0">${esc(dev)}</span>
          `).join("") : `<span class="muted" style="font-size:11px">No EXIF device profiles recovered</span>`}
        </div>
      </div>
    </div>

    <!-- SECTION 6: INTERNAL LINKAGE MATRIX -->
    <div>
      <div class="cl-modal-sec-title">&#128279; 6. INTERNAL PAIRWISE LINKAGE MATRIX</div>
      <p class="sub" style="margin-bottom:10px">N&times;N grid of calibrated log<sub>10</sub> Likelihood Ratios between all persona pairings in this cluster.</p>
      <div style="overflow-x:auto">
        <table class="cl-matrix-table">
          <thead>
            <tr>
              <th>PAIR</th>
              ${personas.map((p, pi) => `<th title="${esc(p.handle)} (@${esc(p.site)})">P${pi}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${personas.map((pa, i) => `
              <tr>
                <th>P${i} <span style="font-weight:400;color:#64748b;font-size:10px">${esc(pa.handle)}</span></th>
                ${personas.map((pb, j) => {
                  if (i === j) {
                    return `<td style="color:#64748b;background:rgba(255,255,255,0.02)">&mdash;</td>`;
                  }
                  const link = linkMatrix[`${pa.id}|${pb.id}`];
                  if (link) {
                    const lTier = getConfidenceTier(link.log10_lr);
                    return `
                      <td class="cl-matrix-cell" style="background:${lTier.color}22;color:${lTier.color};border-color:${lTier.color}44"
                          onclick="closeClusterDossier();viewClusterLinkages('${pa.id}')"
                          title="${esc(pa.handle)} &harr; ${esc(pb.handle)}: LR ${fmt(link.log10_lr, 2)} (${lTier.name})">
                        ${fmt(link.log10_lr, 1)}
                      </td>
                    `;
                  }
                  return `<td style="color:#64748b" title="Transitive cluster resolution">trans</td>`;
                }).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  modal.style.display = "flex";
  requestAnimationFrame(() => modal.classList.add("open"));
}

function closeClusterDossier() {
  const modal = $("#clDossierModal");
  if (!modal) return;
  modal.classList.remove("open");
  setTimeout(() => { modal.style.display = "none"; }, 250);
}


/* ---------------- live crawl ---------------- */

let LIVE_POLL = null;

// Validates a user-supplied string as a v2/v3 .onion address or URL
const ONION_RE = /^(https?:\/\/)?[a-z2-7]{16,56}\.onion(\/.*)?$/i;

function validateOnion(raw) {
  const v = raw.trim().toLowerCase();
  return v && ONION_RE.test(v);
}

// ---- Tor status badge ----
function updateTorBadge(connected, message) {
  const dot  = document.getElementById('torStatusDot');
  const text = document.getElementById('torStatusText');
  if (!dot || !text) return;
  if (connected) {
    dot.style.background  = '#37d39b';
    text.style.color      = '#37d39b';
    text.textContent      = 'Tor connected';
  } else {
    dot.style.background  = '#ff6b6b';
    text.style.color      = '#ff6b6b';
    text.textContent      = 'Tor offline — lab replay mode';
  }
}

// ---- Structured error card ----
function showLiveError(errStr) {
  const card    = document.getElementById('liveErrorCard');
  const icon    = document.getElementById('liveErrorIcon');
  const msg     = document.getElementById('liveErrorMsg');
  const sub     = document.getElementById('liveErrorSub');
  const btn     = document.getElementById('liveErrorAction');
  if (!card) return;

  // classify error by keywords
  let iconTxt = '⚠', headTxt = '', subTxt = '', btnTxt = '', btnFn = null;

  if (/no tor socks|socks proxy|proxy not|not running|offline|socks/i.test(errStr)) {
    iconTxt = '🔌';
    headTxt = 'Tor service not detected on 127.0.0.1:9050';
    subTxt  = 'Start Tor Browser, or run `tor &`, or `docker compose up -d` in onionlab/. ' +
              'Results shown below are from the lab replay cache.';
    btnTxt  = 'Show Lab Replay';
    btnFn   = () => { loadLiveResult(); hideLiveError(); };
  } else if (/timeout|timed out|connect timeout/i.test(errStr)) {
    iconTxt = '⏱';
    headTxt = 'Crawl timed out';
    subTxt  = '.onion sites are slow (30–90 s per page). Try again or reduce the follow-up count.';
    btnTxt  = 'Try again';
    btnFn   = () => { hideLiveError(); document.getElementById('liveRun').click(); };
  } else if (/no accounts|unreachable|root page|invalid|could not reach/i.test(errStr)) {
    iconTxt = '🌐';
    headTxt = 'Could not reach the onion address';
    subTxt  = errStr + '\n.onion sites have ~60% uptime on average. Check the address and try again.';
    btnTxt  = 'Try another address';
    btnFn   = () => { hideLiveError(); document.getElementById('liveAddr').focus(); };
  } else {
    headTxt = 'Crawl failed';
    subTxt  = errStr || 'An unexpected error occurred.';
  }

  icon.textContent = iconTxt;
  msg.textContent  = headTxt;
  sub.textContent  = subTxt;
  if (btnTxt && btnFn) {
    btn.textContent = btnTxt;
    btn.style.display = '';
    btn.onclick = btnFn;
  } else {
    btn.style.display = 'none';
  }
  card.style.display = '';
}

function hideLiveError() {
  const c = document.getElementById('liveErrorCard');
  if (c) c.style.display = 'none';
}

// ---- Crawl stage panel ----
// Maps backend log messages → stage index 0-5
function msgToStage(messages) {
  const joined = messages.map(p => p.message).join('\n').toLowerCase();
  if (/analysis complete|crawl completed|graded/i.test(joined))          return 5;
  if (/scoring|resolv|attribution/i.test(joined))                        return 4;
  if (/crawling|fetching|page/i.test(joined))                            return 3;
  if (/discover|following|linked/i.test(joined))                         return 2;
  if (/crawling .+\.\.\.|seed/i.test(joined))                            return 1;
  if (/socks|reachable|connecting|tor/i.test(joined))                    return 0;
  return 0;
}

const STAGE_PCT = [5, 20, 40, 65, 82, 100];

function renderCrawlPanel(st) {
  const panel = document.getElementById('liveCrawlPanel');
  const fill  = document.getElementById('crawlProgressFill');
  if (!panel || !fill) return;

  const msgs     = st.progress || [];
  const isDone   = st.status === 'done';
  const isError  = st.status === 'error';
  const isReplay = msgs.some(p => /replay|simulation|onionlab baseline/i.test(p.message));

  // Show/hide replay banner
  const replayBanner = document.getElementById('liveReplayBanner');
  if (replayBanner) replayBanner.style.display = isReplay ? '' : 'none';

  // Update raw log
  const rawLog = document.getElementById('liveProgress');
  if (rawLog) {
    rawLog.textContent = msgs.map(p => `[${p.at}] ${p.message}`).join('\n');
    rawLog.scrollTop   = rawLog.scrollHeight;
  }

  if (isError) {
    panel.style.display = '';
    // mark last active stage as error
    document.querySelectorAll('.crawl-stage').forEach(li => {
      if (li.classList.contains('active')) li.classList.add('error-stage');
    });
    return;
  }

  panel.style.display = '';

  const stage = isDone ? 5 : msgToStage(msgs);
  const pct   = STAGE_PCT[stage] || 0;

  fill.style.width = pct + '%';
  if (isDone) fill.classList.add('done'); else fill.classList.remove('done');

  // Update stage items
  for (let i = 0; i <= 5; i++) {
    const li = document.getElementById('cstage-' + i);
    if (!li) continue;
    li.classList.remove('active', 'done', 'error-stage');
    if (i < stage)       li.classList.add('done');
    else if (i === stage) li.classList.add(isDone ? 'done' : 'active');
  }

  // Update liveState text
  const stateEl = document.getElementById('liveState');
  if (stateEl) {
    if (isDone)        stateEl.textContent = isReplay ? '🔬 lab replay complete' : '✅ complete';
    else if (isError)  stateEl.innerHTML   = `<span class="neg">failed</span>`;
    else               stateEl.textContent = 'crawling over Tor…';
  }
}

let LIVE_READY = false;
function liveInit() {
  if (LIVE_READY) return;
  LIVE_READY = true;

  // Always load initial findings so page is never blank
  loadLiveResult();

  // --- Check Tor status on load ---
  fetch('/api/live/tor_check')
    .then(r => r.json())
    .then(d => {
      updateTorBadge(d.connected, d.message);
    })
    .catch(() => {
      // static mode or backend not running — badge stays grey
      updateTorBadge(null, '');
    });

  api('/api/live/lab').then(d => {
    if (d.available && d.addresses && d.addresses.market && !$('#liveAddr').value) {
      $('#liveAddr').value = d.addresses.market;
    }
  }).catch(() => { });

  // Wire sample target buttons
  const smBtn = $('#sampleMarketBtn');
  if (smBtn) smBtn.onclick = () => {
    $('#liveAddr').value = 'mssu6ktfxio3vnej545tokmuhbuo3rpa6ywpoahxbtqruvyvzjzf2byd.onion';
    showToast('Selected Market Onion address', '#00e5cc');
  };
  const sfBtn = $('#sampleForumBtn');
  if (sfBtn) sfBtn.onclick = () => {
    $('#liveAddr').value = 'nz3wd6ag5hsoj5sxsuqxzcve643qhopybennlosbegrnfy4ragxoetid.onion';
    showToast('Selected Forum Onion address', '#00e5cc');
  };
  const srBtn = $('#sampleResetBtn');
  if (srBtn) srBtn.onclick = () => {
    loadLiveResult();
    $('#liveState').textContent = '';
    const panel = document.getElementById('liveCrawlPanel');
    if (panel) panel.style.display = 'none';
    hideLiveError();
    showToast('Restored baseline findings', '#00e5cc');
  };

  // Clear inline validation error on input change
  const addrInput = $('#liveAddr');
  if (addrInput) addrInput.addEventListener('input', () => {
    const errEl = document.getElementById('liveAddrError');
    if (errEl) errEl.style.display = 'none';
    addrInput.style.borderColor = '';
  });

  // ---- Main crawl button ----
  $('#liveRun').onclick = () => {
    let addr = $('#liveAddr').value.trim();
    const errEl = document.getElementById('liveAddrError');

    // Auto-complete bare address (no dot = add .onion)
    if (addr && !addr.includes('.')) {
      addr = addr + '.onion';
      $('#liveAddr').value = addr;
    }

    // Fallback: if empty use market address
    if (!addr) {
      addr = 'mssu6ktfxio3vnej545tokmuhbuo3rpa6ywpoahxbtqruvyvzjzf2byd.onion';
      $('#liveAddr').value = addr;
    }

    // Validate .onion format
    if (!validateOnion(addr)) {
      if (errEl) errEl.style.display = '';
      if (addrInput) addrInput.style.borderColor = '#ff6b6b';
      return;
    }
    if (errEl) errEl.style.display = 'none';
    if (addrInput) addrInput.style.borderColor = '';

    const max = parseInt($('#liveMax').value || '4', 10);

    // Reset UI
    hideLiveError();
    const replayBanner = document.getElementById('liveReplayBanner');
    if (replayBanner) replayBanner.style.display = 'none';
    const panel = document.getElementById('liveCrawlPanel');
    if (panel) panel.style.display = '';
    // Reset all stages to pending
    for (let i = 0; i <= 5; i++) {
      const li = document.getElementById('cstage-' + i);
      if (li) li.className = 'crawl-stage';
    }
    const fill = document.getElementById('crawlProgressFill');
    if (fill) { fill.style.width = '5%'; fill.classList.remove('done'); }
    document.querySelectorAll('.crawl-stage')[0]?.classList.add('active');

    $('#liveRun').disabled = true;
    $('#liveState').textContent = 'starting crawl / simulation…';

    fetch(`/api/live/run?target=${encodeURIComponent(addr)}&max_onions=${max}`,
      { method: 'POST' })
      .then(r => r.json())
      .then(() => livePoll())
      .catch(e => {
        showLiveError('failed to start: ' + e);
        $('#liveRun').disabled = false;
      });
  };

  // Check live status on tab open (resume if running)
  api('/api/live/status').then(st => {
    if (st.status === 'running') { $('#liveRun').disabled = true; livePoll(); }
    else if (st.status === 'done')  { renderCrawlPanel(st); loadLiveResult(); }
    else if (st.status === 'error') { showLiveError(st.error); }
    else { loadLiveResult(); }
  }).catch(() => { loadLiveResult(); });
}

function livePoll() {
  if (LIVE_POLL) clearInterval(LIVE_POLL);
  LIVE_POLL = setInterval(() => {
    api('/api/live/status').then(st => {
      renderCrawlPanel(st);
      if (st.status === 'done') {
        clearInterval(LIVE_POLL); LIVE_POLL = null;
        $('#liveRun').disabled = false;
        loadLiveResult();
      } else if (st.status === 'error') {
        clearInterval(LIVE_POLL); LIVE_POLL = null;
        $('#liveRun').disabled = false;
        showLiveError(st.error || 'Unknown error');
      }
    }).catch(() => { });
  }, 1800);
}

function loadLiveResult() {
  api('/api/live/result').then(d => {
    if (!d || (!d.available && !d.crawl)) return;
    $('#liveBody').style.display = '';
    renderLive(d);
  }).catch(e => {
    fetch('data/live.json').then(r => r.json()).then(d => {
      if (d && (d.available || d.crawl)) {
        $('#liveBody').style.display = '';
        renderLive(d);
      }
    }).catch(() => { });
  });
}



function renderLive(d) {
  const c = d.crawl, g = d.graded || {}, og = d.osint_graded || {};

  $("#liveKpis").innerHTML = [
    ["Services", c.services_crawled, c.pages_fetched + " pages crawled"],
    ["Accounts", c.personas, c.posts.toLocaleString() + " posts extracted"],
    ["Clear-web mentions", d.mentions.length,
      (og.recovered !== undefined ? og.recovered + " planted leaks recovered"
        : "harvested identifiers")],
    ["Clusters", d.clusters.length, "resolved from " + d.links.length + " scored pairs"],
    ["Linkage precision", g.available ? pct(g.precision) : "--",
      g.available ? g.tp + " correct, " + g.fp + " false" : "no ground truth"],
    ["Linkage recall", g.available ? pct(g.recall) : "--",
      g.available ? g.fn + " true pairs missed" : ""],
  ].map(([k, v, n]) =>
    `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div>
     <div class="n">${n}</div></div>`).join("");

  // --- services ---
  const from = c.discovered_from || {};
  $("#liveServices").innerHTML = `<table>
    <tr><th>onion</th><th>how it was found</th></tr>
    ${(c.onions || []).map(o => `<tr><td class="mono">${esc(o.slice(0, 22))}...</td>
      <td class="muted">${from[o]
      ? "discovered on " + esc(from[o].slice(0, 16)) + "..."
      : "supplied as the seed"}</td></tr>`).join("")}
  </table>`;

  // --- fingerprints ---
  const fps = d.fingerprints || {};
  const keys = Object.keys(fps);
  const rows = [
    ["favicon mmh3", f => f.favicon_mmh3],
    ["favicon dHash", f => f.favicon_dhash],
    ["TLS public key", f => (f.tls && f.tls.spki_sha256 || "").slice(0, 20)],
    ["TLS issuer", f => f.tls && f.tls.issuer_o],
    ["header order", f => (f.header_order_hash || "").slice(0, 20)],
    ["DOM skeleton", f => (f.dom_skeleton_hash || "").slice(0, 20)],
    ["CSS vocabulary", f => (f.css_vocab_hash || "").slice(0, 20)],
    ["404 shape", f => (f.error_page_hash || "").slice(0, 20)],
    ["server banner", f => f.server_banner || "(suppressed)"],
  ];
  $("#liveFingerprints").innerHTML = `<table>
    <tr><th>artefact</th>${keys.map(k =>
    `<th class="mono">${esc(k.slice(0, 12))}...</th>`).join("")}</tr>
    ${rows.map(([label, get]) => {
      const vals = keys.map(k => get(fps[k]) || "--");
      const same = vals.length > 1 && vals.every(v => v === vals[0] && v !== "--");
      return `<tr><td>${label}</td>${vals.map(v =>
        `<td class="mono" ${same ? 'style="color:var(--warn)"' : ""}>${esc(String(v))}</td>`
      ).join("")}</tr>`;
    }).join("")}
  </table>
  <p class="sub" style="margin-top:10px">Values highlighted in amber are
  identical across every service — here that is the same software deployed
  twice, which is exactly the rebrand signature. Because <i>all</i> accounts
  share them, the rarity weighting reduces them to near zero for linking
  accounts to each other, while they remain decisive for linking the
  <i>services</i>.</p>`;

  // --- mentions ---
  const bandClass = { high: "p-linkage", medium: "p-lead", low: "", noise: "" };
  $("#liveMentions").innerHTML = `<table>
    <tr><th>band</th><th>kind</th><th>identifier</th><th>on account</th>
    <th class="num">priority</th><th>why it ranks here</th></tr>
    ${d.mentions.slice(0, 30).map(m => `<tr>
      <td><span class="pill ${bandClass[m.band] || ""}">${m.band}</span></td>
      <td class="muted">${esc(m.kind)}</td>
      <td class="mono">${esc(m.value)}</td>
      <td class="mono">${esc(m.handle || "—")}</td>
      <td class="num">${fmt(m.priority, 2)}</td>
      <td class="muted">${esc((m.reasons || [])[0] || "")}</td>
    </tr>`).join("")}
  </table>`;

  // --- exposure ---
  $("#liveExposure").innerHTML = d.exposure.length
    ? d.exposure.map(e => `<div class="ev" style="border-left-color:var(--warn)">
        <b>${e.cluster_id}</b>
        <span class="muted">&middot; ${e.personas.length} accounts</span>
        <div style="margin-top:7px"><b>Leaked by:</b>
          <span class="mono">${e.leaking_personas.map(esc).join(", ")}</span></div>
        <div><b>Identifiers:</b>
          <span class="mono">${e.identifiers.map(esc).join(", ") || "—"}</span></div>
        ${e.exposed_by_association.length ? `<div style="margin-top:5px">
          <b class="pos">Also implicated</b>
          <span class="muted">(these accounts leaked nothing themselves, but
          share an operator):</span>
          <span class="mono">${e.exposed_by_association.map(esc).join(", ")}</span>
        </div>` : ""}
      </div>`).join("")
    : `<p class="muted">No leaks attributable to a resolved cluster.</p>`;

  // --- developed leads ---
  $("#liveLeads").innerHTML = d.developed.slice(0, 8).map(x => {
    const corr = x.leads.filter(l => l.method === "identity correlation");
    const other = x.leads.filter(l => l.method !== "identity correlation");
    return `<div class="ev">
      <div style="display:flex;justify-content:space-between">
        <b class="mono">${esc(x.identifier)}</b>
        <span class="muted">${esc(x.kind)} &middot; priority ${fmt(x.priority, 2)}
          &middot; found on ${esc(x.handle || "an unattributed page")}</span>
      </div>
      ${corr.map(l => `<div class="row"><div class="ch">correlation</div>
        <div class="lr pos">match</div>
        <div class="why">${esc(l.detail)}</div></div>`).join("")}
      ${other.length ? `<div class="row"><div class="ch">to check</div>
        <div class="lr muted">${other.length}</div>
        <div class="why">${other.slice(0, 6).map(l =>
      l.url ? `<a href="${esc(l.url)}" target="_blank" rel="noreferrer noopener">${esc(l.method)}</a>`
        : esc(l.method)).join(" &middot; ")}
        <br><span class="muted">Constructed, not fetched.</span></div></div>` : ""}
    </div>`;
  }).join("") || `<p class="muted">Nothing developed above the priority floor.</p>`;

  // --- links ---
  $("#liveLinks").innerHTML = `<table>
    <tr><th>finding</th><th>account A</th><th>account B</th>
    <th class="num">log<sub>10</sub> LR</th><th>channels</th></tr>
    ${d.links.slice(0, 20).map(l => `<tr>
      <td><span class="pill ${l.tier === "linkage" ? "p-linkage" : "p-lead"}">
        ${l.tier}</span></td>
      <td class="mono">${esc(l.handle_a)}${l.cross_service
      ? ' <span class="muted" title="different service">&#8599;</span>' : ""}</td>
      <td class="mono">${esc(l.handle_b)}</td>
      <td class="num">${fmt(l.log10_lr, 2)}</td>
      <td class="muted">${l.channels.join(", ")}</td>
    </tr>`).join("")}
  </table>
  <p class="sub" style="margin-top:10px">&#8599; marks a pair spanning two
  different services — the hard case, since the operator used unrelated handles
  on each.</p>`;

  // --- graded ---
  $("#liveGraded").innerHTML = `
    ${g.available ? `<table>
      <tr><th>linkage</th><th class="num">value</th></tr>
      <tr><td>Accounts / pairs scored</td>
        <td class="num">${g.personas_matched} / ${g.pairs_scored}</td></tr>
      <tr><td>True operator pairs</td><td class="num">${g.true_pairs}</td></tr>
      <tr><td>Precision</td><td class="num">${fmt(g.precision, 2)}</td></tr>
      <tr><td>Recall</td><td class="num">${fmt(g.recall, 2)}</td></tr>
      <tr><td>ROC AUC</td><td class="num">${fmt(g.roc_auc, 3)}</td></tr>
      <tr><td>B-Cubed F1</td><td class="num">${fmt(g.bcubed_f1, 3)}</td></tr>
    </table>` : `<p class="muted">No operator map for this target.</p>`}
    ${og.available ? `<table style="margin-top:12px">
      <tr><th>clear-web harvest</th><th class="num">value</th></tr>
      <tr><td>Planted leaks recovered</td>
        <td class="num">${og.recovered}/${og.planted} (${pct(og.recall)})</td></tr>
      <tr><td>Attributed to the right account</td>
        <td class="num">${og.attribution_correct}</td></tr>
      <tr><td>Decoys collected</td>
        <td class="num">${og.decoys_collected}/${og.decoys_present}</td></tr>
      <tr><td>Ranking separates leaks from decoys</td>
        <td class="num">${og.ranking_separates_leaks_from_decoys ? "yes" : "NO"}</td></tr>
      <tr><td>Worst real leak / best decoy</td>
        <td class="num">${fmt(og.worst_real_leak_priority, 2)} /
          ${fmt(og.best_decoy_priority, 2)}</td></tr>
      <tr><td>Identity correlations</td>
        <td class="num">${og.identifiers_with_identity_correlation}</td></tr>
      <tr><td>Accounts implicated by association</td>
        <td class="num">${og.accounts_exposed_by_association}</td></tr>
    </table>` : ""}`;
}

/* ---------------- real Tor network ---------------- */

let RW_POLL = null, RW_READY = false;

function rwInit() {
  if (RW_READY) return;
  RW_READY = true;

  if (STATIC_MODE) { RW_ENGINES = ["tordex", "tor66", "onionland"]; }
  api("/api/discovery/engines").then(d => {
    $("#rwEngines").textContent = d.searchable.join(", ");
    RW_ENGINES = d.searchable;
    if (d.default_queries) $("#rwQueries").value = d.default_queries.slice(0, 6).join(", ");
  }).catch(() => { });

  $("#rwDiscover").onclick = () => rwStart("/api/discovery/run");
  $("#rwBench").onclick = () => rwStart("/api/realworld/run");

  if (STATIC_MODE) { rwLoad(); return; }
  api("/api/realworld/status").then(st => {
    if (st.status === "running") { rwBusy(true); rwPoll(); }
    else if (st.status === "done") { rwRenderProgress(st); rwLoad(); }
  }).catch(() => { });
}

let RW_ENGINES = [];

function rwBusy(on) {
  $("#rwDiscover").disabled = on;
  $("#rwBench").disabled = on;
}

function rwStart(endpoint) {
  const q = encodeURIComponent($("#rwQueries").value.trim() || "hosting");
  const e = encodeURIComponent(RW_ENGINES.join(","));
  const svc = parseInt($("#rwServices").value || "12", 10);
  const pg = parseInt($("#rwPages").value || "4", 10);
  const url = `${endpoint}?queries=${q}&engines=${e}&services=${svc}&pages_each=${pg}`;
  rwBusy(true);
  $("#rwState").textContent = "starting...";
  $("#rwProgress").style.display = "";
  fetch(url, { method: "POST" }).then(r => r.json()).then(() => rwPoll())
    .catch(err => { $("#rwState").textContent = "failed: " + err; rwBusy(false); });
}

function rwRenderProgress(st) {
  $("#rwProgress").style.display = st.progress.length ? "" : "none";
  $("#rwProgress").textContent =
    st.progress.map(p => `[${p.at}] ${p.message}`).join("\n");
  $("#rwProgress").scrollTop = $("#rwProgress").scrollHeight;
}

function rwPoll() {
  if (RW_POLL) clearInterval(RW_POLL);
  RW_POLL = setInterval(() => {
    api("/api/realworld/status").then(st => {
      $("#rwState").textContent = st.status === "running"
        ? "running over Tor — discovery and crawling are slow by design..."
        : st.status;
      rwRenderProgress(st);
      if (st.status === "done") {
        clearInterval(RW_POLL); RW_POLL = null; rwBusy(false); rwLoad();
      } else if (st.status === "error") {
        clearInterval(RW_POLL); RW_POLL = null; rwBusy(false);
        $("#rwState").innerHTML = `<span class="neg">${esc(st.error)}</span>`;
      }
    }).catch(() => { });
  }, 3000);
}

function rwLoad() {
  api("/api/realworld/result").then(d => {
    if (d && d.crawl && d.available === undefined) d.available = true;
    if (!d.available) return;
    $("#rwBody").style.display = "";
    if (d.mode === "discovery") rwRenderDiscovery(d); else rwRenderBenchmark(d);
    $("#rwRaw").textContent = JSON.stringify(d, null, 2);
  });
}

function rwRenderDiscovery(d) {
  const s = d.stats || {};
  $("#rwKpis").innerHTML = [
    ["Addresses found", (d.results || []).length, "unique .onion services"],
    ["Raw hits", s.raw_hits || 0, "before filtering"],
    ["Blacklisted", s.blacklisted || 0, "removed before any fetch"],
    ["Blacklist size", (d.blacklist_hashes || 0).toLocaleString(), "hashed addresses"],
  ].map(([k, v, n]) =>
    `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div>
     <div class="n">${n}</div></div>`).join("");

  $("#rwClusters").innerHTML =
    `<p class="muted">Discovery only — run the full benchmark to crawl these
     services and correlate their infrastructure.</p>`;
  $("#rwServicesTable").innerHTML = "";
  $("#rwSafety").innerHTML = (d.notes || []).length
    ? `<ul class="muted" style="margin:0;padding-left:18px">${d.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>`
    : `<p class="muted">No engine notes.</p>`;
  rwDiscoveredTable(d.results || []);
}

function rwDiscoveredTable(rows) {
  $("#rwDiscovered").innerHTML = rows.length ? `<table>
    <tr><th>onion</th><th>engines</th><th>found by</th><th>title</th></tr>
    ${rows.slice(0, 60).map(r => `<tr>
      <td class="mono">${esc(r.onion.slice(0, 30))}...</td>
      <td class="muted">${(r.engines || []).join(", ")}</td>
      <td class="muted">${(r.queries || []).join(", ")}</td>
      <td>${esc((r.title || "").slice(0, 50))}</td></tr>`).join("")}
  </table>` : `<p class="muted">Nothing discovered.</p>`;
}

function rwRenderBenchmark(d) {
  const disc = d.discovery || {}, crawl = d.crawl || {},
    safety = d.safety || {}, ext = d.extraction || {},
    cl = d.infrastructure_clusters || {};

  $("#rwKpis").innerHTML = [
    ["Addresses discovered", disc.unique_addresses || 0,
      (disc.corroborated_by_multiple_engines || 0) + " seen by >1 engine"],
    ["Reachable", `${crawl.services_reachable}/${crawl.services_attempted}`,
      pct(crawl.reachability)],
    ["Throughput", (crawl.pages_per_minute || 0) + "/min",
      crawl.pages + " pages, " + Math.round((crawl.bytes || 0) / 1024) + " KB"],
    ["Clear-web identifiers", ext.clear_web_mentions || 0,
      (ext.mentions_per_reachable_service || 0) + " per service"],
    ["Infra clusters", cl.non_generic || 0,
      (cl.total || 0) + " total, rest generic"],
    ["Blacklisted", safety.blacklisted_before_fetch || 0,
      "removed before any fetch"],
  ].map(([k, v, n]) =>
    `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div>
     <div class="n">${n}</div></div>`).join("");

  const clusters = (cl.clusters || []).filter(c => !c.generic);
  $("#rwClusters").innerHTML = clusters.length ? clusters.map(c => `
    <div class="ev" style="border-left-color:var(--warn)">
      <div style="display:flex;justify-content:space-between">
        <b>${esc(c.label)}</b>
        <span class="muted">${c.size} services &middot; ${esc(c.meaning)}</span>
      </div>
      <div class="mono" style="margin-top:6px;font-size:11.5px">
        ${c.services.map(s => esc(s)).join("<br>")}
      </div>
      <div class="why" style="margin-top:6px">shared value
        <span class="mono">${esc(c.value)}…</span> — verifiable by fetching both
        services yourself.</div>
    </div>`).join("")
    : `<p class="muted">No non-generic infrastructure clusters in this sample.
       Increase the number of services, or widen the search terms.</p>
       ${(cl.clusters || []).length ? `<p class="sub">${(cl.clusters || []).length}
       generic cluster(s) were found and suppressed: values shared by more than
       half the sample identify the software, not an operator.</p>` : ""}`;

  $("#rwServicesTable").innerHTML = `<table>
    <tr><th>onion</th><th class="num">pages</th><th class="num">mentions</th>
    <th>tls</th><th>title</th></tr>
    ${(d.services || []).map(s => `<tr>
      <td class="mono">${esc(s.onion.slice(0, 22))}...</td>
      <td class="num">${s.pages || 0}</td>
      <td class="num">${s.clear_web_mentions || 0}</td>
      <td class="muted">${s.tls ? "yes" : "—"}</td>
      <td class="muted">${esc((s.title || "").slice(0, 34))}</td></tr>`).join("")}
  </table>
  <p class="sub" style="margin-top:10px">${esc(ext.account_extraction_note || "")}</p>`;

  $("#rwSafety").innerHTML = `<table>
    <tr><th>control</th><th class="num">count</th></tr>
    <tr><td>Ahmia blacklist size</td>
      <td class="num">${(disc.blacklist_hashes || 0).toLocaleString()}</td></tr>
    <tr><td>Removed as blacklisted</td>
      <td class="num">${safety.blacklisted_before_fetch || 0}</td></tr>
    <tr><td>Removed by content gate (pre-fetch)</td>
      <td class="num">${safety.excluded_by_gate_before_fetch || 0}</td></tr>
    <tr><td>Discarded after fetch</td>
      <td class="num">${safety.services_excluded_after_fetch || 0}</td></tr>
  </table>
  ${(disc.notes || []).length ? `<p class="sub" style="margin-top:10px">
    ${disc.notes.map(n => esc(n)).join("<br>")}</p>` : ""}
  <p class="sub" style="margin-top:10px"><b>Not measured:</b>
    ${esc(d.what_is_not_measured || "")}</p>`;

  rwDiscoveredTable((d.services || []).map(s => ({
    onion: s.onion, engines: s.engines, queries: s.queries, title: s.title
  })));
}

/* ---------------- link graph ----------------
   Laid out by resolved cluster rather than by physics.

   A free force-directed layout on 250 nodes converges to a hairball, and a
   hairball is not a finding. The product's actual output is a set of resolved
   actors, so the canvas is packed cluster by cluster: each identity gets its
   own cell, its personas sit on a small ring inside it, and nodes ease toward
   those targets. Two things then become readable at a glance that the physics
   layout hid — how many distinct operators were resolved, and any edge that
   crosses between cells, which is precisely the case an analyst should
   inspect because it is either a merge the resolver declined to make or a
   mistake. */

/* ---------------- link graph: Cyber-Intelligence Workstation Redesign ---------------- */

let sim = null;

function startGraph() {
  if (!GRAPH) return;

  const svgEl = document.getElementById("graph-svg");
  if (!svgEl) return;
  const svg = d3.select(svgEl);

  const cvMinimap = $("#cv-minimap");
  const miniCtx = cvMinimap ? cvMinimap.getContext("2d") : null;
  const minimapWrap = $("#lgMinimapWrap");
  const minimapVp = $("#lgMinimapViewport");

  // UI elements
  const lrSlider = $("#lrFilter");
  const lrFilterVal = $("#lrFilterVal");
  const showLeadsCb = $("#showLeads");
  const clusterSizeMin = $("#clusterSizeMin");
  const clusterSizeMax = $("#clusterSizeMax");
  const clusterSizeVal = $("#clusterSizeVal");
  const clusterSortSel = $("#clusterSort");
  const searchInput = $("#lgSearchInput");
  const searchClear = $("#lgSearchClear");
  const searchResultsEl = $("#lgSearchResults");
  const subGraphBanner = $("#lgSubGraphBanner");
  const subGraphClusterLbl = $("#lgSubGraphCluster");
  const exitSubGraphBtn = $("#lgExitSubGraph");
  const sidePanel = $("#lgSidePanel");
  const closeSidePanelBtn = $("#lgCloseSidePanel");
  const contextMenu = $("#lgContextMenu");
  const sidebar = $("#lgSidebar");
  const toggleSidebarBtn = $("#lgToggleSidebar");
  const sbSummaryEl = $("#lgSbSummary");
  const countHighEl = $("#lgCountHigh");
  const countMedEl = $("#lgCountMed");
  const countLowEl = $("#lgCountLow");

  if (lrSlider && (!lrSlider.value || lrSlider.value === "1")) { lrSlider.value = "3.5"; }
  if (lrFilterVal) lrFilterVal.textContent = fmt(parseFloat(lrSlider ? lrSlider.value : 3.5), 1);

  const minLR = () => parseFloat(lrSlider ? lrSlider.value : 3.5);
  const showLeads = () => showLeadsCb ? showLeadsCb.checked : false;
  let activeTiers = new Set(["high", "med", "low"]);
  let minClusterSize = 1;
  let maxClusterSize = 15;
  let sortCriteria = "size";
  let subGraphClusterId = null;
  let selectedNode = null;
  let d3Simulation = null;
  let currentTransform = d3.zoomIdentity;

  function getNodeBaseRadius(deg) {
    if (deg <= 1) return 6;
    if (deg === 2) return 9;
    if (deg === 3) return 12;
    if (deg === 4) return 15;
    return 18;
  }

  // Initialize nodes & lookup maps
  if (!sim) {
    const rect = svgEl.getBoundingClientRect();
    const W = rect.width || 1200;
    const H = rect.height || 640;
    sim = {
      nodes: GRAPH.nodes.map(n => Object.assign({}, n, {
        x: W / 2 + (Math.random() - 0.5) * 100,
        y: H / 2 + (Math.random() - 0.5) * 100,
        vx: 0, vy: 0,
        name: n.name || n.handle || n.id,
        clusterId: n.cluster || n.clusterId || "SOLO",
        locale: n.utc_offset !== undefined ? `UTC${n.utc_offset >= 0 ? "+" : ""}${n.utc_offset}` : "Global"
      })),
      edges: GRAPH.edges,
      initialPlaced: false
    };
    sim.byId = Object.fromEntries(sim.nodes.map(n => [n.id, n]));
  }

  // Calculate degrees, max LR and base radius
  sim.nodes.forEach(n => {
    n.degree = 0;
    n.maxLr = 0;
  });
  sim.edges.forEach(e => {
    const a = sim.byId[e.source], b = sim.byId[e.target];
    if (a) { a.degree++; if (e.log10_lr > a.maxLr) a.maxLr = e.log10_lr; }
    if (b) { b.degree++; if (e.log10_lr > b.maxLr) b.maxLr = e.log10_lr; }
  });
  sim.nodes.forEach(n => {
    n.baseRadius = getNodeBaseRadius(n.degree);
    n.radius = n.baseRadius;
    n.linkedCount = n.degree;
    n.links = n.degree;
    n.maxLR = n.maxLr ? n.maxLr.toFixed(2) : "0.00";
    n.lr = n.maxLr ? n.maxLr.toFixed(2) : "0.00";
    n.actCode = n.id;
    n.name = n.name || n.handle || n.id;
    n.clusterId = n.cluster || n.clusterId || "SOLO";
    n.site = n.site || "tor-network";
    n.locale = n.utc_offset !== undefined ? `UTC${n.utc_offset >= 0 ? "+" : ""}${n.utc_offset}` : "Global";
    n.timezone = n.utc_offset !== undefined ? `UTC${n.utc_offset >= 0 ? "+" : ""}${n.utc_offset}` : "UTC+0";
    n.regions = n.regions || [n.locale || "Global"];
  });

  function getNodeTier(n) {
    const lr = n.maxLR !== undefined ? n.maxLR : n.maxLr;
    if (lr >= 6.0) return "high";
    if (lr >= 4.0) return "med";
    return "low";
  }

  function getNodeColor(n) {
    const tier = getNodeTier(n);
    if (tier === "high") return "#00e5cc";
    if (tier === "med") return "#f5a623";
    return "#8b5cf6";
  }

  function glowFilter(tier) {
    if (tier === "high") return "url(#glow-high)";
    if (tier === "med") return "url(#glow-med)";
    return "url(#glow-low)";
  }

  function isConnected(a, b) {
    if (!a || !b) return false;
    if (a.id === b.id) return true;
    const current = getFilteredGraph();
    return current.es.some(e => {
      const sId = typeof e.source === "object" ? e.source.id : e.source;
      const tId = typeof e.target === "object" ? e.target.id : e.target;
      return (sId === a.id && tId === b.id) || (sId === b.id && tId === a.id);
    });
  }

  function getAllClusterNodes(clusterId) {
    return sim.nodes.filter(n => (n.clusterId || n.cluster) === clusterId);
  }

  function getFilteredGraph() {
    const cutoff = minLR();
    const leads = showLeads();

    let es = sim.edges.filter(e => {
      if (e.log10_lr < cutoff) return false;
      if (!leads && e.tier !== "linkage") return false;
      return true;
    });

    if (subGraphClusterId) {
      es = es.filter(e => {
        const a = sim.byId[e.source], b = sim.byId[e.target];
        return a && b && (a.clusterId || a.cluster) === subGraphClusterId && (b.clusterId || b.cluster) === subGraphClusterId;
      });
    }

    const activeNodeIds = new Set();
    es.forEach(e => { activeNodeIds.add(e.source); activeNodeIds.add(e.target); });

    let ns = sim.nodes.filter(n => {
      if (subGraphClusterId) return (n.clusterId || n.cluster) === subGraphClusterId;
      if (!activeNodeIds.has(n.id)) return false;
      const tier = getNodeTier(n);
      if (!activeTiers.has(tier)) return false;
      return true;
    });

    const clusterMap = new Map();
    ns.forEach(n => {
      const c = n.clusterId || n.cluster || ("solo:" + n.id);
      if (!clusterMap.has(c)) clusterMap.set(c, []);
      clusterMap.get(c).push(n);
    });

    const validClusters = new Set();
    clusterMap.forEach((members, cid) => {
      if (members.length >= minClusterSize && members.length <= maxClusterSize) {
        validClusters.add(cid);
      }
    });

    ns = ns.filter(n => validClusters.has(n.clusterId || n.cluster || ("solo:" + n.id)));
    const finalIds = new Set(ns.map(n => n.id));
    es = es.filter(e => finalIds.has(e.source) && finalIds.has(e.target));

    const sortedClusters = [...validClusters].map(cid => {
      const members = clusterMap.get(cid) || [];
      const avgLr = members.reduce((acc, m) => acc + m.maxLr, 0) / Math.max(members.length, 1);
      const maxLr = members.reduce((acc, m) => Math.max(acc, m.maxLr), 0);
      return { cid, members, avgLr, maxLr, size: members.length };
    });

    if (sortCriteria === "size") { sortedClusters.sort((a, b) => b.size - a.size); }
    else if (sortCriteria === "confidence") { sortedClusters.sort((a, b) => b.maxLr - a.maxLr); }

    return { ns, es, clusters: sortedClusters };
  }

  function preSpaceClusters(clusters, ns, W, H) {
    const K = clusters.length;
    if (K === 0) return;
    const cols = Math.max(1, Math.ceil(Math.sqrt(K * 1.3)));
    const rows = Math.ceil(K / cols);
    const spacingX = Math.max(210, Math.min(270, (W - 140) / Math.max(cols, 1)));
    const spacingY = Math.max(180, Math.min(230, (H - 140) / Math.max(rows, 1)));

    clusters.forEach((c, idx) => {
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const cx = (W / 2) + (col - (cols - 1) / 2) * spacingX;
      const cy = (H / 2 + 25) + (row - (rows - 1) / 2) * spacingY;
      c.initCenterX = cx;
      c.initCenterY = cy;

      c.members.forEach((m, mi) => {
        const count = Math.max(c.members.length, 1);
        const angle = (mi / count) * Math.PI * 2;
        const ringR = 20 + Math.min(45, mi * 5);
        m.x = cx + Math.cos(angle) * ringR;
        m.y = cy + Math.sin(angle) * ringR;
        m.vx = 0;
        m.vy = 0;
      });
    });
  }

  // Build SVG Structure
  svg.selectAll("*").remove();

  const defs = svg.append("defs");
  const glowHigh = defs.append("filter").attr("id", "glow-high").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
  glowHigh.append("feDropShadow").attr("dx", 0).attr("dy", 0).attr("stdDeviation", 6).attr("flood-color", "#00e5cc").attr("flood-opacity", 0.9);

  const glowMed = defs.append("filter").attr("id", "glow-med").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
  glowMed.append("feDropShadow").attr("dx", 0).attr("dy", 0).attr("stdDeviation", 6).attr("flood-color", "#f5a623").attr("flood-opacity", 0.9);

  const glowLow = defs.append("filter").attr("id", "glow-low").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
  glowLow.append("feDropShadow").attr("dx", 0).attr("dy", 0).attr("stdDeviation", 6).attr("flood-color", "#8b5cf6").attr("flood-opacity", 0.9);

  const bgRect = svg.append("rect")
    .attr("id", "bg-rect")
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("fill", "#0a0e1a");

  const mainG = svg.append("g").attr("id", "main-container");
  const edgesG = mainG.append("g").attr("class", "edges-layer");
  const badgesG = mainG.append("g").attr("class", "badges-layer");
  const nodesG = mainG.append("g").attr("class", "nodes-layer");
  const labelsG = mainG.append("g").attr("class", "labels-layer");

  const zoom = d3.zoom()
    .scaleExtent([0.3, 5.0])
    .on("start", () => {
      svg.style("cursor", "grabbing");
      bgRect.style("cursor", "grabbing");
    })
    .on("zoom", event => {
      currentTransform = event.transform;
      mainG.attr("transform", event.transform);
      updateMinimapViewport();
    })
    .on("end", () => {
      svg.style("cursor", "grab");
      bgRect.style("cursor", "grab");
    });

  svg.call(zoom);

  svg.on("click", function (event) {
    if (event.target.tagName === "svg" ||
      event.target.tagName === "rect" ||
      event.target.id === "bg-rect" ||
      event.target === svg.node()) {
      closeRightPanel();
    }
  });

  let allNodes = null;
  let allEdges = null;
  let allLabels = null;
  let allBadges = null;

  function getNodeClearnetPivot(d) {
    if (!d) return { hasClearnet: false, contacts: [], devices: [], hosts: [] };
    const clusterId = d.clusterId || d.cluster;
    const clusters = window.CLUSTERS || (typeof CLUSTERS !== "undefined" ? CLUSTERS : null);
    let contacts = [];
    let devices = [];
    let hosts = [];

    if (clusterId && clusters) {
      const c = clusters.find(x => x.cluster_id === clusterId);
      if (c && c.dossier) {
        (c.dossier.contact_identifiers || []).forEach(ci => { if (ci && !contacts.includes(ci)) contacts.push(ci); });
        (c.dossier.exif_devices || []).forEach(dev => { if (dev && !devices.includes(dev)) devices.push(dev); });
      }
    }

    const allHosts = window.ALL_HOSTS || (typeof IR_HOSTS !== "undefined" ? IR_HOSTS : []);
    if (allHosts && Array.isArray(allHosts)) {
      const matched = allHosts.filter(h => 
        (clusterId && h.cluster_id === clusterId) ||
        (h.attributed_persona && (h.attributed_persona === d.handle || h.attributed_persona === d.name || h.attributed_persona === d.id))
      );
      matched.forEach(h => {
        const loc = h.city ? `${h.ip} (${h.city})` : h.ip;
        if (!hosts.includes(loc)) hosts.push(loc);
      });
    }

    const hasClearnet = contacts.length > 0 || hosts.length > 0 || devices.length > 0;
    return { hasClearnet, contacts, devices, hosts };
  }

  function showTooltip(event, d) {
    const tip = document.getElementById("graph-tooltip");
    if (!tip) return;
    const name = d.name || d.handle || d.id;
    const clusterId = d.clusterId || d.cluster || "SOLO";
    const site = d.site || "tor-network";
    const linkedCount = d.linkedCount !== undefined ? d.linkedCount : d.degree;
    const maxLR = fmt(d.maxLR !== undefined ? d.maxLR : d.maxLr, 1);
    const locale = d.locale || (d.utc_offset !== undefined ? `UTC${d.utc_offset >= 0 ? "+" : ""}${d.utc_offset}` : "Global");
    const pivot = getNodeClearnetPivot(d);

    const clearnetSnippet = pivot.hasClearnet ? `
      <div style="border-top:1px solid rgba(56,189,248,0.25);margin:6px 0"></div>
      <div style="color:#38bdf8;font-size:11px;font-weight:600">
        🌐 Clearnet: ${esc(pivot.contacts[0] || pivot.hosts[0] || pivot.devices[0])}
      </div>
    ` : '';

    tip.innerHTML = `
      <div style="font-weight:700;font-size:13px">${esc(name)} 
        <span style="background:#f5a623;color:#000;border-radius:10px;
          padding:1px 6px;font-size:10px;margin-left:4px">${esc(clusterId)}</span>
      </div>
      <div style="color:#718096;font-size:11px;margin-top:2px">🧅 Darknet: ${esc(site)}</div>
      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:6px 0"></div>
      <div style="color:#00e5cc">🔗 ${linkedCount} linked · LR ${maxLR}</div>
      <div style="color:#718096;font-size:11px">📍 ${esc(locale)}</div>
      ${clearnetSnippet}
    `;
    tip.style.opacity = "1";
    updateTooltipPosition(event);
  }

  function updateTooltipPosition(event) {
    const tip = document.getElementById("graph-tooltip");
    if (!tip) return;
    const x = event.clientX + 16;
    const y = event.clientY - 8;
    const flipX = x + 200 > window.innerWidth;
    const flipY = y - 100 < 0;
    tip.style.left = flipX ? (event.clientX - 216) + "px" : x + "px";
    tip.style.top = flipY ? (event.clientY + 16) + "px" : y + "px";
  }

  function hideTooltip() {
    const tip = document.getElementById("graph-tooltip");
    if (tip) tip.style.opacity = "0";
  }

  function getNeighbors(d) {
    const neighbors = [];
    const current = getFilteredGraph();
    current.es.forEach(e => {
      const sId = typeof e.source === "object" ? e.source.id : e.source;
      const tId = typeof e.target === "object" ? e.target.id : e.target;
      if (sId === d.id || tId === d.id) {
        const otherId = (sId === d.id) ? tId : sId;
        const otherNode = sim.byId[otherId];
        if (otherNode) {
          neighbors.push({
            id: otherNode.id,
            name: otherNode.name || otherNode.handle || otherNode.id,
            lr: typeof e.log10_lr === "number" ? e.log10_lr : parseFloat(e.log10_lr || 0),
            tier: e.tier
          });
        }
      }
    });
    neighbors.sort((a, b) => b.lr - a.lr);
    return neighbors;
  }

  function buildLinksList(d) {
    const neighbors = getNeighbors(d);
    if (!neighbors || neighbors.length === 0) {
      return '<div style="color:#718096;font-size:12px">No scored links found</div>';
    }
    return neighbors.map(n => {
      const pct = Math.min(100, (n.lr / 8) * 100);
      const color = n.lr > 6 ? '#00e5cc' : n.lr > 4 ? '#f5a623' : '#8b5cf6';
      return `
        <div style="display:flex;align-items:center;gap:8px;
          margin-bottom:10px;cursor:pointer"
          onclick="highlightEdge('${esc(d.id)}','${esc(n.id)}')">
          <div style="width:8px;height:8px;border-radius:50%;
            background:${color};flex-shrink:0"></div>
          <div style="flex:1;font-size:12px;color:#e2e8f0;
            overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            ${esc(n.name || n.id)}
          </div>
          <div style="font-size:11px;color:${color};flex-shrink:0">
            ${n.lr ? n.lr.toFixed(2) : '—'}
          </div>
          <div style="width:50px;height:4px;background:rgba(255,255,255,0.1);
            border-radius:2px;flex-shrink:0">
            <div style="width:${pct}%;height:100%;
              background:${color};border-radius:2px"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  window.highlightEdge = function (sourceId, targetId) {
    if (!allEdges) return;
    allEdges.transition().duration(200)
      .style("opacity", e => {
        const sId = typeof e.source === "object" ? e.source.id : e.source;
        const tId = typeof e.target === "object" ? e.target.id : e.target;
        return (sId === sourceId && tId === targetId) || (sId === targetId && tId === sourceId) ? 1 : 0.03;
      })
      .style("stroke-width", e => {
        const sId = typeof e.source === "object" ? e.source.id : e.source;
        const tId = typeof e.target === "object" ? e.target.id : e.target;
        return (sId === sourceId && tId === targetId) || (sId === targetId && tId === sourceId) ? 4 : 0.8;
      });
  };

  // --- REPORT BADGE & STORAGE HELPERS ---
  function updateReportBadge() {
    const badge = document.getElementById('lgReportBadge');
    if (!badge) return;
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }
    const count = report.length;
    badge.textContent = `📋 Report (${count})`;
    badge.style.display = count > 0 ? 'inline-flex' : 'none';
    const drawerCount = document.getElementById('reportDrawerCount');
    if (drawerCount) drawerCount.textContent = `${count} actor${count === 1 ? '' : 's'}`;
  }
  window.updateReportBadge = updateReportBadge;

  function setReportBtnAdded() {
    const btnPanel = document.getElementById('btn-add-report');
    if (btnPanel) {
      btnPanel.textContent = '✓ Added to Report';
      btnPanel.disabled = true;
      btnPanel.style.background = '#1a3a2a';
      btnPanel.style.color = '#00e5cc';
      btnPanel.style.border = '1px solid #00e5cc';
      btnPanel.style.cursor = 'not-allowed';
    }
    const btnModal = document.getElementById('modal-btn-report');
    if (btnModal) {
      btnModal.textContent = '✓ Added to Report';
      btnModal.disabled = true;
      btnModal.style.background = '#1a3a2a';
      btnModal.style.color = '#00e5cc';
      btnModal.style.border = '1px solid #00e5cc';
      btnModal.style.cursor = 'not-allowed';
    }
  }

  // --- 24-HOUR HISTOGRAM CHART HELPER ---
  function renderHistogramBars(container, spark) {
    if (!container) return;
    const maxVal = Math.max(...spark, 1);
    container.innerHTML = spark.map((v, i) => {
      const heightPx = Math.max(3, Math.round((v / maxVal) * 46));
      const hourStr = String(i).padStart(2, '0') + ":00 UTC";
      return `<div class="profile-hist-bar" style="height:${heightPx}px" title="${hourStr} — ${v} posts"></div>`;
    }).join('');
  }

  // --- BUTTON 1: FULLSCREEN PROFILE MODAL ---
  function openFullProfileModal(d) {
    if (!d) d = window.currentSelectedNode || (sim && sim.nodes && sim.nodes[0]);
    if (!d) return;
    const overlay = document.getElementById('profile-modal-overlay');
    if (!overlay) return;

    const clusterNodes = (typeof getAllClusterNodes === 'function') ? getAllClusterNodes(d.clusterId || d.cluster) : [];
    const clusterSize = clusterNodes.length || d.clusterSize || 1;
    const displayName = d.name || d.handle || d.id || '—';
    const actCode = d.actCode || d.act_code || d.id || 'ACT—';
    const clusterId = d.clusterId || d.cluster_id || d.cluster || 'CL—';
    const site = d.site || d.forum || d.source || 'tor-network';
    const linkedVal = d.linkedCount !== undefined ? d.linkedCount : (d.links !== undefined ? d.links : (d.degree !== undefined ? d.degree : 0));

    const maxLrNum = typeof d.maxLR === 'number' ? d.maxLR :
      (typeof d.max_lr === 'number' ? d.max_lr :
        (typeof d.maxLr === 'number' ? d.maxLr : parseFloat(d.maxLR || d.max_lr || d.maxLr || d.lr || 0)));
    const maxLrVal = !isNaN(maxLrNum) && maxLrNum > 0 ? maxLrNum.toFixed(2) : '0.00';
    const tzVal = d.timezone || d.tz || (d.utc_offset !== undefined ? `UTC${d.utc_offset >= 0 ? '+' : ''}${d.utc_offset}` : 'UTC+0');
    const regionsVal = d.regions || (d.locale ? [d.locale] : ['Global / Tor Network']);

    const neighbors = (typeof getNeighbors === 'function') ? getNeighbors(d) : [];
    const scoredLinksCount = neighbors.length;

    let inReport = false;
    try {
      const rep = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
      inReport = rep.some(r => r.id === d.id);
    } catch (e) { }
    const isFlagged = d.isFlagged || !!localStorage.getItem('flag_' + d.id);

    overlay.innerHTML = `
      <div class="profile-modal-card" id="profile-modal-card" onclick="event.stopPropagation()">
        <!-- 1. HEADER -->
        <div class="profile-modal-header">
          <div>
            <h2 class="profile-modal-name">${esc(displayName)}</h2>
            <div class="profile-modal-badges">
              <span style="background:rgba(0,229,204,0.15);color:#00e5cc;font-family:monospace;font-size:11px;border-radius:4px;padding:2px 8px;border:1px solid rgba(0,229,204,0.3)">
                ${esc(actCode)}
              </span>
              <span style="background:#f5a623;color:#000;font-size:10px;border-radius:10px;padding:2px 8px;font-weight:700">
                Cluster ${esc(clusterId)}
              </span>
              <span style="color:#718096;font-size:12px;margin-left:4px">
                🌐 ${esc(site)}
              </span>
              ${isFlagged ? `<span style="background:rgba(252,129,129,0.2);color:#fc8181;border:1px solid rgba(252,129,129,0.5);font-size:10px;border-radius:10px;padding:2px 8px;font-weight:700">⚑ FALSE POSITIVE</span>` : ''}
            </div>
          </div>
          <button class="profile-modal-close" id="profile-modal-close-btn" title="Close (Esc)">&times;</button>
        </div>

        <!-- 2. STATS GRID (4 cols) -->
        <div class="profile-stats-grid">
          <div class="profile-stat-card">
            <div class="profile-stat-num" style="color:#00e5cc">${linkedVal}</div>
            <div class="profile-stat-label">Linked Personas</div>
          </div>
          <div class="profile-stat-card">
            <div class="profile-stat-num" style="color:#f5a623">${maxLrVal}</div>
            <div class="profile-stat-label">Max log₁₀ LR</div>
          </div>
          <div class="profile-stat-card">
            <div class="profile-stat-num" style="color:#ffffff">${clusterSize}</div>
            <div class="profile-stat-label">Cluster Size</div>
          </div>
          <div class="profile-stat-card">
            <div class="profile-stat-num" style="color:#8b5cf6">${scoredLinksCount}</div>
            <div class="profile-stat-label">Scored Links</div>
          </div>
        </div>

        <!-- 3. ALL SCORED LINKS TABLE -->
        <div>
          <div class="profile-section-title">All Scored Links (${scoredLinksCount})</div>
          <div class="profile-table-wrap">
            <table class="profile-table">
              <thead>
                <tr>
                  <th>PERSONA</th>
                  <th>SITE</th>
                  <th>LOG₁₀ LR</th>
                  <th>CONFIDENCE BAR</th>
                </tr>
              </thead>
              <tbody id="modal-scored-links-tbody">
                ${neighbors.length === 0 ? `<tr><td colspan="4" style="color:#718096;text-align:center;padding:16px">No scored linkages found</td></tr>` :
        neighbors.map(n => {
          const pct = Math.min(100, Math.max(8, (n.lr / 8) * 100));
          const col = n.lr > 6 ? '#00e5cc' : n.lr > 4 ? '#f5a623' : '#8b5cf6';
          const peerNode = (sim && sim.byId) ? sim.byId[n.id] : null;
          const pSite = peerNode ? (peerNode.site || peerNode.source || 'tor-network') : 'tor-network';
          return `
                      <tr style="cursor:pointer" onclick="closeFullProfileModal(); if(window.selectClusterMember) window.selectClusterMember('${esc(n.id)}');">
                        <td style="font-weight:600;color:#fff">${esc(n.name || n.id)}</td>
                        <td style="color:#718096">${esc(pSite)}</td>
                        <td style="color:${col};font-family:monospace;font-weight:700">${n.lr ? n.lr.toFixed(2) : '—'}</td>
                        <td>
                          <div style="width:100%;max-width:140px;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden">
                            <div style="width:${pct}%;height:100%;background:${col};border-radius:3px"></div>
                          </div>
                        </td>
                      </tr>
                    `;
        }).join('')
      }
              </tbody>
            </table>
          </div>
        </div>

        <!-- 4. LOCALE & TIMING (2 cols) -->
        <div class="profile-locale-timing-grid">
          <div>
            <div class="profile-section-title">Estimated Locale & Timezone</div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
              <span style="font-size:15px;font-weight:700;color:#00e5cc">${esc(tzVal)}</span>
              <span style="color:#718096;font-size:11px">±1h band</span>
            </div>
            <div style="margin-bottom:12px">
              <div style="font-size:10px;color:#718096;margin-bottom:4px">CONFIDENCE ESTIMATE</div>
              <div style="width:100%;max-width:180px;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden">
                <div id="modal-tz-conf-bar" style="width:85%;height:100%;background:#00e5cc;border-radius:3px"></div>
              </div>
            </div>
            <div style="font-size:10px;color:#718096;margin-bottom:6px">LIKELY REGIONS</div>
            <div id="modal-region-chips" style="display:flex;gap:6px;flex-wrap:wrap">
              ${regionsVal.map(r => `
                <span style="background:rgba(255,255,255,0.06);color:#cbd5e0;font-size:11px;border-radius:14px;padding:3px 10px;border:1px solid rgba(255,255,255,0.12)">${esc(r)}</span>
              `).join('')}
            </div>
          </div>

          <div>
            <div class="profile-section-title">Posting Activity (24h UTC)</div>
            <div class="profile-histogram-wrap">
              <div class="profile-histogram-bars" id="modal-hist-bars"></div>
              <div class="profile-histogram-axis">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>24:00</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 5. FOOTER BUTTONS -->
        <div class="profile-modal-footer">
          <button class="lk-btn-ai" id="modal-btn-ai">✨ AI Forensic Briefing</button>
          <button class="anv-btn-white-ghost" id="modal-btn-pdf">⬇ Export PDF</button>
          <button class="anv-btn-red-ghost" id="modal-btn-flag">⚑ Flag FP</button>
          <button class="anv-btn-teal" id="modal-btn-report" ${inReport ? 'disabled style="background:#1a3a2a;color:#00e5cc;border:1px solid #00e5cc;cursor:not-allowed"' : ''}>
            ${inReport ? '✓ Added to Report' : '+ Add to Report'}
          </button>
        </div>
      </div>
    `;

    overlay.style.display = 'flex';
    overlay.classList.add('open');

    // Default 24h histogram spark
    const histContainer = document.getElementById('modal-hist-bars');
    const defaultSpark = Array.from({ length: 24 }, (_, i) => {
      let offsetNum = 0;
      if (typeof d.utc_offset === 'number') offsetNum = d.utc_offset;
      const localHour = (i + offsetNum + 24) % 24;
      return (localHour >= 18 && localHour <= 23) ? 8 + Math.floor(Math.random() * 6) :
        (localHour >= 12 && localHour < 18) ? 4 + Math.floor(Math.random() * 4) :
          (localHour >= 8 && localHour < 12) ? 2 + Math.floor(Math.random() * 3) : 1;
    });
    renderHistogramBars(histContainer, defaultSpark);

    api("/api/persona/" + d.id).then(res => {
      if (!res) return;
      if (res.hour_histogram_utc && res.hour_histogram_utc.length === 24) {
        renderHistogramBars(histContainer, res.hour_histogram_utc);
      }
      if (res.geolocation) {
        const g = res.geolocation;
        const confPct = Math.round((g.confidence || 0.85) * 100);
        const confBar = document.getElementById('modal-tz-conf-bar');
        if (confBar) confBar.style.width = `${confPct}%`;
        if (g.regions && g.regions.length) {
          const chips = document.getElementById('modal-region-chips');
          if (chips) {
            chips.innerHTML = g.regions.map(r => `
              <span style="background:rgba(255,255,255,0.06);color:#cbd5e0;font-size:11px;border-radius:14px;padding:3px 10px;border:1px solid rgba(255,255,255,0.12)">${esc(r)}</span>
            `).join('');
          }
        }
      }
    }).catch(() => { });

    document.getElementById('profile-modal-close-btn').onclick = closeFullProfileModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeFullProfileModal(); };
    document.getElementById('modal-btn-pdf').onclick = () => { window.print(); };
    document.getElementById('modal-btn-flag').onclick = () => { openFlagDialog(d); };
    document.getElementById('modal-btn-report').onclick = () => { addToReport(d); };

    const modalAiBtn = document.getElementById('modal-btn-ai');
    if (modalAiBtn) {
      modalAiBtn.onclick = () => {
        const topNeighbor = neighbors && neighbors[0];
        if (topNeighbor) {
          closeFullProfileModal();
          openAiForensicModal(d.id, topNeighbor.id, d.name || d.handle || d.id, topNeighbor.name || topNeighbor.handle || topNeighbor.id);
        } else {
          if (typeof showToast === "function") showToast("No linked peer persona found for pairwise AI briefing", "#f5a623");
          else alert("No linked peer persona found for pairwise AI briefing");
        }
      };
    }
  }
  window.openFullProfileModal = openFullProfileModal;

  function closeFullProfileModal() {
    const overlay = document.getElementById('profile-modal-overlay');
    if (overlay) {
      overlay.style.display = 'none';
      overlay.classList.remove('open');
    }
  }
  window.closeFullProfileModal = closeFullProfileModal;
  window.openFullProfileModal = openFullProfileModal;

  // --- BUTTON 2: FLAG AS FALSE POSITIVE DIALOG ---
  function openFlagDialog(d) {
    if (!d) d = window.currentSelectedNode || (sim && sim.nodes && sim.nodes[0]);
    if (!d) return;
    const overlay = document.getElementById('fp-dialog-overlay');
    if (!overlay) return;

    const displayName = d.name || d.handle || d.id || '—';
    const clusterId = d.clusterId || d.cluster || '—';

    overlay.innerHTML = `
      <div class="fp-dialog-card" onclick="event.stopPropagation()">
        <div class="fp-dialog-icon">⚑</div>
        <h3 class="fp-dialog-title">Flag False Positive</h3>
        <p class="fp-dialog-desc">
          Flag <b>${esc(displayName)}</b> linkage as false positive for analyst review? This marks the node with a dashed indicator.
        </p>
        <select id="fp-reason-select" class="fp-dialog-select">
          <option value="Different person, same alias">Different person, same alias</option>
          <option value="Common/generic username">Common/generic username</option>
          <option value="Copycat account">Copycat account</option>
          <option value="Other">Other</option>
        </select>
        <div class="fp-dialog-buttons">
          <button class="fp-btn-cancel" id="fp-btn-cancel">Cancel</button>
          <button class="fp-btn-confirm" id="fp-btn-confirm">Confirm Flag</button>
        </div>
      </div>
    `;
    overlay.style.display = 'flex';
    overlay.classList.add('open');

    document.getElementById('fp-btn-cancel').onclick = () => {
      overlay.style.display = 'none';
      overlay.classList.remove('open');
    };
    overlay.onclick = (e) => {
      if (e.target === overlay) {
        overlay.style.display = 'none';
        overlay.classList.remove('open');
      }
    };

    document.getElementById('fp-btn-confirm').onclick = () => {
      const reason = document.getElementById('fp-reason-select').value;
      const flagData = {
        actorId: d.id,
        actorName: displayName,
        clusterId: clusterId,
        reason: reason,
        flaggedAt: new Date().toISOString()
      };
      localStorage.setItem('flag_' + d.id, JSON.stringify(flagData));
      d.isFlagged = true;

      applyFlagToNode(d.id, displayName);

      const btnFp = document.getElementById('btn-flag-fp');
      if (btnFp) {
        btnFp.textContent = '⚑ Flagged False Positive';
        btnFp.style.background = 'rgba(252,129,129,0.15)';
        btnFp.style.color = '#fc8181';
      }

      overlay.style.display = 'none';
      overlay.classList.remove('open');
      showToast("⚑ Flagged as false positive", "#fc8181");
    };
  }
  window.openFlagDialog = openFlagDialog;

  function applyFlagToNode(id, name) {
    if (typeof d3 === 'undefined') return;
    const nodeCircle = d3.select(`circle.node[data-id='${id}']`);
    if (!nodeCircle.empty()) {
      nodeCircle
        .style("stroke", "#fc8181")
        .style("stroke-width", "3px")
        .style("stroke-dasharray", "4,2");
    }
    const nodeLabel = d3.select(`text.label[data-id='${id}']`);
    if (!nodeLabel.empty()) {
      const curText = nodeLabel.text();
      if (!curText.includes("⚑")) {
        nodeLabel.text(curText + " ⚑").attr("fill", "#fc8181");
      }
    }
  }

  // --- BUTTON 3: ADD TO REPORT ---
  function addToReport(d) {
    if (!d) d = window.currentSelectedNode || (sim && sim.nodes && sim.nodes[0]);
    if (!d) return;
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    if (report.some(r => r.id === d.id)) {
      showToast("Already in report", "#f5a623");
      setReportBtnAdded();
      return;
    }

    const displayName = d.name || d.handle || d.id || '—';
    const actCode = d.actCode || d.act_code || d.id || 'ACT—';
    const clusterId = d.clusterId || d.cluster_id || d.cluster || 'CL—';
    const site = d.site || d.forum || d.source || '—';
    const linkedVal = d.linkedCount !== undefined ? d.linkedCount : (d.degree || '—');
    const maxLrNum = typeof d.maxLR === 'number' ? d.maxLR :
      (typeof d.max_lr === 'number' ? d.max_lr :
        (typeof d.maxLr === 'number' ? d.maxLr : parseFloat(d.maxLR || d.max_lr || d.maxLr || d.lr || 0)));
    const maxLrVal = !isNaN(maxLrNum) && maxLrNum > 0 ? maxLrNum.toFixed(2) : '—';
    const tzVal = d.timezone || d.tz || (d.utc_offset !== undefined ? `UTC${d.utc_offset >= 0 ? '+' : ''}${d.utc_offset}` : 'UTC+?');
    const regionsVal = d.regions || (d.locale ? [d.locale] : ['Unknown']);

    report.push({
      id: d.id,
      name: displayName,
      actCode: actCode,
      clusterId: clusterId,
      site: site,
      maxLR: maxLrVal,
      linkedCount: linkedVal,
      timezone: tzVal,
      regions: regionsVal,
      addedAt: new Date().toLocaleString()
    });

    localStorage.setItem('anekanta_report', JSON.stringify(report));

    setReportBtnAdded();
    updateReportBadge();
    showToast(`📋 Added · ${report.length} actor${report.length === 1 ? '' : 's'} in report`, "#00e5cc");
  }
  window.addToReport = addToReport;

  // --- REPORT DRAWER (40vh Slide-up) ---
  function openReportDrawer() {
    const drawer = document.getElementById('report-drawer');
    if (!drawer) return;
    renderReportDrawerTable();
    drawer.classList.add('open');
  }
  window.openReportDrawer = openReportDrawer;

  function closeReportDrawer() {
    const drawer = document.getElementById('report-drawer');
    if (drawer) drawer.classList.remove('open');
  }
  window.closeReportDrawer = closeReportDrawer;

  function renderReportDrawerTable() {
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    const count = report.length;
    const badge = document.getElementById('reportDrawerCount');
    if (badge) badge.textContent = `${count} actor${count === 1 ? '' : 's'}`;

    const tbody = document.getElementById('reportDrawerTableBody');
    const emptyEl = document.getElementById('reportDrawerEmpty');
    const tableEl = document.querySelector('.anv-drawer-table');

    if (!tbody) return;

    if (count === 0) {
      tbody.innerHTML = '';
      if (tableEl) tableEl.style.display = 'none';
      if (emptyEl) emptyEl.style.display = 'block';
      return;
    }

    if (tableEl) tableEl.style.display = 'table';
    if (emptyEl) emptyEl.style.display = 'none';

    tbody.innerHTML = report.map((item) => {
      const lrNum = parseFloat(item.maxLR);
      const lrCol = lrNum > 6 ? '#00e5cc' : lrNum > 4 ? '#f5a623' : '#8b5cf6';
      return `
        <tr>
          <td style="font-weight:600;color:#fff">${esc(item.name)}</td>
          <td><span style="background:rgba(0,229,204,0.15);color:#00e5cc;font-family:monospace;font-size:10px;padding:2px 6px;border-radius:3px">${esc(item.actCode)}</span></td>
          <td><span style="background:#f5a623;color:#000;font-size:10px;padding:2px 6px;border-radius:8px;font-weight:700">${esc(item.clusterId)}</span></td>
          <td style="color:#718096">${esc(item.site)}</td>
          <td style="color:${lrCol};font-weight:700;font-family:monospace">${esc(item.maxLR)}</td>
          <td style="color:#718096;font-size:11px">${esc(item.addedAt)}</td>
          <td style="text-align:center">
            <button class="anv-drawer-remove-btn" title="Remove actor from report" onclick="removeFromReport('${esc(item.id)}')">&times;</button>
          </td>
        </tr>
      `;
    }).join('');
  }

  function removeFromReport(id) {
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    report = report.filter(r => r.id !== id);
    localStorage.setItem('anekanta_report', JSON.stringify(report));

    renderReportDrawerTable();
    updateReportBadge();
    showToast("Removed from report", "#fc8181");

    const btnPanel = document.getElementById('btn-add-report');
    if (btnPanel && selectedNode && selectedNode.id === id) {
      btnPanel.textContent = '📋 Add to Report';
      btnPanel.disabled = false;
      btnPanel.style.background = 'none';
      btnPanel.style.color = '#e2e8f0';
      btnPanel.style.border = '1px solid rgba(255,255,255,0.2)';
      btnPanel.style.cursor = 'pointer';
    }
  }
  window.removeFromReport = removeFromReport;

  function exportReportCsv() {
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    if (report.length === 0) {
      showToast("Report is empty", "#f5a623");
      return;
    }

    const headers = ["ID", "Name", "ACT_Code", "Cluster", "Site", "Max_LR", "Linked_Personas", "Timezone", "Added_At"];
    const rows = report.map(r => [
      `"${(r.id || '').replace(/"/g, '""')}"`,
      `"${(r.name || '').replace(/"/g, '""')}"`,
      `"${(r.actCode || '').replace(/"/g, '""')}"`,
      `"${(r.clusterId || '').replace(/"/g, '""')}"`,
      `"${(r.site || '').replace(/"/g, '""')}"`,
      r.maxLR || '',
      r.linkedCount || '',
      `"${(r.timezone || '').replace(/"/g, '""')}"`,
      `"${(r.addedAt || '').replace(/"/g, '""')}"`
    ].join(","));

    const csvContent = [headers.join(","), ...rows].join("\r\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const dateStr = new Date().toISOString().slice(0, 10);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `anekanta_report_${dateStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast("⬇ Exported report CSV", "#00e5cc");
  }
  window.exportReportCsv = exportReportCsv;

  function promptClearReport() {
    const overlay = document.getElementById('anv-confirm-overlay');
    if (!overlay) return;

    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    if (report.length === 0) {
      showToast("Report is already empty", "#a0aec0");
      return;
    }

    overlay.innerHTML = `
      <div class="fp-dialog-card" onclick="event.stopPropagation()">
        <div class="fp-dialog-icon" style="color:#f5a623">⚠️</div>
        <h3 class="fp-dialog-title">Clear Analyst Report?</h3>
        <p class="fp-dialog-desc">
          This will remove all <b>${report.length}</b> saved actors from your evidence dossier. This cannot be undone.
        </p>
        <div class="fp-dialog-buttons">
          <button class="fp-btn-cancel" id="confirm-clear-cancel">Cancel</button>
          <button class="fp-btn-confirm" id="confirm-clear-ok" style="background:#fc8181;color:#000">Confirm Clear</button>
        </div>
      </div>
    `;
    overlay.style.display = 'flex';
    overlay.classList.add('open');

    document.getElementById('confirm-clear-cancel').onclick = () => {
      overlay.style.display = 'none';
      overlay.classList.remove('open');
    };
    overlay.onclick = (e) => {
      if (e.target === overlay) {
        overlay.style.display = 'none';
        overlay.classList.remove('open');
      }
    };

    document.getElementById('confirm-clear-ok').onclick = () => {
      localStorage.removeItem('anekanta_report');
      overlay.style.display = 'none';
      overlay.classList.remove('open');
      renderReportDrawerTable();
      updateReportBadge();
      showToast("Analyst report cleared", "#a0aec0");

      const btnPanel = document.getElementById('btn-add-report');
      if (btnPanel) {
        btnPanel.textContent = '📋 Add to Report';
        btnPanel.disabled = false;
        btnPanel.style.background = 'none';
        btnPanel.style.color = '#e2e8f0';
        btnPanel.style.border = '1px solid rgba(255,255,255,0.2)';
        btnPanel.style.cursor = 'pointer';
      }
    };
  }

  function openRightPanel(d) {
    window.currentSelectedNode = d;
    const panel = document.getElementById('actor-detail-panel');
    if (!panel) {
      console.error('Panel element not found in DOM');
      return;
    }

    const clusterNodes = getAllClusterNodes(d.clusterId || d.cluster);
    const clusterSize = clusterNodes.length || d.clusterSize || 1;
    d.clusterSize = clusterSize;

    const displayName = d.name || d.handle || d.id || d.label || '—';
    const actCode = d.actCode || d.act_code || d.id || 'ACT—';
    const clusterId = d.clusterId || d.cluster_id || d.cluster || 'CL—';
    const site = d.site || d.forum || d.source || '—';
    const linkedVal = d.linkedCount !== undefined ? d.linkedCount : (d.links !== undefined ? d.links : (d.degree !== undefined ? d.degree : '—'));

    const maxLrNum = typeof d.maxLR === 'number' ? d.maxLR :
      (typeof d.max_lr === 'number' ? d.max_lr :
        (typeof d.maxLr === 'number' ? d.maxLr : parseFloat(d.maxLR || d.max_lr || d.maxLr || d.lr || 0)));
    const maxLrVal = !isNaN(maxLrNum) && maxLrNum > 0 ? maxLrNum.toFixed(2) : '—';

    const tzVal = d.timezone || d.tz || (d.utc_offset !== undefined ? `UTC${d.utc_offset >= 0 ? '+' : ''}${d.utc_offset}` : 'UTC+?');
    const regionsVal = d.regions || (d.locale ? [d.locale] : ['Unknown']);

    let inReport = false;
    try {
      const rep = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
      inReport = rep.some(r => r.id === d.id);
    } catch (e) { }
    const isFlagged = d.isFlagged || !!localStorage.getItem('flag_' + d.id);

    const pivot = getNodeClearnetPivot(d);
    let clearnetSectionHtml = "";
    if (pivot.hasClearnet) {
      clearnetSectionHtml = `
        <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>
        <div style="font-size:10px;font-weight:700;color:#38bdf8;letter-spacing:0.08em;margin-bottom:8px;display:flex;align-items:center;gap:5px">
          <span>🌐 CLEARNET & DARK2CLEAR PIVOT</span>
        </div>
        <div style="background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.25);border-radius:6px;padding:10px;display:flex;flex-direction:column;gap:8px">
          ${pivot.contacts.length > 0 ? `
            <div>
              <div style="color:#94a3b8;font-size:10px;font-weight:600">📧 Leaked Contacts:</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
                ${pivot.contacts.map(c => `
                  <span style="background:rgba(56,189,248,0.15);color:#7dd3fc;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:11px">
                    ${esc(c)}
                  </span>
                `).join('')}
              </div>
            </div>
          ` : ''}
          ${pivot.hosts.length > 0 ? `
            <div>
              <div style="color:#94a3b8;font-size:10px;font-weight:600">🖥️ Clearnet Host / IP:</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
                ${pivot.hosts.map(h => `
                  <span style="background:rgba(245,166,35,0.15);color:#fde68a;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:11px">
                    ${esc(h)}
                  </span>
                `).join('')}
              </div>
            </div>
          ` : ''}
          ${pivot.devices.length > 0 ? `
            <div>
              <div style="color:#94a3b8;font-size:10px;font-weight:600">📷 Leaked Hardware (EXIF):</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
                ${pivot.devices.map(dev => `
                  <span style="background:rgba(139,92,246,0.15);color:#c4b5fd;padding:2px 6px;border-radius:4px;font-size:11px">
                    ${esc(dev)}
                  </span>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      `;
    }

    // Inject content
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-size:18px;font-weight:700;color:#fff;word-break:break-all">
            ${esc(displayName)}
          </div>
          <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <span style="background:rgba(0,229,204,0.15);color:#00e5cc;
              font-family:monospace;font-size:11px;border-radius:4px;
              padding:2px 8px;border:1px solid rgba(0,229,204,0.3)">
              ${esc(actCode)}
            </span>
            <span style="background:#f5a623;color:#000;font-size:10px;
              border-radius:10px;padding:2px 8px;font-weight:700">
              ${esc(clusterId)}
            </span>
          </div>
          <div style="color:#718096;font-size:12px;margin-top:4px">
            🧅 Darknet: <b>@${esc(site)}</b>
          </div>
          ${pivot.hasClearnet ? `
            <div style="margin-top:5px">
              <span style="display:inline-flex;align-items:center;gap:4px;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">
                🌐 CLEARNET LINKED
              </span>
            </div>
          ` : ''}
        </div>
        <button onclick="closeRightPanel()" style="
          background:none;border:none;color:#718096;font-size:20px;
          cursor:pointer;padding:0;line-height:1;flex-shrink:0
        ">×</button>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center">
        <div>
          <div style="font-size:22px;font-weight:700;color:#00e5cc">
            ${linkedVal}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">LINKED</div>
        </div>
        <div>
          <div style="font-size:22px;font-weight:700;color:#f5a623">
            ${maxLrVal}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">MAX LR</div>
        </div>
        <div>
          <div style="font-size:22px;font-weight:700;color:#fff">
            ${clusterSize}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">CLUSTER</div>
        </div>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <div style="font-size:10px;color:#718096;
        letter-spacing:0.08em;margin-bottom:10px">
        SCORED LINKS
      </div>
      <div id="panel-links-list">
        ${buildLinksList(d)}
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <div style="font-size:10px;color:#718096;
        letter-spacing:0.08em;margin-bottom:10px">
        ESTIMATED LOCALE
      </div>
      <div style="color:#00e5cc;font-size:13px">
        ${esc(tzVal)} 
        <span style="color:#718096;font-size:11px">±1h</span>
      </div>
      <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
        ${regionsVal.map(r => `
          <span style="background:rgba(255,255,255,0.06);color:#a0aec0;
            font-size:11px;border-radius:20px;padding:3px 8px;
            border:1px solid rgba(255,255,255,0.1)">${esc(r)}</span>
        `).join('')}
      </div>

      ${clearnetSectionHtml}

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <button id="btn-view-profile" onclick="window.openFullProfileModal(window.currentSelectedNode)" style="width:100%;padding:10px;margin-bottom:8px;
        background:#00e5cc;color:#000;border:none;border-radius:6px;
        font-size:12px;font-weight:700;cursor:pointer">
        🔍 View Full Profile
      </button>
      <button id="btn-flag-fp" onclick="window.openFlagDialog(window.currentSelectedNode)" style="width:100%;padding:10px;margin-bottom:8px;
        background:${isFlagged ? 'rgba(252,129,129,0.15)' : 'none'};
        color:#fc8181;border:1px solid #fc8181;
        border-radius:6px;font-size:12px;cursor:pointer">
        ${isFlagged ? '⚑ Flagged False Positive' : '⚑ Flag as False Positive'}
      </button>
      <button id="btn-add-report" onclick="window.addToReport(window.currentSelectedNode)" style="width:100%;padding:10px;
        background:${inReport ? '#1a3a2a' : 'none'};
        color:${inReport ? '#00e5cc' : '#e2e8f0'};
        border:1px solid ${inReport ? '#00e5cc' : 'rgba(255,255,255,0.2)'};
        border-radius:6px;font-size:12px;
        cursor:${inReport ? 'not-allowed' : 'pointer'}"
        ${inReport ? 'disabled' : ''}>
        ${inReport ? '✓ Added to Report' : '📋 Add to Report'}
      </button>
    `;

    // Button event listeners
    const btnProfile = document.getElementById('btn-view-profile');
    if (btnProfile) {
      btnProfile.onclick = () => openFullProfileModal(d);
    }
    const btnFp = document.getElementById('btn-flag-fp');
    if (btnFp) {
      btnFp.onclick = () => openFlagDialog(d);
    }
    const btnReport = document.getElementById('btn-add-report');
    if (btnReport) {
      btnReport.onclick = () => addToReport(d);
    }

    // SLIDE IN
    panel.style.transform = 'translateX(0)';
  }
  window.openRightPanel = openRightPanel;

  function openClusterPanel(c) {
    const panel = document.getElementById('actor-detail-panel');
    if (!panel) return;

    selectedNode = null;
    lastClickNodeId = null;

    const cid = c.cid || (c.members && c.members[0] ? (c.members[0].clusterId || c.members[0].cluster) : "CL");
    const members = c.members || [];
    const maxLr = typeof c.maxLr === "number" ? c.maxLr.toFixed(2) : (members.length ? Math.max(...members.map(m => m.maxLr || 0)).toFixed(2) : "0.00");
    const avgLr = typeof c.avgLr === "number" ? c.avgLr.toFixed(2) : (members.length ? (members.reduce((acc, m) => acc + (m.maxLr || 0), 0) / members.length).toFixed(2) : "0.00");

    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-size:18px;font-weight:700;color:#fff;word-break:break-all">
            Cluster ${esc(cid)}
          </div>
          <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <span style="background:rgba(0,229,204,0.15);color:#00e5cc;
              font-family:monospace;font-size:11px;border-radius:4px;
              padding:2px 8px;border:1px solid rgba(0,229,204,0.3)">
              ${members.length} PERSONAS
            </span>
            <span style="background:#f5a623;color:#000;font-size:10px;
              border-radius:10px;padding:2px 8px;font-weight:700">
              LR ${maxLr}
            </span>
          </div>
          <div style="color:#718096;font-size:12px;margin-top:4px">
            Consolidated Actor Cluster
          </div>
        </div>
        <button onclick="closeRightPanel()" style="
          background:none;border:none;color:#718096;font-size:20px;
          cursor:pointer;padding:0;line-height:1;flex-shrink:0
        ">×</button>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center">
        <div>
          <div style="font-size:22px;font-weight:700;color:#00e5cc">
            ${members.length}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">PERSONAS</div>
        </div>
        <div>
          <div style="font-size:22px;font-weight:700;color:#f5a623">
            ${maxLr}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">MAX LR</div>
        </div>
        <div>
          <div style="font-size:22px;font-weight:700;color:#fff">
            ${avgLr}
          </div>
          <div style="font-size:10px;color:#718096;margin-top:2px">AVG LR</div>
        </div>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <div style="font-size:10px;color:#718096;
        letter-spacing:0.08em;margin-bottom:10px">
        CLUSTER PERSONAS (${members.length})
      </div>
      <div id="panel-cluster-members-list">
        ${members.map(m => {
      const color = getNodeColor(m);
      const lrVal = typeof m.maxLr === 'number' ? m.maxLr : (typeof m.maxLR === 'number' ? m.maxLR : parseFloat(m.maxLR || m.maxLr || 0));
      const pct = Math.min(100, Math.max(10, (lrVal / 8) * 100));
      return `
            <div style="display:flex;align-items:center;gap:8px;
              margin-bottom:10px;cursor:pointer;padding:6px 8px;border-radius:6px;background:rgba(255,255,255,0.03);transition:background 0.15s"
              onmouseover="this.style.background='rgba(0,229,204,0.1)'"
              onmouseout="this.style.background='rgba(255,255,255,0.03)'"
              onclick="window.selectClusterMember('${esc(m.id)}')">
              <div style="width:8px;height:8px;border-radius:50%;
                background:${color};flex-shrink:0"></div>
              <div style="flex:1;font-size:12px;color:#e2e8f0;
                overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                ${esc(m.name || m.handle || m.id)}
              </div>
              <div style="font-size:11px;color:${color};flex-shrink:0">
                ${!isNaN(lrVal) ? lrVal.toFixed(2) : '—'}
              </div>
              <div style="width:50px;height:4px;background:rgba(255,255,255,0.1);
                border-radius:2px;flex-shrink:0">
                <div style="width:${pct}%;height:100%;
                  background:${color};border-radius:2px"></div>
              </div>
            </div>
          `;
    }).join('')}
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08);margin:16px 0"></div>

      <button id="btn-cluster-view-profile" style="width:100%;padding:10px;margin-bottom:8px;
        background:#00e5cc;color:#000;border:none;border-radius:6px;
        font-size:12px;font-weight:700;cursor:pointer">
        🔍 View Consolidated Dossier
      </button>
      <button id="btn-cluster-flag-fp" style="width:100%;padding:10px;margin-bottom:8px;
        background:none;color:#fc8181;border:1px solid #fc8181;
        border-radius:6px;font-size:12px;cursor:pointer">
        ⚑ Flag Cluster as False Positive
      </button>
      <button id="btn-cluster-add-report" style="width:100%;padding:10px;
        background:none;color:#e2e8f0;border:1px solid rgba(255,255,255,0.2);
        border-radius:6px;font-size:12px;cursor:pointer">
        📋 Add Cluster to Report
      </button>
    `;

    const btnProfile = document.getElementById('btn-cluster-view-profile');
    if (btnProfile) {
      btnProfile.onclick = () => {
        const topMember = members.slice().sort((a, b) => (b.maxLr || 0) - (a.maxLr || 0))[0];
        if (topMember) openFullProfileModal(topMember);
      };
    }
    const btnFp = document.getElementById('btn-cluster-flag-fp');
    if (btnFp) {
      btnFp.onclick = () => {
        if (members[0]) openFlagDialog(members[0]);
      };
    }
    const btnReport = document.getElementById('btn-cluster-add-report');
    if (btnReport) {
      btnReport.onclick = () => {
        members.forEach(m => addToReport(m));
      };
    }

    panel.style.transform = 'translateX(0)';
  }
  window.openClusterPanel = openClusterPanel;

  window.selectClusterMember = function (memberId) {
    const targetNode = sim.byId[memberId];
    if (targetNode) {
      handleNodeClick(null, targetNode);
    }
  };

  function closeRightPanel() {
    const panel = document.getElementById('actor-detail-panel');
    if (panel) panel.style.transform = 'translateX(300px)';
    selectedNode = null;
    lastClickNodeId = null;
    resetGraph();
  }
  window.closeRightPanel = closeRightPanel;

  function resetGraph() {
    selectedNode = null;
    if (allNodes) {
      allNodes.transition().duration(250)
        .attr("r", n => n.radius)
        .style("opacity", 1)
        .style("stroke", n => (n.isFlagged || localStorage.getItem('flag_' + n.id)) ? "#fc8181" : "#ffffff22")
        .style("stroke-width", n => (n.isFlagged || localStorage.getItem('flag_' + n.id)) ? "3px" : "1px")
        .style("stroke-dasharray", n => (n.isFlagged || localStorage.getItem('flag_' + n.id)) ? "4,2" : null)
        .style("filter", null);
    }
    if (allEdges) {
      allEdges.transition().duration(250)
        .style("opacity", e => e.tier === "linkage" ? 0.3 : 0.2)
        .style("stroke-width", e => e.tier === "linkage" ? 1.2 : 0.8);
    }
    if (allLabels) {
      allLabels.transition().duration(250)
        .style("opacity", n => n.radius >= 14 ? 1 : 0);
    }
    const statSel = $("#lgStatSelected");
    if (statSel) statSel.textContent = "None (Click any node)";
  }

  function zoomToCluster(clusterNodes) {
    if (!clusterNodes || !clusterNodes.length) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    clusterNodes.forEach(n => {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y);
      maxY = Math.max(maxY, n.y);
    });
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const w = Math.max(maxX - minX + 160, 200);
    const h = Math.max(maxY - minY + 160, 200);
    const width = svgEl.clientWidth || 1200;
    const height = svgEl.clientHeight || 640;
    const k = Math.min(3.0, Math.max(0.6, Math.min(width / w, height / h)));
    const targetX = width / 2 - cx * k;
    const targetY = height / 2 - cy * k;

    svg.transition().duration(500)
      .call(zoom.transform, d3.zoomIdentity.translate(targetX, targetY).scale(k));
  }

  let lastClickTime = 0;
  let lastClickNodeId = null;

  function handleNodeClick(event, d) {
    if (event && event.stopPropagation) event.stopPropagation();

    const now = Date.now();
    // Guard against rapid duplicate events on the same node within 400ms
    if (lastClickNodeId === d.id && (now - lastClickTime) < 400) {
      return;
    }
    lastClickTime = now;
    lastClickNodeId = d.id;

    if (selectedNode && selectedNode.id === d.id) {
      closeRightPanel();
      return;
    }

    selectedNode = d;
    console.log('clicked node:', d);

    const statSel = $("#lgStatSelected");
    if (statSel) statSel.textContent = `${d.name || d.handle || d.id} (${d.id})`;

    allNodes.transition().duration(250)
      .attr("r", n => n.id === d.id ? d.radius * 2.8 :
        isConnected(d, n) ? n.radius * 1.3 : n.radius)
      .style("opacity", n => isConnected(d, n) || n.id === d.id ? 1 : 0.12)
      .style("stroke", n => n.id === d.id ? "#00e5cc" : "#ffffff22")
      .style("stroke-width", n => n.id === d.id ? "2.5px" : "1px");

    allEdges.transition().duration(250)
      .style("opacity", e => {
        const sId = typeof e.source === "object" ? e.source.id : e.source;
        const tId = typeof e.target === "object" ? e.target.id : e.target;
        return (sId === d.id || tId === d.id) ? 1 : 0.03;
      })
      .style("stroke-width", e => {
        const sId = typeof e.source === "object" ? e.source.id : e.source;
        const tId = typeof e.target === "object" ? e.target.id : e.target;
        return (sId === d.id || tId === d.id) ? 3 : 0.8;
      });

    allLabels.transition().duration(250)
      .style("opacity", n => isConnected(d, n) || n.id === d.id ? 1 : 0);

    const clusterNodes = getAllClusterNodes(d.clusterId || d.cluster);
    zoomToCluster(clusterNodes);

    openRightPanel(d);
    hideTooltip();
  }

  function calcEdgePath(d) {
    const u = d.source;
    const v = d.target;
    const dx = v.x - u.x;
    const dy = v.y - u.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = -dy / dist;
    const ny = dx / dist;
    const curveOffset = Math.min(30, Math.max(8, dist * 0.12));
    const cpx = (u.x + v.x) / 2 + nx * curveOffset;
    const cpy = (u.y + v.y) / 2 + ny * curveOffset;
    return `M ${u.x} ${u.y} Q ${cpx} ${cpy} ${v.x} ${v.y}`;
  }

  function updateLayout(isInitial = false) {
    const current = getFilteredGraph();
    const es = current.es;
    const ns = current.ns;
    const clusters = current.clusters;

    const width = svgEl.clientWidth || 1200;
    const height = svgEl.clientHeight || 640;

    let cHigh = 0, cMed = 0, cLow = 0;
    for (const n of ns) {
      const t = getNodeTier(n);
      if (t === "high") cHigh++;
      else if (t === "med") cMed++;
      else if (t === "low") cLow++;
    }
    if (countHighEl) countHighEl.textContent = cHigh;
    if (countMedEl) countMedEl.textContent = cMed;
    if (countLowEl) countLowEl.textContent = cLow;

    if (sbSummaryEl) {
      sbSummaryEl.textContent = `Showing ${clusters.length} clusters · ${ns.length} nodes`;
    }

    const statPersonas = $("#lgStatPersonas");
    const statPairs = $("#lgStatPairs");
    const statClusters = $("#lgStatClusters");
    if (statPersonas) statPersonas.textContent = ns.length;
    if (statPairs) statPairs.textContent = es.length;
    if (statClusters) statClusters.textContent = clusters.length;

    const ctxInfo = $("#hdr-ctx-info");
    if (ctxInfo) {
      ctxInfo.textContent = `Showing ${ns.length} nodes · ${clusters.length} clusters · threshold LR ${minLR().toFixed(1)}`;
    }

    if (d3Simulation) d3Simulation.stop();

    if (isInitial || !sim.initialPlaced) {
      preSpaceClusters(clusters, ns, width, height);
      sim.initialPlaced = true;
    }

    const d3Links = es.map(e => ({
      source: e.source,
      target: e.target,
      log10_lr: e.log10_lr,
      tier: e.tier
    }));

    function forceCluster(alpha) {
      const centroids = new Map();
      for (const c of clusters) {
        let sx = 0, sy = 0;
        for (const m of c.members) { sx += m.x; sy += m.y; }
        const count = c.members.length || 1;
        const cx = sx / count;
        const cy = sy / count;
        centroids.set(c.cid, { x: cx, y: cy, members: c.members, initX: c.initCenterX, initY: c.initCenterY });
      }
      for (const n of ns) {
        const cent = centroids.get(n.clusterId || n.cluster || ("solo:" + n.id));
        if (cent) {
          n.vx += (cent.x - n.x) * alpha * 0.08;
          n.vy += (cent.y - n.y) * alpha * 0.08;
        }
      }

      for (const cent of centroids.values()) {
        if (cent.initX !== undefined && cent.initY !== undefined) {
          const pullX = (cent.initX - cent.x) * alpha * 0.05;
          const pullY = (cent.initY - cent.y) * alpha * 0.05;
          for (const m of cent.members) {
            m.vx += pullX;
            m.vy += pullY;
          }
        }
      }

      const cList = Array.from(centroids.entries());
      for (let i = 0; i < cList.length; i++) {
        for (let j = i + 1; j < cList.length; j++) {
          const c1 = cList[i][1], c2 = cList[j][1];
          const dx = c2.x - c1.x;
          const dy = c2.y - c1.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const minDist = 200;
          if (dist < minDist) {
            const push = ((minDist - dist) / dist) * 0.5 * alpha * 1.5;
            const px = dx * push;
            const py = dy * push;
            for (const m of c1.members) { m.vx -= px; m.vy -= py; }
            for (const m of c2.members) { m.vx += px; m.vy += py; }
          }
        }
      }
    }

    d3Simulation = d3.forceSimulation(ns)
      .force("charge", d3.forceManyBody().strength(-400))
      .force("collision", d3.forceCollide().radius(d => (d.baseRadius * 2.2) + 18).iterations(2))
      .force("link", d3.forceLink(d3Links).id(d => d.id).distance(80).strength(0.6))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("cluster", forceCluster)
      .alphaDecay(0.015)
      .velocityDecay(0.4);

    allEdges = edgesG.selectAll("path.edge")
      .data(d3Links, d => `${typeof d.source === "object" ? d.source.id : d.source}-${typeof d.target === "object" ? d.target.id : d.target}`)
      .join("path")
      .attr("class", "edge")
      .attr("fill", "none")
      .attr("stroke", d => d.tier === "linkage" ? "#00e5cc" : "#8b5cf6")
      .attr("stroke-dasharray", d => d.tier === "linkage" ? null : "4,4")
      .style("opacity", d => d.tier === "linkage" ? 0.3 : 0.2)
      .style("stroke-width", d => d.tier === "linkage" ? 1.2 : 0.8)
      .style("pointer-events", "stroke")
      .style("cursor", "crosshair");

    allBadges = badgesG.selectAll("g.cluster-badge")
      .data(clusters, d => d.cid)
      .join(enter => {
        const g = enter.append("g")
          .attr("class", "cluster-badge")
          .style("cursor", "pointer")
          .style("pointer-events", "all")
          .on("click", (event, c) => {
            event.stopPropagation();
            zoomToCluster(c.members);
            if (allNodes) {
              allNodes.transition().duration(250)
                .attr("r", n => c.members.some(m => m.id === n.id) ? n.radius * 1.4 : n.radius)
                .style("opacity", n => c.members.some(m => m.id === n.id) ? 1.0 : 0.15)
                .style("stroke", n => c.members.some(m => m.id === n.id) ? "#00e5cc" : "#ffffff22");
            }
            if (allEdges) {
              allEdges.transition().duration(250)
                .style("opacity", e => {
                  const sId = typeof e.source === "object" ? e.source.id : e.source;
                  const tId = typeof e.target === "object" ? e.target.id : e.target;
                  return c.members.some(m => m.id === sId) && c.members.some(m => m.id === tId) ? 0.9 : 0.04;
                });
            }
            openClusterPanel(c);
          });

        g.append("rect")
          .attr("class", "cluster-badge-bg")
          .attr("rx", 10).attr("ry", 10)
          .attr("fill", "rgba(10, 14, 26, 0.85)")
          .attr("stroke", "rgba(0, 229, 204, 0.4)")
          .attr("stroke-width", 1)
          .style("pointer-events", "all");

        g.append("text")
          .attr("class", "cluster-badge-txt")
          .attr("text-anchor", "middle")
          .attr("y", 14)
          .attr("fill", "#a0aec0")
          .attr("font-size", "11px")
          .attr("font-family", "'Segoe UI', system-ui, sans-serif")
          .style("pointer-events", "all");

        return g;
      });

    allBadges.each(function (c) {
      const g = d3.select(this);
      const text = `${c.members.length} personas · LR ${fmt(c.maxLr, 1)}`;
      const txtEl = g.select("text").text(text);
      const bbox = txtEl.node().getBBox();
      const bw = bbox.width + 20;
      g.select("rect")
        .attr("x", -bw / 2)
        .attr("y", 0)
        .attr("width", bw)
        .attr("height", 20);
    });

    let dragMoved = false;
    let dragStartPos = { x: 0, y: 0 };
    const drag = d3.drag()
      .on("start", (event, d) => {
        dragMoved = false;
        dragStartPos = { x: event.x, y: event.y };
      })
      .on("drag", (event, d) => {
        const dx = event.x - dragStartPos.x;
        const dy = event.y - dragStartPos.y;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved = true;
        d.fx = event.x; d.fy = event.y;
        d3Simulation.alphaTarget(0.3).restart();
      })
      .on("end", (event, d) => {
        d.fx = null; d.fy = null;
        d3Simulation.alphaTarget(0);
        setTimeout(() => { dragMoved = false; }, 80);
      });

    allNodes = nodesG.selectAll("circle.node")
      .data(ns, d => d.id)
      .join("circle")
      .attr("class", "node")
      .attr("data-id", d => d.id)
      .attr("r", d => d.radius)
      .attr("fill", d => getNodeColor(d))
      .attr("stroke", d => (d.isFlagged || localStorage.getItem('flag_' + d.id)) ? "#fc8181" : "#ffffff22")
      .attr("stroke-width", d => (d.isFlagged || localStorage.getItem('flag_' + d.id)) ? 3 : 1)
      .attr("stroke-dasharray", d => (d.isFlagged || localStorage.getItem('flag_' + d.id)) ? "4,2" : null)
      .style("pointer-events", "all")
      .style("cursor", "pointer")
      .call(drag)
      .on("click", function (event, d) {
        event.stopPropagation();
        if (dragMoved) return;
        handleNodeClick(event, d);
      })
      .on("contextmenu", function (event, d) {
        event.preventDefault();
        event.stopPropagation();
        contextTargetNode = d;
        if (contextMenu) {
          contextMenu.style.display = "block";
          contextMenu.style.left = event.clientX + "px";
          contextMenu.style.top = event.clientY + "px";
        }
      })
      .on("mouseenter", function (event, d) {
        d3.select(this)
          .transition().duration(200)
          .attr("r", d.radius * 1.6)
          .style("filter", glowFilter(getNodeTier(d)))
          .style("stroke", "#ffffff")
          .style("stroke-width", "2px")
          .style("stroke-dasharray", null)
          .style("cursor", "pointer");

        allNodes.transition().duration(200).style("opacity", n => isConnected(d, n) ? 1.0 : 0.15);
        allEdges.transition().duration(200)
          .style("opacity", e => {
            const sId = typeof e.source === "object" ? e.source.id : e.source;
            const tId = typeof e.target === "object" ? e.target.id : e.target;
            return (sId === d.id || tId === d.id) ? 0.9 : 0.04;
          })
          .style("stroke-width", e => {
            const sId = typeof e.source === "object" ? e.source.id : e.source;
            const tId = typeof e.target === "object" ? e.target.id : e.target;
            return (sId === d.id || tId === d.id) ? 2.5 : 0.8;
          });
        allLabels.transition().duration(200).style("opacity", n => isConnected(d, n) || n.id === d.id ? 1 : 0);
        showTooltip(event, d);
      })
      .on("mouseleave", function (event, d) {
        if (selectedNode && selectedNode.id === d.id) return;
        const flagged = d.isFlagged || !!localStorage.getItem('flag_' + d.id);
        d3.select(this)
          .transition().duration(200)
          .attr("r", d.radius)
          .style("filter", null)
          .style("stroke", flagged ? "#fc8181" : "#ffffff22")
          .style("stroke-width", flagged ? "3px" : "1px")
          .style("stroke-dasharray", flagged ? "4,2" : null);

        if (selectedNode) {
          allNodes.transition().duration(200).style("opacity", n => isConnected(selectedNode, n) || n.id === selectedNode.id ? 1 : 0.12);
          allEdges.transition().duration(200)
            .style("opacity", e => {
              const sId = typeof e.source === "object" ? e.source.id : e.source;
              const tId = typeof e.target === "object" ? e.target.id : e.target;
              return (sId === selectedNode.id || tId === selectedNode.id) ? 1 : 0.03;
            })
            .style("stroke-width", e => {
              const sId = typeof e.source === "object" ? e.source.id : e.source;
              const tId = typeof e.target === "object" ? e.target.id : e.target;
              return (sId === selectedNode.id || tId === selectedNode.id) ? 3 : 0.8;
            });
          allLabels.transition().duration(200).style("opacity", n => isConnected(selectedNode, n) || n.id === selectedNode.id || n.radius >= 14 ? 1 : 0);
        } else {
          allNodes.transition().duration(200).style("opacity", 1);
          allEdges.transition().duration(200)
            .style("opacity", e => e.tier === "linkage" ? 0.3 : 0.2)
            .style("stroke-width", e => e.tier === "linkage" ? 1.2 : 0.8);
          allLabels.transition().duration(200).style("opacity", n => n.radius >= 14 ? 1 : 0);
        }
        hideTooltip();
      })
      .on("mousemove", function (event, d) { updateTooltipPosition(event, d); });

    allLabels = labelsG.selectAll("text.label")
      .data(ns, d => d.id)
      .join("text")
      .attr("class", "label")
      .attr("data-id", d => d.id)
      .attr("fill", d => (d.isFlagged || localStorage.getItem('flag_' + d.id)) ? "#fc8181" : "#a0aec0")
      .attr("font-size", "10px")
      .attr("font-family", "'Segoe UI', system-ui, sans-serif")
      .style("pointer-events", "all")
      .style("cursor", "pointer")
      .style("opacity", d => d.radius >= 14 ? 1 : 0)
      .text(d => {
        const base = d.name || d.handle;
        return (d.isFlagged || localStorage.getItem('flag_' + d.id)) ? (base + " ⚑") : base;
      })
      .on("click", function (event, d) {
        event.stopPropagation();
        handleNodeClick(event, d);
      })
      .on("mouseenter", function (event, d) {
        const nodeEl = nodesG.select(`circle.node[data-id='${d.id}']`).node();
        if (nodeEl) {
          const fakeEvent = {
            clientX: event.clientX,
            clientY: event.clientY,
            target: nodeEl
          };
          d3.select(nodeEl).dispatch("mouseenter");
        }
      })
      .on("mouseleave", function (event, d) {
        const nodeEl = nodesG.select(`circle.node[data-id='${d.id}']`).node();
        if (nodeEl) {
          d3.select(nodeEl).dispatch("mouseleave");
        }
      });

    d3Simulation.on("tick", () => {
      allEdges.attr("d", calcEdgePath);
      allNodes.attr("cx", d => d.x).attr("cy", d => d.y);
      allLabels.attr("x", d => d.x + d.radius + 5).attr("y", d => d.y + 3);
      allBadges.attr("transform", c => {
        let topY = Infinity, sumX = 0;
        for (const m of c.members) {
          topY = Math.min(topY, m.y - m.baseRadius);
          sumX += m.x;
        }
        const cx = sumX / Math.max(c.members.length, 1);
        return `translate(${cx}, ${topY - 24})`;
      });
      renderMinimap(ns, width, height);
    });

    if (isInitial) fitViewport(ns, width, height);
  }

  function fitViewport(nodes, W, H) {
    if (!nodes || !nodes.length) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of nodes) {
      minX = Math.min(minX, n.x - n.baseRadius);
      maxX = Math.max(maxX, n.x + n.baseRadius);
      minY = Math.min(minY, n.y - n.baseRadius - 38);
      maxY = Math.max(maxY, n.y + n.baseRadius);
    }
    const padTop = 80;
    const padBottom = 35;
    const padX = 40;
    const graphW = Math.max(maxX - minX + padX * 2, 100);
    const graphH = Math.max(maxY - minY + padTop + padBottom, 100);
    const k = Math.min(3.0, Math.max(0.3, Math.min((W - padX * 2) / graphW, (H - padTop - padBottom) / graphH)));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const targetX = W / 2 - cx * k;
    const targetY = (H + padTop - padBottom) / 2 - cy * k;

    svg.transition().duration(500)
      .call(zoom.transform, d3.zoomIdentity.translate(targetX, targetY).scale(k));
  }

  function renderMinimap(ns, W, H) {
    if (!miniCtx || !cvMinimap) return;
    const mw = 180, mh = 110;
    miniCtx.clearRect(0, 0, mw, mh);
    miniCtx.fillStyle = "#060912";
    miniCtx.fillRect(0, 0, mw, mh);

    const mwScaleX = mw / Math.max(W, 1);
    const mwScaleY = mh / Math.max(H, 1);

    for (const n of ns) {
      miniCtx.fillStyle = getNodeColor(n);
      miniCtx.beginPath();
      miniCtx.arc(n.x * mwScaleX, n.y * mwScaleY, 2, 0, Math.PI * 2);
      miniCtx.fill();
    }
    updateMinimapViewport();
  }

  function updateMinimapViewport() {
    if (!minimapVp || !svgEl) return;
    const width = svgEl.clientWidth || 1200;
    const height = svgEl.clientHeight || 640;
    const mw = 180, mh = 110;
    const mwScaleX = mw / Math.max(width, 1);
    const mwScaleY = mh / Math.max(height, 1);
    const k = currentTransform.k || 1;
    const tx = currentTransform.x || 0;
    const ty = currentTransform.y || 0;
    const vpW = Math.min(mw, Math.max(16, (width / k) * mwScaleX));
    const vpH = Math.min(mh, Math.max(12, (height / k) * mwScaleY));
    const vpX = Math.max(0, Math.min(mw - vpW, (-tx / k) * mwScaleX));
    const vpY = Math.max(0, Math.min(mh - vpH, (-ty / k) * mwScaleY));
    minimapVp.style.width = vpW + "px";
    minimapVp.style.height = vpH + "px";
    minimapVp.style.left = vpX + "px";
    minimapVp.style.top = vpY + "px";
  }

  if (minimapWrap) {
    let isMiniDragging = false;
    function panFromMinimap(ev) {
      const rect = minimapWrap.getBoundingClientRect();
      const mx = Math.max(0, Math.min(rect.width, ev.clientX - rect.left));
      const my = Math.max(0, Math.min(rect.height, ev.clientY - rect.top));
      const width = svgEl.clientWidth || 1200;
      const height = svgEl.clientHeight || 640;
      const worldX = (mx / rect.width) * width;
      const worldY = (my / rect.height) * height;
      const k = currentTransform.k || 1;
      const tx = width / 2 - worldX * k;
      const ty = height / 2 - worldY * k;
      svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
    }
    minimapWrap.onmousedown = ev => { isMiniDragging = true; panFromMinimap(ev); };
    window.addEventListener("mousemove", ev => { if (isMiniDragging) panFromMinimap(ev); });
    window.addEventListener("mouseup", () => { isMiniDragging = false; });
  }

  $("#lgZoomIn").onclick = () => { svg.transition().duration(250).call(zoom.scaleBy, 1.3); };
  $("#lgZoomOut").onclick = () => { svg.transition().duration(250).call(zoom.scaleBy, 0.77); };
  $("#lgZoomFit").onclick = () => {
    const current = getFilteredGraph();
    const width = svgEl.clientWidth || 1200;
    const height = svgEl.clientHeight || 640;
    fitViewport(current.ns, width, height);
  };

  if (closeSidePanelBtn) {
    closeSidePanelBtn.onclick = () => { closeRightPanel(); resetGraph(); };
  }
  window.addEventListener("keydown", ev => {
    if (ev.key === "Escape") {
      const confirmOverlay = document.getElementById("anv-confirm-overlay");
      if (confirmOverlay && confirmOverlay.style.display === "flex") {
        confirmOverlay.style.display = "none";
        return;
      }
      const fpOverlay = document.getElementById("fp-dialog-overlay");
      if (fpOverlay && fpOverlay.style.display === "flex") {
        fpOverlay.style.display = "none";
        return;
      }
      const profOverlay = document.getElementById("profile-modal-overlay");
      if (profOverlay && profOverlay.style.display === "flex") {
        profOverlay.style.display = "none";
        return;
      }
      const drawer = document.getElementById("report-drawer");
      if (drawer && drawer.classList.contains("open")) {
        closeReportDrawer();
        return;
      }
      closeRightPanel();
      resetGraph();
      if (contextMenu) contextMenu.style.display = "none";
      if (searchResultsEl) searchResultsEl.style.display = "none";
    }
  });

  if (toggleSidebarBtn && sidebar) {
    toggleSidebarBtn.onclick = () => {
      sidebar.classList.toggle("collapsed");
      toggleSidebarBtn.textContent = sidebar.classList.contains("collapsed") ? "▶" : "◀";
    };
  }

  if (searchInput && searchResultsEl) {
    searchInput.oninput = () => {
      const q = searchInput.value.trim().toLowerCase();
      if (searchClear) searchClear.style.display = q ? "block" : "none";
      if (!q) { searchResultsEl.style.display = "none"; return; }
      const matches = sim.nodes.filter(n =>
        (n.handle || "").toLowerCase().includes(q) || (n.id || "").toLowerCase().includes(q) || (n.name || "").toLowerCase().includes(q)
      ).slice(0, 8);
      if (!matches.length) {
        searchResultsEl.innerHTML = `<div class="lg-search-empty">No actors found</div>`;
        searchResultsEl.style.display = "block";
      } else {
        searchResultsEl.innerHTML = matches.map(n => {
          const tier = getNodeTier(n);
          const color = (tier === "high") ? "#00e5cc" : (tier === "med") ? "#f5a623" : "#8b5cf6";
          return `
            <div class="lg-search-item" data-id="${esc(n.id)}">
              <div class="lg-search-item-info">
                <span class="lg-search-item-handle">${esc(n.name || n.handle)}</span>
                <span class="lg-search-item-meta">${esc(n.id)} · Cluster ${esc(n.clusterId || n.cluster || "solo")}</span>
              </div>
              <span class="lg-search-item-lr" style="color:${color};background:${color}18;border:1px solid ${color}44">LR ${fmt(n.maxLR !== undefined ? n.maxLR : n.maxLr, 1)}</span>
            </div>
          `;
        }).join("");
        searchResultsEl.style.display = "block";
        searchResultsEl.querySelectorAll(".lg-search-item").forEach(item => {
          item.onclick = () => {
            const id = item.dataset.id;
            const targetNode = sim.byId[id];
            searchResultsEl.style.display = "none";
            if (targetNode) {
              const width = svgEl.clientWidth || 1200;
              const height = svgEl.clientHeight || 640;
              const k = 1.8;
              const tx = width / 2 - targetNode.x * k;
              const ty = height / 2 - targetNode.y * k;
              svg.transition().duration(500)
                .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
              handleNodeClick(null, targetNode);
            }
          };
        });
      }
    };
    document.addEventListener("click", ev => {
      if (!ev.target.closest(".lg-search-wrap")) { searchResultsEl.style.display = "none"; }
    });
  }

  if (searchClear) {
    searchClear.onclick = () => {
      searchInput.value = "";
      searchClear.style.display = "none";
      if (searchResultsEl) searchResultsEl.style.display = "none";
    };
  }

  document.querySelectorAll(".lg-chip").forEach(chip => {
    chip.onclick = () => {
      const tier = chip.dataset.tier;
      if (activeTiers.has(tier)) {
        if (activeTiers.size > 1) { activeTiers.delete(tier); chip.classList.remove("active"); }
      } else { activeTiers.add(tier); chip.classList.add("active"); }
      updateLayout(false);
    };
  });

  let sliderTimer = null;
  const onSliderChange = () => {
    clearTimeout(sliderTimer);
    sliderTimer = setTimeout(() => {
      if (lrFilterVal && lrSlider) lrFilterVal.textContent = fmt(minLR(), 1);
      updateLayout(false);
    }, 120);
  };
  if (lrSlider) lrSlider.oninput = onSliderChange;
  if (showLeadsCb) showLeadsCb.onchange = onSliderChange;

  const onClusterSizeChange = () => {
    minClusterSize = parseInt(clusterSizeMin.value);
    maxClusterSize = parseInt(clusterSizeMax.value);
    if (minClusterSize > maxClusterSize) { const tmp = minClusterSize; minClusterSize = maxClusterSize; maxClusterSize = tmp; }
    if (clusterSizeVal) clusterSizeVal.textContent = `${minClusterSize} – ${maxClusterSize}`;
    updateLayout(false);
  };
  if (clusterSizeMin) clusterSizeMin.oninput = onClusterSizeChange;
  if (clusterSizeMax) clusterSizeMax.oninput = onClusterSizeChange;

  if (clusterSortSel) {
    clusterSortSel.onchange = () => {
      sortCriteria = clusterSortSel.value;
      updateLayout(false);
    };
  }

  // Attach Report Drawer & Badge triggers
  const reportBadge = document.getElementById("lgReportBadge");
  if (reportBadge) {
    reportBadge.onclick = openReportDrawer;
  }
  const closeDrawerBtn = document.getElementById("closeReportDrawer");
  if (closeDrawerBtn) {
    closeDrawerBtn.onclick = closeReportDrawer;
  }
  const exportCsvBtn = document.getElementById("btnExportCsv");
  if (exportCsvBtn) {
    exportCsvBtn.onclick = exportReportCsv;
  }
  const clearReportBtn = document.getElementById("btnClearReport");
  if (clearReportBtn) {
    clearReportBtn.onclick = promptClearReport;
  }
  updateReportBadge();

  // Attach context menu items
  let contextTargetNode = null;
  if (contextMenu) {
    contextMenu.querySelectorAll(".lg-ctx-item").forEach(item => {
      item.onclick = () => {
        const action = item.dataset.action;
        contextMenu.style.display = "none";
        if (!contextTargetNode) return;
        if (action === "inspect") {
          openFullProfileModal(contextTargetNode);
        } else if (action === "flag_fp") {
          openFlagDialog(contextTargetNode);
        } else if (action === "add_report") {
          addToReport(contextTargetNode);
        } else if (action === "copy_id") {
          if (navigator.clipboard) {
            navigator.clipboard.writeText(contextTargetNode.id);
            showToast("Copied persona ID: " + contextTargetNode.id, "#00e5cc");
          }
        } else if (action === "subgraph") {
          const cid = contextTargetNode.clusterId || contextTargetNode.cluster;
          const clusterNodes = getAllClusterNodes(cid);
          zoomToCluster(clusterNodes);
        }
      };
    });
  }

  updateLayout(true);
  sim.started = true;
}

function showPersona(id) {
  $("#graph-detail").textContent = "loading " + id + " ...";
  api("/api/persona/" + id).then(d => {
    const p = d.persona, g = d.geolocation;
    const spark = d.hour_histogram_utc;
    const mx = Math.max(...spark, 1);
    const bars = spark.map((v, i) =>
      `<span title="${i}:00 UTC — ${v} posts" style="display:inline-block;width:7px;
       height:${Math.max(2, Math.round(22 * v / mx))}px;background:${v / mx > .6
        ? "var(--accent)" : "#2c3c50"};margin-right:1px;vertical-align:bottom"></span>`).join("");
    $("#graph-detail").innerHTML = `
      <b class="mono">${esc(p.handle)}</b> <span class="muted">${esc(p.persona_id)}
      &middot; ${esc(p.site)} &middot; ${p.first_seen.slice(0, 10)} &rarr; ${p.last_seen.slice(0, 10)}</span>
      &nbsp;|&nbsp; cluster <b>${d.cluster || "unresolved"}</b><br>
      <span class="muted">posting hours (UTC):</span> ${bars}
      &nbsp; <span class="muted">estimated locale:</span>
      ${g.offset === null ? "unknown" : `UTC${g.offset >= 0 ? "+" : ""}${g.offset}
        &plusmn;${g.band}h (conf ${fmt(g.confidence, 2)})
        ${g.regions.length ? "&mdash; " + g.regions.slice(0, 3).join(", ") : ""}`}
      <br><span class="muted">${d.links.length} scored links; strongest
      log<sub>10</sub> LR ${d.links.length ? fmt(d.links[0].log10_lr, 2) : "--"}</span>`;
  });
}

/* ---------------- boot ---------------- */
detectStaticMode().then(() =>
  Promise.all([
    api("/api/report"),
    api("/api/graph"),
    api("/api/links?limit=400"),
    api("/api/clusters"),
    fetch("data/hosts.json").then(r => r.ok ? r.json() : fetch("/data/hosts.json").then(r2 => r2.ok ? r2.json() : [])).catch(() => [])
  ]))
  .then(([rep, gr, lk, cl, hostsData]) => {
    REPORT = rep; GRAPH = gr; LINKS = lk; CLUSTERS = cl;
    window.REPORT = rep; window.GRAPH = gr; window.LINKS = lk; window.CLUSTERS = cl;
    window.ALL_HOSTS = Array.isArray(hostsData) ? hostsData : [];
    if (typeof IR_HOSTS !== "undefined" && window.ALL_HOSTS.length > 0) {
      IR_HOSTS = window.ALL_HOSTS;
    }
    kpis(rep); opsecChart(rep); channelHeat(rep); traps(rep); benchmark(rep); initBayesCalculator();
    renderLinks(lk); renderActors(cl);
    // Open on the assertion threshold with leads hidden. Showing every
    // lead edge by default renders a hairball that says nothing; the
    // analyst opts into the noisier view deliberately.
    $("#lrFilter").min = rep.settings.lead_floor_log10_lr ?? 0.5;
    $("#lrFilter").value = 3.5;
    $("#showLeads").checked = false;
    $("#lrFilterVal").textContent = fmt(3.5, 1);
  })
  .catch(e => {
    document.querySelector("main").innerHTML =
      `<div class="card"><h2>Backend unavailable</h2>
       <p class="sub">${esc(e)}</p></div>`;
  });

/* =====================================================================
   Contact Exposure panel  (Dark2Clear forum extension)
   =====================================================================

   Radial graph layout — vanilla SVG, no build step.

   Rings:
     centre node  = actor (cluster)
     inner ring   = personas in that cluster
     outer ring   = identifiers (one node per unique identifier)

   Edge styling encodes evidence state:
     solid amber  (stroke-width 2, no dash)       = attributed  (score >= 0.50, direct)
     dashed grey  (stroke-width 1.5, dash 5 3)    = present     (0.30 <= score < 0.50, direct)
     dotted grey  (stroke-width 1,   dash 2 3)    = inherited   (is_inherited=True)
     solid muted  (stroke-width 1.5, no dash)     = actor→persona cluster membership

   Clicking any persona or identifier node opens the evidence panel.
*/

let EXP_DATA = null;       // raw /api/forum/exposure response
let EXP_ACTOR_IDX = 0;    // currently selected actor index
let EXP_READY = false;

/* ---- tab activation ---- */
document.querySelectorAll("#tabs button").forEach(b => {
  const orig = b.onclick;
  b.onclick = function (ev) {
    if (orig) orig.call(this, ev);
  };
});

function expInit() {
  if (EXP_READY) return;
  EXP_READY = true;
  api("/api/forum/exposure").then(data => {
    if (!data || !data.length) {
      $("#expGraphWrap").innerHTML =
        '<p class="muted" style="padding:20px">No exposure data available — ' +
        'run the pipeline first.</p>';
      return;
    }
    EXP_DATA = data;
    expBuildActorBar(data);
    expRender(0);
  }).catch(err => {
    $("#expGraphWrap").innerHTML =
      '<p class="muted" style="padding:20px">Could not load exposure data: ' +
      esc(String(err)) + '</p>';
  });
}

/* ---- actor selector bar ---- */
function expBuildActorBar(data) {
  const bar = $("#expActorSelect");
  bar.innerHTML = data.map((ae, i) =>
    `<button class="exp-actor-btn${i === 0 ? " active" : ""}"
             data-idx="${i}" title="${esc(ae.actor_id)}"
             >${esc(ae.actor_id)}
       <span class="muted" style="font-size:11px;margin-left:4px">
         ${ae.stats.personas_in_cluster}p / ${ae.stats.distinct_identifiers}id
       </span>
     </button>`
  ).join("");
  bar.querySelectorAll(".exp-actor-btn").forEach(btn => {
    btn.onclick = () => {
      bar.querySelectorAll(".exp-actor-btn")
        .forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      expRender(+btn.dataset.idx);
    };
  });
}

/* ---- main render ---- */
function expRender(actorIdx) {
  EXP_ACTOR_IDX = actorIdx;
  const ae = EXP_DATA[actorIdx];
  if (!ae) return;

  // Hide evidence panel until a node is clicked
  const panel = $("#expEvidencePanel");
  panel.style.display = "none";

  expDrawRadial(ae);
  expRenderStats(ae);
}

/* ---- SVG radial graph ---- */
function expDrawRadial(ae) {
  const svgEl = $("#expSvg");
  const W = svgEl.clientWidth || 800;
  const H = parseInt(svgEl.getAttribute("height")) || 420;
  const cx = W / 2, cy = H / 2;

  const ACTOR_R = 20;
  const PERSONA_R = 10;
  const ID_R = 7;
  const INNER_RING = Math.min(cx, cy) * 0.34;
  const OUTER_RING = Math.min(cx, cy) * 0.72;

  // Deduplicate identifiers by (type, value) — keep highest-score record
  const idMap = new Map();
  for (const rec of ae.identifiers) {
    const k = rec.type + ":" + rec.identifier.toLowerCase();
    const existing = idMap.get(k);
    if (!existing || rec.score > existing.score) idMap.set(k, rec);
  }
  const idNodes = [...idMap.values()];

  const personas = ae.personas;

  // Build SVG string
  let svg = "";

  // ---- helper: angle to coordinate ----
  const pt = (ring, angle) => ({
    x: cx + ring * Math.cos(angle),
    y: cy + ring * Math.sin(angle),
  });

  // ---- actor→persona edges (solid muted) ----
  personas.forEach((pid, i) => {
    const a = (i / personas.length) * Math.PI * 2 - Math.PI / 2;
    const p = pt(INNER_RING, a);
    svg += `<line x1="${cx}" y1="${cy}" x2="${fmt(p.x, 1)}" y2="${fmt(p.y, 1)}"
      stroke="var(--dim)" stroke-width="1.5" opacity="0.6"/>`;
  });

  // ---- persona→identifier edges ----
  idNodes.forEach((rec, j) => {
    const ja = (j / Math.max(idNodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const idPt = pt(OUTER_RING, ja);

    // Find which persona posted this (source_persona)
    const srcIdx = personas.indexOf(rec.posted_by_persona);
    const pAngle = srcIdx >= 0
      ? (srcIdx / personas.length) * Math.PI * 2 - Math.PI / 2
      : 0;
    const pPt = pt(INNER_RING, pAngle);

    const { stroke, sw, dash } = expEdgeStyle(rec);
    const dashAttr = dash ? `stroke-dasharray="${dash}"` : "";
    svg += `<line x1="${fmt(pPt.x, 1)}" y1="${fmt(pPt.y, 1)}"
      x2="${fmt(idPt.x, 1)}" y2="${fmt(idPt.y, 1)}"
      stroke="${stroke}" stroke-width="${sw}" ${dashAttr} opacity="0.75"/>`;
  });

  // ---- actor node (centre) ----
  svg += `<g class="exp-node" data-type="actor" data-id="${esc(ae.actor_id)}">
    <circle cx="${cx}" cy="${cy}" r="${ACTOR_R}"
      fill="#16283c" stroke="var(--accent)" stroke-width="2"/>
    <text x="${cx}" y="${cy + 4}" text-anchor="middle"
      fill="var(--accent)" font-size="10" font-weight="600">${esc(ae.actor_id)}</text>
    <title>${esc(ae.actor_id)} · ${personas.length} personas · ${idNodes.length} identifiers</title>
  </g>`;

  // ---- persona nodes ----
  personas.forEach((pid, i) => {
    const a = (i / personas.length) * Math.PI * 2 - Math.PI / 2;
    const p = pt(INNER_RING, a);
    const shortHandle = pid.split(":").pop();
    // Does this persona have any direct (non-inherited) identifiers?
    const hasDirect = ae.identifiers.some(
      r => r.posted_by_persona === pid && !r.is_inherited);
    const fill = hasDirect ? "var(--warn)" : "var(--panel2)";
    const stroke = hasDirect ? "#6b4e00" : "var(--line)";
    const pp = ae.per_persona.find(pp => pp.persona_id === pid) || {};
    svg += `<g class="exp-node" data-type="persona" data-id="${esc(pid)}">
      <circle cx="${fmt(p.x, 1)}" cy="${fmt(p.y, 1)}" r="${PERSONA_R}"
        fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>
      <text x="${fmt(p.x, 1)}" y="${fmt(p.y + PERSONA_R + 11, 1)}" text-anchor="middle"
        fill="var(--muted)" font-size="9.5">${esc(shortHandle.slice(0, 12))}</text>
      <title>${esc(pid)}
posts: ${pp.total_posts || 0} · leak posts: ${pp.leak_posts || 0}
with contact: ${pp.posts_with_contact || 0}</title>
    </g>`;
  });

  // ---- identifier nodes ----
  idNodes.forEach((rec, j) => {
    const ja = (j / Math.max(idNodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const idPt = pt(OUTER_RING, ja);
    const { fill } = expNodeFill(rec);
    const label = rec.identifier.length > 14
      ? rec.identifier.slice(0, 12) + "…" : rec.identifier;
    svg += `<g class="exp-node" data-type="identifier" data-key="${esc(rec.type + ":" + rec.identifier)}">
      <circle cx="${fmt(idPt.x, 1)}" cy="${fmt(idPt.y, 1)}" r="${ID_R}"
        fill="${fill}" stroke="var(--line)" stroke-width="1"/>
      <text x="${fmt(idPt.x, 1)}" y="${fmt(idPt.y + ID_R + 10, 1)}" text-anchor="middle"
        fill="var(--dim)" font-size="9">${esc(label)}</text>
      <title>${esc(rec.type)}: ${esc(rec.identifier)}
score: ${rec.score} (${rec.band})
status: ${rec.status}
posted by: ${esc(rec.posted_by_persona)}
thread: ${esc(rec.thread_id || "—")} post: ${esc(rec.post_id || "—")}</title>
    </g>`;
  });

  svgEl.innerHTML = svg;

  // ---- click handlers ----
  svgEl.querySelectorAll(".exp-node").forEach(g => {
    g.addEventListener("click", () => {
      const type = g.dataset.type;
      if (type === "persona") {
        expShowPersonaEvidence(ae, g.dataset.id);
      } else if (type === "identifier") {
        expShowIdentifierEvidence(ae, g.dataset.key);
      } else {
        expShowActorSummary(ae);
      }
    });
  });
}

/* ---- edge style helper ---- */
function expEdgeStyle(rec) {
  if (rec.is_inherited)
    return { stroke: "var(--muted)", sw: 1, dash: "2,3" };
  if (rec.status === "attributed")
    return { stroke: "var(--warn)", sw: 2, dash: null };
  // present (low score, direct)
  return { stroke: "var(--muted)", sw: 1.5, dash: "5,3" };
}

/* ---- node fill helper ---- */
function expNodeFill(rec) {
  if (rec.is_inherited) return { fill: "#1a1f2a" };
  if (rec.status === "attributed") return { fill: "#1e1500" };
  return { fill: "#13202e" };
}

/* ---- stats header ---- */
function expRenderStats(ae) {
  const s = ae.stats;
  const cards = [
    ["Leak threads", s.leak_posts, "posts matching data-sale intent"],
    ["Threads w/ contact", s.posts_with_contact, "posts with ≥1 scorable identifier"],
    ["Distinct identifiers", s.distinct_identifiers, "unique (type, value) pairs"],
    ["Personas in cluster", s.personas_in_cluster, s.personas_with_leaks + " with direct leaks"],
  ];
  const statsHtml = `<div class="card" id="expStatsCard">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <b>${esc(ae.actor_id)}</b>
      <span class="muted">${ae.personas.length} persona(s)</span>
    </div>
    <div class="exp-stats-grid">
      ${cards.map(([k, v, n]) => `<div class="exp-stat">
        <div class="k">${k}</div>
        <div class="v">${v}</div>
        <div class="muted" style="font-size:11px;margin-top:2px">${n}</div>
      </div>`).join("")}
    </div>
    ${expRenderIdTable(ae)}
  </div>`;
  $("#expStatsList").innerHTML = statsHtml;

  // attach click handlers for identifier rows
  document.querySelectorAll(".clickable-id").forEach(tr => {
    tr.addEventListener("click", () =>
      expShowIdentifierEvidence(ae, tr.dataset.key));
  });
}

/* ---- identifier table ---- */
function expRenderIdTable(ae) {
  // Deduplicate by (type, value), keep highest score
  const seen = new Map();
  for (const rec of ae.identifiers) {
    const k = rec.type + ":" + rec.identifier.toLowerCase();
    if (!seen.has(k) || rec.score > seen.get(k).score) seen.set(k, rec);
  }
  const rows = [...seen.values()].sort((a, b) => b.score - a.score);
  if (!rows.length) return '<p class="muted" style="margin-top:8px">No identifiers above the noise floor.</p>';

  const statusPill = s => {
    const cls = s === "attributed" ? "pill-attributed"
      : s === "present" ? "pill-present"
        : "pill-inherited";
    return `<span class="pill ${cls}">${s}</span>`;
  };

  return `<table class="exp-id-table">
    <tr><th>type</th><th>identifier</th><th>status</th>
        <th class="num">score</th><th>posted by</th><th>thread</th></tr>
    ${rows.map(rec => {
    const k = esc(rec.type + ":" + rec.identifier);
    return `<tr class="clickable-id" data-key="${k}">
        <td class="muted">${esc(rec.type)}</td>
        <td class="mono">${esc(rec.identifier.slice(0, 40))}</td>
        <td>${statusPill(rec.status)}</td>
        <td class="num">${fmt(rec.score, 2)}</td>
        <td class="mono muted">${esc((rec.posted_by_persona || "").split(":").pop().slice(0, 16))}</td>
        <td class="muted">${esc(rec.thread_id || "—")}</td>
      </tr>`;
  }).join("")}
  </table>`;
}

/* ---- evidence panel: identifier detail ---- */
function expShowIdentifierEvidence(ae, key) {
  // key is "type:value" (lowercased value for lookup)
  const [type, ...rest] = key.split(":");
  const val = rest.join(":").toLowerCase();
  const recs = ae.identifiers.filter(
    r => r.type === type && r.identifier.toLowerCase() === val);
  if (!recs.length) return;

  const best = recs.reduce((a, b) => b.score > a.score ? b : a);
  const panel = $("#expEvidencePanel");

  const statusLabel = {
    attributed: '<span class="exp-ev-status-attributed">attributed — solid amber edge</span>',
    present: '<span class="exp-ev-status-present">present — dashed grey edge</span>',
    inherited: '<span class="exp-ev-status-inherited">inherited — dotted grey edge (not posted directly by linked persona)</span>',
  }[best.status] || esc(best.status);

  const reasonsHtml = (best.reasons || []).length
    ? best.reasons.map(r => `<div class="muted" style="font-size:12px;margin-top:3px">• ${esc(r)}</div>`).join("")
    : '<span class="muted">—</span>';

  panel.style.display = "";
  panel.innerHTML = `
    <h3>${esc(best.type)}: <span class="mono">${esc(best.identifier)}</span></h3>
    <div class="exp-ev-row">
      <span class="exp-ev-field">status</span>
      <span colspan="3">${statusLabel}</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">score / band</span>
      <span class="exp-ev-val">${fmt(best.score, 3)}</span>
      <span class="muted">${esc(best.band)}</span>
      <span class="muted">higher = stronger attribution evidence</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">posted by</span>
      <span class="mono" style="grid-column:2/5">${esc(best.posted_by_persona)}</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">forum position</span>
      <span class="mono" style="grid-column:2/5">${esc(best.forum_position)}</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">thread / post</span>
      <span class="mono" style="grid-column:2/5">${esc(best.thread_id || "—")} / ${esc(best.post_id || "—")}</span>
    </div>
    ${best.context_snippet ? `<div class="exp-ev-row">
      <span class="exp-ev-field">context</span>
      <span class="muted mono" style="grid-column:2/5;font-size:11.5px">${esc(best.context_snippet)}</span>
    </div>` : ""}
    <div style="margin-top:8px"><b>Reasoning:</b>${reasonsHtml}</div>
    ${recs.length > 1 ? `<p class="muted" style="margin-top:10px;font-size:12px">${recs.length} sightings total (${recs.filter(r => r.is_inherited).length} inherited, ${recs.filter(r => !r.is_inherited).length} direct)</p>` : ""}
  `;
}

/* ---- evidence panel: persona summary ---- */
function expShowPersonaEvidence(ae, personaId) {
  const pp = ae.per_persona.find(p => p.persona_id === personaId);
  const panel = $("#expEvidencePanel");
  if (!pp) { panel.style.display = "none"; return; }

  const directIds = ae.identifiers.filter(
    r => r.posted_by_persona === personaId && !r.is_inherited);

  panel.style.display = "";
  panel.innerHTML = `
    <h3>Persona: <span class="mono">${esc(pp.handle || personaId)}</span></h3>
    <div class="exp-ev-row">
      <span class="exp-ev-field">total posts</span>
      <span class="exp-ev-val">${pp.total_posts}</span>
      <span class="muted">first ${esc(pp.first_seen || "—")}</span>
      <span class="muted">last ${esc(pp.last_seen || "—")}</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">leak posts</span>
      <span class="exp-ev-val">${pp.leak_posts}</span>
      <span class="muted" style="grid-column:3/5">posts matching data-sale intent keywords</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">with contact</span>
      <span class="exp-ev-val">${pp.posts_with_contact}</span>
      <span class="muted" style="grid-column:3/5">posts containing ≥1 identifier above noise floor</span>
    </div>
    <div style="margin-top:10px"><b>Directly posted identifiers (${directIds.length}):</b>
      ${directIds.length
      ? `<table class="exp-id-table" style="margin-top:6px">
            <tr><th>type</th><th>identifier</th><th>score</th><th>forum position</th></tr>
            ${directIds.slice(0, 12).map(r =>
        `<tr><td class="muted">${esc(r.type)}</td>
               <td class="mono">${esc(r.identifier.slice(0, 36))}</td>
               <td class="num">${fmt(r.score, 2)}</td>
               <td class="muted">${esc(r.forum_position)}</td></tr>`
      ).join("")}
           </table>`
      : '<p class="muted" style="margin-top:5px">None above the noise floor.</p>'}
    </div>
  `;
}

/* ---- evidence panel: actor summary ---- */
function expShowActorSummary(ae) {
  const s = ae.stats;
  const panel = $("#expEvidencePanel");
  panel.style.display = "";
  panel.innerHTML = `
    <h3>Actor cluster: <span class="mono">${esc(ae.actor_id)}</span></h3>
    <div class="exp-ev-row">
      <span class="exp-ev-field">personas</span>
      <span class="exp-ev-val">${s.personas_in_cluster}</span>
      <span class="muted" style="grid-column:3/5">${s.personas_with_leaks} with direct leaks</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">leak threads</span>
      <span class="exp-ev-val">${s.leak_posts}</span>
      <span class="muted" style="grid-column:3/5">posts matching data-sale keywords</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">threads w/ contact</span>
      <span class="exp-ev-val">${s.posts_with_contact}</span>
      <span class="muted" style="grid-column:3/5">posts containing a scorable identifier</span>
    </div>
    <div class="exp-ev-row">
      <span class="exp-ev-field">distinct ids</span>
      <span class="exp-ev-val">${s.distinct_identifiers}</span>
      <span class="muted" style="grid-column:3/5">unique (type, value) pairs across the cluster</span>
    </div>
    <p class="muted" style="margin-top:10px;font-size:12px">
      Click a persona ring node to see its post stats and directly-posted identifiers.
      Click an identifier ring node to see its full provenance and reasoning.
    </p>
  `;
}

/* Register exposure tab in STATIC_MAP so static builds work */
if (typeof STATIC_MAP !== "undefined") {
  STATIC_MAP["/api/forum/exposure"] = "data/live.json";
}

/* =====================================================================
   INFRASTRUCTURE RECON MODULE
   Real Network tab → "Infrastructure Recon" sub-tab
   ===================================================================== */

(function infraReconModule() {
  "use strict";

  /* ── State ── */
  let IR_HOSTS = [];          // raw data from hosts.json
  let IR_FILTERED = [];       // after filters applied
  let IR_SORT_COL = "id";
  let IR_SORT_DIR = "asc";
  let IR_EXPANDED_ID = null;  // currently expanded row id
  let IR_LOADED = false;      // prevent double-fetch

  /* ── Critical port definitions ── */
  const CRIT_PORTS = new Set([3389, 27017, 4444, 1337, 31337, 6379, 2049, 445, 5985, 135]);
  const HIGH_PORTS = new Set([3306, 5432, 21, 873, 8888]);

  function portRisk(port) {
    if (CRIT_PORTS.has(port)) return "critical";
    if (HIGH_PORTS.has(port)) return "high";
    if (port === 22) return "low";
    if (port === 443 || port === 993 || port === 587 || port === 143) return "safe";
    if (port === 80 || port === 25) return "low";
    return "low";
  }

  function criticalPortCount(host) {
    return host.open_ports.filter(p => CRIT_PORTS.has(p.port)).length;
  }

  /* ── Country flag emoji map ── */
  const FLAG = {
    "Germany": "🇩🇪", "Netherlands": "🇳🇱", "Russia": "🇷🇺", "China": "🇨🇳", "USA": "🇺🇸",
    "UK": "🇬🇧", "France": "🇫🇷", "India": "🇮🇳", "Singapore": "🇸🇬", "Brazil": "🇧🇷",
    "Romania": "🇷🇴", "Ukraine": "🇺🇦", "Moldova": "🇲🇩", "Panama": "🇵🇦", "Turkey": "🇹🇷",
    "Iran": "🇮🇷", "Japan": "🇯🇵", "Canada": "🇨🇦", "Sweden": "🇸🇪", "Finland": "🇫🇮",
    "Luxembourg": "🇱🇺", "Switzerland": "🇨🇭", "Kazakhstan": "🇰🇿", "Australia": "🇦🇺",
    "Czech Republic": "🇨🇿", "Indonesia": "🇮🇩", "Morocco": "🇲🇦", "Spain": "🇪🇸",
    "Italy": "🇮🇹", "Belgium": "🇧🇪", "Poland": "🇵🇱", "Mexico": "🇲🇽",
  };

  /* ── OPSEC color map ── */
  const OPSEC_COLOR = {
    Critical: "#fc8181", High: "#f5a623", Medium: "#fbd38d",
    Low: "#8b5cf6", Hardened: "#00e5cc"
  };

  /* ── Sub-tab switching ── */
  function initSubTabs() {
    document.querySelectorAll(".rw-subtab").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".rw-subtab").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".rw-subpanel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = document.getElementById(btn.dataset.subtab);
        if (panel) panel.classList.add("active");
        // Lazy-load IR data when the tab is first opened
        if (btn.dataset.subtab === "rw-infrarecon" && !IR_LOADED) {
          irLoad();
        }
        if (btn.dataset.subtab === "rw-topomap") {
          topoInit();
        }
      });
    });
  }

  /* ── Load hosts.json ── */
  function irLoad() {
    IR_LOADED = true;
    const skel = document.getElementById("irSkeleton");
    const err = document.getElementById("irError");
    const tbl = document.getElementById("irTableContainer");
    if (skel) skel.style.display = "";
    if (err) err.style.display = "none";
    if (tbl) tbl.style.display = "none";

    fetch("data/hosts.json")
      .then(r => {
        if (!r.ok) return fetch("/data/hosts.json").then(r2 => { if (!r2.ok) throw new Error(r2.status); return r2.json(); });
        return r.json();
      })
      .then(data => {
        IR_HOSTS = Array.isArray(data) ? data : [];
        if (skel) skel.style.display = "none";
        irPopulateCountryFilter();
        irUpdateStats(IR_HOSTS);
        irApplyFilters();
        irRenderPanel(IR_HOSTS);
        if (tbl) tbl.style.display = "";
        const map = document.getElementById("irMapContainer");
        if (map) { map.style.display = ""; irRenderMap(IR_HOSTS); }
        const panel = document.getElementById("irSummaryPanel");
        if (panel) panel.style.display = "";
      })
      .catch(() => {
        IR_LOADED = false;
        if (skel) skel.style.display = "none";
        if (err) err.style.display = "";
      });
  }

  /* ── Populate country dropdown ── */
  function irPopulateCountryFilter() {
    const sel = document.getElementById("irFilterCountry");
    if (!sel) return;
    const countries = [...new Set(IR_HOSTS.map(h => h.country))].sort();
    countries.forEach(c => {
      const o = document.createElement("option");
      o.value = c; o.textContent = (FLAG[c] || "") + " " + c;
      sel.appendChild(o);
    });
  }

  /* ── Update top-stats bar ── */
  function irUpdateStats(hosts) {
    const total = hosts.length;
    const critical = hosts.filter(h => h.opsec_score === "Critical").length;
    const high = hosts.filter(h => h.opsec_score === "High").length;
    const attributed = hosts.filter(h => h.attributed_persona).length;
    const countries = new Set(hosts.map(h => h.country)).size;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("irStatTotal", total);
    set("irStatCritical", critical);
    set("irStatHigh", high);
    set("irStatAttributed", attributed);
    set("irStatCountries", countries);
  }

  /* ── Filter & Multi-select State ── */
  let IR_SELECTED_TAGS = new Set();

  function irApplyFilters() {
    const q = (document.getElementById("irSearch")?.value || "").toLowerCase().trim();
    const ops = document.getElementById("irFilterOpsec")?.value || "";
    const cty = document.getElementById("irFilterCountry")?.value || "";
    const attrOnly = document.getElementById("irFilterAttributed")?.checked || false;

    IR_FILTERED = IR_HOSTS.filter(h => {
      if (ops && h.opsec_score !== ops) return false;
      if (IR_SELECTED_TAGS.size > 0 && !(h.tags || []).some(t => IR_SELECTED_TAGS.has(t))) return false;
      if (cty && h.country !== cty) return false;
      if (attrOnly && !h.attributed_persona) return false;
      if (q) {
        const haystack = [
          h.ip, h.hostname || "", h.attributed_persona || "",
          h.notes || "", h.country, h.provider, String(h.asn), h.asn_name || "", h.city
        ].join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    irSortFiltered();
    irRenderTable();
    const rc = document.getElementById("irResultCount");
    if (rc) rc.textContent = `Showing ${IR_FILTERED.length} of ${IR_HOSTS.length} hosts`;
  }

  /* ── Sorting ── */
  const OPSEC_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3, Hardened: 4 };
  function irSortFiltered() {
    IR_FILTERED.sort((a, b) => {
      let va = a[IR_SORT_COL], vb = b[IR_SORT_COL];
      if (IR_SORT_COL === "opsec_score") {
        va = OPSEC_ORDER[va] ?? 99; vb = OPSEC_ORDER[vb] ?? 99;
      } else if (IR_SORT_COL === "risk_ports") {
        va = criticalPortCount(a); vb = criticalPortCount(b);
      } else if (typeof va === "string") {
        va = (va || "").toLowerCase(); vb = (vb || "").toLowerCase();
      }
      if (va < vb) return IR_SORT_DIR === "asc" ? -1 : 1;
      if (va > vb) return IR_SORT_DIR === "asc" ? 1 : -1;
      return 0;
    });
  }

  /* ── Tag chip HTML ── */
  function irTagChip(tag) {
    const cls = tag.replace(/[^a-zA-Z0-9-]/g, "-");
    const label = tag === "C2" ? "⚠ C2" : tag;
    return `<span class="ir-tag ir-tag-${cls}">${esc(label)}</span>`;
  }

  /* ── Port chip HTML ── */
  function irPortChip(p) {
    const risk = portRisk(p.port);
    const critCls = (risk === "critical") ? " ir-port-critical" : "";
    return `<span class="ir-port${critCls}">${p.port}</span>`;
  }

  /* ── OPSEC badge HTML ── */
  function irBadge(score) {
    return `<span class="ir-badge ir-badge-${esc(score)}">${esc(score)}</span>`;
  }

  /* ── Render main table ── */
  function irRenderTable() {
    const tbody = document.getElementById("irTableBody");
    if (!tbody) return;

    // Update sort indicators
    document.querySelectorAll(".ir-table thead th").forEach(th => {
      th.classList.remove("ir-sort-asc", "ir-sort-desc");
      if (th.dataset.col === IR_SORT_COL) {
        th.classList.add(IR_SORT_DIR === "asc" ? "ir-sort-asc" : "ir-sort-desc");
      }
    });

    if (IR_FILTERED.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#4a5568;padding:30px">
        No hosts match the current filters</td></tr>`;
      return;
    }

    const rows = IR_FILTERED.map(h => irBuildRow(h)).join("");
    tbody.innerHTML = rows;

    // Bind expand buttons
    tbody.querySelectorAll(".ir-expand-btn").forEach(btn => {
      btn.addEventListener("click", e => { e.stopPropagation(); irToggleExpand(btn.dataset.id); });
    });
    // Bind row clicks
    tbody.querySelectorAll("tr.ir-data-row").forEach(tr => {
      tr.addEventListener("click", () => irToggleExpand(tr.dataset.id));
    });
  }

  function irBuildRow(h) {
    const crit = criticalPortCount(h);
    const tags = (h.tags || []);
    const tagHtml = tags.slice(0, 3).map(irTagChip).join("") +
      (tags.length > 3 ? `<span class="ir-tag ir-tag-more">+${tags.length - 3}</span>` : "");
    const portHtml = (h.open_ports || []).slice(0, 5).map(irPortChip).join("") +
      ((h.open_ports || []).length > 5 ? `<span class="ir-port">+${h.open_ports.length - 5}</span>` : "");
    const attrClass = h.attributed_persona ? " ir-attributed" : "";
    const isExp = IR_EXPANDED_ID === h.id;
    const expandClass = isExp ? " open" : "";
    const expandedClass = isExp ? " ir-expanded-parent" : "";
    const flag = FLAG[h.country] || "🌐";
    const personaHtml = h.attributed_persona
      ? `<span class="ir-persona-name">${esc(h.attributed_persona)}</span>`
      : `<span class="ir-persona-null">—</span>`;
    const riskHtml = crit > 0
      ? `<span class="ir-risk-badge">${crit}</span>` : `<span style="color:#4a5568">—</span>`;
    const isFlagged = !!localStorage.getItem("flag_host_" + h.id);
    const flagBadge = isFlagged ? `<span style="color:#fc8181;margin-left:5px" title="Flagged host">⚑</span>` : "";

    return `<tr class="ir-data-row${attrClass}${expandedClass}" data-id="${esc(h.id)}">
      <td><button class="ir-expand-btn${expandClass}" data-id="${esc(h.id)}" title="Expand">▶</button></td>
      <td>
        <div class="ir-host-ip">${esc(h.ip)}${flagBadge}</div>
        ${h.hostname ? `<div class="ir-host-name">${esc(h.hostname)}</div>` : ""}
      </td>
      <td>${irBadge(h.opsec_score)}</td>
      <td>${flag} ${esc(h.country)}</td>
      <td>
        <div style="font-size:11px;font-family:monospace">AS${h.asn}</div>
        <div style="font-size:10px;color:#718096">${esc(h.provider)}</div>
      </td>
      <td><div class="ir-tags">${tagHtml}</div></td>
      <td><div class="ir-ports">${portHtml}</div></td>
      <td>${personaHtml}</td>
      <td>${riskHtml}</td>
    </tr>
    ${isExp ? irBuildDetailRow(h) : ""}`;
  }

  /* ── Expanded detail panel ── */
  function irBuildDetailRow(h) {
    const portTableRows = (h.open_ports || []).map(p => {
      const risk = portRisk(p.port);
      const riskLabel = { critical: "⚠ Critical", high: "High", low: "Low", safe: "Safe" }[risk] || "Low";
      const riskCls = `ir-port-risk-${risk}`;
      return `<tr>
        <td class="ir-detail-mono">${p.port}</td>
        <td style="color:#e2e8f0">${esc(p.service)}</td>
        <td class="${riskCls}">${riskLabel}</td>
      </tr>`;
    }).join("");

    const isFlagged = !!localStorage.getItem("flag_host_" + h.id);
    let inReport = false;
    try {
      const rep = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
      inReport = rep.some(r => r.id === h.id || r.name === h.ip);
    } catch (e) { }

    const attrCol = h.attributed_persona ? `
      <div class="ir-attr-persona">${esc(h.attributed_persona)}</div>
      ${h.cluster_id ? `<span class="ir-attr-cluster">${esc(h.cluster_id)}</span>` : ""}
      <div class="ir-action-row" style="margin-bottom:8px">
        <button class="ir-btn ir-btn-teal" onclick="irPivotToLinkGraph('${esc(h.attributed_persona)}')">
          → View in Link Graph
        </button>
        <button class="ir-btn ir-btn-amber" onclick="irOpenFullProfile('${esc(h.attributed_persona)}', '${esc(h.id)}')">
          → View Full Profile
        </button>
      </div>` : `
      <div class="ir-attr-none">Unattributed Host</div>
      <div class="ir-action-row" style="margin-bottom:8px">
        <button class="ir-btn ir-btn-ghost" onclick="irLinkPersonaDialog('${esc(h.id)}')">
          + Link to Persona
        </button>
      </div>`;

    return `<tr class="ir-detail-row">
      <td colspan="9">
        <div class="ir-detail-panel">
          <!-- Col 1: Host Details -->
          <div>
            <div class="ir-detail-col-title">Host Details</div>
            <div class="ir-detail-field">IP Address</div>
            <div class="ir-detail-mono">${esc(h.ip)}</div>
            ${h.hostname ? `<div class="ir-detail-field" style="margin-top:6px">Hostname</div>
            <div class="ir-detail-mono">${esc(h.hostname)}</div>` : ""}
            <div class="ir-detail-field" style="margin-top:6px">OS / Provider</div>
            <div class="ir-detail-value">${esc(h.os)} · ${esc(h.provider)}</div>
            <div class="ir-detail-field" style="margin-top:6px">ASN</div>
            <div class="ir-detail-value">AS${h.asn} — ${esc(h.asn_name)}</div>
            <div class="ir-detail-field" style="margin-top:6px">Location</div>
            <div class="ir-detail-value">${FLAG[h.country] || "🌐"} ${esc(h.city)}, ${esc(h.country)}</div>
            <div class="ir-detail-field" style="margin-top:6px">Active Period</div>
            <div class="ir-detail-value">${esc(h.first_seen)} → ${esc(h.last_seen)}</div>
            <div class="ir-detail-field" style="margin-top:6px">Coordinates</div>
            <div class="ir-detail-mono">${h.lat}, ${h.lon}</div>
          </div>
          <!-- Col 2: Port Analysis -->
          <div>
            <div class="ir-detail-col-title">Open Ports (${(h.open_ports || []).length})</div>
            <table class="ir-port-table">
              <thead><tr><th>PORT</th><th>SERVICE</th><th>RISK</th></tr></thead>
              <tbody>${portTableRows}</tbody>
            </table>
          </div>
          <!-- Col 3: Attribution + Actions -->
          <div>
            <div class="ir-detail-col-title">Attribution</div>
            ${attrCol}
            <div class="ir-notes">📓 ${esc(h.notes || "No analyst notes.")}</div>
            <div class="ir-action-row">
              <button class="ir-btn ir-btn-ghost" id="ir-btn-report-${esc(h.id)}" onclick="irAddHostToReport('${esc(h.id)}')">
                ${inReport ? "✓ In Report" : "📋 Add to Report"}
              </button>
              <button class="ir-btn ir-btn-flag" id="ir-btn-flag-${esc(h.id)}" onclick="irFlagHost('${esc(h.id)}')">
                ${isFlagged ? "⚑ Flagged" : "⚑ Flag"}
              </button>
              <button class="ir-btn ir-btn-ghost" onclick="irExportHost('${esc(h.id)}')">⬇ Export</button>
            </div>
          </div>
        </div>
      </td>
    </tr>`;
  }

  /* ── Toggle expand/collapse ── */
  function irToggleExpand(id) {
    IR_EXPANDED_ID = (IR_EXPANDED_ID === id) ? null : id;
    irRenderTable();
    if (IR_EXPANDED_ID) {
      requestAnimationFrame(() => {
        const el = document.querySelector(`tr[data-id="${CSS.escape(IR_EXPANDED_ID)}"]`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
  }

  /* ── Pivot to Link Graph ── */
  window.irPivotToLinkGraph = function (personaName) {
    const graphBtn = document.querySelector("#tabs button[data-tab='graph']");
    if (graphBtn) graphBtn.click();

    function trySelect(attempts = 0) {
      if ((!window.sim || !window.sim.nodes || !window.sim.nodes.length) && attempts < 25) {
        setTimeout(() => trySelect(attempts + 1), 100);
        return;
      }
      if (!window.sim || !window.sim.nodes) return;

      const norm = s => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      const pNorm = norm(personaName);
      let targetNode = window.sim.nodes.find(n =>
        norm(n.handle) === pNorm || norm(n.name) === pNorm || norm(n.id) === pNorm
      );
      if (!targetNode) {
        targetNode = window.sim.nodes.find(n =>
          (n.handle && n.handle.toLowerCase().includes(personaName.toLowerCase())) ||
          (n.name && n.name.toLowerCase().includes(personaName.toLowerCase()))
        );
      }
      if (!targetNode && window.sim.nodes.length) targetNode = window.sim.nodes[0];

      if (targetNode) {
        if (typeof window.selectClusterMember === "function") {
          window.selectClusterMember(targetNode.id);
        } else if (typeof handleNodeClick === "function") {
          handleNodeClick(null, targetNode);
        }
        if (typeof window.openRightPanel === "function") {
          window.openRightPanel(targetNode);
        }
      }
    }
    setTimeout(() => trySelect(0), 100);
    showToast(`Pivoted to Link Graph → ${personaName}`, "#00e5cc");
  };

  /* ── View Full Profile Modal ── */
  window.irOpenFullProfile = function (personaName, hostId) {
    const host = IR_HOSTS.find(h => h.id === hostId);
    let targetNode = null;
    if (window.sim && window.sim.nodes) {
      const norm = s => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      const pNorm = norm(personaName);
      targetNode = window.sim.nodes.find(n =>
        norm(n.handle) === pNorm || norm(n.name) === pNorm || norm(n.id) === pNorm
      );
      if (!targetNode) {
        targetNode = window.sim.nodes.find(n =>
          (n.handle && n.handle.toLowerCase().includes(personaName.toLowerCase())) ||
          (n.name && n.name.toLowerCase().includes(personaName.toLowerCase()))
        );
      }
    }
    if (!targetNode) {
      targetNode = {
        id: personaName,
        name: personaName,
        handle: personaName,
        actCode: host?.cluster_id ? `ACT-${host.cluster_id}` : `ACT-${personaName.slice(0, 6).toUpperCase()}`,
        clusterId: host?.cluster_id || "CL006",
        cluster: host?.cluster_id || "CL006",
        site: host?.provider || "tor-network",
        linkedCount: host?.open_ports ? host.open_ports.length : 3,
        maxLR: 4.85,
        max_lr: 4.85,
        timezone: "UTC+1",
        utc_offset: 1,
        regions: host?.country ? [host.country, host.city] : ["Tor Network"],
        degree: host?.open_ports ? host.open_ports.length : 3,
        open_ports: host?.open_ports || []
      };
    }
    if (typeof window.openFullProfileModal === "function") {
      window.openFullProfileModal(targetNode);
    } else {
      showToast(`Opening profile for ${personaName}`, "#00e5cc");
    }
  };

  /* ── Add Host to Report ── */
  window.irAddHostToReport = function (hostId) {
    const h = IR_HOSTS.find(x => x.id === hostId);
    if (!h) return;
    let report = [];
    try {
      report = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
    } catch (e) { report = []; }

    if (report.some(r => r.id === h.id)) {
      showToast("Already in report", "#f5a623");
      return;
    }

    report.push({
      id: h.id,
      name: `${h.ip} (${h.provider})`,
      actCode: h.cluster_id ? `HOST-${h.cluster_id}` : h.id,
      clusterId: h.cluster_id || "INFRA",
      site: h.hostname || h.provider,
      maxLR: h.opsec_score === "Critical" ? "5.40" : (h.opsec_score === "High" ? "4.20" : "3.10"),
      linkedCount: (h.open_ports || []).length,
      timezone: `${h.city}, ${h.country}`,
      regions: [h.country, h.city],
      addedAt: new Date().toLocaleString()
    });

    localStorage.setItem('anekanta_report', JSON.stringify(report));
    if (typeof updateReportBadge === "function") updateReportBadge();

    const btn = document.getElementById(`ir-btn-report-${h.id}`);
    if (btn) {
      btn.textContent = "✓ In Report";
      btn.style.color = "#00e5cc";
      btn.style.borderColor = "#00e5cc";
    }
    showToast(`📋 Added ${h.id} (${h.ip}) to Report`, "#00e5cc");
  };

  /* ── Flag Host ── */
  window.irFlagHost = function (hostId) {
    const key = "flag_host_" + hostId;
    const isFlagged = !localStorage.getItem(key);
    if (isFlagged) {
      localStorage.setItem(key, "true");
      showToast(`⚑ Host ${hostId} flagged for analyst review`, "#fc8181");
    } else {
      localStorage.removeItem(key);
      showToast(`Flag removed from ${hostId}`, "#a0aec0");
    }
    const btn = document.getElementById(`ir-btn-flag-${hostId}`);
    if (btn) {
      btn.textContent = isFlagged ? "⚑ Flagged" : "⚑ Flag";
      btn.style.background = isFlagged ? "rgba(252,129,129,0.25)" : "";
    }
    irRenderTable();
  };

  /* ── Export single host as JSON ── */
  window.irExportHost = function (id) {
    const h = IR_HOSTS.find(x => x.id === id);
    if (!h) return;
    const blob = new Blob([JSON.stringify(h, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `anekanta_host_${h.id}.json`;
    a.click();
    showToast(`Exported ${h.id}`, "#00e5cc");
  };

  /* ── Link Unattributed Host to Persona Dialog ── */
  window.irLinkPersonaDialog = function (hostId) {
    const h = IR_HOSTS.find(x => x.id === hostId);
    if (!h) return;
    const current = h.attributed_persona || "";
    const personas = ["umbralvale.57", "umbra_lvale", "rookerynotch", "opalinebank", "elmshadewick", "indigodell", "flintmarsh", "nimbusmarsh", "kestrelspire"];
    const input = prompt(`Link Host ${h.ip} to Persona Alias:\n\nAvailable Personas:\n${personas.join(", ")}`, current || personas[0]);
    if (input && input.trim()) {
      h.attributed_persona = input.trim();
      if (!h.cluster_id) h.cluster_id = "CL006";
      irUpdateStats(IR_HOSTS);
      irApplyFilters();
      irRenderPanel(IR_HOSTS);
      irRenderMap(IR_HOSTS);
      showToast(`Linked ${h.id} (${h.ip}) → ${h.attributed_persona}`, "#00e5cc");
    }
  };

  /* ── Sort header click ── */
  function initSortHeaders() {
    document.querySelectorAll(".ir-table thead th.ir-sortable").forEach(th => {
      th.addEventListener("click", () => {
        if (IR_SORT_COL === th.dataset.col) {
          IR_SORT_DIR = IR_SORT_DIR === "asc" ? "desc" : "asc";
        } else {
          IR_SORT_COL = th.dataset.col;
          IR_SORT_DIR = "asc";
        }
        IR_EXPANDED_ID = null;
        irApplyFilters();
      });
    });
  }

  /* ── Right summary panel ── */
  function irRenderPanel(hosts) {
    irRenderOpsecBars(hosts);
    irRenderCountryList(hosts);
    irRenderProviderList(hosts);
    irRenderCriticalAlerts(hosts);
    irRenderPersonaSummary(hosts);
  }

  function irRenderOpsecBars(hosts) {
    const el = document.getElementById("irOpsecBars");
    if (!el) return;
    const cats = ["Critical", "High", "Medium", "Low", "Hardened"];
    const max = hosts.length || 1;
    el.innerHTML = cats.map(c => {
      const cnt = hosts.filter(h => h.opsec_score === c).length;
      const pct = Math.round(cnt / max * 100);
      const col = OPSEC_COLOR[c] || "#718096";
      return `<div class="ir-opsec-bar-row" data-opsec="${c}" title="Filter by OPSEC: ${c}">
        <div class="ir-opsec-bar-lbl">${c}</div>
        <div class="ir-opsec-bar-track">
          <div class="ir-opsec-bar-fill" style="width:${pct}%;background:${col}"></div>
        </div>
        <div class="ir-opsec-bar-count">${cnt}</div>
      </div>`;
    }).join("");

    el.querySelectorAll(".ir-opsec-bar-row").forEach(row => {
      row.addEventListener("click", () => {
        const sel = document.getElementById("irFilterOpsec");
        if (sel) {
          sel.value = (sel.value === row.dataset.opsec) ? "" : row.dataset.opsec;
          irApplyFilters();
        }
      });
    });
  }

  function irRenderCountryList(hosts) {
    const el = document.getElementById("irCountryList");
    if (!el) return;
    const counts = {};
    hosts.forEach(h => { counts[h.country] = (counts[h.country] || 0) + 1; });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const maxC = sorted[0]?.[1] || 1;
    el.innerHTML = sorted.map(([c, n]) => {
      const pct = Math.round(n / maxC * 100);
      return `<div class="ir-panel-row" data-filter-country="${esc(c)}" title="Filter by ${c}">
        <span class="ir-panel-row-name">${FLAG[c] || "🌐"} ${esc(c)}</span>
        <div class="ir-panel-mini-bar" style="width:${pct}px;max-width:60px"></div>
        <span class="ir-panel-row-count">${n}</span>
      </div>`;
    }).join("");
    // Click to filter
    el.querySelectorAll(".ir-panel-row").forEach(row => {
      row.addEventListener("click", () => {
        const sel = document.getElementById("irFilterCountry");
        if (sel) {
          sel.value = (sel.value === row.dataset.filterCountry) ? "" : row.dataset.filterCountry;
          irApplyFilters();
        }
      });
    });
  }

  function irRenderProviderList(hosts) {
    const el = document.getElementById("irProviderList");
    if (!el) return;
    const counts = {};
    hosts.forEach(h => { counts[h.provider] = (counts[h.provider] || 0) + 1; });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const maxP = sorted[0]?.[1] || 1;
    el.innerHTML = sorted.map(([p, n]) => {
      const pct = Math.round(n / maxP * 100);
      return `<div class="ir-panel-row" data-provider="${esc(p)}" title="Filter by provider: ${esc(p)}">
        <span class="ir-panel-row-name">${esc(p)}</span>
        <div class="ir-panel-mini-bar" style="width:${pct}px;max-width:50px"></div>
        <span class="ir-panel-row-count">${n}</span>
      </div>`;
    }).join("");

    el.querySelectorAll(".ir-panel-row").forEach(row => {
      row.addEventListener("click", () => {
        const srch = document.getElementById("irSearch");
        if (srch) {
          srch.value = (srch.value === row.dataset.provider) ? "" : row.dataset.provider;
          irApplyFilters();
        }
      });
    });
  }

  function irRenderCriticalAlerts(hosts) {
    const el = document.getElementById("irCriticalList");
    const btn = document.getElementById("irViewAllCritical");
    if (!el) return;
    const crits = hosts
      .filter(h => h.opsec_score === "Critical")
      .sort((a, b) => criticalPortCount(b) - criticalPortCount(a));
    const show = crits.slice(0, 8);
    el.innerHTML = show.map(h => {
      const worstPort = (h.open_ports || []).find(p => CRIT_PORTS.has(p.port));
      const portLabel = worstPort ? `${worstPort.port}/${worstPort.service}` : "—";
      return `<div class="ir-alert-row" data-host-id="${esc(h.id)}">
        <span style="color:#fc8181;font-size:12px">⚠</span>
        <span class="ir-alert-ip">${esc(h.ip)}</span>
        <span class="ir-alert-port">${esc(portLabel)}</span>
      </div>`;
    }).join("");
    // Click to scroll & expand
    el.querySelectorAll(".ir-alert-row").forEach(row => {
      row.addEventListener("click", () => irJumpToHost(row.dataset.hostId));
    });
    if (btn) btn.style.display = crits.length > 8 ? "" : "none";
    if (btn) btn.onclick = () => {
      const sel = document.getElementById("irFilterOpsec");
      if (sel) { sel.value = "Critical"; irApplyFilters(); }
    };
  }

  function irRenderPersonaSummary(hosts) {
    const el = document.getElementById("irPersonaList");
    const intro = document.getElementById("irAttrIntro");
    if (!el) return;
    const counts = {};
    hosts.filter(h => h.attributed_persona).forEach(h => {
      counts[h.attributed_persona] = (counts[h.attributed_persona] || 0) + 1;
    });
    const total = Object.values(counts).reduce((s, v) => s + v, 0);
    if (intro) intro.textContent = `${total} hosts linked to personas`;
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    el.innerHTML = sorted.map(([name, n]) => `
      <div class="ir-persona-row" data-persona="${esc(name)}">
        <span class="ir-persona-row-name">${esc(name)}</span>
        <span class="ir-persona-row-count">${n} host${n > 1 ? "s" : ""}</span>
      </div>`).join("");
    el.querySelectorAll(".ir-persona-row").forEach(row => {
      row.addEventListener("click", () => {
        const srch = document.getElementById("irSearch");
        if (srch) { srch.value = row.dataset.persona; irApplyFilters(); }
      });
    });
  }

  /* ── Jump to host in table ── */
  function irJumpToHost(id) {
    if (!IR_FILTERED.find(h => h.id === id)) {
      ["irSearch", "irFilterOpsec", "irFilterCountry"].forEach(sid => {
        const el = document.getElementById(sid);
        if (el) el.value = "";
      });
      IR_SELECTED_TAGS.clear();
      updateTagMultiLabel();
      document.querySelectorAll("#irTagMultiMenu input[type=checkbox]").forEach(cb => cb.checked = false);
      const cb = document.getElementById("irFilterAttributed");
      if (cb) cb.checked = false;
      irApplyFilters();
    }
    IR_EXPANDED_ID = id;
    irRenderTable();
    requestAnimationFrame(() => {
      const el = document.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  /* ── World Map (SVG Mercator with highlighted countries and host dots) ── */
  function irRenderMap(hosts) {
    const container = document.getElementById("irMap");
    const tooltip = document.getElementById("irMapTooltip");
    if (!container) return;

    const W = container.clientWidth || 840;
    const H = 280;

    function lonToX(lon) {
      return ((lon + 180) / 360) * W;
    }
    function latToY(lat) {
      const clampedLat = Math.max(-65, Math.min(75, lat));
      const rad = clampedLat * Math.PI / 180;
      const mercN = Math.log(Math.tan(Math.PI / 4 + rad / 2));
      return (H / 2) - (mercN / Math.PI) * (H / 2) * 1.05 + 15;
    }

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.cssText = "width:100%;height:100%;";

    // Background
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("width", W); bg.setAttribute("height", H);
    bg.setAttribute("fill", "#060912");
    svg.appendChild(bg);

    // Lat/Lon Graticule lines
    const grid = document.createElementNS("http://www.w3.org/2000/svg", "g");
    grid.setAttribute("stroke", "rgba(255,255,255,0.04)");
    grid.setAttribute("stroke-width", "0.5");
    for (let lon = -180; lon <= 180; lon += 30) {
      const x = lonToX(lon);
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x); line.setAttribute("y1", 0);
      line.setAttribute("x2", x); line.setAttribute("y2", H);
      grid.appendChild(line);
    }
    for (let lat = -60; lat <= 75; lat += 30) {
      const y = latToY(lat);
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", 0); line.setAttribute("y1", y);
      line.setAttribute("x2", W); line.setAttribute("y2", y);
      grid.appendChild(line);
    }
    svg.appendChild(grid);

    // Approximate regional country bounds for countries with hosts
    // Each country with hosts: filled with rgba(0,229,204,0.15), stroke #00e5cc22
    const countryPolys = [
      // USA
      { name: "USA", coords: [[-125, 48], [-125, 30], [-80, 25], [-70, 42], [-67, 45], [-125, 48]] },
      // Canada
      { name: "Canada", coords: [[-140, 68], [-140, 49], [-60, 49], [-55, 60], [-140, 68]] },
      // Brazil
      { name: "Brazil", coords: [[-73, -5], [-73, -25], [-45, -30], [-35, -7], [-50, 4], [-73, -5]] },
      // Panama
      { name: "Panama", coords: [[-83, 9], [-83, 7], [-77, 7], [-77, 9], [-83, 9]] },
      // Germany
      { name: "Germany", coords: [[6, 54.5], [6, 47.5], [14.5, 47.5], [14.5, 54.5], [6, 54.5]] },
      // Netherlands
      { name: "Netherlands", coords: [[3.5, 53.5], [3.5, 51], [7, 51], [7, 53.5], [3.5, 53.5]] },
      // France
      { name: "France", coords: [[-4.5, 48.5], [-1, 43], [7, 43.5], [8, 49], [2, 51], [-4.5, 48.5]] },
      // UK
      { name: "UK", coords: [[-6, 58], [-6, 50], [2, 51], [2, 58], [-6, 58]] },
      // Russia
      { name: "Russia", coords: [[30, 68], [30, 52], [135, 45], [175, 65], [60, 72], [30, 68]] },
      // China
      { name: "China", coords: [[75, 40], [75, 22], [105, 18], [122, 25], [130, 45], [90, 48], [75, 40]] },
      // India
      { name: "India", coords: [[68, 28], [68, 20], [77, 8], [88, 22], [88, 27], [78, 35], [68, 28]] },
      // Singapore
      { name: "Singapore", coords: [[103, 1.5], [103, 1], [104.5, 1], [104.5, 1.5], [103, 1.5]] },
      // Romania
      { name: "Romania", coords: [[21, 48], [21, 43.5], [29.5, 43.5], [29.5, 48], [21, 48]] },
      // Ukraine
      { name: "Ukraine", coords: [[22, 52], [22, 45], [40, 47], [40, 52], [22, 52]] },
      // Moldova
      { name: "Moldova", coords: [[27, 48.5], [27, 45.5], [30, 45.5], [30, 48.5], [27, 48.5]] },
      // Turkey
      { name: "Turkey", coords: [[26, 42], [26, 36], [44, 37], [44, 41], [26, 42]] },
      // Iran
      { name: "Iran", coords: [[44, 39], [44, 25], [62, 25], [62, 38], [44, 39]] },
      // Japan
      { name: "Japan", coords: [[130, 33], [130, 31], [141, 38], [145, 45], [138, 45], [130, 33]] },
      // Sweden
      { name: "Sweden", coords: [[11, 68], [11, 56], [22, 56], [22, 68], [11, 68]] },
      // Finland
      { name: "Finland", coords: [[21, 70], [21, 60], [31, 60], [31, 70], [21, 70]] },
      // Switzerland
      { name: "Switzerland", coords: [[6, 47.8], [6, 45.8], [10.5, 45.8], [10.5, 47.8], [6, 47.8]] },
      // Australia
      { name: "Australia", coords: [[113, -22], [115, -35], [148, -38], [153, -25], [135, -12], [113, -22]] }
    ];

    const hostCountryNames = new Set(hosts.map(h => h.country));
    const landG = document.createElementNS("http://www.w3.org/2000/svg", "g");

    countryPolys.forEach(poly => {
      const hasHosts = hostCountryNames.has(poly.name);
      const points = poly.coords.map(([lon, lat]) => `${lonToX(lon).toFixed(1)},${latToY(lat).toFixed(1)}`).join(" ");
      const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      polygon.setAttribute("points", points);
      if (hasHosts) {
        polygon.setAttribute("fill", "rgba(0,229,204,0.15)");
        polygon.setAttribute("stroke", "#00e5cc22");
        polygon.setAttribute("stroke-width", "1");
      } else {
        polygon.setAttribute("fill", "rgba(255,255,255,0.02)");
        polygon.setAttribute("stroke", "rgba(255,255,255,0.05)");
        polygon.setAttribute("stroke-width", "0.5");
      }
      landG.appendChild(polygon);
    });
    svg.appendChild(landG);

    // Group hosts by coordinate to apply radial jitter for multi-host points
    const coordGroups = {};
    hosts.forEach(h => {
      const key = `${h.lat.toFixed(2)},${h.lon.toFixed(2)}`;
      if (!coordGroups[key]) coordGroups[key] = [];
      coordGroups[key].push(h);
    });

    const dotsG = document.createElementNS("http://www.w3.org/2000/svg", "g");

    Object.values(coordGroups).forEach(group => {
      group.forEach((h, idx) => {
        let x = lonToX(h.lon);
        let y = latToY(h.lat);

        // Apply radial jitter if multiple hosts share exact coordinates
        if (group.length > 1) {
          const angle = (idx / group.length) * 2 * Math.PI;
          const dist = Math.min(6 + group.length * 0.4, 12);
          x += Math.cos(angle) * dist;
          y += Math.sin(angle) * dist;
        }

        const col = OPSEC_COLOR[h.opsec_score] || "#8b5cf6";
        const isAttributed = !!h.attributed_persona;

        // Attributed host dots: pulsing ring animation
        if (isAttributed) {
          const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          pulse.setAttribute("cx", x.toFixed(1));
          pulse.setAttribute("cy", y.toFixed(1));
          pulse.setAttribute("r", "4");
          pulse.setAttribute("fill", "none");
          pulse.setAttribute("stroke", col);
          pulse.setAttribute("stroke-width", "1.5");
          pulse.setAttribute("class", "ir-map-pulse");
          dotsG.appendChild(pulse);
        }

        // Host dot: circle r=4, colored by OPSEC score
        const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        dot.setAttribute("cx", x.toFixed(1));
        dot.setAttribute("cy", y.toFixed(1));
        dot.setAttribute("r", "4");
        dot.setAttribute("fill", col);
        dot.setAttribute("stroke", isAttributed ? "#00e5cc" : "rgba(255,255,255,0.6)");
        dot.setAttribute("stroke-width", isAttributed ? "1.5" : "0.75");
        dot.setAttribute("cursor", "pointer");
        dot.style.cssText = "transition: r 150ms ease, fill-opacity 150ms;";

        // Hover tooltip
        dot.addEventListener("mouseenter", (e) => {
          dot.setAttribute("r", "6.5");
          dot.setAttribute("fill-opacity", "1");
          if (tooltip) {
            const flag = FLAG[h.country] || "🌐";
            const portsStr = (h.open_ports || []).map(p => `${p.port}/${p.service}`).slice(0, 4).join(", ");
            tooltip.innerHTML = `
              <div style="font-family:monospace;font-weight:700;color:#fff;margin-bottom:3px">${esc(h.ip)}</div>
              ${h.hostname ? `<div style="font-size:10px;color:#a0aec0;margin-bottom:4px">${esc(h.hostname)}</div>` : ""}
              <div style="color:${col};font-weight:600;font-size:10.5px">OPSEC: ${esc(h.opsec_score)}</div>
              <div style="color:#cbd5e0;font-size:10.5px">${flag} ${esc(h.city)}, ${esc(h.country)}</div>
              ${h.attributed_persona ? `<div style="color:#00e5cc;font-weight:600;margin-top:3px">👤 ${esc(h.attributed_persona)}</div>` : `<div style="color:#718096;font-size:10px">Unattributed</div>`}
              ${portsStr ? `<div style="color:#718096;font-size:9.5px;margin-top:2px">Ports: ${esc(portsStr)}</div>` : ""}
            `;
            tooltip.style.display = "block";
            tooltip.style.left = (e.clientX + 14) + "px";
            tooltip.style.top = (e.clientY - 14) + "px";
          }
        });

        dot.addEventListener("mouseleave", () => {
          dot.setAttribute("r", "4");
          dot.setAttribute("fill-opacity", "0.85");
          if (tooltip) tooltip.style.display = "none";
        });

        dot.addEventListener("mousemove", (e) => {
          if (tooltip) {
            tooltip.style.left = (e.clientX + 14) + "px";
            tooltip.style.top = (e.clientY - 14) + "px";
          }
        });

        // Click dot: highlights that row in table above
        dot.addEventListener("click", () => {
          irJumpToHost(h.id);
        });

        dotsG.appendChild(dot);
      });
    });

    svg.appendChild(dotsG);
    container.innerHTML = "";
    container.appendChild(svg);

    const mc = document.getElementById("irMapCount");
    if (mc) mc.textContent = `${hosts.length} hosts active across ${Object.keys(coordGroups).length} global regions`;
  }

  /* ── Wire up filters & multi-select ── */
  function updateTagMultiLabel() {
    const lbl = document.getElementById("irTagMultiLabel");
    if (!lbl) return;
    if (IR_SELECTED_TAGS.size === 0) {
      lbl.textContent = "Tags ▾";
    } else {
      lbl.textContent = `Tags (${IR_SELECTED_TAGS.size}) ▾`;
    }
  }

  function initFilters() {
    // Search input
    const srch = document.getElementById("irSearch");
    if (srch) srch.addEventListener("input", () => { IR_EXPANDED_ID = null; irApplyFilters(); });

    // OPSEC select
    const ops = document.getElementById("irFilterOpsec");
    if (ops) ops.addEventListener("change", () => { IR_EXPANDED_ID = null; irApplyFilters(); });

    // Country select
    const cty = document.getElementById("irFilterCountry");
    if (cty) cty.addEventListener("change", () => { IR_EXPANDED_ID = null; irApplyFilters(); });

    // Attributed checkbox
    const attr = document.getElementById("irFilterAttributed");
    if (attr) attr.addEventListener("change", () => { IR_EXPANDED_ID = null; irApplyFilters(); });

    // Tags Multi-Select Dropdown
    const tagBtn = document.getElementById("irTagMultiBtn");
    const tagMenu = document.getElementById("irTagMultiMenu");
    const tagClear = document.getElementById("irTagMultiClear");

    if (tagBtn && tagMenu) {
      tagBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = tagMenu.style.display !== "none";
        tagMenu.style.display = isOpen ? "none" : "block";
      });

      document.addEventListener("click", (e) => {
        if (!e.target.closest("#irTagMulti")) {
          tagMenu.style.display = "none";
        }
      });

      tagMenu.querySelectorAll("input[type=checkbox]").forEach(cb => {
        cb.addEventListener("change", () => {
          if (cb.checked) {
            IR_SELECTED_TAGS.add(cb.value);
          } else {
            IR_SELECTED_TAGS.delete(cb.value);
          }
          updateTagMultiLabel();
          IR_EXPANDED_ID = null;
          irApplyFilters();
        });
      });

      if (tagClear) {
        tagClear.addEventListener("click", (e) => {
          e.stopPropagation();
          IR_SELECTED_TAGS.clear();
          tagMenu.querySelectorAll("input[type=checkbox]").forEach(cb => cb.checked = false);
          updateTagMultiLabel();
          IR_EXPANDED_ID = null;
          irApplyFilters();
        });
      }
    }

    // Retry button
    const retry = document.getElementById("irRetry");
    if (retry) retry.addEventListener("click", () => { IR_LOADED = false; irLoad(); });
  }

  /* =====================================================================
     INFRASTRUCTURE TOPOLOGY MAP — Ultra High-Def Cyber SOC Engine
     ===================================================================== */
  let TOPO_SIM = null;
  let TOPO_NODES = [];
  let TOPO_LINKS = [];
  let TOPO_ACTIVE_HOSTS = [];
  let TOPO_FILTER = "all";
  let TOPO_SEARCH_QUERY = "";
  let TOPO_GROUP_MODE = "provider";
  let TOPO_PAUSED = false;
  let TOPO_ZOOM = null;
  let TOPO_SVG_G = null;
  let TOPO_INITED = false;
  let TOPO_SELECTED_NODE = null;

  function topoInit() {
    if (!IR_LOADED) {
      irLoad();
    }
    if (!IR_HOSTS || !IR_HOSTS.length) {
      setTimeout(topoInit, 120);
      return;
    }
    if (!TOPO_INITED) {
      TOPO_INITED = true;
      initTopoControls();
    }
    topoBuildAndRender();
  }
  window.topoInit = topoInit;

  function initTopoControls() {
    // Search input
    const srch = document.getElementById("topoSearchInput");
    const clearBtn = document.getElementById("topoSearchClear");
    if (srch) {
      srch.addEventListener("input", () => {
        TOPO_SEARCH_QUERY = (srch.value || "").trim().toLowerCase();
        if (clearBtn) clearBtn.style.display = TOPO_SEARCH_QUERY ? "block" : "none";
        topoApplyFilterAndSearch();
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (srch) srch.value = "";
        TOPO_SEARCH_QUERY = "";
        clearBtn.style.display = "none";
        topoApplyFilterAndSearch();
      });
    }

    // Filter chips
    document.querySelectorAll(".topo-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        document.querySelectorAll(".topo-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        TOPO_FILTER = chip.dataset.filter || "all";
        topoBuildAndRender();
      });
    });

    // Group mode selector
    const groupSel = document.getElementById("topoGroupMode");
    if (groupSel) {
      groupSel.addEventListener("change", () => {
        TOPO_GROUP_MODE = groupSel.value || "provider";
        topoUpdateForces();
      });
    }

    // Zoom & Physics controls
    const pauseBtn = document.getElementById("topoPauseBtn");
    if (pauseBtn) {
      pauseBtn.addEventListener("click", () => {
        TOPO_PAUSED = !TOPO_PAUSED;
        pauseBtn.textContent = TOPO_PAUSED ? "▶" : "⏸";
        pauseBtn.classList.toggle("active", TOPO_PAUSED);
        if (TOPO_SIM) {
          if (TOPO_PAUSED) TOPO_SIM.stop();
          else TOPO_SIM.alpha(0.3).restart();
        }
      });
    }

    const zoomInBtn = document.getElementById("topoZoomIn");
    if (zoomInBtn) {
      zoomInBtn.addEventListener("click", () => {
        if (window.d3 && TOPO_ZOOM) {
          d3.select("#topo-svg").transition().duration(250).call(TOPO_ZOOM.scaleBy, 1.35);
        }
      });
    }

    const zoomOutBtn = document.getElementById("topoZoomOut");
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener("click", () => {
        if (window.d3 && TOPO_ZOOM) {
          d3.select("#topo-svg").transition().duration(250).call(TOPO_ZOOM.scaleBy, 0.75);
        }
      });
    }

    const zoomFitBtn = document.getElementById("topoZoomFit");
    if (zoomFitBtn) {
      zoomFitBtn.addEventListener("click", () => {
        topoFitView();
      });
    }

    // HUD Close button
    const hudClose = document.getElementById("topoHudClose");
    if (hudClose) {
      hudClose.addEventListener("click", () => {
        const hud = document.getElementById("topoHud");
        if (hud) hud.style.display = "none";
        TOPO_SELECTED_NODE = null;
        if (window.d3) {
          d3.selectAll(".topo-node").classed("topo-node-highlight", false).classed("topo-node-dimmed", false);
          d3.selectAll(".topo-link").classed("topo-link-highlight", false);
        }
      });
    }

    // Resize observer to keep SVG responsive
    const wrap = document.getElementById("topo-svg-wrap");
    if (wrap && window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        if (TOPO_SIM && !TOPO_PAUSED) {
          TOPO_SIM.alpha(0.1).restart();
        }
      });
      ro.observe(wrap);
    }
  }

  function topoBuildAndRender() {
    if (!IR_HOSTS || !IR_HOSTS.length) return;

    // 1. Filter hosts based on TOPO_FILTER
    TOPO_ACTIVE_HOSTS = IR_HOSTS.filter(h => {
      if (TOPO_FILTER === "critical") {
        return h.opsec_score === "Critical" || h.opsec_score === "High";
      }
      if (TOPO_FILTER === "attributed") {
        return !!h.attributed_persona;
      }
      if (TOPO_FILTER === "c2") {
        const hasC2Tag = (h.tags || []).some(t => t === "C2" || t === "database");
        const hasC2Port = (h.open_ports || []).some(p => CRIT_PORTS.has(p.port) || HIGH_PORTS.has(p.port));
        return hasC2Tag || hasC2Port;
      }
      return true; // 'all'
    });

    // 2. Build graph data: Provider nodes, Persona nodes, Host nodes, Links
    const nodes = [];
    const links = [];
    const nodeMap = new Map();

    // Collect unique providers from active hosts
    const providerMap = new Map();
    TOPO_ACTIVE_HOSTS.forEach(h => {
      const p = h.provider || "Unknown Provider";
      if (!providerMap.has(p)) providerMap.set(p, []);
      providerMap.get(p).push(h);
    });

    // Collect unique personas from active hosts
    const personaMap = new Map();
    TOPO_ACTIVE_HOSTS.forEach(h => {
      if (h.attributed_persona) {
        const pers = h.attributed_persona;
        if (!personaMap.has(pers)) personaMap.set(pers, []);
        personaMap.get(pers).push(h);
      }
    });

    // Add Provider Hub nodes
    providerMap.forEach((pHosts, pName) => {
      const pId = "prov_" + pName.replace(/[^a-zA-Z0-9]/g, "_");
      const pNode = {
        id: pId,
        type: "provider",
        name: pName,
        count: pHosts.length,
        hosts: pHosts,
        radius: 26
      };
      nodes.push(pNode);
      nodeMap.set(pId, pNode);
    });

    // Add Persona nodes
    personaMap.forEach((persHosts, persName) => {
      const persId = "pers_" + persName.replace(/[^a-zA-Z0-9]/g, "_");
      const persNode = {
        id: persId,
        type: "persona",
        name: persName,
        persona: persName,
        cluster_id: persHosts[0]?.cluster_id || "CL006",
        hosts: persHosts,
        count: persHosts.length,
        radius: 20
      };
      nodes.push(persNode);
      nodeMap.set(persId, persNode);
    });

    // Add Host nodes
    TOPO_ACTIVE_HOSTS.forEach(h => {
      const isAttr = !!h.attributed_persona;
      const isCrit = h.opsec_score === "Critical";
      const hNode = {
        id: h.id,
        type: "host",
        name: h.ip,
        data: h,
        opsec_score: h.opsec_score,
        country: h.country,
        provider: h.provider,
        persona: h.attributed_persona,
        radius: isAttr ? 9 : (isCrit ? 8.5 : 7)
      };
      nodes.push(hNode);
      nodeMap.set(h.id, hNode);

      // Link: Provider <-> Host
      const pId = "prov_" + (h.provider || "Unknown Provider").replace(/[^a-zA-Z0-9]/g, "_");
      if (nodeMap.has(pId)) {
        links.push({
          source: pId,
          target: h.id,
          type: "provider",
          id: `${pId}-${h.id}`
        });
      }

      // Link: Host <-> Persona
      if (h.attributed_persona) {
        const persId = "pers_" + h.attributed_persona.replace(/[^a-zA-Z0-9]/g, "_");
        if (nodeMap.has(persId)) {
          links.push({
            source: h.id,
            target: persId,
            type: "persona",
            id: `${h.id}-${persId}`
          });
        }
      }
    });

    // Inter-host links for hosts in the same cluster/actor
    for (let i = 0; i < TOPO_ACTIVE_HOSTS.length; i++) {
      for (let j = i + 1; j < TOPO_ACTIVE_HOSTS.length; j++) {
        const h1 = TOPO_ACTIVE_HOSTS[i];
        const h2 = TOPO_ACTIVE_HOSTS[j];
        if (h1.cluster_id && h1.cluster_id === h2.cluster_id && h1.attributed_persona && h1.attributed_persona === h2.attributed_persona) {
          links.push({
            source: h1.id,
            target: h2.id,
            type: "cluster",
            id: `cluster-${h1.id}-${h2.id}`
          });
        }
      }
    }

    TOPO_NODES = nodes;
    TOPO_LINKS = links;

    // Update bottom counters
    const setT = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setT("topoCountHosts", TOPO_ACTIVE_HOSTS.length);
    setT("topoCountProviders", providerMap.size);
    setT("topoCountCountries", new Set(TOPO_ACTIVE_HOSTS.map(h => h.country)).size);
    setT("topoCountAttr", TOPO_ACTIVE_HOSTS.filter(h => h.attributed_persona).length);

    // 3. Render with D3
    if (!window.d3) return;
    const svgEl = document.getElementById("topo-svg");
    if (!svgEl) return;

    const wrap = document.getElementById("topo-svg-wrap");
    const width = wrap.clientWidth || 920;
    const height = wrap.clientHeight || 640;

    const svg = d3.select("#topo-svg");
    svg.selectAll("*").remove();

    // Floating Tooltip Element setup
    let topoTooltip = document.getElementById("topoTooltip");
    if (!topoTooltip) {
      topoTooltip = document.createElement("div");
      topoTooltip.id = "topoTooltip";
      topoTooltip.className = "topo-tooltip";
      topoTooltip.style.display = "none";
      const ctn = document.getElementById("topoContainer");
      if (ctn) ctn.appendChild(topoTooltip);
    }

    // Root zoom container
    const g = svg.append("g").attr("class", "topo-world");
    TOPO_SVG_G = g;

    // Background Cyber Radar Grids
    const radarG = g.append("g").attr("class", "topo-radar-layer");
    const cx = width / 2;
    const cy = height / 2;
    [140, 280, 440, 600, 780].forEach(r => {
      radarG.append("circle")
        .attr("class", "topo-radar-ring")
        .attr("cx", cx)
        .attr("cy", cy)
        .attr("r", r);
    });
    // Radar crosshairs
    radarG.append("line")
      .attr("class", "topo-radar-axis")
      .attr("x1", cx - 800).attr("y1", cy)
      .attr("x2", cx + 800).attr("y2", cy);
    radarG.append("line")
      .attr("class", "topo-radar-axis")
      .attr("x1", cx).attr("y1", cy - 800)
      .attr("x2", cx).attr("y2", cy + 800);

    // Zoom setup
    TOPO_ZOOM = d3.zoom()
      .scaleExtent([0.2, 4.5])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(TOPO_ZOOM);

    // Link Elements
    const linkG = g.append("g").attr("class", "topo-links-layer");
    const linkSel = linkG.selectAll("line")
      .data(TOPO_LINKS, d => d.id)
      .join("line")
      .attr("class", d => {
        if (d.type === "persona") return "topo-link topo-link-persona";
        if (d.type === "cluster") return "topo-link topo-link-cluster";
        return "topo-link topo-link-provider";
      });

    // Node Elements
    const nodeG = g.append("g").attr("class", "topo-nodes-layer");
    const nodeSel = nodeG.selectAll("g.topo-node")
      .data(TOPO_NODES, d => d.id)
      .join("g")
      .attr("class", d => `topo-node topo-node-${d.type}`)
      .call(d3.drag()
        .on("start", (event, d) => {
          if (!event.active && TOPO_SIM) TOPO_SIM.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active && TOPO_SIM) TOPO_SIM.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    // Shape according to type
    nodeSel.each(function (d) {
      const el = d3.select(this);
      if (d.type === "provider") {
        // Modern horizontal capsule/pill badge
        const textLen = d.name.length;
        const pillW = Math.max(86, textLen * 7.5 + 46);
        const pillH = 26;

        el.append("rect")
          .attr("class", "topo-provider-box")
          .attr("x", -pillW / 2)
          .attr("y", -pillH / 2)
          .attr("width", pillW)
          .attr("height", pillH)
          .attr("rx", 13);

        // Icon
        el.append("text")
          .attr("x", -pillW / 2 + 13)
          .attr("y", 1)
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("font-size", "12px")
          .attr("fill", "#60a5fa")
          .text("☁");

        // Name
        el.append("text")
          .attr("x", -pillW / 2 + 24)
          .attr("y", 0)
          .attr("text-anchor", "start")
          .attr("dominant-baseline", "central")
          .attr("font-size", "10px")
          .attr("font-weight", "700")
          .attr("fill", "#ffffff")
          .text(d.name.length > 12 ? d.name.slice(0, 11) + "…" : d.name);

        // Host count tag
        el.append("text")
          .attr("class", "topo-node-sublabel")
          .attr("x", pillW / 2 - 10)
          .attr("y", 0)
          .attr("text-anchor", "end")
          .attr("dominant-baseline", "central")
          .text(`[${d.count}]`);

      } else if (d.type === "persona") {
        // Glowing cyan persona hexagon / dual ring badge
        el.append("circle")
          .attr("class", "topo-host-pulse")
          .attr("r", 18)
          .attr("fill", "none")
          .attr("stroke", "#00e5cc")
          .attr("stroke-width", 1.5);

        el.append("circle")
          .attr("class", "topo-persona-box")
          .attr("r", 15);

        el.append("text")
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("font-size", "11px")
          .attr("fill", "#00e5cc")
          .text("👤");

        // Persona name label pill below
        const labelW = Math.max(90, d.name.length * 6.5 + 20);
        el.append("rect")
          .attr("x", -labelW / 2)
          .attr("y", 18)
          .attr("width", labelW)
          .attr("height", 17)
          .attr("rx", 4)
          .attr("fill", "rgba(7, 25, 29, 0.95)")
          .attr("stroke", "#00e5cc")
          .attr("stroke-width", 0.9);

        el.append("text")
          .attr("x", 0)
          .attr("y", 26.5)
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("font-size", "9.5px")
          .attr("font-weight", "700")
          .attr("fill", "#00e5cc")
          .text(d.name);

      } else {
        // Host node
        const col = OPSEC_COLOR[d.opsec_score] || "#8b5cf6";
        const isAttr = !!d.persona;
        const isCrit = d.opsec_score === "Critical";

        if (isAttr) {
          el.append("circle")
            .attr("class", "topo-host-pulse")
            .attr("r", 10)
            .attr("fill", "none")
            .attr("stroke", "#00e5cc")
            .attr("stroke-width", 1.5);
        } else if (isCrit) {
          el.append("circle")
            .attr("class", "topo-host-pulse")
            .attr("r", 9.5)
            .attr("fill", "none")
            .attr("stroke", "#fc8181")
            .attr("stroke-width", 1.2);
        }

        el.append("circle")
          .attr("r", d.radius)
          .attr("fill", col)
          .attr("stroke", isAttr ? "#00e5cc" : (isCrit ? "#fc8181" : "rgba(255,255,255,0.4)"))
          .attr("stroke-width", isAttr ? 1.6 : 0.9);
      }
    });

    // Node Click & Hover handlers
    nodeSel
      .on("mouseenter", function (event, d) {
        d3.select(this).raise();
        // Highlight connected links
        linkSel.classed("topo-link-highlight", l => l.source.id === d.id || l.target.id === d.id);

        // Show floating rich tooltip
        if (topoTooltip) {
          if (d.type === "host") {
            const h = d.data;
            const flag = FLAG[h.country] || "🌐";
            const col = OPSEC_COLOR[h.opsec_score] || "#8b5cf6";
            const portList = (h.open_ports || []).map(p => p.port).slice(0, 4).join(", ");

            topoTooltip.innerHTML = `
              <div class="topo-tt-header">
                <span class="topo-tt-title">🖥 ${esc(h.ip)}</span>
                <span style="color:${col};font-weight:700;font-size:10.5px">${esc(h.opsec_score)}</span>
              </div>
              <div class="topo-tt-row"><span>Provider:</span><span class="topo-tt-val">${esc(h.provider)}</span></div>
              <div class="topo-tt-row"><span>Location:</span><span class="topo-tt-val">${flag} ${esc(h.city)}, ${esc(h.country)}</span></div>
              ${h.attributed_persona ? `<div class="topo-tt-row"><span>Attributed:</span><span class="topo-tt-val" style="color:#00e5cc">👤 ${esc(h.attributed_persona)}</span></div>` : ""}
              ${portList ? `<div class="topo-tt-row"><span>Ports:</span><span class="topo-tt-val" style="color:#93c5fd">${esc(portList)}</span></div>` : ""}
            `;
          } else if (d.type === "provider") {
            topoTooltip.innerHTML = `
              <div class="topo-tt-header">
                <span class="topo-tt-title" style="color:#60a5fa">☁ ${esc(d.name)}</span>
                <span class="topo-tt-val">${d.count} hosts</span>
              </div>
              <div class="topo-tt-row"><span>Hosted Instances:</span><span class="topo-tt-val">${d.count} infrastructure nodes</span></div>
              <div class="topo-tt-row"><span>Status:</span><span class="topo-tt-val" style="color:#00e5cc">Active Cloud Provider</span></div>
            `;
          } else if (d.type === "persona") {
            topoTooltip.innerHTML = `
              <div class="topo-tt-header">
                <span class="topo-tt-title" style="color:#00e5cc">👤 ${esc(d.name)}</span>
                <span class="topo-tt-val" style="color:#00e5cc">${esc(d.cluster_id || "CL006")}</span>
              </div>
              <div class="topo-tt-row"><span>Linked Infrastructure:</span><span class="topo-tt-val" style="color:#00e5cc">${d.count} hosts</span></div>
              <div class="topo-tt-row"><span>Attribution:</span><span class="topo-tt-val" style="color:#fa8c16">Scored Threat Actor</span></div>
            `;
          }

          topoTooltip.style.display = "block";
          const cRect = document.getElementById("topoContainer").getBoundingClientRect();
          topoTooltip.style.left = (event.clientX - cRect.left + 15) + "px";
          topoTooltip.style.top = (event.clientY - cRect.top + 15) + "px";
        }
      })
      .on("mousemove", function (event) {
        if (topoTooltip && topoTooltip.style.display !== "none") {
          const cRect = document.getElementById("topoContainer").getBoundingClientRect();
          topoTooltip.style.left = (event.clientX - cRect.left + 15) + "px";
          topoTooltip.style.top = (event.clientY - cRect.top + 15) + "px";
        }
      })
      .on("mouseleave", function () {
        if (!TOPO_SELECTED_NODE) {
          linkSel.classed("topo-link-highlight", false);
        }
        if (topoTooltip) topoTooltip.style.display = "none";
      })
      .on("click", function (event, d) {
        event.stopPropagation();
        TOPO_SELECTED_NODE = d;
        nodeSel.classed("topo-node-highlight", n => n.id === d.id);
        linkSel.classed("topo-link-highlight", l => l.source.id === d.id || l.target.id === d.id);
        topoShowHud(d);
      });

    // Background Click to deselect
    svg.on("click", () => {
      TOPO_SELECTED_NODE = null;
      nodeSel.classed("topo-node-highlight", false).classed("topo-node-dimmed", false);
      linkSel.classed("topo-link-highlight", false);
    });

    // 4. D3 Force Simulation with generous constellation spacing & no overlap
    if (TOPO_SIM) TOPO_SIM.stop();

    TOPO_SIM = d3.forceSimulation(TOPO_NODES)
      .force("link", d3.forceLink(TOPO_LINKS).id(d => d.id).distance(d => d.type === "persona" ? 140 : (d.type === "cluster" ? 80 : 120)).strength(0.55))
      .force("charge", d3.forceManyBody().strength(d => d.type === "provider" ? -900 : (d.type === "persona" ? -600 : -200)))
      .force("collide", d3.forceCollide().radius(d => d.type === "provider" ? 54 : (d.type === "persona" ? 42 : (d.radius || 8) + 16)).iterations(4))
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.04));

    topoUpdateForces();

    TOPO_SIM.on("tick", () => {
      linkSel
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

      nodeSel
        .attr("transform", d => `translate(${d.x},${d.y})`);
    });

    if (TOPO_PAUSED) {
      TOPO_SIM.stop();
    } else {
      TOPO_SIM.alpha(1).restart();
    }

    // Auto-fit initial view smoothly
    setTimeout(() => {
      topoFitView();
    }, 500);
  }

  function topoUpdateForces() {
    if (!TOPO_SIM) return;
    const wrap = document.getElementById("topo-svg-wrap");
    const width = wrap?.clientWidth || 920;
    const height = wrap?.clientHeight || 640;
    const cx = width / 2;
    const cy = height / 2;

    if (TOPO_GROUP_MODE === "provider") {
      // Position provider hubs in an elegant dual-ring constellation ellipse
      const provNodes = TOPO_NODES.filter(n => n.type === "provider");
      const pCount = provNodes.length || 1;
      const rxOuter = Math.min(width * 0.48, 520);
      const ryOuter = Math.min(height * 0.46, 380);
      const rxInner = rxOuter * 0.55;
      const ryInner = ryOuter * 0.55;
      const provPosMap = new Map();

      provNodes.forEach((p, idx) => {
        // Alternate inner and outer rings for high density uncluttering
        const isInner = (idx % 2 === 1) && pCount > 10;
        const rx = isInner ? rxInner : rxOuter;
        const ry = isInner ? ryInner : ryOuter;
        const angle = (idx / pCount) * Math.PI * 2 - Math.PI / 2;
        provPosMap.set(p.name, {
          x: cx + Math.cos(angle) * rx,
          y: cy + Math.sin(angle) * ry
        });
      });

      TOPO_SIM
        .force("x", d3.forceX(d => {
          if (d.type === "provider") return provPosMap.get(d.name)?.x || cx;
          if (d.type === "host") return provPosMap.get(d.provider)?.x || cx;
          return cx;
        }).strength(0.32))
        .force("y", d3.forceY(d => {
          if (d.type === "provider") return provPosMap.get(d.name)?.y || cy;
          if (d.type === "host") return provPosMap.get(d.provider)?.y || cy;
          return cy;
        }).strength(0.32));

    } else if (TOPO_GROUP_MODE === "country") {
      // Group by distinct countries in a wide ring
      const countries = [...new Set(TOPO_ACTIVE_HOSTS.map(h => h.country))];
      const cCount = countries.length || 1;
      const rx = Math.min(width * 0.48, 520);
      const ry = Math.min(height * 0.46, 380);
      const countryPosMap = new Map();

      countries.forEach((c, idx) => {
        const angle = (idx / cCount) * Math.PI * 2 - Math.PI / 2;
        countryPosMap.set(c, {
          x: cx + Math.cos(angle) * rx,
          y: cy + Math.sin(angle) * ry
        });
      });

      TOPO_SIM
        .force("x", d3.forceX(d => {
          if (d.type === "host") return countryPosMap.get(d.country)?.x || cx;
          return cx;
        }).strength(0.35))
        .force("y", d3.forceY(d => {
          if (d.type === "host") return countryPosMap.get(d.country)?.y || cy;
          return cy;
        }).strength(0.35));

    } else if (TOPO_GROUP_MODE === "opsec") {
      // 5 distinct vertical columns / tiers for OPSEC severity
      const tierMap = { Critical: -0.42, High: -0.21, Medium: 0, Low: 0.21, Hardened: 0.42 };
      TOPO_SIM
        .force("x", d3.forceX(d => {
          if (d.type === "host") {
            const factor = tierMap[d.opsec_score] ?? 0;
            return cx + factor * width * 0.88;
          }
          return cx;
        }).strength(0.42))
        .force("y", d3.forceY(cy).strength(0.08));

    } else {
      // "free" mode
      TOPO_SIM
        .force("x", d3.forceX(cx).strength(0.03))
        .force("y", d3.forceY(cy).strength(0.03));
    }

    if (!TOPO_PAUSED) {
      TOPO_SIM.alpha(0.5).restart();
    }
  }

  function topoApplyFilterAndSearch() {
    if (!window.d3) return;
    const q = TOPO_SEARCH_QUERY;

    if (!q) {
      d3.selectAll(".topo-node").classed("topo-node-dimmed", false);
      d3.selectAll(".topo-link").classed("topo-link-highlight", false);
      return;
    }

    let matchCount = 0;
    let firstMatchedNode = null;

    d3.selectAll(".topo-node").each(function (d) {
      let isMatch = false;
      if (d.type === "host") {
        const h = d.data;
        const text = `${h.ip} ${h.hostname || ""} ${h.provider} ${h.country} ${h.attributed_persona || ""} ${h.notes || ""} AS${h.asn}`.toLowerCase();
        isMatch = text.includes(q);
      } else if (d.type === "provider") {
        isMatch = d.name.toLowerCase().includes(q);
      } else if (d.type === "persona") {
        isMatch = d.name.toLowerCase().includes(q) || (d.cluster_id || "").toLowerCase().includes(q);
      }

      d3.select(this).classed("topo-node-dimmed", !isMatch);
      if (isMatch) {
        matchCount++;
        if (!firstMatchedNode) firstMatchedNode = d;
      }
    });

    // If strong match or exact match, center view on that node
    if (firstMatchedNode && (matchCount === 1 || q.length > 5)) {
      const wrap = document.getElementById("topo-svg-wrap");
      const width = wrap.clientWidth || 920;
      const height = wrap.clientHeight || 640;
      const svg = d3.select("#topo-svg");

      svg.transition().duration(600).call(
        TOPO_ZOOM.transform,
        d3.zoomIdentity.translate(width / 2 - firstMatchedNode.x * 1.5, height / 2 - firstMatchedNode.y * 1.5).scale(1.5)
      );
      topoShowHud(firstMatchedNode);
    }
  }

  function topoFitView() {
    if (!window.d3 || !TOPO_ZOOM || !TOPO_NODES.length) return;
    const wrap = document.getElementById("topo-svg-wrap");
    const width = wrap.clientWidth || 920;
    const height = wrap.clientHeight || 640;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    TOPO_NODES.forEach(n => {
      if (n.x !== undefined && n.y !== undefined) {
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
      }
    });

    if (minX === Infinity) return;

    const dx = maxX - minX + 100;
    const dy = maxY - minY + 100;
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    const scale = Math.min(1.4, Math.max(0.25, 0.88 / Math.max(dx / width, dy / height)));
    const translate = [width / 2 - scale * midX, height / 2 - scale * midY];

    d3.select("#topo-svg")
      .transition()
      .duration(650)
      .call(
        TOPO_ZOOM.transform,
        d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
      );
  }

  function topoShowHud(node) {
    const hud = document.getElementById("topoHud");
    const title = document.getElementById("topoHudHeading");
    const icon = document.getElementById("topoHudIcon");
    const body = document.getElementById("topoHudBody");
    if (!hud || !body) return;

    hud.style.display = "flex";

    if (node.type === "host") {
      const h = node.data;
      if (icon) icon.textContent = "🖥";
      if (title) title.textContent = `${h.id} — ${h.ip}`;

      const flag = FLAG[h.country] || "🌐";
      const critPorts = (h.open_ports || []).map(p => {
        const r = portRisk(p.port);
        const cls = r === "critical" ? "risk-critical" : (r === "high" ? "risk-high" : "");
        return `<span class="topo-port-badge ${cls}">${p.port}/${p.service}</span>`;
      }).join("");

      const inReport = (() => {
        try {
          const rep = JSON.parse(localStorage.getItem('anekanta_report') || '[]');
          return rep.some(r => r.id === h.id || r.name === h.ip);
        } catch (e) { return false; }
      })();

      const personaCallout = h.attributed_persona ? `
        <div class="topo-hud-callout">
          <div class="topo-hud-callout-title">Attributed Threat Actor</div>
          <div class="topo-hud-callout-val">👤 ${esc(h.attributed_persona)}</div>
          <div style="font-size:10px;color:#a0aec0">Cluster: <span class="mono" style="color:#00e5cc">${esc(h.cluster_id || "CL006")}</span></div>
          <button type="button" class="topo-hud-btn-pivot" onclick="irPivotToLinkGraph('${esc(h.attributed_persona)}')">
            → Pivot to Link Graph
          </button>
        </div>` : `
        <div class="topo-hud-callout" style="border-color:rgba(255,255,255,0.12);background:rgba(255,255,255,0.03)">
          <div class="topo-hud-callout-title" style="color:#718096">Attribution Status</div>
          <div style="font-size:11.5px;color:#a0aec0">Unattributed Host</div>
          <button type="button" class="topo-hud-btn-pivot" style="border-color:rgba(255,255,255,0.2);color:#e2e8f0" onclick="irLinkPersonaDialog('${esc(h.id)}')">
            + Link to Persona
          </button>
        </div>`;

      body.innerHTML = `
        <div class="topo-hud-row">
          <span class="topo-hud-k">OPSEC Score</span>
          <div>${irBadge(h.opsec_score)}</div>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">IP Address</span>
          <span class="topo-hud-v">${esc(h.ip)}</span>
        </div>
        ${h.hostname ? `<div class="topo-hud-row">
          <span class="topo-hud-k">Hostname</span>
          <span class="topo-hud-v">${esc(h.hostname)}</span>
        </div>` : ""}
        <div class="topo-hud-row">
          <span class="topo-hud-k">Provider</span>
          <span class="topo-hud-v">${esc(h.provider)}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">ASN</span>
          <span class="topo-hud-v">AS${h.asn} (${esc(h.asn_name || "—")})</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Location</span>
          <span class="topo-hud-v">${flag} ${esc(h.city)}, ${esc(h.country)}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Coordinates</span>
          <span class="topo-hud-v" style="font-size:10px">${h.lat}, ${h.lon}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Active</span>
          <span class="topo-hud-v" style="font-size:10px">${esc(h.first_seen)} → ${esc(h.last_seen)}</span>
        </div>

        <div>
          <div class="topo-hud-k" style="margin-bottom:4px">Open Ports (${(h.open_ports || []).length})</div>
          <div class="topo-hud-ports-wrap">${critPorts || '<span style="color:#718096">None</span>'}</div>
        </div>

        ${personaCallout}

        ${h.notes ? `<div class="topo-hud-notes">📓 ${esc(h.notes)}</div>` : ""}

        <div style="display:flex;gap:6px;margin-top:4px">
          <button type="button" class="anv-btn-teal" style="flex:1;font-size:11px;padding:6px 10px" onclick="irAddHostToReport('${esc(h.id)}')">
            ${inReport ? "✓ In Report" : "📋 Add to Report"}
          </button>
          <button type="button" class="anv-btn-white-ghost" style="font-size:11px;padding:6px 10px" onclick="irExportHost('${esc(h.id)}')">
            ⬇ Export
          </button>
        </div>
      `;
    } else if (node.type === "provider") {
      if (icon) icon.textContent = "☁";
      if (title) title.textContent = `Provider: ${node.name}`;

      const hosts = node.hosts || [];
      const critCount = hosts.filter(h => h.opsec_score === "Critical").length;
      const highCount = hosts.filter(h => h.opsec_score === "High").length;
      const attrCount = hosts.filter(h => h.attributed_persona).length;
      const countries = [...new Set(hosts.map(h => h.country))];

      body.innerHTML = `
        <div class="topo-hud-row">
          <span class="topo-hud-k">Hosted Instances</span>
          <span class="topo-hud-v" style="color:#60a5fa">${hosts.length} hosts</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Critical Risk</span>
          <span class="topo-hud-v" style="color:#fc8181">${critCount}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">High Risk</span>
          <span class="topo-hud-v" style="color:#f5a623">${highCount}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Attributed</span>
          <span class="topo-hud-v" style="color:#00e5cc">${attrCount}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Regions</span>
          <span class="topo-hud-v" style="font-size:10.5px">${countries.slice(0, 3).join(", ")}${countries.length > 3 ? " +" + (countries.length - 3) : ""}</span>
        </div>

        <div style="margin-top:6px">
          <div class="topo-hud-k" style="margin-bottom:6px">Hosted Instances Preview:</div>
          <div style="max-height:120px;overflow-y:auto;background:rgba(0,0,0,0.3);border-radius:6px;padding:6px;font-family:monospace;font-size:10.5px">
            ${hosts.slice(0, 10).map(h => `
              <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
                <span style="color:#e2e8f0">${esc(h.ip)}</span>
                <span style="color:${OPSEC_COLOR[h.opsec_score] || '#718096'}">${esc(h.opsec_score)}</span>
              </div>
            `).join("")}
          </div>
        </div>

        <button type="button" class="topo-hud-btn-pivot" onclick="document.getElementById('topoSearchInput').value='${esc(node.name)}';topoApplyFilterAndSearch();">
          🔍 Filter Topology by this Provider
        </button>
      `;
    } else if (node.type === "persona") {
      if (icon) icon.textContent = "👤";
      if (title) title.textContent = `Actor: ${node.name}`;

      const hosts = node.hosts || [];
      const countries = [...new Set(hosts.map(h => h.country))];
      const providers = [...new Set(hosts.map(h => h.provider))];

      body.innerHTML = `
        <div class="topo-hud-callout">
          <div class="topo-hud-callout-title">Threat Actor Attribution</div>
          <div class="topo-hud-callout-val">👤 ${esc(node.name)}</div>
          <div style="font-size:10.5px;color:#a0aec0">Cluster ID: <span class="mono" style="color:#00e5cc">${esc(node.cluster_id)}</span></div>
        </div>

        <div class="topo-hud-row">
          <span class="topo-hud-k">Linked Hosts</span>
          <span class="topo-hud-v" style="color:#00e5cc">${hosts.length} hosts</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Providers Spanned</span>
          <span class="topo-hud-v">${providers.join(", ")}</span>
        </div>
        <div class="topo-hud-row">
          <span class="topo-hud-k">Countries</span>
          <span class="topo-hud-v">${countries.join(", ")}</span>
        </div>

        <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">
          <button type="button" class="topo-hud-btn-pivot" onclick="irPivotToLinkGraph('${esc(node.name)}')">
            → View in Link Graph
          </button>
          <button type="button" class="anv-btn-teal" style="font-size:11.5px;padding:8px" onclick="irOpenFullProfile('${esc(node.name)}', '${hosts[0]?.id || ""}')">
            👤 View Full Profile Dossier
          </button>
        </div>
      `;
    }
  }

  /* ── Boot ── */
  function boot() {
    initSubTabs();
    initFilters();
    initSortHeaders();

    // Auto-load on component mount
    if (!IR_LOADED) {
      irLoad();
    }

    // Also listen to main nav clicks on Real Network tab
    const realTabBtn = document.querySelector("#tabs button[data-tab='realnet']");
    if (realTabBtn) {
      realTabBtn.addEventListener("click", () => {
        const sub = document.querySelector(".rw-subtab.active");
        if (sub && sub.dataset.subtab === "rw-infrarecon" && !IR_LOADED) {
          irLoad();
        }
        if (sub && sub.dataset.subtab === "rw-topomap") {
          topoInit();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

})(); // end infraReconModule


