"""When each word of a sentence is spoken, so the extension can follow along word by word.

The voice model reports when every phoneme is spoken (model-files-v1.1 and later). Phonemes
come back with the spaces between words kept, so grouping them gives one time span per spoken
word. What was spoken is not quite what the page shows, though: "$5m" is spoken as "five
million dollars", and pronounce.json may respell a name. So spoken words are matched back to
the words of the original sentence, and a page word that became several spoken ones (or the
reverse) gets the span of all of them.
"""
import difflib
import re

# Marks the tokenizer keeps as phonemes; they belong to no word.
PUNCT = set(';:,.!?¡¿—…"«»“”()')
PAGE_WORD = re.compile(r"[^\s—–]+")


def spoken_words(timings):
    """[(start, end), ...] seconds per spoken word, from per-phoneme timings."""
    words, cur = [], None
    for t in timings:
        if t.phoneme == " ":
            if cur:
                words.append(cur)
            cur = None
        elif t.phoneme in PUNCT:
            continue
        elif cur is None:
            cur = [t.start, t.end]
        else:
            cur[1] = t.end
    if cur:
        words.append(cur)
    return [tuple(w) for w in words]


def _norm(word):
    return re.sub(r"[^\w]", "", word.lower())


def page_words(sentence):
    """[(start, end), ...] character spans of the words of a sentence, punctuation trimmed."""
    out = []
    for m in PAGE_WORD.finditer(sentence):
        a, b = m.start(), m.end()
        while a < b and not sentence[a].isalnum():
            a += 1
        while b > a and not sentence[b - 1].isalnum():
            b -= 1
        if a < b:
            out.append((a, b))
    return out


def align(sentence, spoken_text, times):
    """[[char_start, char_end, t_start, t_end], ...] for the words of `sentence`.

    `spoken_text` is what was synthesized (normalized, respelled), `times` the spoken_words()
    of its audio. They can disagree on the word count when the phonemizer joins or splits a
    word; then the times are spread over the text in proportion to word length, which keeps
    the highlight close rather than wrong.
    """
    spoken = spoken_text.split()
    if len(spoken) != len(times):
        times = _spread(times, spoken)
    if not spoken:
        return []
    pw = page_words(sentence)
    a = [_norm(sentence[s:e]) for s, e in pw]
    b = [_norm(w) for w in spoken]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                out.append([*pw[i1 + k], *times[j1 + k]])
        elif op == "replace":
            # "$5m" -> "five million dollars": the page words share the spoken span
            t0, t1 = times[j1][0], times[j2 - 1][1]
            n = i2 - i1
            for k in range(n):
                out.append([*pw[i1 + k], t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n])
        # "delete": page words never spoken (a citation mark); "insert": spoken, not shown
    return [[s, e, round(t0, 3), round(t1, 3)] for s, e, t0, t1 in out]


def _spread(times, spoken):
    """One span per spoken word when the phonemizer's word count differs from the text's."""
    if not times or not spoken:
        return []
    t0, t1 = times[0][0], times[-1][1]
    total = sum(len(w) for w in spoken) or 1
    out, at = [], t0
    for w in spoken:
        end = at + (t1 - t0) * len(w) / total
        out.append((at, end))
        at = end
    return out
