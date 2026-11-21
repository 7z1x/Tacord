import sys
from pathlib import Path

from regersi.lyrics import map_words_to_lines


def load_model(name: str):
    try:
        import stable_whisper
    except ImportError:
        sys.exit("stable-ts is not installed. Run: pip install -U stable-ts")
    return stable_whisper.load_model(name)


def align(model, audio: Path, lyrics, lang: str, prompt: str = None):
    text = "\n".join(lyrics)
    kwargs = {"language": lang}
    if prompt:
        kwargs["initial_prompt"] = prompt
    try:
        result = model.align(str(audio), text, original_split=True, **kwargs)
    except TypeError:
        result = model.align(str(audio), text, **kwargs)

    segs = result.segments
    if len(segs) == len(lyrics):
        return [(s.start, s.end, l) for s, l in zip(segs, lyrics)]

    words = [(w.start, w.end) for w in result.all_words()]
    if len(words) == sum(len(l.split()) for l in lyrics):
        return map_words_to_lines(words, lyrics)

    sys.exit(
        "Alignment result could not be mapped to lyric lines "
        f"({len(segs)} segments vs {len(lyrics)} lines). "
        "Try enabling --separate-vocals or using a larger model (-m large-v3)."
    )


def transcribe(model, audio: Path, lang: str, prompt: str = None):
    kwargs = {"language": lang, "condition_on_previous_text": False}
    if prompt:
        kwargs["initial_prompt"] = prompt
    result = model.transcribe(str(audio), **kwargs)
    return [(s.start, s.end, s.text.strip()) for s in result.segments if s.text.strip()]


def build_vocal_map(transcribed, merge_gap: float = 2.0):
    """From a transcription result, build a list of (start, end) regions
    where vocals/singing are actually detected. Adjacent segments within
    `merge_gap` seconds are merged into one region."""
    if not transcribed:
        return []
    regions = []
    cur_start, cur_end = transcribed[0][0], transcribed[0][1]
    for start, end, _ in transcribed[1:]:
        if start - cur_end <= merge_gap:
            cur_end = max(cur_end, end)
        else:
            regions.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    regions.append((cur_start, cur_end))
    return regions


def flag_misplaced(lines, vocal_map, margin: float = 0.5):
    """Flag lyric lines whose start time falls outside detected vocal
    regions (i.e. placed over instrumentals/silence). Returns a list of
    (line_index, start_time, text) for suspicious lines."""
    flagged = []
    for i, (start, _end, text) in enumerate(lines):
        in_vocal = any(s - margin <= start <= e + margin for s, e in vocal_map)
        if not in_vocal:
            flagged.append((i, start, text))
    return flagged


def verify_alignment(model, audio, lines, lang: str, prompt: str = None):
    """Transcribe the audio to build a vocal map, then flag aligned lines
    that fall outside vocal regions. Returns (marked_lines, flagged, vocal_map)."""
    transcribed = transcribe(model, audio, lang, prompt)
    vocal_map = build_vocal_map(transcribed)
    flagged = flag_misplaced(lines, vocal_map)
    flagged_idx = {f[0] for f in flagged}
    marked = []
    for i, (start, end, text) in enumerate(lines):
        if i in flagged_idx and "(?)" not in text:
            text = f"{text} (?)"
        marked.append((start, end, text))
    return marked, flagged, vocal_map
