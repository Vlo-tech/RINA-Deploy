
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

SHENG_KEYWORDS = [
    "poa", "sasa", "msee", "hao", "niko", "rada", "mbona", "nani", "chill", "flani",
    "ngoja", "buda", "sijui", "fanya", "piga", "genje","keja","single","Bed moja","mtaa","mraazi","bonga","wazi","stage","tulia","hama","kuinama","westi","kanairo","kasa","tao","bukla","punch","mat","caretaker"
]


def detect_language(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "other"
    low = t.lower()
    # cheap Sheng heuristics
    for kw in SHENG_KEYWORDS:
        if kw in low.split():
            return "sheng"
    try:
        lang = detect(t)
        if lang == "sw":
            return "sw"
        if lang.startswith("en"):
            return "en"
        return lang
    except Exception:
        return "other"