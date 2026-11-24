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


# ---------------------------------------------------------------------------
# Segmented alignment (per vocal region) — solves gaps & dense mixes
# ---------------------------------------------------------------------------

def _slice_audio(audio: Path, start: float, end: float, out_path: Path):
    """Extract a [start, end] slice of the audio to a temp WAV file.
    Re-encodes (PCM 16-bit) instead of -c copy so the slice has a correct
    WAV header and clean sample boundaries — -c copy on PCM produces
    glitchy/corrupt audio that breaks Whisper alignment."""
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-to", str(end),
         "-i", str(audio),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
         str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out_path


def _distribute_lines(lyrics, vocal_map, transcribed):
    """Distribute lyric lines across detected vocal regions.

    Uses region DURATION as the primary weight (an objective fact about
    the audio, unlike transcribed word counts which can be wrong on weak
    models). If transcribed words are available, regions where Whisper
    heard more words get a small boost.

    Each region also gets a capacity cap based on its duration so we never
    cram an impossible number of lines into a short region (~3.5s per line
    is a typical singing pace).

    Returns a list of (region_index, start, end, [line_texts]) groups.
    """
    if not vocal_map:
        return [(0, 0.0, 0.0, lyrics)]

    # Count transcribed words per region (best-effort, may be 0)
    def _words_in(rs, re_):
        cnt = 0
        for ts, te, txt in transcribed:
            if ts >= rs - 0.5 and te <= re_ + 0.5:
                cnt += len(txt.split())
        return cnt

    dur = [max(0.1, re_ - rs) for rs, re_ in vocal_map]
    words = [_words_in(rs, re_) for rs, re_ in vocal_map]

    # Weight = duration (primary) + word-count bonus (secondary, capped)
    # so a region Whisper heard a lot in gets a boost, but a region Whisper
    # missed entirely is still weighted by its real length.
    word_bonus = [min(w, dur[i] / 2.0) for i, w in enumerate(words)]
    weights = [dur[i] + word_bonus[i] for i in range(len(vocal_map))]
    total_w = sum(weights)
    n = len(lyrics)

    # Capacity: how many lines can fit in each region at ~3.5s/line
    # (generous; tidy() will fix overlaps). Prevents cramming.
    SECS_PER_LINE = 3.5
    caps = [max(1, int(d / SECS_PER_LINE)) for d in dur]

    chunks = []
    idx = 0
    remaining = n
    for i in range(len(vocal_map)):
        if i == len(vocal_map) - 1:
            # last region takes everything left
            cnt = remaining
        else:
            share = weights[i] / total_w if total_w else 1.0 / len(vocal_map)
            cnt = max(1, round(share * n))
            cnt = min(cnt, caps[i], remaining)
        cnt = max(0, cnt)
        chunk = lyrics[idx:idx + cnt]
        if chunk:
            chunks.append((i, vocal_map[i][0], vocal_map[i][1], chunk))
        idx += cnt
        remaining -= cnt
        if remaining <= 0:
            break

    # Any leftover lines go to the last chunk
    if remaining > 0 and chunks:
        last = chunks[-1]
        chunks[-1] = (last[0], last[1], last[2], last[3] + lyrics[idx:])
    elif remaining > 0:
        chunks.append((0, vocal_map[0][0], vocal_map[0][1], lyrics[idx:]))
    return chunks


def _align_chunk(model, audio_slice: Path, chunk_lyrics, lang: str, prompt: str = None):
    """Align a small group of lyric lines to a short audio slice. Returns
    list of (start, end, text) with times relative to the slice."""
    text = "\n".join(chunk_lyrics)
    kwargs = {"language": lang}
    if prompt:
        kwargs["initial_prompt"] = prompt
    try:
        result = model.align(str(audio_slice), text, original_split=True, **kwargs)
    except TypeError:
        result = model.align(str(audio_slice), text, **kwargs)

    segs = result.segments
    if len(segs) == len(chunk_lyrics):
        return [(s.start, s.end, l) for s, l in zip(segs, chunk_lyrics)]

    words = [(w.start, w.end) for w in result.all_words()]
    if len(words) == sum(len(l.split()) for l in chunk_lyrics):
        return map_words_to_lines(words, chunk_lyrics)

    # Best-effort: take whatever segments Whisper produced, padded/truncated
    if segs:
        out = [(s.start, s.end, chunk_lyrics[i] if i < len(chunk_lyrics) else "")
               for i, s in enumerate(segs)]
        # Pad missing lines at the end with the last timestamp
        last_end = out[-1][1] if out else 0.0
        while len(out) < len(chunk_lyrics):
            out.append((last_end, last_end, chunk_lyrics[len(out)]))
        return out
    return [(0.0, 0.0, l) for l in chunk_lyrics]


def align_segmented(model, audio: Path, lyrics, lang: str, prompt: str = None,
                    merge_gap: float = 6.0, min_region: float = 3.0):
    """Segmented alignment: transcribe to find vocal regions, then align
    each region's lyric chunk separately.

    This solves three problems at once:
      1. Long instrumental gaps no longer corrupt the alignment, because
         each vocal region is aligned independently.
      2. Dense mixes (vocals buried under instruments) benefit because the
         alignment focuses on a short, vocal-heavy slice.
      3. Dialect mismatch is more tolerable on short, focused segments.

    Returns list of (start, end, text) in absolute audio time.
    """
    import tempfile
    print(f"[segmented] Step 1/4: quick transcribe to locate vocal regions...")
    transcribed = transcribe(model, audio, lang, prompt)

    if not transcribed:
        print("[segmented] No vocals detected at all — falling back to full align.")
        return align(model, audio, lyrics, lang, prompt)

    # Build a vocal map with a larger merge gap so short pauses inside a
    # verse don't split it into tiny pieces.
    vocal_map = build_vocal_map(transcribed, merge_gap=merge_gap)

    # Drop tiny regions (likely noise) below min_region seconds
    vocal_map = [(s, e) for s, e in vocal_map if e - s >= min_region]

    if not vocal_map:
        print("[segmented] No sizable vocal regions found — falling back to full align.")
        return align(model, audio, lyrics, lang, prompt)

    total_vocal = sum(e - s for s, e in vocal_map)
    print(f"[segmented] Found {len(vocal_map)} vocal region(s), "
          f"total {total_vocal:.1f}s of vocals:")
    for i, (s, e) in enumerate(vocal_map):
        print(f"  Region {i + 1}: {s:.1f}s - {e:.1f}s  (dur {e - s:.1f}s)")

    # Sanity check: if detected vocals are too sparse for the number of lyric
    # lines (less than ~2.5s per line on average), the transcribe pass was
    # probably weak. Falling back to full align avoids cramming many lines
    # into one tiny region. The user should use a larger model.
    avg_s_per_line = total_vocal / max(len(lyrics), 1)
    if avg_s_per_line < 2.5:
        print(f"[segmented] WARNING: only {total_vocal:.1f}s of vocals detected "
              f"for {len(lyrics)} lines (~{avg_s_per_line:.1f}s/line). This is too "
              f"sparse — the transcribe pass likely missed vocals. "
              f"Falling back to full alignment. Consider a larger model "
              f"(-m medium / large-v3 / large-v3-turbo) for better region detection.")
        return align(model, audio, lyrics, lang, prompt)

    # Distribute lyric lines across regions
    groups = _distribute_lines(lyrics, vocal_map, transcribed)
    print(f"[segmented] Distributing {len(lyrics)} lines across {len(groups)} region(s):")
    for gi, rs, re_, chunk in groups:
        print(f"  Region {gi + 1}: {len(chunk)} line(s) -> {rs:.1f}s..{re_:.1f}s")

    # Align each chunk to its audio slice.
    # Use the OS temp dir (not work_dir) so we never pollute the audio cache,
    # and clean up the slices after we're done.
    print("[segmented] Step 2/4: aligning each region separately...")
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="segalign_"))
    slice_paths = []

    aligned_all = []
    for gi, rs, re_, chunk in groups:
        slice_path = tmp_dir / f"region_{gi}_{rs:.1f}_{re_:.1f}.wav"
        slice_paths.append(slice_path)
        _slice_audio(audio, rs, re_, slice_path)
        try:
            chunk_aligned = _align_chunk(model, slice_path, chunk, lang, prompt)
        except Exception as e:
            print(f"  [region {gi + 1}] align failed ({e}); using proportional fallback.")
            dur = re_ - rs
            step = dur / max(len(chunk), 1)
            chunk_aligned = [(rs + i * step, rs + (i + 1) * step, l)
                             for i, l in enumerate(chunk)]

        # Shift slice-relative times back to absolute audio time
        for st, en, txt in chunk_aligned:
            aligned_all.append((max(rs, rs + st), max(rs, rs + en), txt))
        print(f"  [region {gi + 1}] aligned {len(chunk_aligned)} line(s) "
              f"@ {rs:.1f}s..{re_:.1f}s")

    # Clean up temp slices
    for sp in slice_paths:
        try:
            sp.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    print(f"[segmented] Step 3/4: merged {len(aligned_all)} lines total.")
    print("[segmented] Step 4/4: handing off to tidy() for timestamp cleanup.")
    return aligned_all


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
