"""Recover search text typed with the wrong keyboard layout, e.g. "djlf" -> "вода"
(same physical keys, Russian layout was off). Maps by key position, not sound."""

RU_TO_EN = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u", "ш": "i",
    "щ": "o", "з": "p", "х": "[", "ъ": "]",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j", "л": "k",
    "д": "l", "ж": ";", "э": "'",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m", "б": ",",
    "ю": ".", "ё": "`",
}
EN_TO_RU = {en: ru for ru, en in RU_TO_EN.items()}


def layout_variants(text: str) -> list[str]:
    """The text as typed, plus its reinterpretation on the other keyboard layout
    in both directions, so search matches regardless of which layout was active."""
    lowered = text.lower()
    variants = {
        lowered,
        "".join(EN_TO_RU.get(ch, ch) for ch in lowered),  # typed EN, meant RU
        "".join(RU_TO_EN.get(ch, ch) for ch in lowered),  # typed RU, meant EN
    }
    return [v for v in variants if v]
