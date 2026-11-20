from xml.sax.saxutils import escape

TTML_HEAD = (
    '<tt xmlns:ttm="http://www.w3.org/ns/ttml#metadata" '
    'xmlns:tts="http://www.w3.org/ns/ttml#styling" '
    'xmlns:amll="http://www.example.com/ns/amll" '
    'xmlns:itunes="http://music.apple.com/lyric-ttml-internal" '
    'itunes:timing="Line"><head><metadata>'
    '<ttm:agent type="person" xml:id="v1"/></metadata></head>'
)


def fmt_time(t: float) -> str:
    ms = round(max(t, 0.0) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{m:02d}:{s:02d}.{ms:03d}"


def build_ttml(lines) -> str:
    first, last = lines[0][0], lines[-1][1]
    ps = "".join(
        f'<p begin="{fmt_time(b)}" end="{fmt_time(e)}" ttm:agent="v1" '
        f'itunes:key="L{i}">{escape(t)}</p>'
        for i, (b, e, t) in enumerate(lines, 1)
    )
    return (
        f'{TTML_HEAD}<body dur="{fmt_time(last)}">'
        f'<div begin="{fmt_time(first)}" end="{fmt_time(last)}">{ps}</div></body></tt>'
    )


def tidy(lines, offset: float = 0.0, min_len: float = 0.3):
    out = [[max(0.0, b + offset), max(0.0, e + offset), t] for b, e, t in lines]
    for i, row in enumerate(out):
        if row[1] < row[0] + min_len:
            row[1] = row[0] + min_len
        if i + 1 < len(out):
            nxt = out[i + 1][0]
            if nxt > row[0] and row[1] > nxt:
                row[1] = nxt
    return [tuple(r) for r in out]
