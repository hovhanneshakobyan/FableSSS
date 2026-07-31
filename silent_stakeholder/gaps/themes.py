"""S3 — candidate discovery. Where the hypotheses come from.

Two moves, in this order, and the order is the whole argument:

  1. KEYNESS over the latent pool.  Terms that are over-represented in reviews
     carrying a latent signal (signals.py) versus the rest of the corpus. This
     is NOT a frequency ranking -- "email", "app" and "phone" are the most
     frequent words in the corpus and score near zero here, because they are
     equally frequent everywhere. What survives is vocabulary specific to users
     who worked around, downgraded, or priced a problem.

  2. SEMANTIC BRIDGE into the backlog.  For each candidate we take the user's
     own phrasing, embed it, and ask Qdrant which ISSUES sit nearest. The
     distinctive terms of those issues are the developer vocabulary for the
     same defect -- "battery drain" -> "doze", "wakelock", "jobscheduler".
     Qdrant is used strictly to PROPOSE those terms. It never contributes a
     number: every proposed term is then counted with a word-boundary regex in
     measure.py, and a term that does not survive counting is dropped.

That split is the design. Vectors cross the vocabulary gap, which is the only
thing they are trustworthy for here; keywords do the arithmetic, which is the
only thing a judge can replay by hand.

Statistics: log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi
& Quinn 2008). Plain log-odds and raw tf-idf both put rare typos at the top of a
1,560-document corpus; the prior shrinks a term toward the corpus rate in
proportion to how little evidence it has, and the z-score is comparable across
terms of wildly different frequency. numpy only -- sklearn is in requirements
but is NOT installed in .venv, and a demo is a bad time to find that out.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from gaps.signals import annotated

# Closed-class words plus the corpus's own furniture. "email", "mail", "app",
# "k9" and "k-9" are in here on purpose: in a mail-app review corpus they are
# constants, and a constant cannot distinguish anything.
STOP = set("""
a about above after again against all am an and any are aren't as at be because
been before being below between both but by can cannot could couldn't did didn't
do does doesn't doing don't down during each few for from further had hadn't has
hasn't have haven't having he he'd he'll he's her here here's hers herself him
himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself
let's me more most mustn't my myself no nor not of off on once only or other
ought our ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves then
there there's these they they'd they'll they're they've this those through to too
under until up very was wasn't we we'd we'll we're we've were weren't what what's
when when's where where's which while who who's whom why why's with won't would
wouldn't you you'd you'll you're you've your yours yourself yourselves
app apps email emails mail k9 k-9 android phone use used using user users get
gets got one also even still much many make makes made need needs way ways thing
things time times just like really very good great best love nice awesome
excellent perfect bad worst star stars rating review reviews please thanks thank
work works working doesn does don isn didn ive im its dont cant wont
""".split())

# ------------------------------------------------------------ genre confound
# Reviews are evaluative prose; issue reports are technical prose. So EVERY
# word of judgement is "user-led" against the backlog by construction -- the
# first polarity run returned reliable (34 vs 0), loved (19.8x), powerful,
# brilliant, customizable, useless. All true, none a gap: developers do not
# write "brilliant" in a bug report about any feature whatsoever.
#
# Masking evaluative vocabulary is how the polarity route is held to product
# concepts. It is the same move as MASK below -- control the confound you can
# name, and say out loud that you controlled it.
GENRE = set("""
reliable loved powerful customizable functional brilliant fantastic amazing
superb solid decent poor useless terrible horrible awful garbage junk buggy
clunky ugly beautiful clean simple easy hard difficult intuitive confusing
fast slow quick sluggish smooth stable unstable annoying frustrating painful
happy sad angry disappointed satisfied pleased impressed highly truly totally
absolutely completely definitely honestly personally basically actually simply
recommend recommended favorite favourite prefer preferred worth worthless
free cheap expensive paid premium pro lite version versions client clients
program programs software tool tools product products service services
job jobs stuff bit lot lots plenty bunch kind sort type types
never always sometimes often rarely usually frequently constantly occasionally
now today yesterday recently lately currently finally already almost nearly
""".split())

# Meta-discourse: words ABOUT the product and its process, rather than any
# capability of it. "bugs", "features", "updates", "developers", "fixed" are
# what a review says when it is talking about software development itself, and
# they are user-led against the backlog for the same genre reason as GENRE --
# developers write the thing, users write about the thing. Left in, the first
# full run surfaced "may" at 55% confidence and "far" at 30%, which is the
# engine describing English rather than K-9 Mail.
META = set("""
bug bugs bugfix glitch glitches issue issues problem problems error errors
fix fixes fixed fixing broken breaks update updates updated updating upgrade
upgrades version versions release releases patch patches build builds
developer developers dev devs team support feature features functionality
option options setting settings menu button buttons
may might must shall should could would will can far near goes going gone
come comes came take takes taken give gives given put puts keep keeps kept
add adds added change changes changed changing new old latest previous
look looks looking seem seems seemed quite pretty rather fairly bit little
day days week weeks month months year years hour hours minute minutes
soon later early late long short big small large tiny huge full empty
""".split())

# Issue-side boilerplate: K-9's bug template and the plain verbs a bug report is
# written with. These pass every statistical test for "developer vocabulary" --
# rare in reviews, common in issues, specific enough to dodge the 5% furniture
# cap -- while meaning nothing. Left in, the sync gap proposed "turn", "notice",
# "pull" and "appears" as the backlog's framing, which then matched 165 issues
# including "Add easy way to record debug log" and put it in the evidence trace
# for a sync finding. A wrong citation is worse than a missing one.
TEMPLATE = set("""
expected actual behavior behaviour steps reproduce reproduction reproducible
describe description detail details information info please provide attach
happens happened happening occurs occurred occur tell tells told notice
noticed notices appears appear appeared seen see shown shows showing display
displays displayed turn turns turned pull pulls pulled push pushes pushed
open opens opened close closes closed click clicks clicked tap taps tapped
select selects selected press pressed enter entered start starts started
stop stops stopped run runs running try tries tried check checks checked
log logs logging debug trace stack dump output result results
screenshot screenshots image images picture attached following below above
environment device model os sdk api level build number commit branch
""".split())

TOKEN = re.compile(r"[a-z][a-z'\-]+")

# Issue bodies are markdown: screenshot links, stack traces, fenced code. Left
# in, the mechanism proposer returned "cloud githubusercontent", "com assets"
# and "www" as K-9's developer vocabulary for a UI complaint -- it had found
# the image host of the pasted screenshots. Strip the machinery before reading
# anyone's vocabulary out of it.
NOISE = re.compile(r"https?://\S+|www\.\S+|```.*?```|`[^`]*`|"
                   r"!\[[^\]]*\]\([^)]*\)|<[^>]{1,80}>|\b[0-9a-f]{7,40}\b",
                   re.S)


def clean(text: str) -> str:
    return NOISE.sub(" ", text or "")


# ---------------------------------------------------------------- circularity
# The latent pool is DEFINED by the signals.py regexes, so keyness over it
# rediscovers those regexes: the first run returned "longer", "last update",
# "however", "wish", "instead", "stopped" -- every one of them a trigger phrase,
# not a topic. That is a tautology dressed as a finding, and it is the first
# thing an adversarial judge should attack.
#
# So every literal word appearing in any family pattern is masked out. The mask
# is derived FROM the patterns, not hand-written, so editing a regex updates it
# automatically and the tautology cannot creep back in.
#
# This deliberately costs us the competitor names (F5 is literally a list of
# them). A theme must be able to describe itself without leaning on the phrase
# that recruited its reviews -- if "gmail" only ever appears as an F5 trigger,
# it is our definition talking, not the corpus.
def _mask_from_patterns() -> set[str]:
    from gaps import signals

    words: set[str] = set()
    for src in signals.PATTERNS.values():
        words.update(TOKEN.findall(re.sub(r"\\[a-zA-Z]|\{[\d,]+\}", " ", src).lower()))
    return words


MASK = _mask_from_patterns()

# A term seen in fewer than this many reviews cannot carry a gap: the evidence
# trace would be too thin to defend, whatever its z-score.
MIN_DF = 8

# Dirichlet prior strength. Higher shrinks rare terms harder toward the corpus
# rate. 500 was chosen by inspection: below ~200 single-review typos re-enter
# the top 40, above ~1500 real low-frequency signals ("doze", "widget") sink.
PRIOR = 500.0


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(clean(text).lower())
            if t not in STOP and t not in MASK and t not in GENRE
            and t not in META and t not in TEMPLATE and len(t) > 2]


def terms(text: str) -> set[str]:
    """Unigrams + bigrams, as a SET -- document frequency, not term frequency.

    Per-document presence, so one ranting review that says "sync" nine times
    counts once. Repetition is a property of the reviewer, not of the need.
    """
    toks = tokens(text)
    return set(toks) | {f"{a} {b}" for a, b in zip(toks, toks[1:])}


def _df(rows: list[dict]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        c.update(terms(r["text"]))
    return c


def keyness(pool: list[dict], background: list[dict],
            min_df: int = MIN_DF, prior: float = PRIOR) -> list[tuple[str, float, int]]:
    """[(term, z, df_in_pool)] — most over-represented in `pool` first.

    z is a standardised log-odds difference: how surprising this term's rate in
    the pool is, given how much evidence there is for it overall.
    """
    fg, bg = _df(pool), _df(background)
    total = fg + bg
    n_all = sum(total.values())
    n_fg, n_bg = sum(fg.values()), sum(bg.values())

    out = []
    for term, tot in total.items():
        if fg[term] < min_df:
            continue
        # alpha: this term's share of the whole corpus, scaled by PRIOR.
        a = prior * tot / n_all
        y_f, y_b = fg[term] + a, bg[term] + a
        delta = (math.log(y_f) - math.log(n_fg + prior - y_f)) - \
                (math.log(y_b) - math.log(n_bg + prior - y_b))
        z = delta / math.sqrt(1.0 / y_f + 1.0 / y_b)
        out.append((term, round(z, 3), fg[term]))
    return sorted(out, key=lambda t: -t[1])


def _subsumed(term: str, kept: list[str]) -> bool:
    """Drop "sync" once "syncing disabled" is in -- and the reverse.

    Overlapping seeds produce near-duplicate candidates, which look like four
    findings but are one. Substring containment either direction is enough.
    """
    return any(term in k or k in term for k in kept)


@lru_cache(maxsize=1)
def latent_split() -> tuple[tuple, tuple]:
    """(latent pool, everything else). Cached: keyness is called repeatedly."""
    rows = annotated()
    return (tuple(r for r in rows if r["lam"] > 0),
            tuple(r for r in rows if r["lam"] == 0))


def seeds(n: int = 24, min_z: float = 1.5) -> list[dict]:
    """ROUTE A — quiet needs. User-vocabulary starting points by keyness.

    Deduplicated by substring so "sync" and "syncing disabled" cannot both
    become candidates and inflate the finding count.
    """
    pool, rest = latent_split()
    kept: list[str] = []
    out = []
    for term, z, df in keyness(list(pool), list(rest)):
        if z < min_z or _subsumed(term, kept):
            continue
        kept.append(term)
        out.append({"term": term, "z": z, "df_latent": df, "route": "latent"})
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------- route B
# Keyness alone systematically misses the loudest gap in this corpus. Battery
# complaints are 1-star rants, not workarounds or conditional praise, so they
# never enter the latent pool -- yet "battery" is 1.95x user-led against the
# backlog, which is the single strongest misframing signal we have.
#
# A latent need therefore has two distinct shapes, and one generator cannot see
# both:
#   A quiet     -- present but never escalated  (keyness over the latent pool)
#   B misframed -- loudly escalated, filed under a name users never say
# Both routes feed the SAME measurement and scoring path in measure.py, so a
# candidate's route affects only how it was found, never how it scored.
REVIEWS_N, ISSUES_N = 1560, 1718


@lru_cache(maxsize=1)
def _issue_df() -> Counter:
    from kb import documents as docs
    c: Counter = Counter()
    for d in docs.load("k9_issues"):
        p = d["payload"]
        c.update(terms(f"{p['title']} {p['body']}"))
    return c


def polarity_seeds(n: int = 24, min_df: int = 15,
                   min_ratio: float = 1.3) -> list[dict]:
    """ROUTE B — misframed needs. Terms users say far more than the backlog.

    Rates are per 1,000 documents so the 1,560-review and 1,718-issue corpora
    compare. These counts PROPOSE only; measure.py recounts every survivor with
    kb.lexical, whose word-boundary regex is the number that reaches a slide.
    """
    rev = _df([{"text": r["text"]} for r in annotated()])
    iss = _issue_df()

    scored = []
    for term, df in rev.items():
        if df < min_df:
            continue
        r_rate = PER * df / REVIEWS_N
        i_rate = PER * iss[term] / ISSUES_N
        ratio = r_rate / i_rate if i_rate else float("inf")
        if ratio < min_ratio:
            continue
        # Rank by loudness x evidence: a 10x ratio on 15 reviews should not
        # outrank a 2x ratio on 200. Unmatched terms (inf) sort on df alone.
        strength = (min(ratio, 12.0)) * math.log1p(df)
        scored.append({"term": term, "df_reviews": df, "df_issues": iss[term],
                       "ratio_user_over_dev": round(ratio, 2) if i_rate else None,
                       "strength": round(strength, 2), "route": "polarity"})

    kept: list[str] = []
    out = []
    for c in sorted(scored, key=lambda c: -c["strength"]):
        if _subsumed(c["term"], kept):
            continue
        kept.append(c["term"])
        out.append(c)
        if len(out) >= n:
            break
    return out


PER = 1000
