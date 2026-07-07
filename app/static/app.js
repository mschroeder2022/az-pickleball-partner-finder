"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (url, opts) => {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
function flash(msg, ms = 3000) {
  const f = $("#flash"); f.textContent = msg; f.classList.remove("hidden");
  clearTimeout(flash._t); flash._t = setTimeout(() => f.classList.add("hidden"), ms);
}

let PROFILE = null;
const pState = { sort: "dupr_doubles", order: "desc", sweet: false, active: true, min: "", max: "" };
const tState = { target: false, metro: false, source: "" };

// ---- init -------------------------------------------------------------------
async function boot() {
  PROFILE = await api("/api/profile");
  $("#profileLine").innerHTML =
    `${esc(PROFILE.name)} · DUPR ${PROFILE.dupr_doubles} dbl / ${PROFILE.dupr_singles} sgl · `
    + `${esc(PROFILE.home_base)} · targeting ${PROFILE.metros.length} metros`;
  $("#sweetRange").textContent = PROFILE.rating_sweet.join("–");
  $("#ceilRange").textContent = PROFILE.rating_ceiling.join("–");
  $("#pMin").placeholder = PROFILE.rating_ceiling[0];
  $("#pMax").placeholder = PROFILE.rating_ceiling[1];
  await refreshStatus();
  await loadPlayers();
  await loadTournaments();
}

// ---- status / sources -------------------------------------------------------
let pollTimer = null;
async function refreshStatus() {
  const s = await api("/api/status");
  const cred = s.credentials;
  $("#sources").innerHTML = s.sources.map(src => {
    const running = s.refresh.running && s.refresh.current === src.label;
    let cbadge = "";
    if (src.kind === "auth") {
      const ok = cred[src.key];
      cbadge = ok ? `<span class="badge b-ok">creds set</span>`
                  : `<span class="badge b-warn">needs .env creds</span>`;
    } else {
      cbadge = `<span class="badge b-info">no login</span>`;
    }
    return `<div class="src-item">
      <div><b>${esc(src.label)}</b> ${cbadge}
        ${running ? '<span class="spin"></span>' : ''}</div>
      <div class="row">
        <span class="meta">${esc(lastLogFor(s.log, src.key))}</span>
        <button class="small" data-src="${src.key}">Refresh</button>
      </div></div>`;
  }).join("");
  $$("#sources button[data-src]").forEach(b =>
    b.onclick = () => startRefresh([b.dataset.src]));

  $("#refreshStatus").innerHTML = s.refresh.running
    ? `<span class="spin"></span> running: ${esc(s.refresh.current || "…")}`
    : `${s.counts.players} players · ${s.counts.tournaments} tournaments · ${s.counts.signups} sign-ups`;

  $("#fetchLog").innerHTML = "<table><tbody>" + s.log.map(l =>
    `<tr><td>${esc(l.ran_at)}</td><td><b>${esc(l.source)}</b></td>
     <td>${statusBadge(l.status)}</td><td class="muted">${esc(l.detail)}</td></tr>`).join("")
    + "</tbody></table>";

  // populate source filter
  const sel = $("#tSource");
  if (sel.options.length <= 1)
    s.sources.forEach(src => sel.add(new Option(src.label, src.key)));

  if (s.refresh.running && !pollTimer) {
    pollTimer = setInterval(async () => {
      const st = await api("/api/status");
      await refreshStatus();
      if (!st.refresh.running) {
        clearInterval(pollTimer); pollTimer = null;
        flash("Refresh complete"); loadPlayers(); loadTournaments();
      }
    }, 1500);
  }
}
function lastLogFor(log, key) {
  const e = log.find(l => l.source === key);
  return e ? `${e.status} · ${e.detail}` : "not run yet";
}
function statusBadge(st) {
  const c = st === "ok" ? "b-ok" : st === "error" ? "b-bad" : "b-warn";
  return `<span class="badge ${c}">${esc(st)}</span>`;
}
async function startRefresh(sources) {
  try {
    await api("/api/refresh", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources }),
    });
    flash("Refresh started");
    refreshStatus();
  } catch (e) { flash("Error: " + e.message); }
}

// ---- players ----------------------------------------------------------------
async function loadPlayers() {
  const q = new URLSearchParams();
  q.set("sort", pState.sort); q.set("order", pState.order);
  if (pState.sweet) q.set("sweet_only", "true");
  q.set("active_only", pState.active ? "true" : "false");
  if (pState.min) q.set("min_rating", pState.min);
  if (pState.max) q.set("max_rating", pState.max);
  if ($("#pSearch").value) q.set("search", $("#pSearch").value);
  const rows = await api("/api/players?" + q);
  $("#pCount").textContent = `${rows.length} players`;
  $("#pTable tbody").innerHTML = rows.map(playerRow).join("") ||
    `<tr><td colspan="8" class="muted">No players yet — run a refresh (DUPR needs your .env creds) or add one manually.</td></tr>`;
  $$("#pTable button[data-del]").forEach(b => b.onclick = async () => {
    if (confirm("Delete this player?")) { await api("/api/players/" + b.dataset.del, { method: "DELETE" }); loadPlayers(); }
  });
}
function contactCell(p) {
  const L = [];
  if (p.dupr_profile_url) L.push(`<a href="${esc(p.dupr_profile_url)}" target="_blank" title="Open DUPR profile">DUPR&#8599;</a>`);
  if (p.google_search) L.push(`<a href="${esc(p.google_search)}" target="_blank" title="Google: name + pickleball + their city">G&#128269;</a>`);
  if (p.instagram) {
    const h = p.instagram.replace(/^@/, "");
    L.push(`<a href="https://instagram.com/${esc(h)}" target="_blank">@${esc(h)}</a>`);
  } else if (p.instagram_search) {
    L.push(`<a href="${esc(p.instagram_search)}" target="_blank" title="Instagram search">IG&#128269;</a>`);
  }
  if (p.youtube_search) L.push(`<a href="${esc(p.youtube_search)}" target="_blank" title="YouTube search">YT&#128269;</a>`);
  if (p.email) L.push(`<a href="mailto:${esc(p.email)}">email</a>`);
  if (p.phone) L.push(`<span class="muted">${esc(p.phone)}</span>`);
  return `<span class="links">${L.join("")}</span>`;
}
function activityBadge(p) {
  const d = p.last_match_date ? esc(p.last_match_date) : null;
  if (p.activity_status === "active") return `<span class="badge b-active">${d || "active"}</span>`;
  if (p.activity_status === "inactive") return `<span class="badge b-inactive">${d || "&gt;1yr"}</span>`;
  return `<span class="badge b-unknown">?</span>`;
}
function playerRow(p) {
  const dbl = p.dupr_doubles == null ? '<span class="muted">—</span>'
    : `<span class="rating ${p.in_sweet_spot ? "sweet" : ""}">${p.dupr_doubles.toFixed(3)}</span>`
      + (p.dupr_reliability === "provisional" ? ' <span class="muted" title="provisional">*</span>' : "");
  const sup = (p.signups || []).map(s =>
    `<span class="chip">${esc(s.tournament)}${s.start_date ? " · " + esc(s.start_date) : ""}</span>`).join("")
    || '<span class="muted">—</span>';
  const av = p.image_url
    ? `<img class="avatar" src="${esc(p.image_url)}" loading="lazy" alt="" onerror="this.remove()">`
    : `<span class="avatar avatar-blank"></span>`;
  return `<tr class="${p.in_sweet_spot ? "sweet" : ""}">
    <td><span class="pname">${av}<span><b>${esc(p.name)}</b>${p.club ? `<div class="muted">${esc(p.club)}</div>` : ""}</span></span></td>
    <td>${dbl}</td>
    <td class="rating">${p.dupr_singles == null ? "" : p.dupr_singles.toFixed(3)}</td>
    <td>${esc(p.city || "")}</td>
    <td>${activityBadge(p)}</td>
    <td>${contactCell(p)}</td>
    <td>${sup}</td>
    <td><button class="small" data-del="${p.id}">✕</button></td>
  </tr>`;
}

// ---- tournaments ------------------------------------------------------------
async function loadTournaments() {
  const q = new URLSearchParams();
  if (tState.target) q.set("target_only", "true");
  if (tState.metro) q.set("in_metro_only", "true");
  if (tState.source) q.set("source", tState.source);
  const rows = await api("/api/tournaments?" + q);
  $("#tCount").textContent = `${rows.length} tournaments`;
  // group by source
  const groups = {};
  rows.forEach(t => (groups[t.source] = groups[t.source] || []).push(t));
  $("#tBoard").innerHTML = Object.entries(groups).map(([src, ts]) =>
    `<div class="panel"><h2>${esc(src)} · ${ts.length}</h2>
      <div class="grid2">${ts.map(tCard).join("")}</div></div>`).join("")
    || `<div class="panel muted">No tournaments yet — run a refresh.</div>`;
  $$("#tBoard button[data-del]").forEach(b => b.onclick = async () => {
    if (confirm("Delete this tournament?")) { await api("/api/tournaments/" + b.dataset.del, { method: "DELETE" }); loadTournaments(); }
  });
  $$("details.cand").forEach(d => d.addEventListener("toggle", () => {
    if (d.open && !d.dataset.built) { d.dataset.built = "1"; buildCandidates(d); }
  }));
}
function buildCandidates(d) {
  const tid = d.dataset.tid;
  const tourCap = d.dataset.cap;                 // "" if unknown
  const controls = $(".cand-controls", d);
  const caps = (PROFILE.cap_choices || [8.5, 9, 9.5, 10]);
  const capOpts = caps.map(c => `<option value="${c}">${c}</option>`).join("");
  controls.innerHTML = `
    <div class="row" style="gap:8px; align-items:center;">
      <label class="f">Combined cap
        <select class="cand-cap">
          ${tourCap ? `<option value="${tourCap}">${tourCap} (from event)</option>` : `<option value="">— pick a cap —</option>`}
          ${capOpts}
        </select></label>
      <label class="f" style="flex-direction:row; align-items:center; gap:5px; margin-top:12px;">
        <input type="checkbox" class="cand-elig"> eligible only</label>
      <span class="cand-summary muted" style="margin-top:12px;"></span>
    </div>`;
  const capSel = $(".cand-cap", controls);
  const eligChk = $(".cand-elig", controls);
  const rerender = () => renderCandidates(d, tid, capSel.value, eligChk.checked);
  capSel.onchange = rerender;
  eligChk.onchange = rerender;
  rerender();
}

async function renderCandidates(d, tid, cap, eligibleOnly) {
  const box = $(".cand-body", d);
  box.innerHTML = '<span class="spin"></span> loading…';
  const q = new URLSearchParams();
  if (cap) q.set("cap", cap);
  if (eligibleOnly) q.set("eligible_only", "true");
  try {
    const r = await api(`/api/tournaments/${tid}/candidates?` + q);
    const cap2 = r.cap;
    const sum = $(".cand-summary", d);
    if (sum) sum.innerHTML = cap2 != null
      ? `You ${r.my_rating} + partner · cap ${cap2} · <b class="ok">${r.eligible_count} eligible</b> · ${r.signed_up_count} already signed up`
      : `Pick a cap to check eligibility · ${r.candidates.length} in range, ${r.signed_up_count} signed up`;
    if (!r.candidates.length) {
      box.innerHTML = '<span class="muted">No matching players (all signed up, or none loaded — run a DUPR refresh).</span>';
      return;
    }
    box.innerHTML = `<table><thead><tr>
        <th>Partner</th><th>DUPR</th><th>G/Age</th>
        <th>${cap2 != null ? "Combined" : ""}</th><th>Contact</th></tr></thead><tbody>` +
      r.candidates.slice(0, 60).map(c => candRow(c, cap2)).join("") +
      `</tbody></table>` +
      (r.candidates.length > 60 ? `<div class="muted" style="margin-top:4px;">showing 60 of ${r.candidates.length}</div>` : "");
  } catch (e) { box.innerHTML = "error: " + esc(e.message); }
}

function candRow(c, cap) {
  const e = c.eligibility || {};
  const g = c.gender === "FEMALE" ? "♀" : c.gender === "MALE" ? "♂" : "";
  let combinedCell = "";
  if (cap != null && !e.unknown) {
    const badge = e.eligible
      ? `<span class="badge b-ok">✓ ${e.combined}</span>`
      : `<span class="badge b-bad">✗ ${e.combined}</span>`;
    const why = (e.reasons || []).length ? ` <span class="chip">${e.reasons.map(esc).join(", ")}</span>` : "";
    combinedCell = `${badge}${why}`;
  }
  return `<tr>
    <td>${e.eligible ? "🟢" : (cap != null ? "🔴" : "⚪")} <b>${esc(c.name)}</b>
      ${c.city ? `<div class="muted">${esc(c.city)}</div>` : ""}</td>
    <td class="rating ${c.in_sweet_spot ? "sweet" : ""}">${c.dupr_doubles != null ? c.dupr_doubles.toFixed(3) : "—"}${c.dupr_reliability === "provisional" ? ' <span class="muted">*</span>' : ""}</td>
    <td>${g}${c.age != null ? " " + c.age : ""}</td>
    <td>${combinedCell}</td>
    <td>${contactCell(c)}</td>
  </tr>`;
}

function tCard(t) {
  const when = t.start_date ? (t.start_date + (t.end_date && t.end_date !== t.start_date ? " → " + t.end_date : "")) : "date TBA";
  const where = [t.venue, t.city, t.state].filter(Boolean).join(", ");
  const metro = t.nearest_metro
    ? `<span class="badge ${t.in_target_metro ? "b-ok" : "b-warn"}">${esc(t.nearest_metro)} ${t.metro_distance_mi != null ? "~" + Math.round(t.metro_distance_mi) + "mi" : ""}</span>`
    : `<span class="badge b-warn">location?</span>`;
  const divs = (t.divisions || []).slice(0, 6).map(d => `<span class="chip">${esc(d.name || d.level)}</span>`).join("");
  return `<div class="tcard">
    <h3>${esc(t.name)} ${t.is_target ? '<span class="badge b-ok">target</span>' : ""}</h3>
    <div class="when">${esc(when)}</div>
    <div class="muted">${esc(where)}</div>
    <div style="margin:6px 0;">${metro}
      ${t.entry_fee ? `<span class="chip">${esc(t.entry_fee)}</span>` : ""}
      <span class="chip">${t.signup_count} signed up</span></div>
    <div>${divs}</div>
    ${t.registration_url ? `<div style="margin-top:6px;"><a href="${esc(t.registration_url)}" target="_blank">Register / details →</a></div>` : ""}
    <details class="cand" data-tid="${t.id}" data-cap="${t.combined_cap != null ? t.combined_cap : ""}">
      <summary>Who near me is NOT signed up? (eligible partners)</summary>
      <div class="cand-controls" style="margin-top:6px;"></div>
      <div class="cand-body" style="margin-top:6px;"></div>
    </details>
    <div style="margin-top:6px;"><button class="small" data-del="${t.id}">✕ delete</button></div>
  </div>`;
}

// ---- events -----------------------------------------------------------------
$("#refreshAll").onclick = () => startRefresh(null);
$$(".tab").forEach(t => t.onclick = () => {
  $$(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  $("#tab-partners").classList.toggle("hidden", t.dataset.tab !== "partners");
  $("#tab-tournaments").classList.toggle("hidden", t.dataset.tab !== "tournaments");
});
$("#pReload").onclick = () => { pState.min = $("#pMin").value; pState.max = $("#pMax").value; loadPlayers(); };
$("#pSearch").addEventListener("keydown", e => { if (e.key === "Enter") loadPlayers(); });
$("#pSweet").onclick = () => { pState.sweet = !pState.sweet; $("#pSweet").classList.toggle("on", pState.sweet); loadPlayers(); };
$("#pActive").onclick = () => { pState.active = !pState.active; $("#pActive").classList.toggle("on", pState.active); loadPlayers(); };
$$("#pTable th[data-sort]").forEach(th => th.onclick = () => {
  const c = th.dataset.sort;
  if (pState.sort === c) pState.order = pState.order === "asc" ? "desc" : "asc";
  else { pState.sort = c; pState.order = "desc"; }
  loadPlayers();
});
$("#npAdd").onclick = async () => {
  const name = $("#npName").value.trim();
  if (!name) return flash("Name required");
  await api("/api/players", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name, dupr_doubles: parseFloat($("#npD").value) || null,
      city: $("#npCity").value || null, instagram: $("#npIg").value || null,
      email: $("#npEmail").value || null, phone: $("#npPhone").value || null,
    }),
  });
  ["#npName", "#npD", "#npCity", "#npIg", "#npEmail", "#npPhone"].forEach(s => $(s).value = "");
  flash("Player added"); loadPlayers();
};

$("#tTarget").onclick = () => { tState.target = !tState.target; $("#tTarget").classList.toggle("on", tState.target); loadTournaments(); };
$("#tMetro").onclick = () => { tState.metro = !tState.metro; $("#tMetro").classList.toggle("on", tState.metro); loadTournaments(); };
$("#tReload").onclick = () => { tState.source = $("#tSource").value; loadTournaments(); };
$("#ntAdd").onclick = async () => {
  const name = $("#ntName").value.trim();
  if (!name) return flash("Name required");
  await api("/api/tournaments", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name, start_date: $("#ntStart").value || null, city: $("#ntCity").value || null,
      venue: $("#ntVenue").value || null, registration_url: $("#ntUrl").value || null,
    }),
  });
  ["#ntName", "#ntStart", "#ntCity", "#ntVenue", "#ntUrl"].forEach(s => $(s).value = "");
  flash("Tournament added"); loadTournaments();
};

boot().catch(e => flash("Load error: " + e.message, 8000));
