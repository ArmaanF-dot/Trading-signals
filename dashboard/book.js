/* Baco: the portfolio, the bet tracker and the calculators. Everything the person types here is kept in
   this browser's localStorage only (holdings, bets, notes), never sent anywhere. Uses the helpers that
   app.js exposes on window.Baco. */
(() => {
  "use strict";
  const B = window.Baco, { $, store, esc, num, fmt, px, signed, chg, setHTML, setText, setClass } = B;
  const today = () => new Date().toISOString().slice(0, 10);
  const gbp = (v, d = 0) => !num(v) ? "–" : `${v < 0 ? "−" : ""}£${fmt(Math.abs(v), d)}`;
  const usd = (v, d = 0) => !num(v) ? "–" : `${v < 0 ? "−" : ""}$${fmt(Math.abs(v), d)}`;
  const tone = (v) => !num(v) || Math.abs(v) < 0.005 ? "" : v > 0 ? "up" : "down";
  const visible = (id) => { const el = $(id); return el && !el.closest(".view")?.hidden; };

  // ---------- a small line chart used for portfolio value and bankroll ----------
  // values: [{x: label, y: number}], ref: optional second series with the same length.
  function lineChart(box, pts, { ref = null, fmtY = (v) => fmt(v, 0), empty = "Not enough history yet." } = {}) {
    if (!pts || pts.length < 2) { setHTML(box, `<p class="empty">${esc(empty)}</p>`); return; }
    const W = 600, H = 190, L = 8, R = 8, T = 12, Bt = 22;
    const ys = pts.map((p) => p.y).concat(ref ? ref.map((p) => p.y) : []).filter(num);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
    const X = (i) => L + (i / (pts.length - 1)) * (W - L - R), Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - Bt);
    const path = (arr) => arr.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(p.y).toFixed(1)}`).join("");
    const lastUp = pts[pts.length - 1].y >= pts[0].y;
    const ticks = [lo + pad, (lo + hi) / 2, hi - pad].map((v) => `<text x="${W - R}" y="${(Y(v) - 4).toFixed(1)}" text-anchor="end" class="ax">${esc(fmtY(v))}</text><line x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="gl"/>`).join("");
    const first = pts[0].x, last = pts[pts.length - 1].x;
    setHTML(box, `<svg viewBox="0 0 ${W} ${H}" class="lc" role="img" aria-label="Line chart from ${esc(first)} to ${esc(last)}">`
      + ticks + `<path d="${path(pts)} L${X(pts.length - 1).toFixed(1)} ${H - Bt} L${L} ${H - Bt}Z" class="ar ${lastUp ? "up" : "down"}"/>`
      + (ref ? `<path d="${path(ref)}" class="rf"/>` : "") + `<path d="${path(pts)}" class="ln ${lastUp ? "up" : "down"}" pathLength="1"/>`
      + `<circle cx="${X(pts.length - 1).toFixed(1)}" cy="${Y(pts[pts.length - 1].y).toFixed(1)}" r="3.5" class="dt ${lastUp ? "up" : "down"}"/>`
      + `<text x="${L}" y="${H - 5}" class="ax">${esc(first)}</text><text x="${W - R}" y="${H - 5}" text-anchor="end" class="ax">${esc(last)}</text></svg>`);
  }
  B.lineChart = lineChart;

  // ================= portfolio =================
  let holdings = store.get("holdings", []);
  let cash = store.get("cash", 0);
  let equity = store.get("equity", []);        // [{d, v (USD), spy}]
  const saveH = () => { store.set("holdings", holdings); B.reconnectUS(); B.mark(); };
  B.extraSyms = () => holdings.map((h) => h.sym).filter((s) => !B.CRYPTO.some((c) => c[0] === s));

  function pfState() {
    const rows = holdings.map((h) => {
      const { price, prev } = B.priceOf(h.sym);
      const priced = num(price);
      const value = priced ? h.qty * price : null;
      const day = priced && num(prev) ? h.qty * (price - prev) : null;
      const gain = priced && h.cost > 0 ? value - h.qty * h.cost : null;
      return { ...h, price, prev, value, day, gain, dayPct: priced && num(prev) && prev ? (price / prev - 1) * 100 : null, gainPct: priced && h.cost > 0 ? (price / h.cost - 1) * 100 : null };
    });
    const priced = rows.filter((r) => num(r.value));
    const invested = priced.reduce((a, r) => a + r.value, 0);
    const total = invested + (+cash || 0);
    const day = priced.reduce((a, r) => a + (r.day || 0), 0);
    const dayBase = priced.reduce((a, r) => a + (num(r.day) ? r.value - r.day : r.value), 0);
    const costBasis = priced.reduce((a, r) => a + (r.cost > 0 ? r.qty * r.cost : r.value), 0);
    const gain = invested - costBasis;
    rows.forEach((r) => { r.weight = num(r.value) && total > 0 ? (r.value / total) * 100 : null; });
    return { rows, priced: priced.length, unpriced: rows.length - priced.length, invested, total, day, dayPct: dayBase ? (day / dayBase) * 100 : null, gain, gainPct: costBasis ? (gain / costBasis) * 100 : null, costBasis };
  }
  const toGBP = (v) => { const r = B.gbpusd(); return num(v) && r ? v / r : null; };

  function recordEquity(st) {
    if (!holdings.length || st.unpriced || !st.total) return;
    const spy = B.priceOf("SPY").price, d = today();
    if (!num(spy)) return;
    const last = equity[equity.length - 1];
    if (last && last.d === d) { last.v = st.total; last.spy = spy; } else equity.push({ d, v: st.total, spy });
    if (equity.length > 800) equity = equity.slice(-800);
    store.set("equity", equity);
  }

  function renderPortfolio() {
    const st = pfState();
    recordEquity(st);
    const empty = !holdings.length;
    const big = (label, html, sub = "", cls = "") => `<div class="stat"><small>${label}</small><b class="${cls}">${html}</b><span>${sub}</span></div>`;
    const first = equity[0], lastE = equity[equity.length - 1];
    let vs = "–", vsCls = "", vsSub = "Needs a few days of history";
    if (first && lastE && equity.length >= 2 && first.v && first.spy) {
      const mine = (lastE.v / first.v - 1) * 100, spy = (lastE.spy / first.spy - 1) * 100;
      vs = signed(mine - spy, 1); vsCls = tone(mine - spy); vsSub = `You ${signed(mine, 1)}, S&P 500 ${signed(spy, 1)} since ${B.shortDate(first.d)}`;
    }
    setHTML($("#pf-summary"), empty ? '<p class="empty">Add a holding below to see its value, today\'s move and your gain or loss. Paper positions count too.</p>'
      : big("Total value", gbp(toGBP(st.total)), usd(st.total), "") + big("Today", st.dayPct == null ? "–" : signed(st.dayPct, 2), gbp(toGBP(st.day)), tone(st.day))
        + big("Gain or loss", st.gainPct == null ? "–" : signed(st.gainPct, 1), gbp(toGBP(st.gain)) + " on cost", tone(st.gain)) + big("Against the S&amp;P 500", vs, vsSub, vsCls));
    setText($("#pf-note"), empty ? "" : (st.unpriced ? `${st.unpriced} holding${st.unpriced === 1 ? "" : "s"} without a price yet: add a free Alpaca or Finnhub key in Settings. ` : "")
      + (B.gbpusd() ? "" : "Pound conversion waiting for the exchange rate. ") + "Totals are in pounds at the latest GBP/USD rate; the dollar figure is the underlying value.");

    // table
    const tb = $("#pf-table tbody");
    setHTML(tb, st.rows.length ? st.rows.map((r, i) => `<tr><td><b>${esc(r.sym)}</b></td><td class="r">${fmt(r.qty, r.qty % 1 ? 4 : 0)}</td><td class="r">${r.cost > 0 ? "$" + px(r.cost) : "–"}</td>`
      + `<td class="r">${num(r.price) ? "$" + px(r.price) : '<span class="muted">no price</span>'}</td><td class="r">${chg(r.dayPct, { d: 2 })}</td>`
      + `<td class="r">${num(r.value) ? usd(r.value) : "–"}</td><td class="r">${num(r.weight) ? fmt(r.weight, 1) + "%" : "–"}</td>`
      + `<td class="r ${tone(r.gain)}">${num(r.gain) ? `${usd(r.gain)} <small>${signed(r.gainPct, 1)}</small>` : "–"}</td>`
      + `<td class="r"><button class="icon-btn" data-pf-rm="${i}" aria-label="Remove ${esc(r.sym)}" title="Remove"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button></td></tr>`).join("")
      : '<tr><td colspan="9" class="empty muted">No holdings yet.</td></tr>');

    // allocation
    const slices = st.rows.filter((r) => num(r.weight)).sort((a, b) => b.weight - a.weight);
    const cashW = st.total > 0 ? ((+cash || 0) / st.total) * 100 : 0;
    const parts = slices.map((r, i) => ({ name: r.sym, w: r.weight, c: i % 6 })).concat(cashW > 0.05 ? [{ name: "Cash", w: cashW, c: 6 }] : []);
    setHTML($("#pf-alloc"), parts.length ? `<div class="alloc-bar" role="img" aria-label="Allocation">${parts.map((p) => `<i class="c${p.c}" style="flex:${p.w}" title="${esc(p.name)} ${fmt(p.w, 1)}%"></i>`).join("")}</div>`
      + `<ul class="alloc-list">${parts.map((p) => `<li><i class="c${p.c}"></i><span>${esc(p.name)}</span><b>${fmt(p.w, 1)}%</b></li>`).join("")}</ul>` : '<p class="empty">Nothing to show yet.</p>');
    const top = slices[0];
    const conc = top && top.weight >= 40 ? ["Concentrated", "down"] : top && top.weight >= 25 ? ["Top position " + fmt(top.weight, 0) + "%", "warn"] : top ? ["Spread out", "up"] : ["", ""];
    setText($("#pf-risk-badge"), conc[0]); setClass($("#pf-risk-badge"), "badge " + conc[1]);

    // curve
    const curve = equity.map((e) => ({ x: B.shortDate(e.d), y: toGBP(e.v) ?? e.v }));
    const ref = equity.length >= 2 && equity[0].spy ? equity.map((e) => ({ x: e.d, y: (toGBP(equity[0].v) ?? equity[0].v) * (e.spy / equity[0].spy) })) : null;
    if (equity.length < 2) lineChart($("#pf-curve"), null, { empty: "History builds up as you open Baco on different days." });
    else if ($("#pf-curve").__sig !== equity.length + ":" + equity[equity.length - 1].v) { $("#pf-curve").__sig = equity.length + ":" + equity[equity.length - 1].v; lineChart($("#pf-curve"), curve, { ref, fmtY: (v) => "£" + fmt(v, 0) }); }
    setText($("#pf-curve-badge"), equity.length >= 2 ? `${equity.length} days` : "");

    if (document.activeElement !== $("#pf-cash")) $("#pf-cash").value = cash || "";
  }

  $("#pf-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const sym = B.toTicker($("#pf-sym").value), qty = +$("#pf-qty").value, cost = +$("#pf-cost").value || 0;
    if (!/^[A-Z][A-Z.\-]{0,9}$/.test(sym) || !(qty > 0)) { $("#pf-sym").placeholder = "Enter a ticker and a number of shares"; return; }
    const ex = holdings.find((h) => h.sym === sym);
    if (ex) { const tq = ex.qty + qty; ex.cost = cost > 0 ? ((ex.cost || 0) * ex.qty + cost * qty) / tq : ex.cost; ex.qty = tq; } else holdings.push({ sym, qty, cost });
    saveH(); e.target.reset(); $("#pf-sym").placeholder = "Symbol, e.g. AAPL or BTC";
  });
  document.addEventListener("click", (e) => { const b = e.target.closest("[data-pf-rm]"); if (b) { holdings.splice(+b.dataset.pfRm, 1); saveH(); } });
  $("#pf-cash").addEventListener("change", (e) => { cash = Math.max(0, +e.target.value || 0); store.set("cash", cash); B.mark(); });

  // ================= bets =================
  let bets = store.get("bets", []);
  let bank = store.get("bank", 0);
  const saveBets = () => { store.set("bets", bets); B.mark(); };
  const profitOf = (b) => b.status === "won" ? b.stake * (b.odds - 1) : b.status === "lost" ? -b.stake : 0;
  B.addBet = (b) => { bets.unshift({ id: Date.now() + Math.random(), ts: today(), status: "open", ...b }); saveBets(); };
  B.betStats = () => {
    const done = bets.filter((b) => b.status === "won" || b.status === "lost");
    const staked = done.reduce((a, b) => a + b.stake, 0), profit = bets.reduce((a, b) => a + profitOf(b), 0);
    const withP = done.filter((b) => num(b.p));
    return { bets, done, open: bets.filter((b) => b.status === "open"), staked, profit, roi: staked ? (profit / staked) * 100 : null, hit: done.length ? (done.filter((b) => b.status === "won").length / done.length) * 100 : null,
      said: withP.length ? withP.reduce((a, b) => a + b.p, 0) / withP.length : null, saidHit: withP.length ? (withP.filter((b) => b.status === "won").length / withP.length) * 100 : null, bank: (+bank || 0) + profit };
  };
  function renderBets() {
    const s = B.betStats();
    const st = (l, h, sub = "", c = "") => `<div class="stat"><small>${l}</small><b class="${c}">${h}</b><span>${sub}</span></div>`;
    setHTML($("#bt-stats"), st("Bankroll", bank ? gbp(s.bank) : "–", bank ? `Started with ${gbp(bank)}` : "Set your starting bankroll below", bank ? tone(s.profit) : "")
      + st("Profit", s.done.length ? gbp(s.profit, 2) : "–", `${s.done.length} settled, ${s.open.length} open`, tone(s.profit)) + st("Return on stakes", s.roi == null ? "–" : signed(s.roi, 1), s.staked ? `${gbp(s.staked)} staked` : "", tone(s.roi))
      + st("Hit rate", s.hit == null ? "–" : fmt(s.hit, 0) + "%", s.said != null ? `You said ${fmt(s.said, 0)}% on average` : "Add a chance % to compare"));
    setText($("#bt-badge"), s.done.length ? `${s.done.length} settled` : "Paper first");
    setText($("#bt-hint"), s.done.length < 100 ? `Judge it on results only once you have a few hundred settled bets: ${s.done.length} is far too few to tell skill from luck. Bet only money you can afford to lose.` : "A decent sample. Compare your hit rate with the chances you stated.");
    const sorted = bets.slice().reverse().filter((b) => b.status !== "open");
    let run = +bank || 0; const pts = [{ x: "Start", y: run }];
    sorted.forEach((b) => { run += profitOf(b); pts.push({ x: B.shortDate(b.ts), y: run }); });
    const sig = pts.length + ":" + run + ":" + bank;
    if ($("#bt-curve").__sig !== sig) { $("#bt-curve").__sig = sig; lineChart($("#bt-curve"), pts, { fmtY: (v) => "£" + fmt(v, 0), empty: "Log and settle bets to see your bankroll move." }); }
    const rows = bets.map((b, i) => {
      const res = b.status === "open" ? `<span class="res"><button class="mini up" data-bt="won" data-i="${i}">Won</button><button class="mini down" data-bt="lost" data-i="${i}">Lost</button><button class="mini" data-bt="void" data-i="${i}">Void</button></span>`
        : `<span class="badge ${b.status === "won" ? "up" : b.status === "lost" ? "down" : ""}">${B.cap(b.status)}</span>`;
      return `<tr><td>${esc(B.shortDate(b.ts))}</td><td title="${esc(b.sel)}">${esc(b.sel)}</td><td class="r">${fmt(b.odds, 2)}</td><td class="r">${gbp(b.stake, 2)}</td><td class="r">${num(b.p) ? fmt(b.p, 0) + "%" : "–"}</td><td>${res}</td>`
        + `<td class="r ${tone(profitOf(b))}">${b.status === "open" ? "–" : gbp(profitOf(b), 2)} <button class="icon-btn sm" data-bt="del" data-i="${i}" aria-label="Delete bet" title="Delete"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button></td></tr>`;
    }).join("");
    setHTML($("#bt-table tbody"), rows || '<tr><td colspan="7" class="empty muted">No bets logged yet.</td></tr>');
    if (document.activeElement !== $("#bt-bank")) $("#bt-bank").value = bank || "";
    // glance on the overview
    const st2 = pfState();
    setHTML($("#book-glance"), `<div class="stat"><small>Portfolio</small><b>${holdings.length ? gbp(toGBP(st2.total)) : "–"}</b><span>${holdings.length ? (st2.dayPct == null ? "" : `<span class="chg ${tone(st2.day)}">${signed(st2.dayPct, 2)}</span> today`) : "No holdings yet"}</span></div>`
      + `<div class="stat"><small>Bankroll</small><b>${bank ? gbp(s.bank) : "–"}</b><span>${s.open.length} open bet${s.open.length === 1 ? "" : "s"}</span></div>`
      + `<div class="stat"><small>Bet profit</small><b class="${tone(s.profit)}">${s.done.length ? gbp(s.profit, 2) : "–"}</b><span>${s.done.length} settled</span></div>`);
    setText($("#book-glance-note"), holdings.length || bets.length ? "Stored only in this browser." : "Add holdings and log bets to track your results here.");
  }
  $("#bt-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const sel = $("#bt-sel").value.trim(), odds = +$("#bt-odds").value, stake = +$("#bt-stake").value, p = +$("#bt-p").value || null;
    if (!sel || !(odds > 1) || !(stake > 0)) { $("#bt-hint").textContent = "Enter a selection, decimal odds above 1 and a stake."; return; }
    B.addBet({ sel, odds, stake, p }); e.target.reset();
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-bt]"); if (!b) return;
    const i = +b.dataset.i;
    if (b.dataset.bt === "del") bets.splice(i, 1); else bets[i].status = b.dataset.bt;
    saveBets();
  });
  $("#bt-bank").addEventListener("change", (e) => { bank = Math.max(0, +e.target.value || 0); store.set("bank", bank); B.mark(); });
  B.bankroll = () => B.betStats().bank;

  // ================= calculators =================
  const readCalc = (box) => { const o = {}; for (const i of document.querySelectorAll(`${box} [data-k]`)) o[i.dataset.k] = i.value; return o; };
  function parseOdds(t) {
    t = String(t || "").trim(); if (!t) return null;
    if (/^[+-]\d+$/.test(t)) { const a = +t; return a > 0 ? 1 + a / 100 : 1 + 100 / -a; }
    const f = t.match(/^(\d+(?:\.\d+)?)\s*[\/-]\s*(\d+(?:\.\d+)?)$/); if (f) return 1 + f[1] / f[2];
    const d = +t; return d > 1 ? d : null;
  }
  B.parseOdds = parseOdds;
  // Fractional Kelly stake: a quarter of full Kelly, never above 5% of the bankroll.
  B.kelly = (odds, p, bank2) => {
    const bb = odds - 1, edge = p * odds - 1, full = bb > 0 ? (p * bb - (1 - p)) / bb : 0;
    const frac = Math.max(0, Math.min(0.05, full * 0.25));
    return { edge, full, frac, stake: bank2 ? frac * bank2 : null };
  };
  function calcs() {
    const a = readCalc("#calc-pos"), acct = +a.acct, risk = +a.risk, entry = +a.entry, stop = +a.stop;
    setHTML($("#calc-pos-out"), acct > 0 && risk > 0 && entry > 0 && stop > 0 && entry !== stop
      ? (() => { const per = Math.abs(entry - stop), shares = Math.floor((acct * risk / 100) / per), cost = shares * entry;
          return `<p><b>${fmt(shares, 0)} shares</b> costing ${fmt(cost, 0)} (${fmt(cost / acct * 100, 0)}% of the account). If the stop is hit you lose about ${fmt(shares * per, 0)}, which is ${fmt(risk, 1)}% of the account.${cost > acct ? ' <span class="down">More than the account: you would need leverage.</span>' : ""}</p>`; })()
      : '<p class="hint">Fill in the four boxes.</p>');
    const b = readCalc("#calc-bet"), odds = parseOdds(b.odds), p = +b.p / 100, bk = +b.bank || B.bankroll() || 0;
    if (odds && p > 0 && p < 1) {
      const k = B.kelly(odds, p, bk);
      setHTML($("#calc-bet-out"), `<p>Price implies <b>${fmt(100 / odds, 1)}%</b>; you say <b>${fmt(p * 100, 1)}%</b>. Edge <b class="${tone(k.edge)}">${signed(k.edge * 100, 1)}</b>. `
        + (k.edge > 0 ? `Full Kelly is ${fmt(k.full * 100, 1)}% of the bankroll; the cautious stake is <b>${fmt(k.frac * 100, 1)}%</b>${bk ? ` (${gbp(k.stake, 2)})` : ""}.` : "No bet: the price is no better than your chance.") + " Your chance is only an estimate, and a wrong one makes Kelly overbet.</p>");
    } else setHTML($("#calc-bet-out"), '<p class="hint">Enter the odds and your chance.</p>');
    const f = readCalc("#calc-fx"), amt = +f.amt, cost = +f.cost, r = B.gbpusd();
    const need = cost > 0 && cost < 100 ? (cost / (100 - cost)) * 100 : null;
    document.querySelector('#calc-fx [data-k="need"]').value = need == null ? "" : fmt(need, 2);
    setHTML($("#calc-fx-out"), (amt > 0 && cost >= 0 ? `<p>Costs take about <b>${fmt(amt * cost / 100, 2)}</b> from ${fmt(amt, 0)}; the trade must gain ${need == null ? "–" : fmt(need, 2) + "%"} just to break even.</p>` : "")
      + (r && amt > 0 ? `<p>${fmt(amt, 0)} US$ is about <b>£${fmt(amt / r, 0)}</b>; £${fmt(amt, 0)} is about <b>$${fmt(amt * r, 0)}</b> (GBP/USD ${fmt(r, 4)}).</p>` : "") || '<p class="hint">Enter an amount and a cost.</p>');
  }
  document.addEventListener("input", (e) => { if (e.target.closest(".calc")) calcs(); });
  B.onData.push(calcs);

  // ================= notes and backup =================
  const notes = $("#notes"); notes.value = store.get("notes", "");
  let nt = 0;
  notes.addEventListener("input", () => { clearTimeout(nt); setText($("#note-saved"), "Saving…"); nt = setTimeout(() => { store.set("notes", notes.value); setText($("#note-saved"), "Saved"); }, 600); });
  const SECRET = /^(alpacaId|alpacaSecret|finnhub)$/;
  $("#bk-save").addEventListener("click", () => {
    const out = {};
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith("jarvis.") && !SECRET.test(k.slice(7))) out[k] = localStorage.getItem(k); } } catch { /* ignore */ }
    const url = URL.createObjectURL(new Blob([JSON.stringify({ baco_backup: 1, saved: new Date().toISOString(), data: out }, null, 1)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `baco-backup-${today()}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    setText($("#bk-msg"), "Saved to your downloads.");
  });
  $("#bk-load").addEventListener("click", () => $("#bk-file").click());
  $("#bk-file").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      if (!j.baco_backup || typeof j.data !== "object") throw new Error("not a backup");
      let n = 0;
      for (const [k, v] of Object.entries(j.data)) if (k.startsWith("jarvis.") && !SECRET.test(k.slice(7)) && typeof v === "string") { localStorage.setItem(k, v); n++; }
      setText($("#bk-msg"), `Loaded ${n} items. Reloading…`); setTimeout(() => location.reload(), 700);
    } catch { setText($("#bk-msg"), "That file is not a Baco backup."); }
    e.target.value = "";
  });

  // ================= voice and alerts =================
  const plainGBP = (v) => v == null ? "unknown" : `${Math.round(v).toLocaleString("en-GB")} pounds`;
  B.answerHooks.push((q) => {
    if (/\b(?:portfolio|holdings?|positions?|investments?|net worth|my (?:money|stocks|shares))\b/.test(q) && !/\bbet/.test(q)) {
      const st = pfState();
      if (!holdings.length) return "You haven't added any holdings yet. Open the Portfolio tab and add your first one.";
      const best = st.rows.filter((r) => num(r.dayPct)).sort((a, b) => Math.abs(b.dayPct) - Math.abs(a.dayPct))[0];
      return `Your portfolio is worth about ${plainGBP(toGBP(st.total))}${st.dayPct != null ? `, ${st.dayPct >= 0 ? "up" : "down"} ${fmt(Math.abs(st.dayPct), 2)}% today` : ""}. `
        + (st.gainPct != null ? `Overall you're ${st.gain >= 0 ? "up" : "down"} ${fmt(Math.abs(st.gainPct), 1)}% on what you paid. ` : "") + (best ? `The biggest mover is ${best.sym}, ${signed(best.dayPct, 1)}.` : "")
        + (st.unpriced ? ` ${st.unpriced} holding${st.unpriced === 1 ? " has" : "s have"} no price yet.` : "");
    }
    if (/\b(?:my bets?|bankroll|betting|bet tracker|how am i doing (?:on|with) (?:the )?(?:bets|fights))\b/.test(q)) {
      const s = B.betStats();
      if (!bets.length) return "You haven't logged any bets yet. Open Fight night to log one.";
      return `You have ${s.open.length} open bet${s.open.length === 1 ? "" : "s"} and ${s.done.length} settled. ${s.done.length ? `Profit is ${gbp(s.profit, 2).replace("£", "").replace("−", "minus ")} pounds, a return of ${fmt(s.roi, 1)}% on ${fmt(s.staked, 0)} pounds staked. ` : ""}${bank ? `Your bankroll stands at ${plainGBP(s.bank)}.` : ""}`;
    }
    return null;
  });
  B.alertHooks.push(() => {
    const out = [];
    for (const r of pfState().rows) if (num(r.dayPct) && Math.abs(r.dayPct) >= 4) out.push({ tone: r.dayPct > 0 ? "up" : "down", ico: r.dayPct > 0 ? "up" : "down", cat: "Portfolio", title: `${r.sym} ${r.dayPct > 0 ? "up" : "down"} ${fmt(Math.abs(r.dayPct), 1)}%`, detail: "A big move in something you hold." });
    return out.slice(0, 2);
  });

  // ================= render =================
  let lastSig = "";
  B.onRender.push(() => {
    renderBets(); // also feeds the overview glance
    if (visible("#pf-summary")) renderPortfolio();
    const st = pfState(), sig = JSON.stringify([st.total, st.day, equity.length]);
    if (sig !== lastSig) { lastSig = sig; if (!visible("#pf-summary") && holdings.length) renderPortfolio(); }
  });
  B.onData.push(() => { renderPortfolio(); calcs(); });
  calcs();
})();
