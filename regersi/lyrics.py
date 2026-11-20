import re
from pathlib import Path


def read_lyrics(path):
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or re.fullmatch(r"\[[^\]]*\]", s):
            continue
        lines.append(s)
    return lines


def map_words_to_lines(words, lyrics):
    out, k = [], 0
    for line in lyrics:
        n = len(line.split())
        chunk = words[k:k + n]
        k += n
        out.append((chunk[0][0], chunk[-1][1], line))
    return out
