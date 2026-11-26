/* Baco homescreen: one compact tile per area. Each tile is a button that opens that area's tab. */
(() => {
  "use strict";
  const B = window.Baco, { $, esc, fmt, signed, setHTML } = B;
  const tile = (el, label, big, line, tone = "") => setHTML(el, `<small>${esc(label)}</small><b class="${tone}">${big}</b><span>${line}</span><i class="go" aria-hidden="true">›</i>`);

  function render() {
    const W = B.world, K = B.book; if (!W || !K) return;
    // Portfolio
    const pf = K.pf(), bs = K.bets();
    tile($("#h-pf"), "Portfolio", pf.n ? K.gbp(pf.totalGBP) : "–",
      pf.n ? (pf.dayPct == null ? "Waiting for prices" : `<em class="${K.tone(pf.day)}">${signed(pf.dayPct, 2)}</em> today`) + ` · ${bs.open.length} open bet${bs.open.length === 1 ? "" : "s"}` : "Add holdings to track results", pf.n ? K.tone(pf.day) : "");
    // Fight night
    const e = W.ufcEvents()[0];
    if (e) {
      const fs = (e.fights || []).slice().sort((a, b) => b.confidence - a.confidence), top = fs[0], strong = fs.filter((f) => f.confidence >= 0.7).length;
      tile($("#h-ufc"), "Fight night", esc(e.name.replace(/^UFC\s*/i, "UFC ")), top ? `Top pick ${esc(top.pick)} ${fmt(top.confidence * 100, 0)}% · ${strong} strong` + (W.ufcIsSample() ? " · sample" : "") : "No picks yet");
    } else tile($("#h-ufc"), "Fight night", "No card yet", "Load the model's picks to see bets");
    // Travel
    const bus = W.busNext().find((x) => x.catchable), tube = W.tubeNext().find((x) => x.catchable);
    const lead = (x) => x.lb.left <= 0 ? "leave now" : `leave in ${W.inMins(x.lb.left)}`;
    tile($("#h-travel"), "Getting around", bus ? `Bus ${esc(bus.line)} ${W.hm(new Date(bus.dep))}` : "No bus soon",
      [bus ? lead(bus) : "", tube ? `tube ${W.hm(new Date(tube.at))}, ${lead(tube)}` : ""].filter(Boolean).join(" · ") || "Times load shortly");
    // Coming up
    const n = W.nextUp()[0];
    tile($("#h-soon"), "Coming up", n ? esc(n.title) : "Nothing soon", n ? `${esc(n.when)} · ${esc(n.sub)}` : "Calendar is empty");
    // Signals
    const S = B.data.signals || {}, fresh = (S.watchlist || []).filter((r) => B.ageDays(r.signal_date) <= 7).length;
    tile($("#h-sig"), "Signals", `${fresh} fresh`, `${(S.avoid || []).length} to avoid · ${(S.combo || []).length} combo`);
    // Mood (read from the gauge so it never disagrees with the card below)
    tile($("#h-mood"), "Market mood", esc(($("#mood-word") || {}).textContent || "–"), esc(($("#mood-line") || {}).textContent || ""));
  }
  B.onRender.push(render); B.onData.push(render); render();
})();
