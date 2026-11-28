# Live call analyser

Plays alongside a live earnings call (or any webcast) on your Windows PC, writes a running transcript,
and flags cues in plain English: hedging, negative wording, long pauses, slow or evasive answers, and
changes in how someone sounds against their own norm. Free, local, no accounts, no keys.

> **Read this first.** The cues are *colour*, not a validated trade signal. This repo's studies found no
> return edge from earnings-call wording (`reports/calls_study.md`), and the audio test is still
> collecting data (`reports/voice_feasibility.md`). Use it to follow a call more closely, not to trade
> off a flag. The tool says this in the view and in every summary.

## Install and run (Windows)

1. Install **Python 3.12 (64-bit)** from python.org if you do not have 3.11 or 3.12. Tick "Add to PATH".
2. Get this repo (`git clone https://github.com/ArmaanF-dot/trading-signals` or Download ZIP).
3. In the repo folder, double-click `live\run_live.bat`, or in a terminal:

   ```
   live\run_live.bat
   ```

   The first run makes a private environment, installs the packages in `live\requirements.txt` and
   downloads the speech model (`small.en`, about 0.5 GB, once). Later runs start straight away.
   Prefer to manage Python yourself? `pip install -r live\requirements.txt` then `python -m live`.

4. A browser tab opens at `http://127.0.0.1:8765/`. Play the call in another tab or window (company
   webcast, YouTube, anything with sound through your **default speakers or headphones**). The tool
   listens to what the PC is playing (WASAPI loopback), so it needs no access to the company or the
   player. Press **Ctrl+C** in the terminal when the call ends: it prints the final call summary and
   saves it, with the transcript, to `live_runs\` (local only, git-ignored).

Try it without any set-up first: `python -m live --demo` replays a synthetic call (generated voices,
scripted words) so you can see the view and the cues. To test on a recording:
`python -m live --file call.wav` (wav needs nothing extra; mp3 and others need ffmpeg on PATH).

## What you see

* **Cues now**: each flag with its time. Amber is "watch", red is "worth a look", grey is background.
* **Last three minutes**: management against their own call average (speed, hedging, tone, long pauses).
* **Prepared remarks against Q&A**: the shift in speaking rate, pitch, pitch variation, pauses, hedging
  and word tone once Q&A has started.
* **Transcript** by voice, a speaking rate and pitch-spread chart, and the voices the tool has found.

## What it measures

From the raw audio, per phrase (a stretch of speech between pauses of 0.6 s or more) and per speaker turn,
reusing `edge/voice/features.py` from the earnings-call audio collector:

| Cue | How |
| --- | --- |
| Pitch and spread | Praat pitch track in semitones, so male and female voices compare as changes |
| Speaking rate | syllable nuclei per second of speech |
| Pauses, long pauses | gaps of 0.25 s+ inside a phrase and between phrases; 1 s+ counted as long, 1.5 s+ flagged |
| Answer latency | question ends to answer starts; 2.5 s+ "slowish", 4 s+ flagged |
| Deviation from baseline | a speaker's last three phrases against their own earlier phrases (needs 11+ phrases of theirs), flagged at about 2.5 standard errors and a minimum real-world size |
| Prepared against Q&A | management's two sections compared once both have enough speech |

From the transcript, using the word lists of the language study (`live/words.py`, checked against
`edge/textchg.py` and `edge/calls.py` by a test): hedging, negative language, uncertainty, filler words,
and a "possible sidestep" when an answer opens with a deflecting phrase ("too early to say", "we don't
break out") or barely uses the words of the question.

## Honest limits

* **Not a signal.** See the box at the top. A flag is a prompt to listen, not a reason to buy or sell.
* **Speaker separation is crude.** Voices are grouped by sound (online clustering), not identified by
  name; two similar-sounding executives can merge, one person on a bad line can split. Roles are guessed:
  management is whoever talks most before questions, the operator is the first voice, analysts join in Q&A.
* **Q&A start** is detected from operator phrases and new voices after 5 minutes. If it misses, the
  prepared-against-Q&A comparison stays empty.
* **Transcription is imperfect**, especially names, numbers and quiet speakers, and Whisper drops "um"
  and "uh", so filler counts are a minimum. If your CPU is slow the transcript lags (the view says by how
  much); try `--model base.en` or `tiny.en`. Audio is never dropped.
* **Cue thresholds are judgement calls**, set by hand and tested on synthetic audio, not tuned on real
  calls. Expect some noise.
* **Verified on a Linux build machine with synthetic audio only.** The Windows loopback capture and the
  Whisper model run only on a real PC; the tests cover everything else.
* Treat a recording of a public webcast as for your own use. The tool keeps no audio; transcripts and
  summaries stay in `live_runs\` and are git-ignored. Nothing is sent anywhere.

## Options

```
python -m live --model base.en        smaller, faster speech model (tiny.en, base.en, small.en, medium.en)
python -m live --list-devices         show loopback devices; --device N picks one if the default is wrong
python -m live --port 9000            another port for the view
python -m live --no-browser           do not open the browser
python -m live --speaker-threshold 1.4  higher = fewer distinct voices (merge more), lower = split more
python -m live --file call.wav --speed 0   analyse a recording as fast as possible
```

## Troubleshooting

* **Silence / nothing appears:** the call must play through the Windows *default output device*. Check
  with `--list-devices`; pick another with `--device N`.
* **"PyAudioWPatch" import error:** you are not on Windows or the install failed; use `--file` or `--demo`.
* **Transcript far behind:** use a smaller model.
* **Too many voices:** raise `--speaker-threshold`; **too few:** lower it.

## Tests

`pytest tests/test_live.py` runs offline: a synthetic call with five generated voices and scripted words
goes through the segmenter, audio features, speaker clustering, role and Q&A detection, every cue, the
summaries and the local web server.
