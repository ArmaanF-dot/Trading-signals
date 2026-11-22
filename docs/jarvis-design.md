# Jarvis design notes

Jarvis should look like a calm, professional market workstation (think Koyfin, TradingView, Linear or Stripe's dashboards), not a sci-fi screen. These notes keep later changes consistent.

## What made the old look amateur

| Problem | Why it read as cartoony | What replaced it |
|---|---|---|
| Spinning core, grid floor, scanlines, glow blobs, corner brackets | Decoration that carries no data competes with the data | Nothing. Plain surfaces |
| Neon glow on text and borders | Glow blurs edges and makes everything shout | Flat colour, no glow anywhere |
| Cyan, violet, neon green and hot pink all at once | Too many saturated hues, so nothing stands out | Neutral greys plus one blue accent; green, red and amber only for data |
| Three typefaces, including a sci-fi display face, wide-tracked capitals and diamond glyphs | Mixed voices and costume lettering | Inter only, sentence case, normal tracking |
| A speedometer gauge for market mood | Skeuomorphic, hard to read precisely, hides the parts | A bar per index around a zero line, with the average as the headline |
| Highlight pills inside the brief, solid coloured flags | Heavy marks inside text | Semibold numbers, coloured only when signed |
| Big radii and pill shapes everywhere | Toy-like | 10px cards, 6-7px controls |

## Rules

1. **Colour means something.** Green is up, red is down, amber is caution or delayed, blue is the brand and "new". Everything else is grey. A sparkline stays grey until the move is big for that market.
2. **Quiet by default, loud only for what matters.** A big move gets a tinted border, a tinted change chip and a "Large move" tag. Normal moves are just coloured text.
3. **Hairlines, not boxes.** Rows are separated by 1px lines at 7% white. Cards have one border and no shadow.
4. **One typeface.** Inter 400/500/600. Prices and table columns use tabular figures so they don't jitter.
5. **Thin marks.** Bars are 8px with a 4px rounded data end and a square base; lines are 1.5px; meters are 4px. Status colours always come with a word ("Very nervous", "Live").
6. **No ornament, little motion.** A short fade-in on load and a brief colour flash when a price changes. No looping animations.

## Tokens (dashboard/style.css)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0b0c0e` | Page |
| `--surface` / `-2` / `-3` | `#121316` / `#17191d` / `#1e2125` | Cards, table heads and hovers, badges |
| `--border` / `-2` | 7% / 12% white | Hairlines / controls |
| `--text` / `-2` / `-3` | `#ececee` / `#a0a3ab` / `#7a7f89` | Primary, secondary, muted |
| `--accent` | `#4f8cff` | Brand mark, primary button, focus ring, "New" |
| `--up` / `--down` / `--warn` | `#34b27b` / `#ef5b5b` / `#d9a23c` | Data only |

The app icons (`dashboard/icons/*`, `app/jarvis.ico`) use the same blue mark as the top bar.
