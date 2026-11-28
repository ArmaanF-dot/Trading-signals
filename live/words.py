"""Word lists and plain-English text cues for the live analyser.

The lists are copies of the ones used in the repo's earnings-call language study (edge/textchg.py and
edge/calls.py), kept here so the live tool runs without pandas or the rest of the research code.
tests/test_live.py fails if they drift apart.
"""
from __future__ import annotations

import re

NEG = set("""adverse adversely against allegation allegations breach claims closure closures concern concerns
curtail curtailed decline declined declines declining decrease decreased default deficiencies
deficiency delay delayed delays deteriorate deteriorated deterioration difficult difficulties
difficulty diminish dispute disputes disruption disruptions downturn fail failed failure failures
harm harmed impair impaired impairment inability ineffective inefficient insolvency investigation
lawsuit lawsuits layoffs loss losses negative negatively penalties problem problems recall restate
restated restatement restructuring severe shortage shortages shortfall slowdown suffer terminate
terminated termination threat unable unfavorable unfavourable volatile volatility weak weaker
weakness worsen worsened writedown writeoff""".split())

POS = set("""achieve achieved attain benefit benefits best better effective efficient enhance enhanced excellent
favorable favourable gain gains good greater growth improve improved improvement improvements
improving increase increased innovative leading opportunities opportunity outperform profitability
profitable record resilient robust solid strength strengthen strengthened strong stronger succeed
success successful successfully surpass""".split())

UNC = set("""approximately assume believe could depend depends doubt estimate estimates fluctuate fluctuations
indefinite may might possible possibly predict probable probably risk risks risky roughly uncertain
uncertainties uncertainty unclear unknown unpredictable unproved variability volatile""".split())

HEDGE = set("""appears approximately arguably around fairly generally hopefully largely likely maybe mostly
partially partly perhaps possibly potentially probably relatively roughly seem seems somewhat
suggest suggests unlikely""".split())

CERTAIN = set("""absolutely always certainly clearly committed confidence confident definitely ensure guarantee never
obviously undoubtedly""".split())

HEDGE_PHRASES = ('sort of', 'kind of', 'i think', 'i guess', 'i would say', 'i suppose', 'a little bit', 'to some extent', 'more or less', 'we believe', 'we hope', 'we expect to be able')
FILLER_WORDS = {'hmm', 'er', 'erm', 'uh', 'ah', 'um'}
FILLER_PHRASES = ('you know', 'i mean', 'you see', 'let me think', 'how do i say')

# Phrases that often start an answer which does not engage with the question. A cue, not a verdict:
# plenty of good answers begin "as we said" and plenty of evasive ones do not.
DEFLECT_PHRASES = (
    "as we've said", "as we have said", "as we've mentioned", "as i mentioned", "as we mentioned", "as i said",
    "we don't break out", "we do not break out", "we don't provide", "we do not provide", "we don't guide",
    "we're not going to", "we are not going to", "i'm not going to", "i am not going to", "not going to comment",
    "too early to say", "too early to tell", "it's too early", "we'll update you", "we will update you",
    "we'll come back to", "we will come back to", "take a step back", "let me step back", "i'll let", "i will let",
    "we'll have more to say", "we will have more to say", "stay tuned", "we'll see", "difficult to say",
    "hard to say", "hard to predict", "not something we",
)

STOPWORDS = set("""a an the and or but if of to in on for with at by from as is are was were be been being it its this that
these those we our us you your they their he she i my me do does did have has had not no so than then there here what which who
whom when where why how can could would should will shall may might just very more most some any about into over also""".split())

_WORD = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def text_stats(text: str) -> dict:
    """Counts of each cue class in a block of text, plus the word count."""
    low = text.lower()
    toks = tokens(low)
    return {
        "words": len(toks),
        "pos": sum(t in POS for t in toks),
        "neg": sum(t in NEG for t in toks),
        "unc": sum(t in UNC for t in toks),
        "hedge": sum(t in HEDGE for t in toks) + sum(low.count(p) for p in HEDGE_PHRASES),
        "certain": sum(t in CERTAIN for t in toks),
        "filler": sum(t in FILLER_WORDS for t in toks) + sum(low.count(p) for p in FILLER_PHRASES),
        "neg_words": sorted({t for t in toks if t in NEG}),
        "hedge_words": sorted({t for t in toks if t in HEDGE} | {p for p in HEDGE_PHRASES if p in low}),
    }


def deflection(question: str, answer: str) -> str | None:
    """A plain-English reason the answer may sidestep the question, or None."""
    low = answer.lower()
    ans_toks = tokens(low)
    if len(ans_toks) < 8:
        return None
    for p in DEFLECT_PHRASES:
        if p in low[:160]:
            return f'opens with "{p}"'
    q = {t for t in tokens(question) if t not in STOPWORDS and len(t) > 3}
    if len(q) >= 4 and len(ans_toks) >= 40:
        overlap = len(q & set(ans_toks)) / len(q)
        if overlap < 0.12:
            return "barely uses the words of the question"
    return None
