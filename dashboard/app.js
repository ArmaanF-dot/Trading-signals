/* Jarvis: market homescreen. Live data comes straight from the providers' public
   websockets using keys kept in this browser's localStorage; the rest comes from
   data.json, rebuilt by GitHub Actions. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem("jarvis." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("jarvis." + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => v !== null && v !== undefined && v !== "" && !isNaN(v);
  const fmt = (v, d = 2) => !num(v) ? "–" : Number(v).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const px = (v) => !num(v) ? "–" : fmt(v, v >= 1 ? 2 : 4);
  // invert: for things where up is bad news (the fear gauge), colour a rise red.
  const chg = (v, d = 2, invert = false) => !num(v) ? '<span class="chg flat">–</span>'
    : `<span class="chg ${Math.abs(v) < 0.005 ? "flat" : (v > 0) !== invert ? "up" : "down"}">${v > 0 ? "▲" : v < 0 ? "▼" : ""} ${fmt(Math.abs(v), d)}%</span>`;
  const shortDate = (iso) => { const d = new Date(iso + "T12:00:00Z"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };
  const pctTxt = (v, d = 1) => !num(v) ? "–" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : "−"}${fmt(Math.abs(v), d)}%</span>`;
  const money = (v, cur = "$") => !num(v) ? "–" : v >= 1e9 ? `${cur}${fmt(v / 1e9, 1)}bn` : v >= 1e6 ? `${cur}${fmt(v / 1e6, 1)}m` : `${cur}${fmt(v / 1e3, 0)}k`;
  const daysAgo = (iso) => {
    const d = new Date(iso + "T12:00:00Z"); if (isNaN(d)) return "";
    const n = Math.round((Date.now() - d) / 864e5);
    return n <= 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`;
  };

  let DATA = { markets: { uk_delayed: [], us_reference: [] }, signals: { watchlist: [], avoid: [], most_shorted: [], combo: [] }, analyst: {}, uk_names: [] };
  const keys = () => ({ aid: store.get("alpacaId", ""), asec: store.get("alpacaSecret", ""), fh: store.get("finnhub", ""), crypto: store.get("crypto", "coinbase") });
  let watch = store.get("watch", ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT"]);
  const us = {};      // sym -> {price, prev, src}
  const crypto = {};  // coin -> {price, open}
  const hist = {};    // key -> recent live prices, for sparklines
  const last = {};    // for flash direction

  // ---------- header: greeting and market hours ----------
  const MARKETS = [
    { name: "London", tz: "Europe/London", open: [8, 0], close: [16, 30] },
    { name: "New York", tz: "America/New_York", open: [9, 30], close: [16, 0], pre: [4, 0], post: [20, 0] },
    { name: "Tokyo", tz: "Asia/Tokyo", open: [9, 0], close: [15, 30] },
  ];
  function tzParts(tz) {
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false }).formatToParts(new Date());
    const g = (t) => p.find((x) => x.type === t)?.value;
    return { h: +g("hour") % 24, m: +g("minute"), wd: g("weekday") };
  }
  function renderHeader() {
    const h = new Date().getHours();
    $("#greeting").textContent = h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    $("#today").textContent = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
    $("#clocks").innerHTML = MARKETS.map((mk) => {
      const { h: hh, m, wd } = tzParts(mk.tz);
      const mins = hh * 60 + m, at = (a) => a[0] * 60 + a[1];
      const weekday = !["Sat", "Sun"].includes(wd);
      let st = "shut", label = "closed";
      if (weekday && mins >= at(mk.open) && mins < at(mk.close)) { st = "open"; label = "open"; }
      else if (weekday && mk.pre && mins >= at(mk.pre) && mins < at(mk.open)) { st = "pre"; label = "pre-market"; }
      else if (weekday && mk.post && mins >= at(mk.close) && mins < at(mk.post)) { st = "pre"; label = "after hours"; }
      const time = `${String(hh).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      return `<span class="pill ${st}"><i></i>${mk.name} <b>${label}</b> · ${time}</span>`;
    }).join("");
  }

  // ---------- sparklines ----------
  function spark(values, up) {
    const v = (values || []).filter(num);
    if (v.length < 2) return '<svg class="spark"></svg>';
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = v.map((y, i) => `${(i / (v.length - 1)) * 100},${26 - ((y - lo) / span) * 22}`).join(" ");
    const col = up ? "var(--up)" : "var(--down)";
    return `<svg class="spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;
  }
  function pushHist(key, p) {
    const h = hist[key] || (hist[key] = []);
    const now = Date.now();
    if (!h.length || now - h[h.length - 1].t > 4000) h.push({ t: now, p }); else h[h.length - 1].p = p;
    if (h.length > 90) h.shift();
  }

  // ---------- market tiles ----------
  const TILES = [
    { key: "^FTSE", name: "FTSE 100", what: "Biggest UK companies" },
    { key: "^FTMC", name: "FTSE 250", what: "Mid-sized UK companies" },
    { key: "SPY", name: "S&P 500", what: "Biggest US companies (SPY fund)" },
    { key: "QQQ", name: "Nasdaq 100", what: "US tech giants (QQQ fund)" },
    { key: "IWM", name: "Russell 2000", what: "Small US companies (IWM fund)" },
    { key: "BTC", name: "Bitcoin", what: "US$, change over 24h", crypto: true },
    { key: "ETH", name: "Ethereum", what: "US$, change over 24h", crypto: true },
    { key: "^VIX", name: "Fear gauge", what: "VIX: higher means more nervous", invert: true },
    { key: "GBPUSD=X", name: "Pound", what: "Dollars per pound" },
    { key: "GC=F", name: "Gold", what: "US$ per ounce" },
  ];
  function quoteFor(sym) {
    return [...DATA.markets.uk_delayed, ...DATA.markets.us_reference].find((q) => q.symbol === sym);
  }
  function renderTiles() {
    $("#tiles").innerHTML = TILES.map((t) => {
      let price, change, line, live = false;
      if (t.crypto) {
        const c = crypto[t.key] || {};
        price = c.price; change = num(c.price) && c.open ? (c.price / c.open - 1) * 100 : null;
        line = (hist[t.key] || []).map((x) => x.p); live = num(c.price);
      } else {
        const q = quoteFor(t.key) || {};
        const l = us[t.key];
        if (l && l.src === "live") { price = l.price; change = l.prev ? (l.price / l.prev - 1) * 100 : q.change_pct; live = true; line = (hist[t.key] || []).map((x) => x.p); }
        else { price = q.price; change = q.change_pct; line = q.closes; }
        if (!num(price)) return "";
      }
      const up = (num(change) ? change >= 0 : true) !== !!t.invert;
      return `<div class="tile"><div class="name"><span class="${live ? "live-dot" : "delayed-dot"}"></span>${esc(t.name)}</div>
        <div class="val ${flashCls("t" + t.key, price)}">${num(price) ? px(price) : "…"}</div>${chg(change, 2, t.invert)}<div class="what">${esc(t.what)}</div>${spark(line, up)}</div>`;
    }).join("") || '<div class="empty">Prices appear after the next rebuild.</div>';
  }

  // ---------- live lists ----------
  let dirty = true;
  const mark = () => { dirty = true; };
  function flashCls(key, v) {
    const p = last[key]; last[key] = v;
    if (p === undefined || v === p || !num(v) || !num(p)) return "";
    return v > p ? "flash-up" : "flash-down";
  }
  const SRC_LABEL = { live: "live", delayed: "delayed", quote: "last close", iex: "last trade" };
  function renderWatch() {
    const list = $("#watch");
    if (!watch.length) { list.innerHTML = '<li class="empty">Add a stock above to follow it here.</li>'; return; }
    list.innerHTML = watch.map((s) => {
      const q = us[s] || {};
      const c = num(q.price) && q.prev ? (q.price / q.prev - 1) * 100 : null;
      return `<li><span class="sym">${esc(s)}${q.src ? `<small>${esc(SRC_LABEL[q.src] || q.src)}</small>` : ""}</span>
        <span class="price ${flashCls("w" + s, q.price)}">${num(q.price) ? "$" + px(q.price) : "–"}</span>${chg(c)}
        <button class="x" data-rm="${esc(s)}" title="Remove ${esc(s)}" aria-label="Remove ${esc(s)}">×</button></li>`;
    }).join("");
  }
  const CRYPTO = [["BTC", "Bitcoin"], ["ETH", "Ethereum"], ["SOL", "Solana"], ["XRP", "XRP"], ["DOGE", "Dogecoin"], ["ADA", "Cardano"], ["LINK", "Chainlink"]];
  function renderCrypto() {
    $("#crypto").innerHTML = CRYPTO.map(([c, name]) => {
      const q = crypto[c] || {};
      const ch = num(q.price) && q.open ? (q.price / q.open - 1) * 100 : null;
      return `<li><span class="sym">${name}<small>${c}</small></span><span class="price ${flashCls("c" + c, q.price)}">${num(q.price) ? "$" + px(q.price) : "–"}</span>${chg(ch)}</li>`;
    }).join("");
  }
  function render() {
    if (!dirty) return;
    dirty = false;
    renderTiles(); renderWatch(); renderCrypto();
  }
  setInterval(render, 600);

  // ---------- signals and the brief ----------
  function rolesOf(insiders) {
    const s = String(insiders || "");
    if (/Chief Executive|\bCEO\b/i.test(s)) return "including the chief executive";
    if (/Chief Financial|\bCFO\b/i.test(s)) return "including the finance chief";
    if (/President|Chair/i.test(s)) return "including the chair or president";
    if (/Director/i.test(s)) return "including a director";
    return "";
  }
  function renderSignals() {
    const S = DATA.signals;
    $("#insider").innerHTML = S.watchlist.length ? S.watchlist.slice(0, 6).map((r) => {
      const who = [`${r.n_insiders ?? "Several"} insiders bought`, rolesOf(r.insiders)].filter(Boolean).join(", ");
      const since = num(r.ret_20d) ? ` · ${pctTxt(r.ret_20d * 100)} in the 20 days after` : num(r.ret_5d) ? ` · ${pctTxt(r.ret_5d * 100)} in the 5 days after` : "";
      return `<div class="sig ${r.ticker ? "click" : ""}" data-sym="${esc(r.ticker || "")}" title="${esc(r.insiders)}">
        <span class="t">${esc(r.ticker || r.issuer)}<small>${esc(r.ticker ? r.issuer : "")}</small></span><span class="big">${money(r.total_value)}</span>
        <span class="line">${esc(who)}.</span>
        <span class="when">${esc(daysAgo(r.signal_date))}${num(r.market_cap) ? ` · company worth ${money(r.market_cap)}` : ""}${since}</span></div>`;
    }).join("") : '<div class="empty">No insider buying clusters in the last 30 days.</div>';

    $("#avoid").innerHTML = S.avoid.length ? S.avoid.slice(0, 6).map((r) => `<div class="sig" title="${esc(r.isin)}">
        <span class="t">${esc(r.issuer)}${r.ticker ? `<small>${esc(r.ticker)}</small>` : ""}</span><span class="big down">${fmt(r.new_pct, 1)}% shorted</span>
        <span class="line">Short bets up ${fmt(r.delta_pp, 1)} points since ${esc(shortDate(r.since))}.</span></div>`).join("")
      : '<div class="empty">No UK shares saw a big jump in short bets this month.</div>';

    $("#shorted-top").innerHTML = (S.most_shorted || []).slice(0, 5).map((r) =>
      `<li>${esc(titleCase(r.issuer))}<span>${fmt(r.net_short_pct, 1)}%</span></li>`).join("") || '<li class="muted">No data yet.</li>';
  }
  function titleCase(s) {
    s = String(s || "");
    return s === s.toUpperCase() ? s.toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase()).replace(/\bPlc\b/g, "plc") : s;
  }
  function renderBrief() {
    const text = DATA.brief?.text || "No brief yet.";
    $("#brief").innerHTML = text.split(/\n\s*\n/).map((p) => `<p>${esc(p.trim())}</p>`).join("");
    const ai = DATA.brief?.source === "ai";
    $("#brief-src").textContent = ai ? "written by Claude" : "automatic summary";
    const built = new Date(DATA.generated_at);
    $("#built").textContent = isNaN(built) ? "" : "Updated " + built.toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" }) + ". Prices marked delayed were captured then.";
  }

  // ---------- more detail ----------
  function table(sel, rows, fn, cols, empty) {
    $(sel + " tbody").innerHTML = rows.length ? rows.map(fn).join("") : `<tr><td colspan="${cols}" class="empty muted">${empty}</td></tr>`;
  }
  function renderDetail() {
    const S = DATA.signals;
    const all = [...DATA.markets.uk_delayed, ...DATA.markets.us_reference, ...(DATA.uk_names || [])];
    table("#ref", all, (q) => {
      const c = q.closes || []; const d5 = c.length >= 2 ? (c[c.length - 1] / c[0] - 1) * 100 : null;
      return `<tr><td>${esc(q.name)}</td><td class="r">${px(q.price)}</td><td class="r">${pctTxt(q.change_pct, 2)}</td><td class="r">${pctTxt(d5)}</td></tr>`;
    }, 4, "No prices in this build.");
    table("#shorted", S.most_shorted || [], (r) => `<tr><td>${esc(titleCase(r.issuer))}${r.ticker ? ` <span class="muted">${esc(r.ticker)}</span>` : ""}</td><td class="r">${fmt(r.net_short_pct, 2)}%</td></tr>`, 2, "No FCA data yet.");
    table("#combo", S.combo, (r) => `<tr><td>${esc(r.signal_date)}</td><td>${esc(r.company)}</td><td class="r">${fmt(+r.total_net_short_pct, 1)}%</td><td class="r">£${fmt(+r.director_value_gbp, 0)}</td></tr>`, 4, "None yet. Director buys are added by hand to data/rns_director_buys.csv.");
    const f = DATA.feed;
    if (!f || !f.rows?.length) return;
    $("#p-feed").hidden = false;
    $("#feed-asof").textContent = f.as_of ? "as of " + f.as_of : "";
    $("#feed-note").textContent = f.disclaimer || "";
    if (f.track_record) { $("#track").hidden = false; $("#track-text").textContent = f.track_record; }
    const cols = f.columns.filter((c) => c !== "evidence").slice(0, 8);
    $("#feed thead").innerHTML = "<tr>" + cols.map((c) => `<th>${esc(c[0].toUpperCase() + c.slice(1))}</th>`).join("") + "</tr>";
    $("#feed tbody").innerHTML = f.rows.map((r) => `<tr title="${esc(r.evidence || "")}">` + cols.map((c) => {
      const v = r[c];
      if (c === "stance") return `<td class="${v === "avoid" ? "down" : v === "watch" ? "up" : "muted"}">${esc(v)}</td>`;
      return `<td title="${esc(v)}">${esc(v)}</td>`;
    }).join("") + "</tr>").join("");
  }
  function renderStatic() {
    renderBrief(); renderSignals(); renderDetail();
    for (const q of DATA.markets.us_reference) if (!us[q.symbol] && /^[A-Z]+$/.test(q.symbol)) us[q.symbol] = { price: q.price, prev: q.prev_close, src: "delayed" };
    fillAnalystPicker(); mark();
  }

  // ---------- analysts ----------
  function fillAnalystPicker() {
    const syms = [...new Set([...DATA.signals.watchlist.map((r) => r.ticker).filter(Boolean), ...watch])].filter((s) => /^[A-Z.\-]+$/.test(s) && !["SPY", "QQQ", "IWM", "DIA"].includes(s));
    const sel = $("#analyst-sym"); const cur = sel.value;
    sel.innerHTML = syms.map((s) => `<option>${esc(s)}</option>`).join("");
    if (syms.includes(cur)) sel.value = cur;
    loadAnalyst(sel.value);
  }
  async function loadAnalyst(sym) {
    const box = $("#analyst");
    if (!sym) { box.innerHTML = '<p class="hint">Add a stock to your watchlist to see what analysts think of it.</p>'; return; }
    let rows = DATA.analyst?.[sym];
    const k = keys().fh;
    if (!rows && k) {
      box.innerHTML = '<p class="hint">Loading…</p>';
      try {
        const r = await fetch(`https://finnhub.io/api/v1/stock/recommendation?symbol=${encodeURIComponent(sym)}&token=${encodeURIComponent(k)}`);
        rows = r.ok ? await r.json() : null;
      } catch { rows = null; }
    }
    if (!rows || !rows.length) {
      box.innerHTML = k ? `<p class="hint">No analyst ratings for ${esc(sym)} on Finnhub's free plan.</p>` : '<p class="hint">Add a free Finnhub key (Keys button) to see how many analysts rate each stock a buy, hold or sell.</p>';
      return;
    }
    const m = rows[0];
    const buys = (m.strongBuy || 0) + (m.buy || 0), holds = m.hold || 0, sells = (m.sell || 0) + (m.strongSell || 0), tot = buys + holds + sells || 1;
    const [word, cls] = buys >= holds && buys >= sells ? ["Buy", "up"] : sells > holds ? ["Sell", "down"] : ["Hold", "flat"];
    let trend = "";
    const old = rows[3] || rows[rows.length - 1];
    if (old && old !== m) {
      const ob = ((old.strongBuy || 0) + (old.buy || 0)) / (((old.strongBuy || 0) + (old.buy || 0) + (old.hold || 0) + (old.sell || 0) + (old.strongSell || 0)) || 1);
      const diff = buys / tot - ob;
      trend = Math.abs(diff) < 0.03 ? " Views are about the same as a few months ago." : diff > 0 ? " Analysts have grown more positive recently." : " Analysts have grown more cautious recently.";
    }
    const segs = [["strongBuy", "c-sb"], ["buy", "c-b"], ["hold", "c-h"], ["sell", "c-s"], ["strongSell", "c-ss"]];
    box.innerHTML = `<p class="verdict">Most analysts say <b class="${cls}">${word}</b> for ${esc(sym)}: ${buys} buy, ${holds} hold, ${sells} sell.${trend}</p>` +
      rows.slice(0, 4).map((mm) => {
        const t = segs.reduce((a, [k2]) => a + (mm[k2] || 0), 0) || 1;
        const month = new Date((mm.period || "") + "T12:00:00Z");
        return `<div class="rec"><span>${isNaN(month) ? esc(mm.period) : month.toLocaleDateString("en-GB", { month: "short", year: "2-digit" })}</span><span class="bar">${segs.map(([k2, c]) => mm[k2] ? `<i class="${c}" style="width:${(mm[k2] / t) * 100}%" title="${k2}: ${mm[k2]}"></i>` : "").join("")}</span><span class="r">${t}</span></div>`;
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
          if (q && q.pc) { us[s] = { ...(us[s] || {}), prev: q.pc, price: us[s]?.src === "live" ? us[s].price : (q.c || us[s]?.price), src: us[s]?.src === "live" ? "live" : "quote" }; mark(); }
        } catch { /* ignore */ }
      }
    } else if (aid && asec) {
      try {
        const r = await fetch(`https://data.alpaca.markets/v2/stocks/snapshots?symbols=${syms.map(encodeURIComponent).join(",")}&feed=iex`, { headers: { "APCA-API-KEY-ID": aid, "APCA-API-SECRET-KEY": asec } });
        const j = r.ok ? await r.json() : {};
        for (const [s, v] of Object.entries(j)) us[s] = { ...(us[s] || {}), prev: v?.prevDailyBar?.c ?? us[s]?.prev, price: us[s]?.src === "live" ? us[s].price : (v?.latestTrade?.p ?? us[s]?.price), src: us[s]?.src === "live" ? "live" : "iex" };
        mark();
      } catch { /* browser may block cross-origin; the stream still works */ }
    }
  }
  function onTrade(s, p) { us[s] = { ...(us[s] || {}), price: p, src: "live" }; pushHist(s, p); mark(); }
  function setUsStatus(text, live) { const b = $("#us-status"); b.textContent = text; b.className = "tag" + (live ? " live" : ""); $("#pulse").classList.toggle("on", !!live); }
  function connectUS() {
    if (usWs) { usWs.onclose = null; try { usWs.close(); } catch { /* */ } usWs = null; }
    const { aid, asec, fh } = keys();
    const syms = [...new Set([...watch, "SPY", "QQQ", "IWM"])].filter((s) => /^[A-Z.\-]{1,10}$/.test(s));
    prevCloses(syms);
    if (aid && asec) {
      setUsStatus("connecting", false);
      usWs = new WebSocket("wss://stream.data.alpaca.markets/v2/iex");
      usWs.onmessage = (ev) => {
        let msgs; try { msgs = JSON.parse(ev.data); } catch { return; }
        for (const m of msgs) {
          if (m.T === "success" && m.msg === "connected") usWs.send(JSON.stringify({ action: "auth", key: aid, secret: asec }));
          else if (m.T === "success" && m.msg === "authenticated") { usRetry = 1000; usWs.send(JSON.stringify({ action: "subscribe", trades: syms })); setUsStatus("live", true); }
          else if (m.T === "error") setUsStatus(`Alpaca error: ${m.msg}`, false);
          else if (m.T === "t") onTrade(m.S, m.p);
        }
      };
    } else if (fh) {
      setUsStatus("connecting", false);
      usWs = new WebSocket(`wss://ws.finnhub.io?token=${encodeURIComponent(fh)}`);
      usWs.onopen = () => { usRetry = 1000; syms.forEach((s) => usWs.send(JSON.stringify({ type: "subscribe", symbol: s }))); setUsStatus("live", true); };
      usWs.onmessage = (ev) => { let m; try { m = JSON.parse(ev.data); } catch { return; } if (m.type === "trade") for (const t of m.data || []) onTrade(t.s, t.p); };
    } else {
      setUsStatus("delayed", false);
      $("#watch-note").textContent = "For live US prices, add a free Alpaca or Finnhub key with the Keys button.";
      return;
    }
    $("#watch-note").textContent = "Prices update with each trade while the US market is open (2:30pm to 9pm UK time).";
    usWs.onclose = () => { setUsStatus("reconnecting", false); setTimeout(connectUS, usRetry); usRetry = Math.min(usRetry * 2, 60000); };
  }

  // ---------- crypto live ----------
  let cWs = null, cRetry = 1000;
  function connectCrypto() {
    if (cWs) { cWs.onclose = null; try { cWs.close(); } catch { /* */ } }
    const src = keys().crypto;
    const status = (t, live) => { const b = $("#crypto-status"); b.textContent = t; b.className = "tag" + (live ? " live" : ""); };
    const coins = CRYPTO.map(([c]) => c);
    const onTick = (c, price, open) => { crypto[c] = { price, open }; pushHist(c, price); mark(); };
    if (src === "binance") {
      cWs = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${coins.map((c) => c.toLowerCase() + "usdt@miniTicker").join("/")}`);
      cWs.onmessage = (ev) => { let d; try { d = JSON.parse(ev.data).data; } catch { return; } if (d) onTick(d.s.replace("USDT", ""), +d.c, +d.o); };
      cWs.onopen = () => { cRetry = 1000; status("live", true); };
    } else {
      cWs = new WebSocket("wss://ws-feed.exchange.coinbase.com");
      cWs.onopen = () => { cRetry = 1000; cWs.send(JSON.stringify({ type: "subscribe", product_ids: coins.map((c) => c + "-USD"), channels: ["ticker"] })); status("live", true); };
      cWs.onmessage = (ev) => { let m; try { m = JSON.parse(ev.data); } catch { return; } if (m.type === "ticker") onTick(m.product_id.split("-")[0], +m.price, +m.open_24h); };
    }
    cWs.onclose = () => { status("reconnecting", false); setTimeout(connectCrypto, cRetry); cRetry = Math.min(cRetry * 2, 60000); };
  }

  // ---------- watchlist ----------
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
    if (!v) return;
    if (!addSym(v)) inp.placeholder = `"${v}" isn't a ticker. Try AAPL or TSLA.`;
    else inp.placeholder = "Add a US stock, e.g. AAPL";
  });
  document.addEventListener("keydown", (e) => { if (e.key === "/" && !/INPUT|SELECT/.test(document.activeElement?.tagName) && !$("#settings").open) { e.preventDefault(); $("#cmd-input").focus(); } });
  document.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]"); if (rm) { e.stopPropagation(); rmSym(rm.dataset.rm); return; }
    const card = e.target.closest(".sig[data-sym]"); if (card && card.dataset.sym) addSym(card.dataset.sym);
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

  // ---------- install as an app ----------
  let installEvt = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvt = e; $("#install").hidden = false; });
  window.addEventListener("appinstalled", () => { $("#install").hidden = true; installEvt = null; });
  $("#install").addEventListener("click", async () => { if (!installEvt) return; installEvt.prompt(); await installEvt.userChoice; installEvt = null; $("#install").hidden = true; });
  const standalone = matchMedia("(display-mode: standalone)").matches || /--app/.test(location.search);
  if (/Windows/.test(navigator.userAgent) && !standalone) $("#win-app").hidden = false;
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

  // ---------- boot ----------
  renderHeader(); setInterval(renderHeader, 30000);
  renderSignals();
  fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : Promise.reject(r.status))
    .then((d) => { DATA = { ...DATA, ...d }; renderStatic(); })
    .catch(() => { $("#brief").innerHTML = "<p>Couldn't load today's data. The page may still be building; try again in a minute.</p>"; })
    .finally(() => { connectUS(); connectCrypto(); });
  // Refresh build-time data every 10 minutes without restarting the live streams.
  setInterval(() => fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((d) => { if (d) { DATA = { ...DATA, ...d }; renderStatic(); } }).catch(() => {}), 600000);
})();
