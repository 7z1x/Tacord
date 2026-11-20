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
    sys.exit(f"File lirik tidak ditemukan: {arg}\n(juga dicari di {alt.parent})")


def resolve_out(arg, nama: str) -> Path:
    if not arg:
        return BASE / "ttml" / f"{nama}.ttml"
    p = Path(arg)
    return BASE / "ttml" / p.name if p.parent == Path(".") else p


def run():
    args = parser().parse_args()

    cache = Path(args.cache) if args.cache else BASE / "audio"
    lyric_path = resolve_lyric(args.lyric) if args.lyric else None

    audio, judul, work = get_audio(args.sumber, cache, cookies=args.cookies, args_judul=args.judul)
    print(f"Audio siap: {audio} ({judul})")

    trim_offset = 0.0
    if args.mulai_dari is not None:
        from regersi.audio import trim_audio
        mulai = parse_time(args.mulai_dari)
        print(f"Memotong audio mulai dari {args.mulai_dari} (~{mulai:.3f}s)...")
        audio = trim_audio(audio, work, mulai)
        trim_offset = max(0.0, mulai - 5.0)

    if args.pisah_vokal:
        print("Memisahkan vokal...")
        audio = separate_vocals(audio, work)

    print(f"Memuat model '{args.model}'...")
    try:
        model = load_model(args.model)
    except Exception as e:
        sys.exit(f"Gagal memuat model Whisper '{args.model}': {e}")

    if lyric_path:
        lyrics = read_lyrics(lyric_path)
        if not lyrics:
            sys.exit("File lirik kosong.")
        if any("(?)" in l for l in lyrics):
            print("PERINGATAN: masih ada tanda (?) di file lirik dan akan ikut masuk ke TTML. "
                  "Hapus setelah kamu cek.")
        print(f"Menyelaraskan {len(lyrics)} baris dari {lyric_path.name} dengan audio...")
        lines = align(model, audio, lyrics, args.bahasa, prompt=args.prompt)
    else:
        print("Tidak ada lirik, AI menebak teks dari audio (hasil = draft)...")
        try:
            lines = transcribe(model, audio, args.bahasa, prompt=args.prompt)
        except Exception as e:
            sys.exit(f"Transkripsi gagal: {e}")
        if not lines:
            sys.exit("Tidak ada suara/lirik yang terdeteksi.")

    try:
        lines = tidy(lines, offset=args.offset + trim_offset)
    except Exception as e:
        sys.exit(f"Gagal merapikan hasil: {e}")

    nama = re.sub(r'[\\/:*?"<>|]+', "", judul).strip() or "lyric"
    out = resolve_out(args.out, nama)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_text(build_ttml(lines), encoding="utf-8")
    except Exception as e:
        sys.exit(f"Gagal menulis file TTML: {e}")
    print(f"Selesai: {out} ({len(lines)} baris, sampai {fmt_time(lines[-1][1])})")

    if not lyric_path:
        draft = BASE / "lyric" / f"{out.stem}.draft.txt"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("\n".join(t for _, _, t in lines) + "\n", encoding="utf-8")
        print(f"Draft teks: {draft}")
        ragu = sum("(?)" in t for _, _, t in lines)
        if ragu:
            print(f"{ragu} baris bertanda (?): dengarkan lagi, perbaiki, lalu hapus tandanya.")
        print(f'Koreksi teksnya, lalu jalankan lagi dengan: --lyric "{draft.name}"')
