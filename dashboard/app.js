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
  const signed = (v, d = 1) => !num(v) ? "–" : `${v >= 0 ? "+" : "−"}${fmt(Math.abs(v), d)}%`;
  const cap = (s) => { s = String(s ?? ""); return s.charAt(0).toUpperCase() + s.slice(1); };
  // Change figure: green or red text; moves at or past `hot` also get a tinted chip.
  // invert: for things where up is bad news (the fear gauge), colour a rise red.
  const chg = (v, { d = 2, invert = false, hot = 3 } = {}) => {
    if (!num(v)) return '<span class="chg">–</span>';
    const a = Math.abs(v), dir = a < 0.005 ? "" : (v > 0) !== invert ? " up" : " down";
    return `<span class="chg${dir}${dir && a >= hot ? " strong" : ""}">${signed(v, d)}</span>`;
  };
  // Small line icons (24px grid, drawn with strokes) for the attention list.
  const ICONS = {
    up: '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    down: '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
    warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.2a6.5 6.5 0 0 1 3 5.8"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m5.7 5.7 12.6 12.6"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    scan: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  };
  const icon = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[k]}</svg>`;
  const shortDate = (iso) => { const d = new Date(iso + "T12:00:00Z"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };
  const pctTxt = (v, d = 1) => !num(v) ? "–" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : "−"}${fmt(Math.abs(v), d)}%</span>`;
  const money = (v, cur = "$") => !num(v) ? "–" : v >= 1e9 ? `${cur}${fmt(v / 1e9, 1)}bn` : v >= 1e6 ? `${cur}${fmt(v / 1e6, 1)}m` : `${cur}${fmt(v / 1e3, 0)}k`;
  const ageDays = (iso) => { const d = new Date(iso + "T12:00:00Z"); return isNaN(d) ? Infinity : Math.round((Date.now() - d) / 864e5); };
  const daysAgo = (iso) => { const n = ageDays(iso); return !isFinite(n) ? "" : n <= 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`; };
  // Only touch the DOM when something actually changed, so hover states, clicks and
  // animations aren't interrupted by the live ticks.
  const setHTML = (el, html) => { if (el && el.__html !== html) { el.__html = html; el.innerHTML = html; } };
  const setText = (el, t) => { if (el && el.textContent !== t) el.textContent = t; };
  const setClass = (el, c) => { if (el && el.getAttribute("class") !== c) el.setAttribute("class", c); };

  let DATA = { markets: { uk_delayed: [], us_reference: [] }, signals: { watchlist: [], avoid: [], most_shorted: [], combo: [] }, analyst: {}, uk_names: [] };
  let loaded = false;
  const keys = () => ({ aid: store.get("alpacaId", ""), asec: store.get("alpacaSecret", ""), fh: store.get("finnhub", ""), crypto: store.get("crypto", "coinbase") });
  let watch = store.get("watch", ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT"]);
  const us = {};      // sym -> {price, prev, src}
  const crypto = {};  // coin -> {price, open}
  const hist = {};    // key -> recent live prices, for sparklines
  const last = {};    // for flash direction
  const sys = { us: "delayed", crypto: "connecting" };
  const INDEX_FUNDS = ["SPY", "QQQ", "IWM", "DIA"];

  // ---------- header: greeting, systems line and market hours ----------
  const MARKETS = [
    { name: "London", tz: "Europe/London", open: [8, 0], close: [16, 30] },
    { name: "New York", tz: "America/New_York", open: [9, 30], close: [16, 0], pre: [4, 0], post: [20, 0] },
    { name: "Tokyo", tz: "Asia/Tokyo", open: [9, 0], close: [15, 30] },
  ];
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  function tzParts(tz) {
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false }).formatToParts(new Date());
    const g = (t) => p.find((x) => x.type === t)?.value;
    return { h: +g("hour") % 24, m: +g("minute"), wd: g("weekday") };
  }
  const dur = (mins) => mins >= 1440 ? `${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h` : mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`;
  function marketState(mk) {
    const { h, m, wd } = tzParts(mk.tz);
    const now = h * 60 + m, at = (a) => a[0] * 60 + a[1], di = DAYS.indexOf(wd), weekday = di >= 0 && di < 5;
    let st = "shut", label = "closed";
    if (weekday && now >= at(mk.open) && now < at(mk.close)) { st = "open"; label = "open"; }
    else if (weekday && mk.pre && now >= at(mk.pre) && now < at(mk.open)) { st = "pre"; label = "pre-market"; }
    else if (weekday && mk.post && now >= at(mk.close) && now < at(mk.post)) { st = "pre"; label = "after hours"; }
    let next;
    if (st === "open") next = { verb: "closes", mins: at(mk.close) - now };
    else {
      let days = 0;  // holidays aren't known here, so this is the usual timetable
      if (!(weekday && now < at(mk.open))) { days = 1; let d = (di + 1) % 7; while (d >= 5) { days++; d = (d + 1) % 7; } }
      next = { verb: "opens", mins: days * 1440 + at(mk.open) - now };
    }
    return { st, label, time: `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`, next };
  }
  function renderHeader() {
    const h = new Date().getHours();
    const name = String(store.get("name", "") || "").trim();
    setText($("#greeting"), (h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening") + (name ? `, ${name}` : ""));
    setText($("#today"), new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }));
    const states = MARKETS.map((mk) => ({ mk, ...marketState(mk) }));
    setHTML($("#clocks"), states.map((s) => `<span class="sess ${s.st}"><span class="nm"><i class="dot"></i>${s.mk.name}</span>`
      + `<span class="st"><b>${cap(s.label)}</b><span class="t">${s.time}</span></span></span>`).join(""));
    const soon = states.slice().sort((a, b) => a.next.mins - b.next.mins)[0];
    setHTML($("#next"), soon ? `<b>${soon.mk.name} ${soon.next.verb}</b> in ${dur(soon.next.mins)}` : "");
  }
  const dotFor = (st) => st === "live" ? "live" : /error/i.test(st) ? "err" : "delayed";
  function renderSys() {
    const b = new Date(DATA.generated_at);
    const when = isNaN(b) ? "" : b.toDateString() === new Date().toDateString()
      ? b.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
      : b.toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" });
    const usSt = /error/i.test(sys.us) ? "error" : sys.us;
    setHTML($("#sys"), `<span class="st"><i class="dot ${dotFor(sys.crypto)}"></i>Crypto ${esc(sys.crypto)}</span><span class="st"><i class="dot ${dotFor(usSt)}"></i>US ${esc(usSt)}</span>`
      + (when ? `<span class="st data"><i class="dot ${Date.now() - b < 45 * 60000 ? "live" : "delayed"}"></i>Updated ${esc(when)}</span>` : ""));
  }
  // Status badge with a dot: "Live", "Delayed", "Connecting", or an error message.
  function setBadge(el, text, live) {
    el.title = text;
    setHTML(el, `<i class="dot ${live ? "live" : dotFor(text)}"></i>${esc(cap(text))}`);
  }

  // ---------- sparklines ----------
  // Grey by default; the tile turns it green, red or amber only when the move is big.
  function spark(values) {
    const v = (values || []).filter(num);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = v.map((y, i) => `${((i / (v.length - 1)) * 100).toFixed(2)},${(30 - ((y - lo) / span) * 26).toFixed(2)}`).join(" ");
    return `<svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polygon class="ar" points="0,32 ${pts} 100,32"/><polyline class="ln" points="${pts}"/></svg>`;
  }
  function pushHist(key, p) {
    const h = hist[key] || (hist[key] = []);
    const now = Date.now();
    if (!h.length || now - h[h.length - 1].t > 4000) h.push({ t: now, p }); else h[h.length - 1].p = p;
    if (h.length > 90) h.shift();
  }
  function flash(el, p, v) {
    if (!num(p) || !num(v) || p === v) return;
    el.classList.remove("flash-up", "flash-down");
    void el.offsetWidth;  // restart the animation
    el.classList.add(v > p ? "flash-up" : "flash-down");
  }
  function setPrice(el, key, v, cur = "", empty = "–") {
    const txt = num(v) ? cur + px(v) : empty;
    if (el.textContent === txt) return;
    flash(el, last[key], v);
    el.textContent = txt;
    if (num(v)) last[key] = v;
  }

  // ---------- market tiles ----------
  // hot: the size of move (in %) that counts as big for that market.
  const TILES = [
    { key: "^FTSE", name: "FTSE 100", what: "Biggest UK companies", who: "the biggest UK companies", hot: 1.5, mood: true },
    { key: "^FTMC", name: "FTSE 250", what: "Mid-sized UK companies", who: "mid-sized UK companies", hot: 1.5, mood: true },
    { key: "SPY", name: "S&P 500", what: "Biggest US companies", who: "the biggest US companies", hot: 1.5, mood: true },
    { key: "QQQ", name: "Nasdaq 100", what: "US tech giants", who: "US tech giants", hot: 1.5, mood: true },
    { key: "IWM", name: "Russell 2000", what: "Small US companies", who: "small US companies", hot: 2, mood: true },
    { key: "BTC", name: "Bitcoin", what: "US$, change over 24h", crypto: true, hot: 5 },
    { key: "ETH", name: "Ethereum", what: "US$, change over 24h", crypto: true, hot: 6 },
    { key: "^VIX", name: "Fear gauge", what: "VIX: higher is more nervous", invert: true, hot: 15 },
    { key: "GBPUSD=X", name: "Pound", what: "Dollars per pound", who: "the pound", hot: 0.8 },
    { key: "GC=F", name: "Gold", what: "US$ per ounce", who: "gold", hot: 2 },
  ];
  const VIX = TILES.find((t) => t.key === "^VIX");
  const cryptoHot = (c) => c === "BTC" ? 5 : c === "ETH" ? 6 : 8;
  function quoteFor(sym) {
    return [...DATA.markets.uk_delayed, ...DATA.markets.us_reference].find((q) => q.symbol === sym);
  }
  function tileState(t) {
    if (t.crypto) {
      const c = crypto[t.key] || {};
      return { price: c.price, change: num(c.price) && c.open ? (c.price / c.open - 1) * 100 : null, line: (hist[t.key] || []).map((x) => x.p), live: num(c.price) };
    }
    const q = quoteFor(t.key) || {}, l = us[t.key];
    if (l && l.src === "live") {
      const line = (q.closes || []).length >= 2 ? [...q.closes.slice(0, -1), l.price] : (hist[t.key] || []).map((x) => x.p);
      return { price: l.price, change: l.prev ? (l.price / l.prev - 1) * 100 : q.change_pct, line, live: true };
    }
    return { price: q.price, change: q.change_pct, line: q.closes, live: false };
  }
  function isHot(t, s) {
    if (t === VIX) return (num(s.price) && s.price >= 30) || (num(s.change) && s.change >= t.hot);
    return num(s.change) && Math.abs(s.change) >= t.hot;
  }
  const tileEls = {};
  function buildTiles() {
    const box = $("#tiles");
    box.innerHTML = "";
    for (const t of TILES) {
      const el = document.createElement("div");
      el.className = "tile";
      el.hidden = !t.crypto;
      el.innerHTML = `<div class="tile-top"><span class="name">${esc(t.name)}</span><i class="src"></i></div>`
        + `<div class="val">…</div><div class="tile-chg"><span class="cbox"></span><span class="flag"></span></div>`
        + `<div class="sbox"></div><div class="what">${esc(t.what)}</div>`;
      box.appendChild(el);
      tileEls[t.key] = el;
    }
  }
  function renderTiles() {
    for (const t of TILES) {
      const el = tileEls[t.key], s = tileState(t);
      if (!t.crypto && !num(s.price)) { el.hidden = true; continue; }
      el.hidden = false;
      const hot = isHot(t, s), tone = t === VIX ? "warn" : s.change >= 0 ? "up" : "down";
      setClass(el, hot ? `tile hot is-${tone}` : "tile");
      const flag = el.querySelector(".flag");
      setText(flag, hot ? (t === VIX ? "Elevated" : "Large move") : "");
      setClass(flag, "flag" + (hot ? " " + tone : ""));
      const src = el.querySelector(".src");
      setClass(src, "src " + (s.live ? "live" : "delayed"));
      src.title = s.live ? "Live" : "About 15 minutes delayed";
      setPrice(el.querySelector(".val"), "t" + t.key, s.price, "", "…");
      setHTML(el.querySelector(".cbox"), chg(s.change, { invert: t.invert, hot: t.hot }) + (t.crypto ? '<span class="per">24h</span>' : ""));
      setHTML(el.querySelector(".sbox"), spark(s.line));
    }
  }

  // ---------- market summary ----------
  // A plain diverging bar chart of today's move in each main index around a zero line,
  // with the average as the headline number. The scale snaps to a round number so
  // small days look small and big days look big.
  const vixBand = (v) => !num(v) ? null : v < 15 ? ["Calm", "up"] : v < 20 ? ["Normal", ""] : v < 30 ? ["A bit nervous", "warn"] : ["Very nervous", "down"];
  const toneOf = (v) => !num(v) || Math.abs(v) < 0.005 ? "" : v > 0 ? "up" : "down";
  function renderMood() {
    const rows = TILES.filter((t) => t.mood).map((t) => ({ t, s: tileState(t) })).filter((r) => num(r.s.change));
    const n = rows.length, avg = n ? rows.reduce((a, r) => a + r.s.change, 0) / n : null;
    const ups = rows.filter((r) => r.s.change > 0).length, downs = rows.filter((r) => r.s.change < 0).length;
    const big = rows.slice().sort((a, b) => Math.abs(b.s.change) - Math.abs(a.s.change))[0];
    const vix = tileState(VIX), band = vixBand(vix.price), live = rows.some((r) => r.s.live);
    const word = !num(avg) ? "Waiting" : avg <= -1.5 ? "Sell-off" : avg <= -0.4 ? "Down day" : avg < 0.4 ? "Mixed" : avg < 1.5 ? "Up day" : "Rally";
    const tone = !num(avg) ? "" : avg >= 0.4 ? "up" : avg <= -0.4 ? "down" : "";
    setText($("#mood-word"), word);
    setClass($("#mood-word"), "badge" + (tone ? " " + tone : ""));
    setText($("#mood-avg"), num(avg) ? signed(avg, 2) : "–");
    setClass($("#mood-avg"), "hero-num" + (toneOf(avg) ? " " + toneOf(avg) : ""));
    setHTML($("#mood-tag"), live ? '<i class="dot live"></i>Live' : "Latest session");
    let line = "Waiting for prices.";
    if (n) {
      line = `Average move across ${n} main indices. ` + (ups === n ? "Every one is up." : downs === n ? "Every one is down."
        : ups > downs ? `Most are up (${ups} of ${n}).` : downs > ups ? `Most are down (${downs} of ${n}).` : "They are split.");
    }
    setText($("#mood-line"), line);
    const mx = n ? Math.max(...rows.map((r) => Math.abs(r.s.change))) : 0;
    const scale = [1, 2, 3, 5, 8, 10, 15, 20, 30, 50].find((x) => x >= mx * 1.05) || Math.ceil(mx);
    setHTML($("#breadth"), n ? rows.map(({ t, s }) => {
      const d = toneOf(s.change), w = Math.min(50, (Math.abs(s.change) / scale) * 50);
      return `<div class="br-row" title="${esc(t.name)}: ${signed(s.change, 2)}${s.live ? " (live)" : ""}"><span class="lb">${esc(t.name)}</span>`
        + `<span class="br-track">${d ? `<i class="br-bar ${d}" style="width:${w.toFixed(2)}%"></i>` : ""}</span><span class="vl ${d}">${signed(s.change, 2)}</span></div>`;
    }).join("") + `<div class="br-axis" aria-hidden="true"><span></span><span class="scale"><span>−${scale}%</span><span>0</span><span>+${scale}%</span></span><span></span></div>` : "");
    const stat = (label, value, sub, cls = "") => `<div class="stat"><small>${label}</small><b class="${cls}">${value}</b><span>${sub}</span></div>`;
    setHTML($("#readouts"), [
      stat("Fear gauge", num(vix.price) ? fmt(vix.price, 1) : "–", band ? `<i class="dot ${band[1]}"></i>${band[0]}` : "No data"),
      stat("Rising / falling", n ? `${ups} / ${downs}` : "–", "Main indices"),
      stat("Biggest move", big ? signed(big.s.change, 2) : "–", big ? esc(big.t.name) : "No data", big ? toneOf(big.s.change) : ""),
    ].join(""));
  }

  // ---------- needs your attention ----------
  // Priority order: fear gauge, big market moves, fresh insider buying, crypto swings,
  // watchlist swings, then the top name to steer clear of. At most six.
  const CRYPTO = [["BTC", "Bitcoin"], ["ETH", "Ethereum"], ["SOL", "Solana"], ["XRP", "XRP"], ["DOGE", "Dogecoin"], ["ADA", "Cardano"], ["LINK", "Chainlink"]];
  function alertsList() {
    const out = [];
    const add = (tone, ico, cat, title, detail) => out.push({ tone, ico, cat, title, detail });
    const move = (v) => `${v > 0 ? "up" : "down"} ${fmt(Math.abs(v), 1)}%`;
    const dirIco = (v) => v > 0 ? "up" : "down";
    const v = tileState(VIX);
    if (num(v.price) && v.price >= 30) add("warn", "warn", "Fear gauge", `Fear gauge at ${fmt(v.price, 1)}`, "Investors are very nervous. Expect big swings.");
    else if (num(v.change) && v.change >= VIX.hot) add("warn", "warn", "Fear gauge", `Fear gauge up ${fmt(v.change, 0)}%`, "Nerves are rising fast today.");
    // Big moves in two or more main indices the same way are one story, so they share
    // one alert and leave room for signals.
    const hot = TILES.filter((t) => t !== VIX && !t.crypto).map((t) => ({ t, s: tileState(t) })).filter((x) => isHot(x.t, x.s));
    const singles = hot.filter((x) => !x.t.mood);
    for (const dir of [-1, 1]) {
      const g = hot.filter((x) => x.t.mood && Math.sign(x.s.change) === dir).sort((a, b) => Math.abs(b.s.change) - Math.abs(a.s.change));
      if (g.length >= 2) add(dir > 0 ? "up" : "down", dirIco(dir), "Markets", `Big ${dir > 0 ? "rises" : "falls"} in ${g.length} main indices`, g.map((x) => `${x.t.name} ${signed(x.s.change)}`).join(", ") + ".");
      else singles.unshift(...g);
    }
    for (const { t, s } of singles) add(s.change > 0 ? "up" : "down", dirIco(s.change), "Markets", `${t.name} ${move(s.change)}`, `An unusually ${s.change > 0 ? "strong" : "weak"} day for ${t.who}.`);
    for (const r of (DATA.signals.watchlist || []).filter((r) => ageDays(r.signal_date) <= 7).slice(0, 2))
      add("info", "people", "Insiders", `Insiders buying ${r.ticker || titleCase(r.issuer)}`, `${r.n_insiders ?? "Several"} insiders spent ${money(r.total_value)}, ${daysAgo(r.signal_date)}. Worth researching.`);
    for (const [c, name] of CRYPTO) {
      const q = crypto[c] || {}, ch = num(q.price) && q.open ? (q.price / q.open - 1) * 100 : null;
      if (num(ch) && Math.abs(ch) >= cryptoHot(c)) add(ch > 0 ? "up" : "down", dirIco(ch), "Crypto", `${name} ${move(ch)} in 24h`, "A big swing, even for crypto.");
    }
    for (const s of watch) {
      if (INDEX_FUNDS.includes(s)) continue;
      const q = us[s] || {}, ch = num(q.price) && q.prev ? (q.price / q.prev - 1) * 100 : null;
      if (num(ch) && Math.abs(ch) >= 3) add(ch > 0 ? "up" : "down", dirIco(ch), "Watchlist", `${s} ${move(ch)}`, "A big move for a stock on your watchlist.");
    }
    const a = (DATA.signals.avoid || [])[0];
    if (a) add("down", "ban", "Avoid", `Steer clear of ${titleCase(a.issuer)}`, `Short bets up ${fmt(a.delta_pp, 1)} points this month, to ${fmt(a.new_pct, 1)}%.`);
    return out.slice(0, 6);
  }
  function renderAlerts() {
    const list = loaded ? alertsList() : [];
    const cnt = $("#alert-count");
    cnt.hidden = !list.length;
    setText(cnt, String(list.length));
    const row = (cls, ico, title, detail, cat = "") => `<div class="alert ${cls}"><span class="ic">${icon(ico)}</span>`
      + `<div><p class="tt">${title}</p><p class="dd">${detail}</p></div>${cat ? `<span class="cat">${cat}</span>` : ""}</div>`;
    setHTML($("#alerts"), list.length
      ? list.map((a) => row(`is-${a.tone}`, a.ico, esc(a.title), esc(a.detail), esc(a.cat))).join("")
      : loaded ? row("calm is-up", "check", "All quiet. Nothing stands out right now.", "Big moves, fresh insider buying and big swings on your watchlist will show up here.")
        : row("calm", "scan", "Scanning…", "Checking markets and signals."));
  }

  // ---------- live lists ----------
  let dirty = true;
  const mark = () => { dirty = true; };
  const SRC_LABEL = { live: "live", delayed: "delayed", quote: "last close", iex: "last trade" };
  // Rows are built once per set of symbols and then updated cell by cell, so the
  // remove buttons stay put while prices stream in.
  function keyed(box, ids, skeleton) {
    const want = ids.join("|");
    if (box.__keys !== want) {
      box.__keys = want;
      box.innerHTML = ids.map((k) => `<li>${skeleton(k)}</li>`).join("");
    }
    return box.children;
  }
  function renderWatch() {
    const box = $("#watch");
    if (!watch.length) {
      if (box.__keys !== "") { box.__keys = ""; box.innerHTML = '<li class="empty">Add a stock above to follow it here.</li>'; }
      return;
    }
    const lis = keyed(box, watch, (s) => `<span class="sym"></span><span class="price"></span><span class="cc"></span><button class="x" data-rm="${esc(s)}" title="Remove ${esc(s)}" aria-label="Remove ${esc(s)}">×</button>`);
    watch.forEach((s, i) => {
      const li = lis[i], q = us[s] || {};
      const c = num(q.price) && q.prev ? (q.price / q.prev - 1) * 100 : null;
      setHTML(li.children[0], `${esc(s)}${q.src ? `<small>${esc(SRC_LABEL[q.src] || q.src)}</small>` : ""}`);
      setPrice(li.children[1], "w" + s, q.price, "$");
      setHTML(li.children[2], chg(c, { hot: INDEX_FUNDS.includes(s) ? 1.5 : 3 }));
    });
  }
  function renderCrypto() {
    const lis = keyed($("#crypto"), CRYPTO.map(([c]) => c), (c) => `<span class="sym">${esc(CRYPTO.find((x) => x[0] === c)[1])}<small>${c}</small></span><span class="price"></span><span class="cc"></span>`);
    CRYPTO.forEach(([c], i) => {
      const li = lis[i], q = crypto[c] || {};
      const ch = num(q.price) && q.open ? (q.price / q.open - 1) * 100 : null;
      setPrice(li.children[1], "c" + c, q.price, "$");
      setHTML(li.children[2], chg(ch, { hot: cryptoHot(c) }));
    });
  }
  function render() {
    if (!dirty) return;
    dirty = false;
    renderTiles(); renderWatch(); renderCrypto(); renderMood(); renderAlerts();
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
  function titleCase(s) {
    s = String(s || "");
    return s === s.toUpperCase() ? s.toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase()).replace(/\bPlc\b/g, "plc") : s;
  }
  function renderSignals() {
    const S = DATA.signals;
    setHTML($("#insider"), S.watchlist.length ? S.watchlist.slice(0, 6).map((r) => {
      const who = [`${r.n_insiders ?? "Several"} insiders bought`, rolesOf(r.insiders)].filter(Boolean).join(", ");
      const since = num(r.ret_20d) ? ` · ${pctTxt(r.ret_20d * 100)} in the 20 days after` : num(r.ret_5d) ? ` · ${pctTxt(r.ret_5d * 100)} in the 5 days after` : "";
      const fresh = ageDays(r.signal_date) <= 7 ? '<span class="new">New</span>' : "";
      const click = r.ticker ? ' click" role="button" tabindex="0' : "";
      return `<div class="sig${click}" data-sym="${esc(r.ticker || "")}" title="${esc(r.insiders)}">`
        + `<div class="hd"><span class="sym">${esc(r.ticker || titleCase(r.issuer))}</span><span class="co">${esc(r.ticker ? titleCase(r.issuer) : "")}</span>${fresh}</div>`
        + `<span class="amt">${money(r.total_value)}</span><p class="ln">${esc(who)}.</p>`
        + `<p class="mt">${esc(cap(daysAgo(r.signal_date)))}${num(r.market_cap) ? ` · company worth ${money(r.market_cap)}` : ""}${since}</p></div>`;
    }).join("") : '<p class="empty">No insider buying clusters in the last 30 days.</p>');

    setHTML($("#avoid"), S.avoid.length ? S.avoid.slice(0, 6).map((r) => `<div class="sig" title="${esc(r.isin)}">`
        + `<div class="hd"><span class="sym">${esc(titleCase(r.issuer))}</span><span class="co">${esc(r.ticker || "")}</span></div>`
        + `<span class="amt">${fmt(r.new_pct, 1)}%<small>shorted</small></span>`
        + `<p class="ln">Short bets up ${fmt(r.delta_pp, 1)} points since ${esc(shortDate(r.since))}.</p></div>`).join("")
      : '<p class="empty">No UK shares saw a big jump in short bets this month.</p>');

    const top = (S.most_shorted || []).slice(0, 5), mx = Math.max(1, ...top.map((r) => +r.net_short_pct || 0));
    setHTML($("#shorted-top"), top.map((r, i) => `<li><span class="rk">${i + 1}</span><span class="nm">${esc(titleCase(r.issuer))}</span>`
      + `<span class="meter"><i style="width:${Math.round(((+r.net_short_pct || 0) / mx) * 100)}%"></i></span><span class="v">${fmt(r.net_short_pct, 1)}%</span></li>`).join("")
      || '<li class="muted">No data yet.</li>');
  }
  // Make the numbers in the brief easy to spot: signed moves in green or red (a rising
  // fear gauge counts as bad news), other percentages and money amounts in bright white.
  function highlight(p) {
    return p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/([£$€]\d[\d,]*(?:\.\d+)?(?:\s?(?:bn|m|k|billion|million)\b)?)|(?<![\w.,])([+\-−]?)(\d+(?:\.\d+)?)(%|pp\b)/g,
      (m, cash, sign, n, unit, off, str) => {
        if (cash) return `<span class="hl">${cash}</span>`;
        let dir = unit === "%" && sign ? (sign === "+" ? "up" : "down") : "";
        const clause = str.slice(Math.max(0, off - 80), off).split(/[,;:]|\.\s|\b(?:and|while|but|as)\b/i).pop();
        if (dir && /VIX|gauge|volatil/i.test(clause)) dir = dir === "up" ? "down" : "up";
        return `<span class="hl${dir ? " " + dir : ""}">${m}</span>`;
      });
  }
  function renderBrief() {
    const text = DATA.brief?.text || "No brief yet.";
    setHTML($("#brief"), text.split(/\n\s*\n/).map((p) => `<p>${highlight(esc(p.trim()))}</p>`).join(""));
    $("#brief").classList.toggle("short", text.length < 360);
    const ai = DATA.brief?.source === "ai";
    setText($("#brief-src"), ai ? "Written by Claude" : "Automatic summary");
    setClass($("#brief-src"), "badge" + (ai ? " ai" : ""));
    const built = new Date(DATA.generated_at);
    setText($("#built"), isNaN(built) ? "" : "Updated " + built.toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" }) + ". Prices marked delayed were captured then.");
  }

  // ---------- more detail ----------
  function table(sel, rows, fn, cols, empty) {
    setHTML($(sel + " tbody"), rows.length ? rows.map(fn).join("") : `<tr><td colspan="${cols}" class="empty muted">${empty}</td></tr>`);
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
    setHTML($("#feed thead"), "<tr>" + cols.map((c) => `<th>${esc(c[0].toUpperCase() + c.slice(1))}</th>`).join("") + "</tr>");
    setHTML($("#feed tbody"), f.rows.map((r) => `<tr title="${esc(r.evidence || "")}">` + cols.map((c) => {
      const v = r[c];
      if (c === "stance") return `<td class="${v === "avoid" ? "down" : v === "watch" ? "up" : "muted"}">${esc(v)}</td>`;
      return `<td title="${esc(v)}">${esc(v)}</td>`;
    }).join("") + "</tr>").join(""));
  }
  function renderStatic() {
    renderBrief(); renderSignals(); renderDetail(); renderSys();
    for (const q of DATA.markets.us_reference) if (!us[q.symbol] && /^[A-Z]+$/.test(q.symbol)) us[q.symbol] = { price: q.price, prev: q.prev_close, src: "delayed" };
    fillAnalystPicker(); mark();
  }

  // ---------- analysts ----------
  function fillAnalystPicker() {
    const syms = [...new Set([...DATA.signals.watchlist.map((r) => r.ticker).filter(Boolean), ...watch])].filter((s) => /^[A-Z.\-]+$/.test(s) && !INDEX_FUNDS.includes(s));
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
      box.innerHTML = k ? `<p class="hint">No analyst ratings for ${esc(sym)} on Finnhub's free plan.</p>` : '<p class="hint">Add a free Finnhub key (Settings button) to see how many analysts rate each stock a buy, hold or sell.</p>';
      return;
    }
    const m = rows[0];
    const buys = (m.strongBuy || 0) + (m.buy || 0), holds = m.hold || 0, sells = (m.sell || 0) + (m.strongSell || 0), tot = buys + holds + sells || 1;
    const [word, cls] = buys >= holds && buys >= sells ? ["Buy", "up"] : sells > holds ? ["Sell", "down"] : ["Hold", ""];
    let trend = "";
    const old = rows[3] || rows[rows.length - 1];
    if (old && old !== m) {
      const ob = ((old.strongBuy || 0) + (old.buy || 0)) / (((old.strongBuy || 0) + (old.buy || 0) + (old.hold || 0) + (old.sell || 0) + (old.strongSell || 0)) || 1);
      const diff = buys / tot - ob;
      trend = Math.abs(diff) < 0.03 ? "Views are about the same as a few months ago." : diff > 0 ? "Analysts have grown more positive recently." : "Analysts have grown more cautious recently.";
    }
    const segs = [["strongBuy", "c-sb", "Strong buy"], ["buy", "c-b", "Buy"], ["hold", "c-h", "Hold"], ["sell", "c-s", "Sell"], ["strongSell", "c-ss", "Strong sell"]];
    box.innerHTML = `<p class="verdict"><span>Consensus for <b>${esc(sym)}</b></span><span class="badge ${cls}">${word}</span><span>${buys} buy · ${holds} hold · ${sells} sell</span></p>`
      + (trend ? `<p class="hint trend">${trend}</p>` : "")
      + `<div class="recs">` + rows.slice(0, 4).map((mm) => {
        const t = segs.reduce((a, [k2]) => a + (mm[k2] || 0), 0) || 1;
        const month = new Date((mm.period || "") + "T12:00:00Z");
        return `<div class="rec"><span>${isNaN(month) ? esc(mm.period) : month.toLocaleDateString("en-GB", { month: "short", year: "2-digit" })}</span>`
          + `<span class="bar">${segs.map(([k2, c, lb]) => mm[k2] ? `<i class="${c}" style="flex:${mm[k2]}" title="${lb}: ${mm[k2]}"></i>` : "").join("")}</span><span class="r">${t}</span></div>`;
      }).join("") + `</div><div class="legend">${segs.map(([, c, lb]) => `<span><i class="${c}"></i>${lb}</span>`).join("")}</div>`;
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
  function setUsStatus(text, live) {
    setBadge($("#us-status"), text, live);
    sys.us = live ? "live" : /error/i.test(text) ? "error" : text;
    renderSys();
  }
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
      $("#watch-note").textContent = "For live US prices, add a free Alpaca or Finnhub key in Settings.";
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
    const status = (t, live) => { setBadge($("#crypto-status"), t, live); sys.crypto = t; renderSys(); };
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
  document.addEventListener("keydown", (e) => {
    const card = e.target.closest?.(".sig.click[data-sym]");
    if (card && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); addSym(card.dataset.sym); }
  });

  // ---------- settings ----------
  function openSettings() {
    const k = keys();
    $("#k-name").value = store.get("name", "");
    $("#k-alpaca-id").value = k.aid; $("#k-alpaca-secret").value = k.asec; $("#k-finnhub").value = k.fh; $("#k-crypto").value = k.crypto;
    $("#settings").showModal();
  }
  $("#open-settings").addEventListener("click", openSettings);
  $("#settings").addEventListener("close", () => {
    if ($("#settings").returnValue !== "save") return;
    store.set("name", $("#k-name").value.trim().slice(0, 30));
    store.set("alpacaId", $("#k-alpaca-id").value.trim()); store.set("alpacaSecret", $("#k-alpaca-secret").value.trim());
    store.set("finnhub", $("#k-finnhub").value.trim()); store.set("crypto", $("#k-crypto").value);
    renderHeader(); connectUS(); connectCrypto(); fillAnalystPicker();
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
  buildTiles();
  renderHeader(); setInterval(renderHeader, 30000);
  renderSys(); render();
  fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : Promise.reject(r.status))
    .then((d) => { DATA = { ...DATA, ...d }; loaded = true; renderStatic(); })
    .catch(() => { loaded = true; renderSignals(); mark(); $("#brief").innerHTML = "<p>Couldn't load today's data. The page may still be building; try again in a minute.</p>"; })
    .finally(() => { connectUS(); connectCrypto(); });
  // Refresh build-time data every 10 minutes without restarting the live streams.
  setInterval(() => fetch("data.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((d) => { if (d) { DATA = { ...DATA, ...d }; renderStatic(); } }).catch(() => {}), 600000);
})();
