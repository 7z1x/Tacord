import re
import sys
from pathlib import Path

from regersi import BASE
from regersi.ai import load_model, align, transcribe
from regersi.audio import get_audio, separate_vocals, parse_time
from regersi.cli import parser
from regersi.lyrics import read_lyrics
from regersi.ttml import build_ttml, fmt_time, tidy


def resolve_lyric(arg: str) -> Path:
    p = Path(arg)
    if p.is_file():
        return p
    alt = BASE / "lyric" / p.name
    if alt.is_file():
        return alt
    sys.exit(f"Lyric file not found: {arg}\n(also searched in {alt.parent})")


def resolve_out(arg, name: str) -> Path:
    if not arg:
        return BASE / "ttml" / f"{name}.ttml"
    p = Path(arg)
    return BASE / "ttml" / p.name if p.parent == Path(".") else p


def run():
    args = parser().parse_args()

    cache = Path(args.cache) if args.cache else BASE / "audio"
    lyric_path = resolve_lyric(args.lyric) if args.lyric else None

    audio, title, work = get_audio(args.source, cache, cookies=args.cookies, args_title=args.title)
    print(f"Audio ready: {audio} ({title})")

    trim_offset = 0.0
    if args.start_from is not None:
        from regersi.audio import trim_audio
        start = parse_time(args.start_from)
        print(f"Trimming audio from {args.start_from} (~{start:.3f}s)...")
        audio = trim_audio(audio, work, start)
        trim_offset = max(0.0, start - 5.0)

    if args.separate_vocals:
        print("Separating vocals...")
        audio = separate_vocals(audio, work)

    print(f"Loading model '{args.model}'...")
    try:
        model = load_model(args.model)
    except Exception as e:
        sys.exit(f"Failed to load Whisper model '{args.model}': {e}")

    if lyric_path:
        lyrics = read_lyrics(lyric_path)
        if not lyrics:
            sys.exit("Lyric file is empty.")
        if any("(?)" in l for l in lyrics):
            print("WARNING: the lyric file still contains (?) marks and they will be included in the TTML. "
                  "Remove them after reviewing.")
        print(f"Aligning {len(lyrics)} lines from {lyric_path.name} with audio...")
        lines = align(model, audio, lyrics, args.language, prompt=args.prompt)
    else:
        print("No lyric file provided, AI is transcribing text from audio (result = draft)...")
        try:
            lines = transcribe(model, audio, args.language, prompt=args.prompt)
        except Exception as e:
            sys.exit(f"Transcription failed: {e}")
        if not lines:
            sys.exit("No voice/lyrics detected in audio.")

    try:
        lines = tidy(lines, offset=args.offset + trim_offset)
    except Exception as e:
        sys.exit(f"Failed to tidy results: {e}")

    name = re.sub(r'[\\/:*?"<>|]+', "", title).strip() or "lyric"
    out = resolve_out(args.out, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_text(build_ttml(lines), encoding="utf-8")
    except Exception as e:
        sys.exit(f"Failed to write TTML file: {e}")
    print(f"Done: {out} ({len(lines)} lines, until {fmt_time(lines[-1][1])})")

    if not lyric_path:
        draft = BASE / "lyric" / f"{out.stem}.draft.txt"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("\n".join(t for _, _, t in lines) + "\n", encoding="utf-8")
        print(f"Draft text: {draft}")
        uncertain = sum("(?)" in t for _, _, t in lines)
        if uncertain:
            print(f"{uncertain} lines marked with (?): listen again, fix them, then remove the marks.")
        print(f'Edit the text, then run again with: --lyric "{draft.name}"')
