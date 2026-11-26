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
        "Try using a larger model (-m large-v3)."
    )


def transcribe(model, audio: Path, lang: str, prompt: str = None):
    kwargs = {"language": lang, "condition_on_previous_text": False}
    if prompt:
        kwargs["initial_prompt"] = prompt
    result = model.transcribe(str(audio), **kwargs)
    return [(s.start, s.end, s.text.strip()) for s in result.segments if s.text.strip()]
