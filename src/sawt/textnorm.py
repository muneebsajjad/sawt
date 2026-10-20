"""Turn written forms into spoken ones before synthesis.

TTS reads "1847" as digits, "Ch. XIV" as letters, "$5m" as punctuation. A novel may contain
none of this; a history book is made of it. Applied before the pronunciation dictionary, so a
hand-written override always wins.
"""
import re

from num2words import num2words

CURRENCY = {"$": ("dollar", "dollars"), "£": ("pound", "pounds"),
            "€": ("euro", "euros"), "¥": ("yen", "yen")}
SCALE = {"k": "thousand", "m": "million", "bn": "billion", "b": "billion", "tr": "trillion"}

ABBREV = {
    r"\bMr\.": "Mister", r"\bMrs\.": "Missus", r"\bMs\.": "Miz", r"\bDr\.": "Doctor",
    r"\bProf\.": "Professor", r"\bSt\.": "Saint", r"\bMt\.": "Mount",
    r"\bvs\.?\b": "versus", r"\betc\.": "et cetera", r"\bi\.e\.": "that is",
    r"\be\.g\.": "for example", r"\bcf\.": "compare", r"\bca\.": "circa",
    r"\bvol\.": "volume", r"\bpp\.": "pages", r"\bp\.": "page", r"\bch\.": "chapter",
    r"\bfig\.": "figure", r"\bNo\.": "number", r"\bapprox\.": "approximately",
    r"\ba\.m\.": "A M", r"\bp\.m\.": "P M", r"\bB\.C\.": "B C", r"\bA\.D\.": "A D",
}

ROMAN_RE = re.compile(
    r'\b(?:Chapter|Part|Book|Section|Act|Scene|Volume)\s+'
    r'(M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))\b')
ROMAN_MAP = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        val = ROMAN_MAP.get(ch, 0)
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total


def _year(n):
    """1847 -> eighteen forty-seven; 2003 -> two thousand and three."""
    return num2words(n, to="year") if 1100 <= n <= 2099 else num2words(n)


def normalize(text):
    # abbreviations first — their periods otherwise look like sentence ends to the chunker
    for pat, rep in ABBREV.items():
        text = re.sub(pat, rep, text)

    text = ROMAN_RE.sub(
        lambda m: m.group(0)[:m.start(1) - m.start(0)] + num2words(roman_to_int(m.group(1))),
        text)

    # decades: 1920s -> nineteen twenties
    text = re.sub(r'\b(1[0-9]|20)([0-9])0s\b',
                  lambda m: num2words(int(m.group(1)), to="year").split("-")[0] + " "
                            + {"2": "twenties", "3": "thirties", "4": "forties", "5": "fifties",
                               "6": "sixties", "7": "seventies", "8": "eighties",
                               "9": "nineties", "0": "hundreds", "1": "tens"}[m.group(2)],
                  text)

    # currency with a scale suffix: $5m -> five million dollars
    def _cur(m):
        sym, num, scale = m.group(1), m.group(2).replace(",", ""), (m.group(3) or "").lower()
        value = float(num) if "." in num else int(num)
        words = num2words(value)
        unit = CURRENCY[sym][0 if value == 1 and not scale else 1]
        return f"{words} {SCALE[scale]} {unit}" if scale else f"{words} {unit}"

    # the scale suffix must attach to the number, so no whitespace is consumed before it —
    # otherwise "£3 and" loses the space and becomes "three poundsand"
    text = re.sub(rf'([{"".join(CURRENCY)}])\s?([\d,]+(?:\.\d+)?)(bn|tr|[kmb])?\b',
                  _cur, text, flags=re.I)

    text = re.sub(r'(\d+(?:\.\d+)?)\s?%',
                  lambda m: f"{num2words(float(m.group(1)) if '.' in m.group(1) else int(m.group(1)))} percent",
                  text)

    # numeric ranges: pp. 3-7 -> pages three to seven
    text = re.sub(r'(?<=\d)\s?[-\u2013]\s?(?=\d)', ' to ', text)

    # ordinals: 21st -> twenty-first
    text = re.sub(r'\b(\d+)(st|nd|rd|th)\b',
                  lambda m: num2words(int(m.group(1)), to="ordinal"), text)

    # years and plain numbers, commas stripped
    def _num(m):
        token = m.group(0)
        had_comma = "," in token
        raw = token.replace(",", "")
        if "." in raw:
            whole, _, frac = raw.partition(".")
            return (num2words(int(whole)) + " point "
                    + " ".join(num2words(int(d)) for d in frac))
        n = int(raw)
        # "1,250" is a quantity; only a bare four-digit number reads as a year
        return _year(n) if len(raw) == 4 and not had_comma else num2words(n)

    text = re.sub(r'\b\d[\d,]*(?:\.\d+)?\b', _num, text)
    return text


if __name__ == "__main__":
    samples = [
        "By 1847 he had spent $5m, roughly 12.5% of the estate.",
        "See Chapter XIV, pp. 3-7, i.e. the part Mr. Hyde wrote.",
        "The 1920s ended on her 21st birthday, ca. 1,250 miles away.",
        "Dr. Samsa paid £3 and waited until 9 a.m.",
    ]
    for s in samples:
        print(f"  {s}\n-> {normalize(s)}\n")
