import re

# Ukrainian + Russian Cyrillic -> Latin (simplified, for comparison only, not for display)
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ъ": "", "ы": "y", "э": "e", "ю": "iu", "я": "ia",
}
# English spellings -> the same sound classes the transliteration produces ("Boombox" ~ "БумБокс")
_SOUND_RULES = [
    ("ck", "k"), ("ph", "f"), ("oo", "u"), ("ee", "i"), ("x", "ks"), ("w", "v"), ("q", "k"),
    ("c", "k"), ("y", "i"), ("j", "i"), ("kh", "h"),
]
_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
_REPEATS = re.compile(r"(.)\1+")


def phonetic_key(text: str) -> str:
    """Script-independent comparison key: 'Тартак' and 'Tartak' give the same key."""
    out = "".join(_CYRILLIC.get(ch, ch) for ch in text.casefold())
    out = _SPACES.sub(" ", _PUNCT.sub(" ", out)).strip()
    for src, dst in _SOUND_RULES:
        out = out.replace(src, dst)
    return _REPEATS.sub(r"\1", out)
