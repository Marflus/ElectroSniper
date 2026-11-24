const state = {
  statusTab: "active",
  search: "",
  site: "all",
  category: "all",
  sort: "score",
  onlyOpened: false,
  page: 1,
  pageSize: 20,
  totalPages: 1,
  totalItems: 0,
  selectedId: null,
  countdownSec: null,
  isPaused: false,
  isScanning: false,
};

const CAT_LABELS = {
  consoles: "Consoles & Manettes",
  informatique: "Informatique",
  outillage: "Outillage",
  audio: "Audio & Hi-Fi",
  photo: "Photo & Drone",
  petit_electro: "Petit Électro",
  tablettes: "Tablettes",
  autre: "Autre",
};

// Pastilles de site en SVG inline : aucun appel réseau, rendu net à toutes les tailles
const SITE_LOGOS = {
  leboncoin: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="#ff6e14"/><text x="12" y="16" text-anchor="middle" font-family="Arial, sans-serif" font-size="9.5" font-weight="700" fill="#fff">lbc</text></svg>`,
  vinted: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="#09b1ba"/><text x="12" y="17.5" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#fff">V</text></svg>`,
  facebook: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="12" fill="#1877f2"/><text x="12.6" y="19" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#fff">f</text></svg>`,
  ebay: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="#fff"/><text x="12" y="16.5" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#e53238">e</text></svg>`,
};

const ICONS = {
  truck: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
  pin: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`,
  wrench: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
  alert: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  ban: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`,
  star: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  starFill: `<svg class="ic-sm" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  eyeOff: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`,
  ext: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
  check: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  copy: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  spark: `<svg class="ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/></svg>`,
  imgOff: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
};

function siteFaviconHtml(site, large = false) {
  const svg = SITE_LOGOS[site];
  if (!svg) return "";
  const cls = large ? "site-favicon-lg" : "site-favicon";
  return `<span class="site-logo ${cls}">${svg}</span>`;
}

function euro(v, signed = false) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const n = Math.round(Number(v));
  return `${signed && n > 0 ? "+" : ""}${n} €`;
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Erreur HTTP ${res.status}`);
  }
  return data;
}

function formatCountdown(sec) {
  if (sec === null || sec === undefined) return "--:--";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function scoreClass(score) {
  if (score === null || score === undefined) return "score-na";
  if (score >= 72) return "score-high";
  if (score >= 55) return "score-mid";
  return "score-low";
}

function siteBadgeClass(site) {
  if (site === "leboncoin") return "badge-lbc";
  if (site === "vinted") return "badge-vinted";
  if (site === "ebay") return "badge-ebay";
  return "badge-fb";
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    state.isPaused = data.paused;
    state.isScanning = data.scanning;
    state.countdownSec = data.next_scan_in_seconds;

    document.getElementById("status-step").textContent = data.current_step || "Prêt";
    document.getElementById("api-cost").textContent = `$${(data.api_cost.total_usd || 0).toFixed(3)}`;
    document.getElementById("countdown").textContent = data.scanning
      ? "En cours..."
      : data.paused
      ? "Pause"
      : formatCountdown(state.countdownSec);

    document.getElementById("btn-pause").textContent = data.paused ? "Reprendre" : "Pause";
    document.getElementById("btn-scan-now").disabled = data.scanning;

    const btnTriage = document.getElementById("btn-triage-now");
    const btnTriageLabel = document.getElementById("btn-triage-label");
    const pendingAi = data.pending_ai_count ?? 0;
    btnTriage.disabled = data.scanning || pendingAi === 0;
    btnTriageLabel.textContent = pendingAi > 0 ? `Noter IA (${pendingAi})` : "IA à jour";

    document.getElementById("lbl-threshold").textContent = data.min_alert_score;
    document.getElementById("stat-gems").textContent = data.stats.total_gems ?? 0;
    document.getElementById("stat-scanned").textContent = data.stats.total_scanned ?? 0;
    document.getElementById("stat-last-scan").textContent = data.stats.last_scan_found ?? 0;
    const keptLast = data.stats.last_scan_kept ?? 0;
    document.getElementById("stat-last-scan-sub").textContent = `${keptLast} retenue${keptLast > 1 ? "s" : ""}`;
    document.getElementById("stat-kept").textContent = data.stats.total_kept ?? 0;
    const analyzed = data.stats.total_analyzed ?? 0;
    document.getElementById("stat-analyzed-sub").textContent = `${analyzed} notée${analyzed > 1 ? "s" : ""} IA`;
    document.getElementById("stat-rejected").textContent = data.stats.total_rejected ?? 0;
    document.getElementById("stat-fav").textContent = data.stats.total_favorites ?? 0;
    document.getElementById("stat-notified").textContent = data.stats.total_notified ?? 0;

    const banner = document.getElementById("config-banner");
    const warnings = [];
    if (!data.anthropic_configured) {
      warnings.push("Clé ANTHROPIC_API_KEY manquante ou exemple dans .env — ajoute ta vraie clé puis redémarre.");
    } else if (data.last_ai_error) {
      warnings.push(`Erreur API Anthropic : ${data.last_ai_error}`);
    }
    if (!data.telegram_configured) {
      warnings.push("Bot Telegram non configuré dans .env (alertes désactivées).");
    }
    if (warnings.length) {
      banner.innerHTML = `${ICONS.alert}<span>${esc(warnings.join("  |  "))}</span>`;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }

    const pillsEl = document.getElementById("site-pills");
    const sites = ["leboncoin", "vinted", "facebook", "ebay"];
    pillsEl.innerHTML = sites
      .map((s) => {
        const h = data.site_health[s];
        const status = h ? h.status : "En attente";
        let dot = "";
        if (status === "OK") dot = "ok";
        else if (status === "Prêt") dot = "ready";
        else if (status.includes("Cooldown") || status.includes("manquante")) dot = "warn";
        else if (status === "Erreur") dot = "err";
        return `<span class="site-pill" title="${esc(h?.last_error || status)}"><span class="dot ${dot}"></span>${siteFaviconHtml(s)}${esc(s)} · ${esc(status)}</span>`;
      })
      .join("");
  } catch (err) {
    console.error("Erreur status:", err);
  }
}

async function refreshListings() {
  const showRejected = state.statusTab === "rejected";
  const params = new URLSearchParams({
    search: state.search,
    site: state.site,
    category: state.category,
    status: showRejected ? "active" : state.statusTab,
    sort: state.sort,
    show_rejected: String(showRejected),
    only_opened: String(state.onlyOpened),
    page: String(state.page),
    limit: String(state.pageSize),
  });

  try {
    const data = await api(`/api/listings?${params.toString()}`);
    state.totalItems = data.total ?? data.items.length;
    state.totalPages = data.total_pages ?? 1;
    if (state.page > state.totalPages) {
      state.page = state.totalPages;
    }
    renderPagination();
    renderListings(data.items, showRejected);
  } catch (err) {
    showToast(err.message);
  }
}

function renderPagination() {
  const topEl = document.getElementById("pagination-top");
  const botEl = document.getElementById("pagination-bottom");
  if (state.totalItems === 0) {
    topEl.classList.add("hidden");
    botEl.classList.add("hidden");
    return;
  }

  const start = (state.page - 1) * state.pageSize + 1;
  const end = Math.min(state.totalItems, state.page * state.pageSize);
  const html = `
    <span>Affichage <strong>${start}–${end}</strong> sur <strong>${state.totalItems}</strong> annonces (max 20 par page)</span>
    <div class="pagination-controls">
      <button class="btn btn-ghost" data-page-nav="prev" ${state.page <= 1 ? "disabled" : ""}>Précédent</button>
      <span>Page <strong>${state.page}</strong> / ${state.totalPages}</span>
      <button class="btn btn-ghost" data-page-nav="next" ${state.page >= state.totalPages ? "disabled" : ""}>Suivant</button>
    </div>
  `;

  for (const el of [topEl, botEl]) {
    el.innerHTML = html;
    el.classList.remove("hidden");
    el.querySelectorAll("[data-page-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.pageNav === "prev" && state.page > 1) {
          state.page -= 1;
          refreshListings();
          window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (btn.dataset.pageNav === "next" && state.page < state.totalPages) {
          state.page += 1;
          refreshListings();
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }
}

function renderListings(items, showRejected) {
  const grid = document.getElementById("listings-grid");
  if (!items.length) {
    grid.innerHTML = `<div class="empty-state">Aucune annonce dans cette vue pour le moment.<br/>Clique sur <strong>Scanner</strong> ou ajuste les filtres.</div>`;
    return;
  }

  grid.innerHTML = items
    .map((it) => {
      const shipText =
        it.shipping_price !== null && it.shipping_price !== undefined
          ? `+ ${Number(it.shipping_price).toFixed(2)} € port`
          : it.shipping_note || (it.shipping_available ? "Livraison dispo" : "Main propre");

      const profit = it.estimated_profit_eur;
      const hasRisk = it.success_pct !== null && it.success_pct !== undefined;
      const profitHtml =
        profit !== null && profit !== undefined
          ? `<span class="${profit >= 0 ? "profit-pos" : "profit-neg"}" title="${hasRisk ? "Gain espéré, pondéré par le risque d'échec de la réparation" : "Marge nette estimée"}">${euro(profit, true)} ${hasRisk ? "espéré" : "net"}</span>`
          : `<span class="muted">En attente IA</span>`;
      const riskLine = hasRisk
        ? `<div class="profit-row risk-row">
             <span>Réussite ~${it.success_pct}% · si réparé ${euro(it.profit_if_success_eur, true)}</span>
             ${it.max_buy_price_eur ? `<span title="Prix d'achat max conseillé (hors port)">Max ${euro(it.max_buy_price_eur)}</span>` : `<span class="profit-neg">Pas rentable</span>`}
           </div>`
        : "";

      const photoHtml = it.image_url
        ? `<img class="card-photo" src="${esc(it.image_url)}" alt="" loading="lazy" onerror="this.style.display='none'" />`
        : `<div class="card-photo-placeholder">${ICONS.imgOff}<span>Photo non disponible</span></div>`;

      // Note calculée par l'ancien algorithme : affichée grisée en attendant la renotation
      const staleScore = it.ai_analyzed && !it.score_version && !it.deep_analysis;
      const scoreDisplay = it.ai_analyzed ? it.ai_score : "--";
      const isFav = it.user_status === "favorite";

      return `
        <article class="card" data-id="${it.id}">
          <div class="card-media">
            ${photoHtml}
            <div class="media-overlay-top">
              <span class="site-tag-float">${siteFaviconHtml(it.site, true)}${esc(it.site)}</span>
              <div class="score-pill ${staleScore ? "score-na" : scoreClass(it.ai_score)}" title="${staleScore ? "Ancienne notation, en attente de recalcul (bouton Noter IA)" : "Note globale IA /100"}">${scoreDisplay}</div>
            </div>
            <div class="media-overlay-bottom">
              ${it.already_opened ? `<span class="badge badge-warn" title="${esc(it.opened_reason)}">${ICONS.alert} Déjà ouvert</span>` : ""}
              ${it.deep_analysis ? `<span class="badge badge-deep">${ICONS.spark} Analysé</span>` : ""}
            </div>
          </div>

          <div class="card-content">
            <div class="badges">
              <span class="badge">${esc(CAT_LABELS[it.category] || it.category)}</span>
            </div>
            <h3 class="card-title">${esc(it.title)}</h3>
            <div class="price-row">
              <span class="price">${Math.round(it.price)} €</span>
              <span class="shipping">${ICONS.truck}<span>${esc(shipText)}</span></span>
            </div>

            ${
              showRejected
                ? `<div class="fault-line">${ICONS.ban}<span>${esc(it.reject_reason)}</span></div>`
                : `
                  <div class="fault-line">${ICONS.wrench}<span>${esc(it.suspected_fault || "Diagnostic rapide en attente (clique sur Noter IA)")}</span></div>
                  ${
                    it.ai_analyzed
                      ? `
                        <div class="mini-bars">
                          <div class="mini-bar-item">Répar. ${it.repair_score}/10
                            <div class="bar-track"><div class="bar-fill" style="width:${it.repair_score * 10}%"></div></div>
                          </div>
                          <div class="mini-bar-item">Revente ${it.resale_score}/10
                            <div class="bar-track"><div class="bar-fill" style="width:${it.resale_score * 10}%"></div></div>
                          </div>
                          <div class="mini-bar-item">Marge ${it.margin_score}/10
                            <div class="bar-track"><div class="bar-fill" style="width:${it.margin_score * 10}%"></div></div>
                          </div>
                        </div>
                        <div class="profit-row">
                          <span>Revente ~${Math.round(it.estimated_resale_eur || 0)} € · Pièces ~${Math.round(it.estimated_parts_eur || 0)} €</span>
                          ${profitHtml}
                        </div>
                        ${riskLine}
                      `
                      : ""
                  }
                `
            }
          </div>

          <div class="card-footer" onclick="event.stopPropagation()">
            <span class="loc-text">${ICONS.pin}<span>${esc(it.location || "France")}</span></span>
            <div class="card-actions">
              <button class="mini-btn ${isFav ? "fav-on" : ""}" onclick="setListingStatus(${it.id}, '${isFav ? "new" : "favorite"}')" title="Favori">${isFav ? ICONS.starFill : ICONS.star}</button>
              <button class="mini-btn" onclick="setListingStatus(${it.id}, '${it.user_status === "ignored" ? "new" : "ignored"}')" title="Masquer">${ICONS.eyeOff}</button>
              <a class="mini-btn" href="${esc(it.url)}" target="_blank" rel="noopener">Ouvrir ${ICONS.ext}</a>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  grid.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", () => openDrawer(Number(card.dataset.id)));
  });
}

async function setListingStatus(id, newStatus) {
  try {
    await api(`/api/listings/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ user_status: newStatus }),
    });
    await Promise.all([refreshListings(), refreshStatus()]);
    if (state.selectedId === id) openDrawer(id);
  } catch (err) {
    showToast(err.message);
  }
}

async function openDrawer(id) {
  state.selectedId = id;
  document.getElementById("drawer-backdrop").classList.remove("hidden");
  document.getElementById("detail-drawer").classList.remove("hidden");
  document.getElementById("drawer-body").innerHTML = `<div class="muted">Chargement...</div>`;

  try {
    const it = await api(`/api/listings/${id}`);
    renderDrawer(it);
  } catch (err) {
    document.getElementById("drawer-body").innerHTML = `<div class="muted">${esc(err.message)}</div>`;
  }
}

function closeDrawer() {
  state.selectedId = null;
  document.getElementById("drawer-backdrop").classList.add("hidden");
  document.getElementById("detail-drawer").classList.add("hidden");
}

function renderDrawer(it) {
  document.getElementById("drawer-title").textContent = it.title;
  const shipText =
    it.shipping_price !== null && it.shipping_price !== undefined
      ? `${Number(it.shipping_price).toFixed(2)} €`
      : it.shipping_note || "NC";

  const deep = it.deep_analysis;
  const deepHtml = deep
    ? `
      <div class="verdict-banner verdict-${esc(deep.verdict)}">
        <span>Verdict : ${esc(deep.verdict.replace("_", " "))} · Note recalibrée : ${deep.score ?? it.ai_score ?? "--"}/100</span>
        <span>Achat max conseillé : ${Math.round(deep.recommended_max_buy_eur)} €</span>
      </div>

      <div class="section-box">
        <h3>Analyse de marché & rentabilité</h3>
        <p style="margin:0 0 11px;font-size:13px;line-height:1.5;color:var(--text-soft);">${esc(deep.summary)}</p>
        <div class="kv-grid">
          <div class="kv-item"><span>Valeur occasion (vendu)</span><strong>${Math.round(deep.market_price_low_eur)} – ${Math.round(deep.market_price_high_eur)} €</strong></div>
          <div class="kv-item"><span>Gain espéré (pondéré risque)</span><strong class="${deep.estimated_net_profit_eur >= 0 ? "profit-pos" : "profit-neg"}">${euro(deep.estimated_net_profit_eur, true)}</strong></div>
          ${
            deep.success_pct !== undefined
              ? `<div class="kv-item"><span>Chance de réussite</span><strong>${deep.success_pct}%</strong></div>
                 <div class="kv-item"><span>Si réparé / perte max si échec</span><strong>${euro(deep.profit_if_success_eur, true)} / -${Math.round(deep.max_loss_eur)} €</strong></div>`
              : ""
          }
          <div class="kv-item"><span>Budget pièces</span><strong>~${Math.round(deep.estimated_parts_eur)} €</strong></div>
          <div class="kv-item"><span>Temps de réparation</span><strong>${esc(deep.estimated_repair_time)}</strong></div>
          <div class="kv-item" style="grid-column:1 / -1;"><span>Vitesse de revente</span><strong>${esc(deep.resale_speed)}</strong></div>
        </div>
      </div>

      <div class="section-box">
        <h3>Pannes probables</h3>
        ${(deep.probable_faults || [])
          .map(
            (f) => `
            <div class="fault-item">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:3px;">
                <strong>${esc(f.fault)}</strong>
                <span class="badge">${esc(f.probability)}%</span>
              </div>
              <span class="muted">${esc(f.fix)}</span>
            </div>`
          )
          .join("")}
      </div>

      ${
        deep.red_flags && deep.red_flags.length
          ? `<div class="section-box">
              <h3>Points de vigilance</h3>
              <ul style="margin:0;padding-left:18px;font-size:13px;color:#fca5a5;line-height:1.5;">
                ${deep.red_flags.map((rf) => `<li>${esc(rf)}</li>`).join("")}
              </ul>
            </div>`
          : ""
      }

      ${
        deep.questions_for_seller && deep.questions_for_seller.length
          ? `<div class="section-box">
              <h3>Questions à poser au vendeur</h3>
              <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5;color:var(--text-soft);">
                ${deep.questions_for_seller.map((q) => `<li>${esc(q)}</li>`).join("")}
              </ul>
            </div>`
          : ""
      }

      <div style="text-align:right;">
        <span class="muted" style="font-size:11px;margin-right:8px;">${esc(deep.model || "")}</span>
        <button id="btn-run-deep" class="mini-btn">${ICONS.spark} Recalculer l'analyse approfondie</button>
      </div>

      ${
        deep.seller_message_template
          ? `<div class="section-box">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <h3 style="margin:0;">Message prêt pour le vendeur</h3>
                <button class="mini-btn" id="btn-copy-msg">${ICONS.copy} Copier</button>
              </div>
              <div class="copy-box" id="seller-msg-text">${esc(deep.seller_message_template)}</div>
            </div>`
          : ""
      }
    `
    : `
      <div class="section-box" style="text-align:center;padding:18px 15px;">
        <p class="muted" style="margin:0 0 12px;font-size:13px;line-height:1.45;">
          Lance l'analyse approfondie (Claude Sonnet) pour obtenir le diagnostic des pannes probables,
          la cote du marché, le prix d'achat max conseillé et un message prêt pour le vendeur.
        </p>
        <button id="btn-run-deep" class="btn btn-primary">${ICONS.spark} Lancer l'analyse approfondie</button>
      </div>
    `;

  const isFav = it.user_status === "favorite";
  document.getElementById("drawer-body").innerHTML = `
    <div class="drawer-hero">
      ${it.image_url ? `<img src="${esc(it.image_url)}" alt="" />` : ""}
      <div>
        <div class="badges">
          <span class="badge ${siteBadgeClass(it.site)}">${siteFaviconHtml(it.site)}${esc(it.site)}</span>
          <span class="badge">${esc(CAT_LABELS[it.category] || it.category)}</span>
          ${it.already_opened ? `<span class="badge badge-warn">${ICONS.alert} ${esc(it.opened_reason || "Déjà ouvert")}</span>` : ""}
        </div>
        <div class="price-row" style="margin-top:10px;">
          <span class="price" style="font-size:26px;">${Math.round(it.price)} €</span>
          <span class="shipping">${ICONS.truck}<span>Port : ${esc(shipText)}</span></span>
        </div>
        <p class="loc-text" style="margin:7px 0 0;">${ICONS.pin}<span>${esc(it.location || "Localisation NC")}</span></p>
        <div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;">
          <a class="btn btn-primary" href="${esc(it.url)}" target="_blank" rel="noopener">Voir l'annonce ${ICONS.ext}</a>
          <button class="btn btn-ghost" onclick="setListingStatus(${it.id}, '${isFav ? "new" : "favorite"}')">${isFav ? ICONS.starFill : ICONS.star} Favori</button>
          <button class="btn btn-ghost" onclick="setListingStatus(${it.id}, 'bought')">${ICONS.check} Acheté</button>
          <button class="btn btn-ghost" onclick="setListingStatus(${it.id}, 'ignored')">${ICONS.eyeOff} Masquer</button>
        </div>
      </div>
    </div>

    <div class="section-box">
      <h3>${it.deep_analysis ? "Note recalibrée par analyse approfondie" : "Évaluation rapide"} (Score ${it.ai_score ?? "--"}/100)</h3>
      <p style="margin:0 0 6px;font-size:13px;"><strong>Panne suspectée :</strong> ${esc(it.suspected_fault || "NC")}</p>
      ${it.deep_analysis ? "" : `<p class="muted" style="margin:0;font-size:13px;line-height:1.45;">${esc(it.ai_reasoning || "Non analysée.")}</p>`}
      ${
        it.ai_analyzed && it.success_pct !== null && it.success_pct !== undefined
          ? `<div class="kv-grid" style="margin-top:11px;">
              <div class="kv-item"><span>Coût d'achat (prix + port)</span><strong>${euro(Number(it.price) + Number(it.shipping_price ?? 6))}</strong></div>
              <div class="kv-item"><span>Revente estimée / pièces</span><strong>${euro(it.estimated_resale_eur)} / ${euro(it.estimated_parts_eur)}</strong></div>
              <div class="kv-item"><span>Chance de réussite</span><strong>${it.success_pct}%</strong></div>
              <div class="kv-item"><span>Si réparé / perte max</span><strong>${euro(it.profit_if_success_eur, true)} / -${Math.round(it.max_loss_eur || 0)} €</strong></div>
              <div class="kv-item"><span>Gain espéré (pondéré risque)</span><strong class="${it.estimated_profit_eur >= 0 ? "profit-pos" : "profit-neg"}">${euro(it.estimated_profit_eur, true)}</strong></div>
              <div class="kv-item"><span>Prix d'achat max conseillé</span><strong>${it.max_buy_price_eur ? euro(it.max_buy_price_eur) : "Pas rentable"}</strong></div>
            </div>`
          : ""
      }
    </div>

    ${deepHtml}

    <div class="section-box">
      <h3>Description de l'annonce</h3>
      <p style="margin:0;font-size:13px;white-space:pre-wrap;line-height:1.5;color:var(--text-soft);">${esc(it.description || "Aucune description.")}</p>
    </div>

    <div class="section-box">
      <h3>Notes personnelles</h3>
      <textarea id="drawer-notes" class="notes-area" placeholder="Ex : Offre envoyée à 45 EUR, attente réponse...">${esc(it.user_notes || "")}</textarea>
      <div style="margin-top:8px;text-align:right;">
        <button id="btn-save-notes" class="btn btn-ghost">Sauvegarder la note</button>
      </div>
    </div>
  `;

  const btnDeep = document.getElementById("btn-run-deep");
  if (btnDeep) {
    btnDeep.addEventListener("click", async () => {
      btnDeep.disabled = true;
      btnDeep.textContent = "Analyse approfondie en cours (30-60 s)...";
      try {
        const res = await api(`/api/listings/${it.id}/deep-analyze`, { method: "POST" });
        renderDrawer(res.item);
        refreshListings();
        refreshStatus();
        showToast("Analyse approfondie terminée");
      } catch (err) {
        btnDeep.disabled = false;
        btnDeep.innerHTML = `${ICONS.spark} Lancer l'analyse approfondie`;
        showToast(err.message);
      }
    });
  }

  const btnCopy = document.getElementById("btn-copy-msg");
  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      const txt = document.getElementById("seller-msg-text").textContent;
      navigator.clipboard.writeText(txt);
      showToast("Message copié dans le presse-papiers");
    });
  }

  document.getElementById("btn-save-notes").addEventListener("click", async () => {
    const notes = document.getElementById("drawer-notes").value;
    try {
      await api(`/api/listings/${it.id}/status`, {
        method: "POST",
        body: JSON.stringify({ user_notes: notes }),
      });
      showToast("Note enregistrée");
    } catch (err) {
      showToast(err.message);
    }
  });
}

async function openSettingsModal() {
  const modal = document.getElementById("settings-modal");
  modal.classList.remove("hidden");
  const form = document.getElementById("settings-form");
  try {
    const s = await api("/api/settings");
    for (const [k, v] of Object.entries(s)) {
      const field = form.elements.namedItem(k);
      if (!field) continue;
      if (field.type === "checkbox") field.checked = Boolean(v);
      else field.value = v;
    }
  } catch (err) {
    showToast(err.message);
  }
}

async function openLogsModal() {
  const modal = document.getElementById("logs-modal");
  modal.classList.remove("hidden");
  const container = document.getElementById("logs-list");
  container.innerHTML = `<div class="muted">Chargement...</div>`;
  try {
    const data = await api("/api/logs");
    if (!data.logs.length) {
      container.innerHTML = `<div class="muted">Aucun journal pour l'instant.</div>`;
      return;
    }
    container.innerHTML = data.logs
      .map(
        (l) => `
        <div class="log-row">
          <span class="muted">${esc((l.created_at || "").replace("T", " ").slice(0, 19))}</span>
          <strong class="log-${esc(l.status)}">${siteFaviconHtml(l.site)} [${esc(l.site)} · ${esc(l.status)}]</strong>
          <span>${esc(l.message)}</span>
        </div>`
      )
      .join("");
  } catch (err) {
    container.innerHTML = `<div class="muted">${esc(err.message)}</div>`;
  }
}

function bindEvents() {
  document.getElementById("btn-scan-now").addEventListener("click", async () => {
    try {
      await api("/api/scan/trigger", { method: "POST" });
      showToast("Scan déclenché");
      setTimeout(refreshStatus, 600);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-triage-now").addEventListener("click", async () => {
    try {
      const res = await api("/api/ai/triage-now", { method: "POST" });
      showToast(res.message);
      setTimeout(refreshStatus, 600);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-pause").addEventListener("click", async () => {
    const ep = state.isPaused ? "/api/scan/resume" : "/api/scan/pause";
    await api(ep, { method: "POST" });
    refreshStatus();
  });

  document.getElementById("btn-settings").addEventListener("click", openSettingsModal);
  document.getElementById("btn-logs").addEventListener("click", openLogsModal);
  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);

  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById(btn.dataset.closeModal).classList.add("hidden");
    });
  });

  document.getElementById("btn-test-telegram").addEventListener("click", async () => {
    try {
      const res = await api("/api/telegram/test", { method: "POST" });
      showToast(res.message);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const payload = {
      SCAN_INTERVAL_MINUTES: Number(form.SCAN_INTERVAL_MINUTES.value),
      MIN_ALERT_SCORE: Number(form.MIN_ALERT_SCORE.value),
      MIN_ALERT_PROFIT_EUR: Number(form.MIN_ALERT_PROFIT_EUR.value),
      MIN_PRICE_EUR: Number(form.MIN_PRICE_EUR.value),
      MAX_PRICE_EUR: Number(form.MAX_PRICE_EUR.value),
      REQUIRE_SHIPPING: form.REQUIRE_SHIPPING.checked,
      EXCLUDE_ALREADY_OPENED: form.EXCLUDE_ALREADY_OPENED.checked,
      ENABLE_LEBONCOIN: form.ENABLE_LEBONCOIN.checked,
      ENABLE_VINTED: form.ENABLE_VINTED.checked,
      ENABLE_FACEBOOK: form.ENABLE_FACEBOOK.checked,
      ENABLE_EBAY: form.ENABLE_EBAY.checked,
      FB_CITY: (form.FB_CITY?.value || "france").trim().toLowerCase(),
      LBC_DATADOME_COOKIE: (form.LBC_DATADOME_COOKIE?.value || "").trim(),
    };
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
      document.getElementById("settings-modal").classList.add("hidden");
      showToast("Paramètres sauvegardés");
      refreshStatus();
      refreshListings();
    } catch (err) {
      showToast(err.message);
    }
  });

  document.querySelectorAll("#status-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#status-tabs .tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      state.statusTab = tab.dataset.status;
      state.page = 1;
      refreshListings();
    });
  });

  let searchDebounce = null;
  document.getElementById("filter-search").addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.search = e.target.value;
      state.page = 1;
      refreshListings();
    }, 250);
  });

  document.getElementById("filter-site").addEventListener("change", (e) => {
    state.site = e.target.value;
    state.page = 1;
    refreshListings();
  });
  document.getElementById("filter-category").addEventListener("change", (e) => {
    state.category = e.target.value;
    state.page = 1;
    refreshListings();
  });
  document.getElementById("filter-sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    state.page = 1;
    refreshListings();
  });
  document.getElementById("filter-opened").addEventListener("change", (e) => {
    state.onlyOpened = e.target.checked;
    state.page = 1;
    refreshListings();
  });
}

setInterval(() => {
  if (!state.isPaused && !state.isScanning && state.countdownSec !== null && state.countdownSec > 0) {
    state.countdownSec -= 1;
    document.getElementById("countdown").textContent = formatCountdown(state.countdownSec);
  }
}, 1000);

setInterval(() => {
  refreshStatus();
  if (state.isScanning) refreshListings();
}, 4000);

setInterval(() => {
  refreshListings();
}, 25000);

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await Promise.all([refreshStatus(), refreshListings()]);

  const openId = new URLSearchParams(window.location.search).get("open");
  if (openId && !Number.isNaN(Number(openId))) {
    openDrawer(Number(openId));
  }
});
