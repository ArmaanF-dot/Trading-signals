/* Jarvis: static market homescreen. Live data comes straight from the providers'
   public websockets using keys kept in this browser's localStorage. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem("jarvis." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("jarvis." + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, d = 2) => (v === null || v === undefined || isNaN(v)) ? "–" : Number(v).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const px = (v) => v === null || v === undefined ? "–" : fmt(v, v >= 1000 ? 2 : v >= 1 ? 2 : 4);
  const pct = (v, d = 2) => (v === null || v === undefined || isNaN(v)) ? '<span class="muted">–</span>' : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${fmt(v, d)}%</span>`;
  const money = (v) => v == null ? "–" : v >= 1e9 ? `$${fmt(v / 1e9, 1)}bn` : v >= 1e6 ? `$${fmt(v / 1e6, 1)}m` : `$${fmt(v / 1e3, 0)}k`;

  let DATA = { markets: { uk_delayed: [], us_reference: [] }, signals: { watchlist: [], avoid: [], most_shorted: [], combo: [] }, analyst: {}, uk_names: [] };
  const keys = () => ({ aid: store.get("alpacaId", ""), asec: store.get("alpacaSecret", ""), fh: store.get("finnhub", ""), crypto: store.get("crypto", "coinbase") });
  let watch = store.get("watch", ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT"]);
  const us = {};      // sym -> {price, prev, src}
  const crypto = {};  // pair -> {price, open}
  const last = {};    // for flash direction

  // ---------- clocks ----------
  const MARKETS = [
    { name: "LDN", tz: "Europe/London", open: [8, 0], close: [16, 30] },
    { name: "NY", tz: "America/New_York", open: [9, 30], close: [16, 0], pre: [4, 0], post: [20, 0] },
    { name: "TKY", tz: "Asia/Tokyo", open: [9, 0], close: [15, 30] },
  ];
  function tzParts(tz) {
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false }).formatToParts(new Date());
    const g = (t) => p.find((x) => x.type === t)?.value;
    return { h: +g("hour") % 24, m: +g("minute"), wd: g("weekday") };
  }
  function renderClocks() {
    $("#clocks").innerHTML = MARKETS.map((mk) => {
      const { h, m, wd } = tzParts(mk.tz);
      const mins = h * 60 + m, at = (a) => a[0] * 60 + a[1];
      const weekday = !["Sat", "Sun"].includes(wd);
      let st = "shut", label = "closed";
      if (weekday && mins >= at(mk.open) && mins < at(mk.close)) { st = "open"; label = "open"; }
      else if (weekday && mk.pre && mins >= at(mk.pre) && mins < at(mk.open)) { st = "pre"; label = "pre"; }
      else if (weekday && mk.post && mins >= at(mk.close) && mins < at(mk.post)) { st = "pre"; label = "after"; }
      return `<span>${mk.name} <b>${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}</b> <span class="${st}">${label}</span></span>`;
    }).join("");
  }

  // ---------- rendering ----------
  let dirty = true;
  const mark = () => { dirty = true; };
  function flashCls(key, v) {
    const p = last[key]; last[key] = v;
    if (p === undefined || v === p) return "";
    return v > p ? "flash-up" : "flash-down";
  }
  function renderWatch() {
    const body = $("#watch tbody");
    if (!watch.length) { body.innerHTML = `<tr><td colspan="4" class="empty">Type a ticker above to add one.</td></tr>`; return; }
    body.innerHTML = watch.map((s) => {
      const q = us[s] || {};
      const chg = q.price != null && q.prev ? (q.price / q.prev - 1) * 100 : null;
      return `<tr class="click" data-sym="${esc(s)}"><td>${esc(s)} ${q.src ? `<span class="muted">${esc(q.src)}</span>` : ""}</td>
        <td class="r ${flashCls("w" + s, q.price)}">${px(q.price)}</td><td class="r">${pct(chg)}</td>
        <td class="r"><button class="x" data-rm="${esc(s)}" title="Remove">×</button></td></tr>`;
    }).join("");
  }
  const CRYPTO = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK"];
  function renderCrypto() {
    $("#crypto tbody").innerHTML = CRYPTO.map((c) => {
      const q = crypto[c] || {};
      const chg = q.price != null && q.open ? (q.price / q.open - 1) * 100 : null;
      return `<tr><td>${c}/USD</td><td class="r ${flashCls("c" + c, q.price)}">${px(q.price)}</td><td class="r">${pct(chg)}</td></tr>`;
    }).join("");
  }
  function renderTape() {
    const items = [];
    for (const c of ["BTC", "ETH", "SOL"]) if (crypto[c]?.price) items.push([c, crypto[c].price, crypto[c].open ? (crypto[c].price / crypto[c].open - 1) * 100 : null]);
    for (const s of watch.slice(0, 8)) if (us[s]?.price) items.push([s, us[s].price, us[s].prev ? (us[s].price / us[s].prev - 1) * 100 : null]);
    for (const q of DATA.markets.uk_delayed) items.push([q.name + "*", q.price, q.change_pct]);
    for (const q of DATA.markets.us_reference) if (["^VIX", "GC=F", "^TNX"].includes(q.symbol)) items.push([q.name, q.price, q.change_pct]);
    $("#tape").innerHTML = items.map(([n, p, c]) => `<span><b>${esc(n)}</b>${px(p)} ${pct(c)}</span>`).join("") || '<span class="muted">waiting for data…</span>';
  }
  function render() {
    if (!dirty) return;
    dirty = false;
    renderWatch(); renderCrypto(); renderTape();
  }
  setInterval(render, 500);

  // ---------- static panels from data.json ----------
  function table(sel, rows, fn, cols, empty) {
    $(sel + " tbody").innerHTML = rows.length ? rows.map(fn).join("") : `<tr><td colspan="${cols}" class="empty">${empty}</td></tr>`;
  }
  function renderStatic() {
    const built = new Date(DATA.generated_at);
    $("#built").textContent = isNaN(built) ? "" : "built " + built.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
    $("#brief").textContent = DATA.brief?.text || "No brief yet.";
    $("#brief-src").textContent = DATA.brief?.source === "ai" ? "AI" : "auto";
    const S = DATA.signals;
    table("#insider", S.watchlist, (r) => `<tr class="click" data-sym="${esc(r.ticker || "")}">
      <td>${esc(r.signal_date)}</td><td>${esc(r.ticker || "–")}</td><td title="${esc(r.insiders)}">${esc(r.issuer)}</td>
      <td class="r">${r.n_insiders ?? "–"}</td><td class="r">${money(r.total_value)}</td><td class="r">${money(r.market_cap)}</td>
      <td class="r">${pct(r.ret_5d == null ? null : r.ret_5d * 100, 1)}</td><td class="r">${pct(r.ret_20d == null ? null : r.ret_20d * 100, 1)}</td></tr>`, 8, "No cluster buys in the last 30 days.");
    table("#avoid", S.avoid, (r) => `<tr title="${esc(r.isin)}, since ${esc(r.since)}"><td>${esc(r.issuer)}${r.ticker ? ` <span class="muted">${esc(r.ticker)}</span>` : ""}</td>
      <td class="r">${fmt(r.new_pct, 2)}%</td><td class="r down">+${fmt(r.delta_pp, 2)}pp</td></tr>`, 3, "Nothing crossed the threshold. Needs a few days of FCA history to build up.");
    table("#shorted", S.most_shorted || [], (r) => `<tr><td>${esc(r.issuer)}${r.ticker ? ` <span class="muted">${esc(r.ticker)}</span>` : ""}</td><td class="r">${fmt(r.net_short_pct, 2)}%</td></tr>`, 2, "No FCA snapshot yet.");
    table("#combo", S.combo, (r) => `<tr><td>${esc(r.signal_date)}</td><td>${esc(r.company)}</td><td class="r">${fmt(+r.total_net_short_pct, 2)}%</td><td class="r">£${fmt(+r.director_value_gbp, 0)}</td></tr>`, 4, "No hits. Director buys are added by hand to data/rns_director_buys.csv.");
    const uk = [...DATA.markets.uk_delayed, ...(DATA.uk_names || [])];
    table("#uk", uk, (q) => `<tr title="${esc(q.symbol)} at ${esc(q.time || "")}"><td>${esc(q.name)}</td><td class="r">${px(q.price)}</td><td class="r">${pct(q.change_pct)}</td></tr>`, 3, "No delayed quotes in this build.");
    const ukT = DATA.markets.uk_delayed[0]?.time;
    if (ukT) $("#uk-note").textContent = `Yahoo quotes, about 15 minutes delayed, as of ${new Date(ukT).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}. No free live UK feed exists.`;
    table("#ref", DATA.markets.us_reference, (q) => {
      const c = q.closes || []; const d5 = c.length >= 2 ? (c[c.length - 1] / c[0] - 1) * 100 : null;
      return `<tr><td>${esc(q.name)}</td><td class="r">${px(q.price)}</td><td class="r">${pct(q.change_pct)}</td><td class="r">${pct(d5, 1)}</td></tr>`;
    }, 4, "No reference quotes in this build.");
    for (const q of DATA.markets.us_reference) if (!us[q.symbol] && !q.symbol.includes("^") && !q.symbol.includes("=")) us[q.symbol] = { price: q.price, prev: q.prev_close, src: "delayed" };
    renderFeed(); fillAnalystPicker(); mark();
  }
  function renderFeed() {
    const f = DATA.feed;
    if (!f || !f.rows?.length) return;
    $("#p-feed").hidden = false;
    const cols = f.columns.slice(0, 12);
    $("#feed thead").innerHTML = "<tr>" + cols.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr>";
    $("#feed tbody").innerHTML = f.rows.map((r) => "<tr>" + cols.map((c) => {
      const v = r[c]; const n = Number(v);
      const isRet = /ret|return|excess/i.test(c) && v !== "" && !isNaN(n);
      return `<td class="${isRet ? "r" : ""}">${isRet ? pct(Math.abs(n) < 5 ? n * 100 : n, 1) : esc(v)}</td>`;
    }).join("") + "</tr>").join("");
  }

  // ---------- analyst trends ----------
  function fillAnalystPicker() {
    const syms = [...new Set([...watch, ...DATA.signals.watchlist.map((r) => r.ticker).filter(Boolean)])].filter((s) => /^[A-Z.\-]+$/.test(s) && !["SPY", "QQQ", "IWM", "DIA"].includes(s));
    const sel = $("#analyst-sym"); const cur = sel.value;
    sel.innerHTML = syms.map((s) => `<option>${esc(s)}</option>`).join("");
    if (syms.includes(cur)) sel.value = cur;
    loadAnalyst(sel.value);
  }
  async function loadAnalyst(sym) {
    const box = $("#analyst");
    if (!sym) { box.innerHTML = '<p class="note">Add a stock to your watchlist.</p>'; return; }
    let rows = DATA.analyst?.[sym];
    const k = keys().fh;
    if (!rows && k) {
      box.innerHTML = '<p class="note">Loading…</p>';
      try {
        const r = await fetch(`https://finnhub.io/api/v1/stock/recommendation?symbol=${encodeURIComponent(sym)}&token=${encodeURIComponent(k)}`);
        rows = r.ok ? await r.json() : null;
      } catch { rows = null; }
    }
    if (!rows || !rows.length) {
      box.innerHTML = k ? `<p class="note">No analyst coverage for ${esc(sym)} on Finnhub's free plan.</p>` : '<p class="note">Add a free Finnhub key (Keys button) to see buy, hold and sell trends.</p>';
      return;
    }
    const segs = [["strongBuy", "c-sb"], ["buy", "c-b"], ["hold", "c-h"], ["sell", "c-s"], ["strongSell", "c-ss"]];
    box.innerHTML = rows.slice(0, 4).map((m) => {
      const tot = segs.reduce((a, [k2]) => a + (m[k2] || 0), 0) || 1;
      return `<div class="rec"><span>${esc((m.period || "").slice(0, 7))}</span><span class="bar">${segs.map(([k2, c]) => m[k2] ? `<i class="${c}" style="width:${(m[k2] / tot) * 100}%" title="${k2}: ${m[k2]}"></i>` : "").join("")}</span><span class="r">${tot}</span></div>`;
    }).join("") + `<div class="legend"><span><i class="c-sb"></i>Strong buy</span><span><i class="c-b"></i>Buy</span><span><i class="c-h"></i>Hold</span><span><i class="c-s"></i>Sell</span><span><i class="c-ss"></i>Strong sell</span></div>`;
  }
  $("#analyst-sym").addEventListener("change", (e) => loadAnalyst(e.target.value));

  // ---------- US live ----------
  let usWs = null, usRetry = 1000;
  async function prevCloses(syms) {
    const { fh, aid, asec } = keys();
    if (fh) {
      for (const s of syms) {
        try {
          const r = await fetch(`https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(s)}&token=${encodeURIComponent(fh)}`);
          const q = r.ok ? await r.json() : null;
          if (q && q.pc) { us[s] = { ...(us[s] || {}), prev: q.pc, price: us[s]?.src === "live" ? us[s].price : (q.c || us[s]?.price), src: us[s]?.src || "quote" }; mark(); }
        } catch { /* ignore */ }
      }
    } else if (aid && asec) {
      try {
        const r = await fetch(`https://data.alpaca.markets/v2/stocks/snapshots?symbols=${syms.map(encodeURIComponent).join(",")}&feed=iex`, { headers: { "APCA-API-KEY-ID": aid, "APCA-API-SECRET-KEY": asec } });
        const j = r.ok ? await r.json() : {};
        for (const [s, v] of Object.entries(j)) { us[s] = { ...(us[s] || {}), prev: v?.prevDailyBar?.c ?? us[s]?.prev, price: us[s]?.src === "live" ? us[s].price : (v?.latestTrade?.p ?? us[s]?.price), src: us[s]?.src || "iex" }; }
        mark();
      } catch { /* browser may block cross-origin; stream still works */ }
    }
  }
  function onTrade(s, p) { us[s] = { ...(us[s] || {}), price: p, src: "live" }; mark(); }
  function setUsStatus(text, live) { const b = $("#us-status"); b.textContent = text; b.className = "badge" + (live ? " live" : ""); $("#pulse").classList.toggle("on", !!live); }
  function connectUS() {
    if (usWs) { usWs.onclose = null; try { usWs.close(); } catch { /* */ } usWs = null; }
    const { aid, asec, fh } = keys();
    const syms = watch.filter((s) => /^[A-Z.\-]{1,10}$/.test(s));
    prevCloses(syms);
    if (aid && asec) {
      setUsStatus("US: Alpaca connecting", false);
      usWs = new WebSocket("wss://stream.data.alpaca.markets/v2/iex");
      usWs.onmessage = (ev) => {
        let msgs; try { msgs = JSON.parse(ev.data); } catch { return; }
        for (const m of msgs) {
          if (m.T === "success" && m.msg === "connected") usWs.send(JSON.stringify({ action: "auth", key: aid, secret: asec }));
          else if (m.T === "success" && m.msg === "authenticated") { usRetry = 1000; usWs.send(JSON.stringify({ action: "subscribe", trades: syms })); setUsStatus("US: live IEX", true); }
          else if (m.T === "error") setUsStatus(`US: Alpaca error ${m.code}: ${m.msg}`, false);
          else if (m.T === "t") onTrade(m.S, m.p);
        }
      };
    } else if (fh) {
      setUsStatus("US: Finnhub connecting", false);
      usWs = new WebSocket(`wss://ws.finnhub.io?token=${encodeURIComponent(fh)}`);
      usWs.onopen = () => { usRetry = 1000; syms.forEach((s) => usWs.send(JSON.stringify({ type: "subscribe", symbol: s }))); setUsStatus("US: live Finnhub", true); };
      usWs.onmessage = (ev) => { let m; try { m = JSON.parse(ev.data); } catch { return; } if (m.type === "trade") for (const t of m.data || []) onTrade(t.s, t.p); };
    } else {
      setUsStatus("US: delayed (add keys for live)", false);
      $("#watch-note").textContent = "Add free Alpaca or Finnhub keys (Keys button) for live US prices. Until then, ETFs show the delayed build-time price.";
      return;
    }
    $("#watch-note").textContent = "Live trades only print while the market trades (IEX covers about 2-3% of US volume, so quiet names update slowly).";
    usWs.onclose = () => { setUsStatus("US: reconnecting", false); setTimeout(connectUS, usRetry); usRetry = Math.min(usRetry * 2, 60000); };
  }

  // ---------- crypto live ----------
  let cWs = null, cRetry = 1000;
  function connectCrypto() {
    if (cWs) { cWs.onclose = null; try { cWs.close(); } catch { /* */ } }
    const src = keys().crypto;
    const status = (t, live) => { const b = $("#crypto-status"); b.textContent = t; b.className = "badge" + (live ? " live" : ""); };
    if (src === "binance") {
      const streams = CRYPTO.map((c) => c.toLowerCase() + "usdt@miniTicker").join("/");
      cWs = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`);
      cWs.onmessage = (ev) => { const d = JSON.parse(ev.data).data; if (!d) return; const c = d.s.replace("USDT", ""); crypto[c] = { price: +d.c, open: +d.o }; mark(); };
      cWs.onopen = () => { cRetry = 1000; status("live Binance (USDT)", true); };
    } else {
      cWs = new WebSocket("wss://ws-feed.exchange.coinbase.com");
      cWs.onopen = () => { cRetry = 1000; cWs.send(JSON.stringify({ type: "subscribe", product_ids: CRYPTO.map((c) => c + "-USD"), channels: ["ticker"] })); status("live Coinbase", true); };
      cWs.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.type !== "ticker") return; const c = m.product_id.split("-")[0]; crypto[c] = { price: +m.price, open: +m.open_24h }; mark(); };
    }
    cWs.onclose = () => { status("reconnecting", false); setTimeout(connectCrypto, cRetry); cRetry = Math.min(cRetry * 2, 60000); };
  }

  // ---------- watchlist + command bar ----------
  function addSym(s) {
    s = s.trim().toUpperCase();
    if (!/^[A-Z][A-Z.\-]{0,9}$/.test(s)) return false;
    if (!watch.includes(s)) { watch.push(s); store.set("watch", watch); connectUS(); fillAnalystPicker(); }
    $("#analyst-sym").value = s; loadAnalyst(s); mark();
    return true;
  }
  function rmSym(s) { watch = watch.filter((x) => x !== s); store.set("watch", watch); connectUS(); fillAnalystPicker(); mark(); }
  $("#cmd").addEventListener("submit", (e) => {
    e.preventDefault();
    const inp = $("#cmd-input"); const v = inp.value.trim(); inp.value = "";
    const [cmd, arg] = v.split(/\s+/);
    if (!v) return;
    if (/^help$/i.test(cmd)) { inp.placeholder = "TICKER adds · rm TICKER removes · keys opens settings · clear empties watchlist"; return; }
    if (/^keys$/i.test(cmd)) { openSettings(); return; }
    if (/^clear$/i.test(cmd)) { watch = []; store.set("watch", watch); connectUS(); mark(); return; }
    if (/^rm$/i.test(cmd) && arg) { rmSym(arg.toUpperCase()); return; }
    if (!addSym(cmd)) inp.placeholder = `Not a ticker: ${v}. Type 'help'.`;
  });
  document.addEventListener("keydown", (e) => { if (e.key === "/" && document.activeElement !== $("#cmd-input") && !$("#settings").open) { e.preventDefault(); $("#cmd-input").focus(); } });
  document.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]"); if (rm) { e.stopPropagation(); rmSym(rm.dataset.rm); return; }
    const row = e.target.closest("tr[data-sym]"); if (row && row.dataset.sym) addSym(row.dataset.sym);
  });

  // ---------- settings ----------
  function openSettings() {
    const k = keys();
    $("#k-alpaca-id").value = k.aid; $("#k-alpaca-secret").value = k.asec; $("#k-finnhub").value = k.fh; $("#k-crypto").value = k.crypto;
    $("#settings").showModal();
  }
  $("#open-settings").addEventListener("click", openSettings);
  $("#settings").addEventListener("close", () => {
    if ($("#settings").returnValue !== "save") return;
    store.set("alpacaId", $("#k-alpaca-id").value.trim()); store.set("alpacaSecret", $("#k-alpaca-secret").value.trim());
    store.set("finnhub", $("#k-finnhub").value.trim()); store.set("crypto", $("#k-crypto").value);
    connectUS(); connectCrypto(); fillAnalystPicker();
  });

  // ---------- boot ----------
  renderClocks(); setInterval(renderClocks, 15000);
  fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : Promise.reject(r.status))
    .then((d) => { DATA = { ...DATA, ...d }; renderStatic(); })
    .catch(() => { $("#brief").textContent = "Could not load data.json. The page may still be building."; })
    .finally(() => { connectUS(); connectCrypto(); });
  // Refresh build-time data every 10 minutes without reloading live streams.
  setInterval(() => fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((d) => { if (d) { DATA = { ...DATA, ...d }; renderStatic(); } }).catch(() => {}), 600000);
})();
