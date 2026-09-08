"""Word counts over plain text."""

import re

WORD = re.compile(r"[a-z]+")


def count_words(text):
    """Return a dict of lowercase word -> occurrences.

    Words are runs of ASCII letters; digits and punctuation separate them.
    """
    counts = {}
    for word in WORD.findall(text.lower()):
        counts[word] = counts.get(word, 0) + 1
    return counts


def top_words(text, n):
    """Return the ``n`` most frequent words as (word, count) pairs.

    Most frequent first; ties are broken alphabetically.
    """
    counts = count_words(text)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:max(n, 0)]
