# Earnings-call audio collector: feasibility (28 Nov 2026)

## Can we fetch company IR webcasts directly?
No, not in a way that scales. Calls are hosted by several vendors, each with its own player:
`edge.media-server.com` (Notified/Choruscall) has `Disallow: /` for every crawler; `investor.apple.com`
answers 403 to a script; Q4 and ON24 players need event registration or stream via protected manifests.
That is one custom scraper per vendor, at least some of which the site rules forbid. Not done.

## What works instead
Castify (`casti.fyi`) publishes a public podcast RSS feed per company with the call recording as an MP3
(about 500 US large caps, 4 to 8 quarters each, about 2,450 calls in total; new calls appear in the feed
on the day). `robots.txt` allows crawling (it only blocks `GPTBot`). Audio is 48 kHz stereo, around 70 MB
for a 50-minute call. Caveat: Castify is a rehost of the company recording, so its rights to it are not
ours to check. We stream each file to a temp folder, extract numbers and delete it. The public repo holds
only derived features, never audio or a transcript.

## Actions limits
A 50-minute call: download plus decode about 15 s, analysis about 12 s, 1 GB RAM is enough. 4.5 hours of
a daily run is therefore around 300 calls. Peak earnings days bring 40 to 150 calls from this catalogue.
Repo storage: summaries and per-turn features are about 3 KB gzip per call; 5-minute bars about 7 KB
per call. Less than 30 MB a year.

## What is recorded (`data/voice/`)
* `calls.csv`: per call, features for executives' prepared remarks, executives in Q&A, analysts, and the
  shift between them. Pitch (semitones), pitch spread, speaking rate (syllable nuclei per second),
  pauses and long pauses per minute, pause length, flat voiced stretches (a proxy for "um"/"uh"), answer latency.
* `turns/YYYY-MM.csv.gz`: the same per speaker turn.
* `bars/YYYY-MM.csv.gz`: 5-minute bars incl. pre and post market from the day before the call to two days
  after, from Yahoo (only the last 60 days exist, so older backfilled calls get daily returns only).
* Daily and later returns are not stored: they are joined from price history at test time.

## Limits to keep in mind
* Speaker separation is crude (MFCC clustering, no neural diariser, no names). It separates operator,
  executives and analysts well enough for role-level features, not individual executives.
* Call start time is not in the audio and the free Nasdaq calendar mostly says "time not supplied".
  The intraday test will have to infer timing from the bars (first big volume bar after the release).
* No labelled stress or deception truth exists; the test is purely whether features predict returns.

## When a test is meaningful
Backfill of about 2,450 past calls should finish in about 8 daily runs. After that, a daily-return
test on roughly 2,000 calls (2025 to 2026, one regime, so treat as in-sample for one year) is possible
in the first week of December. The intraday test only has bars from 28 Nov onwards plus the prior 60
days, so about 300 calls by early December, and needs the February 2027 season for a proper sample
(about 400 calls with bars from that season alone).
