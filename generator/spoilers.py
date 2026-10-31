"""Poistka proti spoilerom: zakázané kľúče, vzory v texte a filter viet v injury poznámkach."""
import re

FORBIDDEN_KEYS = {
    "score", "scores", "linescore", "linescores", "winner", "winners", "loser",
    "record", "records", "standings", "rank", "leaders", "leader", "statistics", "stats",
    "points", "rebounds", "assists", "minutes", "plusminus", "totals",
    "odds", "pickcenter", "winprobability", "againstthespread", "spread", "overunder",
    "headline", "headlines", "highlights", "article", "news", "recap", "videos",
    "plays", "boxscore", "seasonseries", "period", "periods", "overtime", "clock",
    "displayclock", "attendance", "result", "ejected", "detail_status", "shortdetail",
    "longcomment", "shortcomment",
}

# Skóre typu 112-108 / 98–101 (obe čísla v rozsahu bežného NBA skóre).
_SCORE_RE = re.compile(r"(?<![\d.\-–])(\d{2,3})\s?[-–:]\s?(\d{2,3})(?![\d\-–])")
_PATTERNS = [
    re.compile(r"\b[1-9]?OT\b"),
    re.compile(r"overtime|predĺžen", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*(points?|pts|rebounds?|reb|assists?|ast|steals?|blocks?|bodov|bodmi|doskok\w*|asistenc\w*)\b", re.I),
    re.compile(r"\b(wins?|won|losses?|lost|victory|defeat(ed|s)?|beat|blowout|víťaz\w*|zvíťaz\w*|prehr\w*|výhr\w*)\b", re.I),
    re.compile(r"\b(double-double|triple-double|career-high|season-high|top performer)\b", re.I),
    re.compile(r"\(\d{1,2}-\d{1,2}\)"),  # bilancia (5-3)
    re.compile(r"Final/", re.I),
]


def text_violations(text):
    if not isinstance(text, str):
        return []
    found = []
    for m in _SCORE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if 60 <= a <= 200 and 60 <= b <= 200:
            found.append(m.group(0))
    for p in _PATTERNS:
        m = p.search(text)
        if m:
            found.append(m.group(0))
    return found


def find_violations(obj, path="$"):
    """Rekurzívne prejde výstup a vráti zoznam porušení (kľúč alebo text)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower().replace("_", "") in FORBIDDEN_KEYS:
                out.append(f"{path}.{k}: zakázaný kľúč")
            out.extend(find_violations(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(find_violations(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        for hit in text_violations(obj):
            out.append(f"{path}: spoilerový text '{hit}'")
    return out


class SpoilerError(Exception):
    pass


def assert_clean(obj, label="output"):
    v = find_violations(obj)
    if v:
        raise SpoilerError(f"{label}: " + "; ".join(v[:10]))


# --- filter viet v anglických injury poznámkach (vstup pre zhrnutie) ---
_GAME_SENTENCE = re.compile(
    r"quarter|half\b|halftime|overtime|\bOT\b|\bwin\b|\bwins\b|\bwon\b|\bloss\b|\blost\b|victory|defeat|"
    r"scor|points|rebound|assist|steal|block|averag|shooting|percent|\bFG\b|3-pointer|"
    r"minutes|left the game|exited|career-high|season-high|double-double|triple-double|"
    r"\d+-\d+\b|fantasy|stash|usage|appearances|start(ed|ing)? (lineup|five)|"
    r"tonight|last night|in the (first|second|third|fourth)\b",
    re.I,
)


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", text or "") if s.strip()]


def filter_injury_text(text):
    """Zahodí vety, ktoré popisujú priebeh zápasu, štatistiky alebo výsledky."""
    return " ".join(s for s in split_sentences(text) if not _GAME_SENTENCE.search(s))
