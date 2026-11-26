/* Baco: the outside world. Earnings and economic calendar, headlines, the UFC model's picks, and the
   commute (buses from the build-time timetable, the tube live from TfL). Uses window.Baco from app.js. */
(() => {
  "use strict";
  const B = window.Baco, { $, store, esc, num, fmt, setHTML, setText, setClass } = B;
  const D = () => B.data;
  const visible = (id) => { const el = $(id); return el && !el.closest(".view")?.hidden; };
  const TZ = "Europe/London";
  const hm = (d) => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
  const dayKey = (d) => d.toLocaleDateString("en-CA", { timeZone: TZ });
  const dayLabel = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  const rel = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 60000); return isNaN(m) ? "" : m < 60 ? `${Math.max(1, m)}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`; };
  const inMins = (m) => m <= 0 ? "now" : m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
  const cap = B.money;

  // The names the person follows: watchlist, holdings and the insider list.
  const myNames = () => new Set([...B.watch, ...B.extraSyms(), ...(D().signals?.watchlist || []).map((r) => r.ticker).filter(Boolean)].map((s) => String(s).toUpperCase()));

  // ================= headlines =================
  function renderNews() {
    const items = (D().news || []).slice(0, 7);
    setHTML($("#news"), items.length ? items.map((n) => `<li><a href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a><span class="meta">${esc(n.source)}${n.published ? " · " + rel(n.published) : ""}</span></li>`).join("")
      : '<li class="empty">No headlines in this build.</li>');
    setText($("#news-src"), items.length ? "BBC News and Yahoo Finance" : "");
  }

  // ================= calendar =================
  const earn = () => D().calendar?.earnings || [];
  const macro = () => D().calendar?.macro || [];
  function renderCalendar() {
    const mine = myNames(), only = $("#cal-mine").checked;
    const rows = earn().filter((r) => !only || mine.has(r.symbol));
    const by = {};
    rows.forEach((r) => (by[r.date] ||= []).push(r));
    setHTML($("#cal-earn"), Object.keys(by).length ? Object.entries(by).map(([d, rs]) => `<h3 class="day">${esc(dayLabel(d))}${d === dayKey(new Date()) ? ' <span class="badge sm up">Today</span>' : ""}</h3><div class="cal-rows">`
      + rs.map((r) => `<div class="cal-row${mine.has(r.symbol) ? " mine" : ""}"><span class="sym">${esc(r.symbol)}${mine.has(r.symbol) ? ' <i title="On your lists">★</i>' : ""}</span><span class="nm" title="${esc(r.name)}">${esc(r.name)}</span>`
        + `<span class="tm">${esc(r.time)}</span><span class="eps">${num(r.eps_forecast) ? "EPS " + fmt(r.eps_forecast, 2) : ""}</span><span class="cp">${num(r.market_cap) ? cap(r.market_cap) : ""}</span></div>`).join("") + "</div>").join("")
      : `<p class="empty">${only ? "None of your names report in the next two weeks." : "No earnings data in this build."}</p>`);
    const now = Date.now(), ev = macro().filter((m) => new Date(m.when) > now - 36e5);
    const by2 = {};
    ev.forEach((m) => (by2[dayKey(new Date(m.when))] ||= []).push(m));
    setHTML($("#cal-macro"), Object.keys(by2).length ? Object.entries(by2).map(([d, ms]) => `<h3 class="day">${esc(dayLabel(d))}</h3><div class="cal-rows">`
      + ms.map((m) => `<div class="cal-row mac"><span class="tm">${hm(new Date(m.when))}</span><span class="ccy">${esc(m.country)}</span><span class="nm" title="${esc(m.title)}">${esc(m.title)}</span>`
        + `<i class="dot ${m.impact === "High" ? "down" : "warn"}" title="${esc(m.impact)} impact"></i><span class="eps">${m.forecast ? "f " + esc(m.forecast) : ""}${m.previous ? " · p " + esc(m.previous) : ""}</span></div>`).join("") + "</div>").join("")
      : '<p class="empty">No releases in this build.</p>');
    setHTML($("#cal-ufc"), ufcEvents().length ? ufcEvents().map((e) => `<div class="cal-row ufc"><span class="tm">${esc(e.dates?.[0] ? dayLabel(e.dates[0]) : "")}</span><span class="nm">${esc(e.name)}</span><span class="eps">${e.n_fights} fights</span></div>`).join("")
      : '<p class="empty">No fight card loaded. See Fight night.</p>');
  }
  $("#cal-mine").checked = store.get("calMine", false);
  $("#cal-mine").addEventListener("change", (e) => { store.set("calMine", e.target.checked); renderCalendar(); });

  // ================= coming up (overview) =================
  function nextUp() {
    const mine = myNames(), items = [], now = Date.now(), today = dayKey(new Date());
    for (const r of earn()) {
      const days = Math.round((new Date(r.date + "T12:00:00Z") - new Date(today + "T12:00:00Z")) / 864e5);
      if (mine.has(r.symbol) && days <= 10) items.push({ t: new Date(r.date + "T12:00:00Z").getTime(), when: days === 0 ? "Today" : days === 1 ? "Tomorrow" : dayLabel(r.date), ico: "cal", title: `${r.symbol} reports`, sub: `${r.name}, ${r.time.toLowerCase()}`, mine: true });
    }
    for (const m of macro()) { const t = new Date(m.when).getTime(); if (m.impact === "High" && t > now && t - now < 3 * 864e5) items.push({ t, when: `${dayKey(new Date(t)) === today ? "Today" : dayLabel(dayKey(new Date(t)))} ${hm(new Date(t))}`, ico: "warn", title: `${m.country} ${m.title}`, sub: m.forecast ? `Forecast ${m.forecast}, previous ${m.previous || "?"}` : "High impact" }); }
    const big = earn().filter((r) => !mine.has(r.symbol)).slice(0, 40).sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 2);
    for (const r of big) items.push({ t: new Date(r.date + "T12:00:00Z").getTime() + 1, when: dayLabel(r.date), ico: "cal", title: `${r.symbol} reports`, sub: `${r.name}, ${cap(r.market_cap)} company` });
    const e = ufcEvents()[0];
    if (e?.dates?.[0]) items.push({ t: new Date(e.dates[0] + "T20:00:00Z").getTime(), when: dayLabel(e.dates[0]), ico: "fight", title: e.name, sub: `${e.n_fights} fights${ufcIsSample() ? " (sample data)" : ""}` });
    items.sort((a, b) => a.t - b.t);
    return items;
  }
  function renderSoon() {
    const it = nextUp().slice(0, 6);
    setHTML($("#soon"), it.length ? `<ul class="soon">${it.map((i) => `<li class="${i.mine ? "mine" : ""}"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true">${{ cal: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>', warn: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', fight: '<path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.5 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"/>' }[i.ico]}</svg></span>`
      + `<div><b>${esc(i.title)}</b><span>${esc(i.sub)}</span></div><time>${esc(i.when)}</time></li>`).join("")}</ul>` : '<p class="empty">Nothing on the calendar yet.</p>');
  }

  // ================= travel =================
  const T = () => D().travel;
  const walk = (k) => +store.get(k === "bus" ? "walkBus" : "walkTube", T()?.[k]?.walk_min ?? (k === "bus" ? 12 : 11));
  let tube = { at: 0, trains: [], status: null, err: null, loading: false };
  async function loadTube() {
    const id = T()?.tube?.naptan; if (!id || tube.loading) return;
    tube.loading = true;
    try {
      const [a, s] = await Promise.all([fetch(`https://api.tfl.gov.uk/StopPoint/${id}/Arrivals`), fetch("https://api.tfl.gov.uk/Line/metropolitan/Status")]);
      if (!a.ok) throw new Error(a.status);
      tube.trains = (await a.json()).map((x) => ({ at: new Date(x.expectedArrival).getTime(), to: x.destinationName || x.towards || "", platform: x.platformName || "", line: x.lineName }));
      try { const j = s.ok ? await s.json() : null; tube.status = j?.[0]?.lineStatuses?.[0] || null; } catch { tube.status = null; }
      tube.err = null; tube.at = Date.now();
    } catch (e) { tube.err = "Live tube times are unavailable right now."; }
    tube.loading = false; B.mark();
  }
  const dirOf = (p) => /south|east/i.test(p) ? "in" : /north|west/i.test(p) ? "out" : "all";
  function leaveBy(depMs, mins) { const left = Math.round((depMs - mins * 60000 - Date.now()) / 60000); return { at: new Date(depMs - mins * 60000), left }; }
  function busNext() {
    const b = T()?.bus; if (!b) return [];
    const w = walk("bus"), now = Date.now(), all = [];
    for (const s of b.stops) for (const d of s.departures) {
      const dep = new Date(d.expected || d.scheduled).getTime(), lb = leaveBy(dep, w);
      if (dep < now - 60000) continue;
      all.push({ ...d, dep, lb, stopName: s.name, catchable: lb.left >= 0 });
    }
    return all.sort((x, y) => x.dep - y.dep);
  }
  function tubeNext() {
    const dir = store.get("tubeDir", "in"), w = walk("tube");
    return tube.trains.filter((t) => t.at > Date.now() - 30000 && (dir === "all" || dirOf(t.platform) === dir)).sort((a, b) => a.at - b.at).map((t) => ({ ...t, lb: leaveBy(t.at, w), catchable: leaveBy(t.at, w).left >= 0 }));
  }
  function renderTravel() {
    const t = T();
    if (!t) { setHTML($("#travel"), '<p class="empty">Travel times are not in this build.</p>'); setText($("#travel-badge"), ""); return; }
    const bus = busNext(), bs = bus.filter((x) => x.catchable).slice(0, 4), tn = tubeNext(), ts = tn.filter((x) => x.catchable).slice(0, 4);
    const lead = (x, what) => x ? (x.lb.left <= 0 ? `<b>Leave now</b> for ${what}` : `Leave in <b>${inMins(x.lb.left)}</b> (${hm(x.lb.at)}) for ${what}`) : "";
    const busRows = bs.map((x, i) => `<li class="${i === 0 ? "first" : ""}"><span class="line">${esc(x.line)}</span><div><b>${hm(new Date(x.dep))}${x.expected && x.expected !== x.scheduled ? ` <small>due ${hm(new Date(x.scheduled))}</small>` : ""}</b><span>${esc(x.to)}, there about ${hm(new Date(x.dep + x.ride_min * 60000))}</span></div><time>leave ${hm(x.lb.at)}<small>in ${inMins(x.lb.left)}</small></time></li>`).join("");
    const tubeRows = ts.map((x, i) => `<li class="${i === 0 ? "first" : ""}"><span class="line met">Met</span><div><b>${hm(new Date(x.at))}</b><span>${esc(x.to || x.platform)}</span></div><time>leave ${hm(x.lb.at)}<small>in ${inMins(x.lb.left)}</small></time></li>`).join("");
    const age = D().generated_at ? Math.round((Date.now() - new Date(D().generated_at)) / 60000) : null;
    const st = tube.status, bad = st && st.statusSeverity !== 10;
    setHTML($("#travel"), `<div class="trip"><h3><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3.5" width="16" height="14" rx="2.5"/><path d="M4 11h16M8 21v-3.5M16 21v-3.5"/></svg>Bus to Warwick</h3>`
      + `<p class="lead">${bs.length ? lead(bs[0], `the ${esc(bs[0].line)}`) : "No more buses in the timetable for now."}</p>${bs.length ? `<ul class="deps">${busRows}</ul>` : ""}`
      + `<p class="hint small">${esc(t.bus.label)}. ${walk("bus")} minute walk. Timetable${age != null ? `, with live running as at ${age < 1 ? "now" : age + " min ago"}` : ""}; the stop shown first is the University-bound side.</p></div>`
      + `<div class="trip"><h3><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3.5" width="14" height="14" rx="3"/><path d="M5 12h14M9 21l1.5-3.5M15 21l-1.5-3.5"/></svg>Tube from Northwood</h3>`
      + (tube.err && !tube.trains.length ? `<p class="hint">${esc(tube.err)}</p>` : `<p class="lead">${ts.length ? lead(ts[0], "the next train") : "No catchable trains listed right now."}</p>${ts.length ? `<ul class="deps">${tubeRows}</ul>` : ""}`)
      + `<p class="hint small">${esc(t.tube.label)}. ${walk("tube")} minute walk. ${bad ? `<b class="down">Metropolitan line: ${esc(st.statusSeverityDescription)}.</b> ` : st ? "Metropolitan line: good service. " : ""}${tube.at ? `Live from TfL, updated ${hm(new Date(tube.at))}.` : ""}</p></div>`);
    setHTML($("#travel-badge"), tube.at ? '<i class="dot live"></i>Tube live' : '<i class="dot delayed"></i>Bus timetable');
  }
  setInterval(() => { if (document.visibilityState === "visible") loadTube(); }, 30000);
  B.onData.push(loadTube);

  // ================= UFC =================
  const SAMPLE = {
    schema: 1, public: true, sample: true, generated_at: new Date().toISOString(),
    events: [{ name: "SAMPLE CARD (made-up fighters)", dates: [dayKey(new Date(Date.now() + 6 * 864e5))], days_to_go: 6, n_fights: 4, fights: [
      { a: "Fighter Alpha", b: "Fighter Bravo", weight_class: "Lightweight", rounds: 5, p_a: 0.83, p_elo_a: 0.74, p_distance: 0.52, pick: "Fighter Alpha", pick_side: "A", confidence: 0.83, confidence_label: "High", tier: "80+", drivers: [["Striking differential", 9.1], ["Age", 3.2]], flags: [], thin_data: false },
      { a: "Fighter Charlie", b: "Fighter Delta", weight_class: "Welterweight", rounds: 3, p_a: 0.27, p_elo_a: 0.4, p_distance: 0.6, pick: "Fighter Delta", pick_side: "B", confidence: 0.73, confidence_label: "Good", tier: "70-80", drivers: [["Takedown defence", 6.5]], flags: [], thin_data: false },
      { a: "Fighter Echo", b: "Fighter Foxtrot", weight_class: "Bantamweight", rounds: 3, p_a: 0.56, p_elo_a: 0.52, p_distance: 0.66, pick: "Fighter Echo", pick_side: "A", confidence: 0.56, confidence_label: "Toss-up", tier: null, drivers: [], flags: [], thin_data: false },
      { a: "Fighter Golf", b: "Fighter Hotel", weight_class: "Flyweight", rounds: 3, p_a: 0.38, p_elo_a: 0.45, p_distance: 0.7, pick: "Fighter Hotel", pick_side: "B", confidence: 0.62, confidence_label: "Moderate", tier: null, drivers: [["Reach", 2.0]], flags: ["thin data on a fighter"], thin_data: true },
    ] }],
    forward: { logged: 0, graded: 0, needed: 150 }, evidence: [], gap: null,
  };
  // Convert the model's own ufc-ui/data.json (kept private) to the dashboard's format, in the browser.
  function normaliseRaw(raw) {
    const tier = (c) => c >= 0.8 ? "High" : c >= 0.7 ? "Good" : c >= 0.6 ? "Moderate" : "Toss-up";
    return { schema: 1, public: false, generated_at: new Date().toISOString(), local: true, model_as_of: raw.asof, forward: raw.forward || { logged: 0, graded: 0, needed: 150 }, evidence: raw.evidence || [], gap: raw.gap,
      events: (raw.cards || []).map((c) => ({ name: c.name, dates: c.dates, days_to_go: c.days, n_fights: (c.fights || []).length, fights: (c.fights || []).map((f) => {
        const pa = +f.p_model, conf = Math.max(pa, 1 - pa), a = pa >= 0.5;
        return { a: f.a, b: f.b, weight_class: f.wc, rounds: f.rounds, p_a: pa, p_elo_a: f.p_elo, p_distance: f.dist, pick: a ? f.a : f.b, pick_side: a ? "A" : "B", confidence: conf, confidence_label: tier(conf), tier: f.pick?.tier || null,
          drivers: (f.drivers || []).slice(0, 3), flags: f.flags || [], thin_data: !!f.coverage && Math.min(...f.coverage) < 3, price_a: f.best_a, price_b: f.best_b, book_a: f.best_a_book, book_b: f.best_b_book, market_p_a: f.p_mkt };
      }) })) };
  }
  let ufcLocal = null; try { ufcLocal = JSON.parse(localStorage.getItem("jarvis.ufcLocal") || "null"); } catch { /* ignore */ }
  let useSample = false;
  const ufcData = () => useSample ? SAMPLE : (ufcLocal || D().ufc || null);
  const ufcIsSample = () => useSample;
  const ufcEvents = () => ufcData()?.events || [];
  let evIdx = 0, oddsIn = {};     // oddsIn[fightKey] = {a, b} typed or from the model file
  const fkey = (e, f) => `${e.name}|${f.a}|${f.b}`;
  const bar = (p) => `<span class="pbar" role="img" aria-label="${fmt(p * 100, 0)}% / ${fmt((1 - p) * 100, 0)}%"><i style="width:${(p * 100).toFixed(1)}%"></i></span>`;
  function fightCard(e, f, compact) {
    const k = fkey(e, f), o = oddsIn[k] || {};
    const oa = o.a ?? f.price_a, ob = o.b ?? f.price_b;
    const pa = f.p_a, pb = 1 - pa, conf = f.confidence, pickA = f.pick_side === "A";
    const sides = [["A", f.a, pa, oa], ["B", f.b, pb, ob]].map(([s, n, p, odds]) => {
      if (!(odds > 1)) return { s, n, p, odds: null };
      const kk = B.kelly(odds, p, B.bankroll()); return { s, n, p, odds, ...kk };
    });
    const value = sides.filter((x) => x.odds && x.edge > 0.03).sort((x, y) => y.edge - x.edge)[0];
    const cls = f.confidence_label === "High" ? "up" : f.confidence_label === "Good" ? "up" : f.confidence_label === "Moderate" ? "warn" : "";
    return `<article class="fight${compact ? " compact" : ""}" data-fk="${esc(k)}"><header><span class="wc">${esc(f.weight_class || "")} · ${f.rounds || 3} rounds</span>`
      + `<span class="badge ${cls}" title="The model's chance that its pick wins">${esc(f.confidence_label)} · ${fmt(conf * 100, 0)}%</span>${f.tier ? `<span class="badge ai" title="Meets the paper-test rule: 70%+ confident">${esc(f.tier)} pick</span>` : ""}${f.thin_data ? '<span class="badge warn" title="A fighter has fewer than 3 UFC fights in the data">Thin data</span>' : ""}</header>`
      + `<div class="vs"><div class="fgt ${pickA ? "pick" : ""}"><b>${esc(f.a)}</b><span>${fmt(pa * 100, 0)}%</span></div>${bar(pa)}<div class="fgt r ${!pickA ? "pick" : ""}"><b>${esc(f.b)}</b><span>${fmt(pb * 100, 0)}%</span></div></div>`
      + `<p class="why">Model pick: <b>${esc(f.pick)}</b>${num(f.p_distance) ? `. Goes the distance: ${fmt(f.p_distance * 100, 0)}%` : ""}${f.drivers?.length ? `. Main drivers: ${f.drivers.map((d) => esc(d[0])).join(", ")}` : ""}.${f.flags?.length ? ` <span class="down">${esc(f.flags.join("; "))}.</span>` : ""}</p>`
      + `<div class="odds-row"><label>${esc(f.a.split(" ").slice(-1)[0])} odds<input data-odds="a" type="number" step="0.01" min="1.01" value="${oa || ""}" placeholder="2.10"></label>`
      + `<label>${esc(f.b.split(" ").slice(-1)[0])} odds<input data-odds="b" type="number" step="0.01" min="1.01" value="${ob || ""}" placeholder="1.80"></label>`
      + (value ? `<div class="val"><b class="up">Value: ${esc(value.n)} at ${fmt(value.odds, 2)}</b><span>edge ${B.signed(value.edge * 100, 1)} · cautious stake ${value.stake != null && B.bankroll() ? "£" + fmt(value.stake, 2) : fmt(value.frac * 100, 1) + "% of bankroll"}</span><button class="btn" type="button" data-log="${value.s}">Log bet</button></div>`
        : (oa > 1 || ob > 1) ? '<div class="val"><span class="muted">No value at these prices</span></div>' : '<div class="val"><span class="muted">Enter the price you can get to check for value</span></div>') + "</div></article>";
  }
  function renderUfc() {
    const d = ufcData(), evs = ufcEvents();
    const sel = $("#ufc-event");
    if (evIdx >= evs.length) evIdx = 0;
    const optHtml = evs.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join("");
    if (sel.__h !== optHtml) { sel.__h = optHtml; sel.innerHTML = optHtml; }
    sel.value = String(evIdx); sel.hidden = evs.length < 2;
    $("#ufc-sample").textContent = useSample ? "Hide sample" : "Show sample";
    $("#ufc-import").textContent = ufcLocal ? "Replace model file" : "Load model file";
    const none = !d || !evs.length;
    $("#ufc-empty").hidden = !none; $("#ufc-card").hidden = none;
    if (none) {
      setHTML($("#ufc-empty"), `<div class="empty-state"><p><b>No fight card is published yet.</b></p><p>The model lives in your MMA-betting repository, and its price data is not allowed to be shared publicly, so the picks are not on this page until you send them here.</p>`
        + `<ol><li>In the MMA-betting folder run <code>python scripts/signal_data.py</code>.</li><li>Press <b>Load model file</b> above and choose <code>ufc-ui/data.json</code>. It stays in this browser.</li></ol><p>To publish the model's own picks (without any bookmaker prices) so they appear for you on every device, run <code>python run.py ufc ../MMA-betting/ufc-ui/data.json</code> in the Baco repository and commit <code>data/ufc_predictions.json</code>.</p></div>`);
      setHTML($("#ufc-picks"), ""); setText($("#ufc-title"), "Next card"); setText($("#ufc-note"), "");
      renderEvidence(null); return;
    }
    const e = evs[evIdx], fights = e.fights || [];
    setText($("#ufc-title"), e.name);
    setHTML($("#ufc-note"), (d.sample ? '<b class="down">SAMPLE DATA: these fighters and numbers are made up, to show the layout.</b> ' : "") + `${e.dates?.[0] ? dayLabel(e.dates[0]) : ""}${e.days_to_go != null ? ` (${e.days_to_go === 0 ? "today" : e.days_to_go + " days to go"})` : ""}. `
      + (d.local ? "Loaded from your model file, in this browser only. " : d.public ? "Published by the model without bookmaker prices: type the price you can get to check for value. " : "")
      + "The percentage is the model's chance of its pick winning, not a promise.");
    const strong = fights.filter((f) => f.confidence >= 0.7).sort((a, b) => b.confidence - a.confidence);
    setHTML($("#ufc-picks"), `<h3 class="sub-head">Potential bets: picks the model is 70%+ sure about</h3>` + (strong.length ? `<div class="fights">${strong.map((f) => fightCard(e, f, true)).join("")}</div>` : '<p class="empty">No fight clears 70% on this card. Passing is a fine decision.</p>'));
    setText($("#ufc-count"), `${fights.length} fights`);
    setHTML($("#ufc-fights"), fights.map((f) => fightCard(e, f, false)).join(""));
    renderEvidence(d);
  }
  function renderEvidence(d) {
    const f = d?.forward || { logged: 0, graded: 0, needed: 150 }, ev = d?.evidence || [];
    const kindTxt = { test: "Tested", lead: "Found after the fact", untradable: "Not tradable" };
    setHTML($("#ufc-evidence"), `<p class="hint">Betting the model's picks has not beaten bookmaker prices in tests so far; the ranges below include zero. A forward test on fights not yet fought is running.</p>`
      + `<div class="fwd"><div class="meter"><i style="width:${Math.min(100, (f.graded / f.needed) * 100)}%"></i></div><p class="hint small">Forward test: ${f.graded} of ${f.needed} picks graded (${f.logged} logged). Keep it paper-only until then.</p></div>`
      + (ev.length ? `<ul class="evid">${ev.map((x) => `<li><span>${esc(x.label)}<small>${esc(x.n)} · ${esc(kindTxt[x.kind] || x.kind)}</small></span><b class="${x.lo > 0 ? "up" : x.hi < 0 ? "down" : ""}">${B.signed(x.v, 1)}<small>${fmt(x.lo, 1)} to ${fmt(x.hi, 1)}</small></b></li>`).join("")}</ul><p class="hint small">Return on money staked, with a 95% range.</p>` : ""));
  }
  $("#ufc-event").addEventListener("change", (e) => { evIdx = +e.target.value; renderUfc(); });
  $("#ufc-sample").addEventListener("click", () => { useSample = !useSample; evIdx = 0; renderUfc(); });
  $("#ufc-import").addEventListener("click", () => $("#ufc-file").click());
  $("#ufc-file").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      const n = j.cards ? normaliseRaw(j) : (j.schema === 1 && Array.isArray(j.events) ? { ...j, local: true } : null);
      if (!n) throw new Error("format");
      ufcLocal = n; try { localStorage.setItem("jarvis.ufcLocal", JSON.stringify(n)); } catch { /* too big or private mode */ }
      useSample = false; evIdx = 0; renderUfc(); renderCalendar(); renderSoon();
    } catch { setText($("#ufc-note"), "That file isn't the model's ufc-ui/data.json."); }
    e.target.value = "";
  });
  // typing odds updates the value check in place
  document.addEventListener("input", (e) => {
    const inp = e.target.closest("[data-odds]"); if (!inp) return;
    const card = inp.closest(".fight"), k = card.dataset.fk;
    (oddsIn[k] ||= {})[inp.dataset.odds] = +inp.value || null;
    const act = document.activeElement, side = act?.dataset?.odds, pos = act?.selectionStart;
    const ev = ufcEvents()[evIdx], f = ev?.fights.find((x) => fkey(ev, x) === k);
    if (!f) return;
    const tmp = document.createElement("div"); tmp.innerHTML = fightCard(ev, f, card.classList.contains("compact"));
    // keep the inputs (and focus) and replace only the value area
    card.querySelector(".odds-row .val")?.replaceWith(tmp.querySelector(".odds-row .val"));
    // mirror the typed value into the same fight elsewhere on the page
    for (const other of document.querySelectorAll(`.fight[data-fk="${CSS.escape(k)}"]`)) if (other !== card) { const o = other.querySelector(`[data-odds="${inp.dataset.odds}"]`); if (o) o.value = inp.value; other.querySelector(".odds-row .val")?.replaceWith(tmp.querySelector(".odds-row .val").cloneNode(true)); }
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-log]"); if (!b) return;
    const card = b.closest(".fight"), ev = ufcEvents()[evIdx], f = ev?.fights.find((x) => fkey(ev, x) === card.dataset.fk); if (!f) return;
    const side = b.dataset.log, o = oddsIn[card.dataset.fk] || {}, odds = o[side.toLowerCase()] ?? f[side === "A" ? "price_a" : "price_b"], p = side === "A" ? f.p_a : 1 - f.p_a;
    const k = B.kelly(odds, p, B.bankroll());
    B.addBet({ sel: `${side === "A" ? f.a : f.b} to win (${ev.name})`, odds, stake: Math.round((k.stake || 0) * 100) / 100 || 0.01, p: Math.round(p * 100) });
    b.textContent = "Logged"; b.disabled = true;
    setText($("#bt-hint"), "Logged with the suggested stake. Edit by deleting and re-adding, or settle it when the fight is over.");
  });

  // ================= voice and alerts =================
  B.answerHooks.push((q) => {
    if (/\b(?:bus|buses|warwick|university)\b/.test(q) && !/\bufc\b/.test(q)) {
      const n = busNext().filter((x) => x.catchable)[0];
      if (!T()) return "I don't have bus times in this build.";
      return n ? `The next bus you can catch is the ${n.line} at ${hm(new Date(n.dep))}. ${n.lb.left <= 0 ? "Leave now" : `Leave in ${inMins(n.lb.left)}, at ${hm(n.lb.at)}`}, allowing ${walk("bus")} minutes to walk. It reaches the University at about ${hm(new Date(n.dep + n.ride_min * 60000))}. That's from the timetable, with live running as at the last update.`
        : "I can't see another bus to the University in the timetable I have.";
    }
    if (/\b(?:tube|train|metropolitan|northwood|underground)\b/.test(q)) {
      const n = tubeNext().filter((x) => x.catchable)[0];
      if (!tube.at) return tube.err || "I'm still fetching live tube times. Ask again in a moment.";
      return n ? `The next train you can catch from Northwood is at ${hm(new Date(n.at))}${n.to ? ` towards ${n.to}` : ""}. ${n.lb.left <= 0 ? "Leave now" : `Leave in ${inMins(n.lb.left)}, at ${hm(n.lb.at)}`}, allowing ${walk("tube")} minutes to walk.` : "There are no catchable trains listed right now.";
    }
    if (/\b(?:earnings|reports?|results)\b/.test(q) && !/\bpoint|portfolio\b/.test(q)) {
      const mine = myNames(), list = earn(), pick = list.filter((r) => mine.has(r.symbol)).slice(0, 3), use = pick.length ? pick : list.slice(0, 3);
      return use.length ? `${pick.length ? "From your lists" : "The biggest reports coming up"}: ` + use.map((r) => `${r.symbol} on ${dayLabel(r.date)}, ${r.time.toLowerCase()}`).join("; ") + "." : "I have no earnings dates in this build.";
    }
    if (/\b(?:ufc|fight|fights|fighters?|mma|card)\b/.test(q)) {
      const e = ufcEvents()[0]; if (!e) return "There's no fight card loaded yet. Open Fight night to load your model file.";
      const s = e.fights.filter((f) => f.confidence >= 0.7).sort((a, b) => b.confidence - a.confidence).slice(0, 3);
      return `${e.name}${ufcIsSample() ? " (sample data)" : ""}: ${e.fights.length} fights. ` + (s.length ? "The model's strongest picks are " + s.map((f) => `${f.pick} at ${fmt(f.confidence * 100, 0)}%`).join(", ") + ". It hasn't proved an edge over the bookmakers, so keep it to paper bets." : "No pick reaches 70%, so nothing stands out.");
    }
    if (/\b(?:economy|economic|calendar|cpi|inflation|rates?|fed|bank of england|jobs report|payrolls)\b/.test(q) && /\b(?:when|next|calendar|this week|release)\b/.test(q)) {
      const n = macro().filter((m) => m.impact === "High" && new Date(m.when) > Date.now()).slice(0, 3);
      return n.length ? "Next big releases: " + n.map((m) => `${m.country} ${m.title} on ${dayLabel(dayKey(new Date(m.when)))} at ${hm(new Date(m.when))}`).join("; ") + "." : "No high-impact releases in the data I have.";
    }
    return null;
  });
  B.alertHooks.push(() => {
    const out = [], mine = myNames(), today = dayKey(new Date());
    for (const r of earn().filter((x) => mine.has(x.symbol) && (x.date === today || x.date === dayKey(new Date(Date.now() + 864e5)))).slice(0, 2))
      out.push({ tone: "info", ico: "cal", cat: "Earnings", title: `${r.symbol} reports ${r.date === today ? "today" : "tomorrow"}`, detail: `${r.name}, ${r.time.toLowerCase()}. Expect a big move either way.` });
    const e = ufcEvents()[0];
    if (e && !ufcIsSample() && e.dates?.[0] && (new Date(e.dates[0] + "T20:00:00Z") - Date.now()) / 864e5 <= 3 && (new Date(e.dates[0] + "T20:00:00Z") - Date.now()) > -864e5) out.push({ tone: "info", ico: "fight", cat: "Fight night", title: `${e.name} is ${e.dates[0] === today ? "tonight" : "soon"}`, detail: "Check the model's picks and your bets." });
    const n = busNext().find((x) => x.catchable);
    const h = new Date().getHours(), wd = new Date().getDay();
    if (n && n.lb.left <= 10 && h >= 6 && h < 11 && wd > 0 && wd < 6) out.push({ tone: "info", ico: "bus", cat: "Bus", title: `Leave in ${inMins(n.lb.left)} for the ${n.line}`, detail: `Departs ${hm(new Date(n.dep))}, University about ${hm(new Date(n.dep + n.ride_min * 60000))}.` });
    return out;
  });

  // ================= render =================
  B.onRender.push(() => {
    renderTravel();
    if (visible("#cal-earn")) renderCalendar();
    if (visible("#ufc-title") && !document.activeElement?.matches?.("[data-odds]")) renderUfc();
  });
  B.world = { busNext, tubeNext, nextUp, ufcEvents, ufcIsSample, hm, inMins, dayLabel, walk };
  B.onData.push(() => { renderNews(); renderSoon(); renderCalendar(); renderUfc(); renderTravel(); });
  setInterval(() => { renderSoon(); }, 60000);
  renderUfc(); renderCalendar(); renderSoon();
})();
