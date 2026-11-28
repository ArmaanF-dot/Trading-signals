"""A synthetic call for trying the tool without audio set-up (and for the tests).

The voices are generated tones shaped to sound different from one another, and the words are scripted.
There is no real speech, so the transcript is scripted too: the demo only shows how the view and the
cues behave, not how good the transcription is on your PC.
"""
from __future__ import annotations

import numpy as np

SR = 16000

VOICES = {
    "operator": {"f0": 205, "formants": (800, 1500, 3000)},
    "ceo": {"f0": 112, "formants": (600, 1200, 2500)},
    "cfo": {"f0": 140, "formants": (450, 1800, 2700)},
    "analyst1": {"f0": 175, "formants": (350, 2200, 3100)},
    "analyst2": {"f0": 120, "formants": (700, 1000, 2000)},
}


def synth(voice: str, text: str, syl_hz: float = 4.5, f0_shift: float = 0.0, sec_per_word: float = 0.38,
          rng: np.random.Generator | None = None) -> np.ndarray:
    """A phrase of 'speech': harmonics shaped by three formants, vibrato, syllable-rate amplitude pulses."""
    rng = rng or np.random.default_rng(0)
    v = VOICES[voice]
    dur = max(1.2, len(text.split()) * sec_per_word)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = (v["f0"] + 0.0) * 2 ** (f0_shift / 12) * (1 + 0.04 * np.sin(2 * np.pi * 0.7 * t) + 0.015 * np.sin(2 * np.pi * 5 * t))
    phase = 2 * np.pi * np.cumsum(f0) / SR
    x = np.zeros(n)
    for k in range(1, 28):
        fk = k * v["f0"] * 2 ** (f0_shift / 12)
        if fk > 4200:
            break
        amp = 0.04 / k + sum(np.exp(-((fk - F) / 220.0) ** 2) for F in v["formants"])
        x += amp * np.sin(k * phase)
    env = 0.55 + 0.45 * np.sin(np.pi * syl_hz * t) ** 2
    x = x * env
    x = 0.25 * x / (np.abs(x).max() + 1e-9)
    x += rng.normal(0, 4e-4, n)
    return x.astype(np.float32)


# (voice, text, gap before in seconds, options)
def script() -> list[tuple[str, str, float, dict]]:
    s: list[tuple[str, str, float, dict]] = []
    add = lambda v, t, g=1.0, **o: s.append((v, t, g, o))
    add("operator", "Good afternoon and welcome to the Example Corp fourth quarter earnings call.", 2.0)
    add("operator", "All participants are in listen only mode until the question and answer session.", 1.0)
    prepared_ceo = [
        "Thank you operator and good afternoon everyone, we had a strong quarter with record revenue and solid growth.",
        "Our flagship products performed better than expected and margins improved for the third quarter in a row.",
        "We are very confident in the strength of our pipeline and the quality of our customer relationships.",
        "Operating efficiency improved again as we executed on our cost programme and we achieved our targets.",
        "Demand was robust across every region and our leading position in the core market was strengthened.",
        "Cash generation was excellent, we increased the dividend and we continued to invest in innovative new products.",
        "Our teams delivered successful launches and we remain committed to profitable growth for shareholders.",
        "The strength of the balance sheet gives us real flexibility and we will keep investing in the business.",
        "Customer retention improved, enterprise bookings were strong and our partners are growing with us.",
        "We believe these results show the benefit of our strategy and the improvements we have made to the business.",
        "Finally I want to thank our employees who delivered another solid and successful year for the company.",
        "With that I will hand over to our finance chief who will take you through the numbers in more detail.",
    ]
    for t in prepared_ceo:
        add("ceo", t, 1.2)
    cfo = [
        "Thanks everyone, revenue grew twelve percent in the quarter with strong contribution from services.",
        "Gross margin was in line with our plan and operating income increased on better cost discipline.",
        "We ended the year with a solid cash position and we expect continued growth next year.",
        "Our guidance for the first quarter reflects our current visibility and the pipeline we see today.",
        "I will now hand back to the operator for questions from our analysts on the line today.",
    ]
    for t in cfo:
        add("cfo", t, 1.3)
    add("operator", "We will now begin the question and answer session. Our first question comes from the line of the first analyst.", 1.5)
    add("analyst1", "Thanks for taking my question, can you talk about gross margin pressure from pricing next year and whether "
                    "the improvement in margins is sustainable given the competitive pricing environment you face now.", 1.4)
    add("ceo", "Well, perhaps, I think margins are somewhat sort of stable and we probably see roughly similar trends,", 1.4, syl_hz=3.2)
    add("ceo", "although it is difficult to say and it is too early to say how pricing will really develop.", 1.8, syl_hz=3.2)
    add("ceo", "We believe the long term outlook is fine and we remain committed to our targets over time.", 1.0, syl_hz=3.2)
    add("operator", "Our next question comes from the line of the second analyst.", 2.0)
    add("analyst2", "Hi, could you explain the decline in your European orders and the weakness in the services business "
                    "and whether the inventory problems you mentioned last quarter are now resolved for the customer base.", 1.2)
    add("ceo", "We did see some difficult conditions, the decline in orders was a concern and the inventory problems "
               "caused delays, losses and some weakness although we believe it is probably somewhat temporary.", 4.6,
        syl_hz=3.6, f0_shift=2.5)
    add("ceo", "The weakness in Europe was larger than we planned and the shortfall in services hurt the quarter.", 1.0,
        syl_hz=3.6, f0_shift=2.5)
    add("ceo", "We are working through the problems and we expect the recovery to take some time from here.", 1.0,
        syl_hz=3.6, f0_shift=2.5)
    return s


def build() -> tuple[np.ndarray, list[str]]:
    """The whole synthetic call as audio plus the matching list of transcript lines."""
    rng = np.random.default_rng(1)
    parts, lines = [], []
    for voice, text, gap, opts in script():
        parts.append(rng.normal(0, 4e-4, int(gap * SR)).astype(np.float32))
        parts.append(synth(voice, text, rng=rng, **opts))
        lines.append(text)
    parts.append(rng.normal(0, 4e-4, 2 * SR).astype(np.float32))
    return np.concatenate(parts), lines
