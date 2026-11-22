# Exotic and frontier markets from a UK retail account: feasibility

**Verdict:** the countries themselves (Mongolia, Tajikistan) are not tradeable by a UK retail account; Colombia is, through a handful of liquid proxies. The one testable idea, that commodity-linked country ETFs lag their commodity, found nothing out of sample (see `frontier_etf_backtest.md`). Local-data ideas such as Colombian insolvency filings have no free, point-in-time, backtestable feed and almost no listed targets, so they are not worth building. Not recommended as a signal source.

Facts below are from general knowledge of these markets and were not re-checked against broker or exchange pages in this run; confirm with your broker before acting.

## What a UK retail account can actually buy

| Country | Direct local market | Realistic proxies | Notes |
|---|---|---|---|
| Mongolia | Mongolian Stock Exchange, tiny, local brokers only, no shorting or derivatives | Mongolian Mining Corp (Hong Kong listing), Rio Tinto (Oyu Tolgoi), coal and copper futures or ETFs | No Mongolia ETF with real liquidity. Proxies are driven by China demand and commodity prices more than Mongolian news. |
| Tajikistan | Essentially no investable exchange | Gold and aluminium producers elsewhere, nothing country-specific | Not investable. |
| Colombia | Bolsa de Valores de Colombia, not on UK retail platforms | ADRs: Ecopetrol (EC), Bancolombia (CIB), Grupo Aval (AVAL); the US-listed Colombia ETF (GXG) | GXG no longer returned Yahoo data in this run, so treat it as delisted or unavailable. ADRs are the live route. |
| Other frontier (Vietnam, Argentina, Nigeria, Kenya) | Mostly closed or capital-controlled | Vietnam and Argentina ETFs, frontier-basket ETFs | Thin, with wide spreads. |

UK-specific catch: since 2018 the PRIIPs/KID rules mean most UK retail brokers cannot sell US-domiciled ETFs, only UCITS funds (London-listed, accumulating or distributing). Single-country frontier ETFs are rarely available as UCITS. US-listed ADRs and single stocks are not affected. Shorting means CFDs or spread bets, with financing costs and spreads of roughly the 2 to 3 per cent the project already assumes.

## Local-data ideas

- **Colombian insolvency filings (Supersociedades):** the regulator publishes proceedings, but not as a clean historical feed with filing timestamps, and nearly all of the companies are private. Only a few names (Ecopetrol, Bancolombia, Grupo Aval and similar) are listed, so the event count is close to zero and no backtest has power.
- **Mongolian or Tajik local data:** coal export volumes, customs data and Mongolian exchange announcements are published late, in local language, mostly as PDFs. The listed instruments that benefit (Hong Kong miners, global majors) already react to China and commodity data, which is fast and public.
- **Why slow information rarely helps here:** the ADR or ETF trades in US hours on global commodity and risk news, so a local data point that moves it is usually priced within a day. Where it is not, the spread and shorting cost take the edge.

## What was tested

Single-country ETFs for commodity-dependent markets versus their commodity (oil, copper, gold, Brent, soybeans), signal = the part of the commodity move the ETF had not yet priced. Result in `frontier_etf_backtest.md`: in sample (2011-2015) the signal looked real (rank IC t about 2.5, +20% a year gross), out of sample (2016-2026, 130 months) it was gone (rank IC t -0.4, +0.8% a year gross, negative after costs). This is the same pattern as the earlier studies: an in-sample pattern that does not survive. Caveats: ETFs only (Colombia ETF missing), survivorship bias in favour of the strategy, and shorting not realistically available.

## Recommendation

Do not add frontier countries as a standalone model. If a future thread wants exposure, the cheapest honest route is to treat Ecopetrol, Bancolombia and Hong Kong-listed Mongolian miners as ordinary stocks inside the signal feed, driven by the commodity and China data the project already follows, and judge them by forward tracking rather than another backtest.
