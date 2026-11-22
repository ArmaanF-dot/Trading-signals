# Jarvis design notes

Jarvis should feel like a premium, lively market instrument: editorial and professional, never neon or sci-fi, and never the generic "dark grey plus blue accent" dashboard look.

## History
- PR #16, neon HUD: rejected as cartoony.
- PR #18, calm grey workstation: rejected as generic and vibe-coded.
- PR #19, the current direction: themed, editorial and animated.

## Identity
- **Logo:** a dial. A coloured disc with a white arc, a needle and a hub, next to a serif "Jarvis" wordmark. It echoes the market mood gauge, and the needle sweeps while Jarvis is listening or speaking.
- **Type:** Newsreader for headlines, the brief, answers and big numbers. IBM Plex Sans for interface text. Small uppercase labels (11px, letter spacing 0.06–0.09em) for table heads and stat labels.
- **Colour schemes:** chosen in Settings. Each one sets the tokens at the top of `dashboard/style.css`.

  | Theme | Look | Brand | Accent |
  |---|---|---|---|
  | Crimson (default) | Warm black | Red | Gold |
  | Swiss | White paper | Red | Black |
  | Navy | Deep navy | Gold | Gold |
  | Graphite | Black | Orange | Orange |

  Green and red only ever mean up and down. Amber means caution or delayed.

## Motion (all of it switches off with "reduce motion")
- **Gauge:** the needle and the per-index markers ride on springs. When prices first arrive, the needle sweeps the whole dial once, then settles on the average. Hovering an index row highlights its marker.
- **Ticker tape:** scrolls continuously and pauses on hover.
- **Markets:** session strips fill as each market's trading day progresses.
- **Sparklines** draw in once, then update in place.
- **Headline numbers** count up once.
- **Alerts** slide in when the list changes. Prices flash briefly when they change. Asking about a market pings its tile.

## Ask Jarvis
- **Where it works:** typed, or spoken with the microphone button. Voice needs browser speech recognition, which Chrome, Edge and Safari have.
- **How it answers:** in the browser, from the data already on the page. It covers mood, attention items, the brief, the fear gauge, indices, crypto, the pound, gold, watchlist stocks, insiders, names to avoid, market hours, and adding or removing watchlist stocks.
- **Speaking:** answers are read aloud with a British English voice where the device has one. Settings controls when: after voice questions (the default), always, or never.
