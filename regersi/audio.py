import re
import subprocess
import sys
from pathlib import Path

from regersi import BASE


def parse_time(s: str) -> float:
    """Parse 'ss.mmm', 'mm:ss.mmm', atau 'hh:mm:ss.mmm' ke detik."""
    parts = s.strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        m, sec = parts
        return int(m) * 60 + float(sec)
    h, m, sec = parts
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _clean_url(url: str) -> str:
    """Bersihkan URL YouTube: hanya simpan video ID, buang parameter lain."""
    from urllib.parse import urlparse, parse_qs, urlencode
    parsed = urlparse(url)

    # youtube.com/watch?v=XXXX&list=...&start_radio=... -> youtube.com/watch?v=XXXX
    if "youtube.com" in parsed.hostname and parsed.path == "/watch":
        qs = parse_qs(parsed.query)
        if "v" in qs:
            clean_query = urlencode({"v": qs["v"][0]})
            url = f"{parsed.scheme}://{parsed.hostname}{parsed.path}?{clean_query}"
            print(f"URL dibersihkan: {url}")
            return url

    # youtu.be/XXXX?si=...&list=... -> youtu.be/XXXX (tanpa query)
    if parsed.hostname and "youtu.be" in parsed.hostname:
        url = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
        print(f"URL dibersihkan: {url}")
        return url

    return url


def _ydl_opts(cookies=None, **extra):
    opts = {
        "format": "18/bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web_embedded"]}},
    }
    if cookies:
        opts["cookiesfrombrowser"] = (cookies,)
    opts.update(extra)
    return opts


def _slug(name: str) -> str:
    """Ambil bagian judul setelah tanda '-' terakhir, lalu 2 kata awal."""
    if " - " in name:
        name = name.rsplit(" - ", 1)[-1]
    # Buang konten dalam kurung di akhir judul (official video, audio, dll)
    name = re.sub(r"\s*[\(\[].*?[\)\]]\s*$", "", name).strip()
    words = re.sub(r"[^\w\s]", " ", name).split()
    slug = "_".join(words[:2]).strip("_")
    return slug or "audio"


def get_audio(sumber: str, cache: Path, cookies: str = None, args_judul: str = None):
    p = Path(sumber)
    if p.is_file():
        work = cache / p.stem
        work.mkdir(parents=True, exist_ok=True)
        return p, p.stem, work

    try:
        import yt_dlp
    except ImportError:
        sys.exit("yt-dlp belum terpasang. Jalankan: pip install -U yt-dlp")

    clean_url = _clean_url(sumber)

    try:
        with yt_dlp.YoutubeDL(_ydl_opts(cookies)) as ydl:
            info = ydl.extract_info(clean_url, download=False)
    except Exception as e:
        sys.exit(
            f"Gagal mengambil info audio dari YouTube: {e}\n\n"
            "Solusi:\n"
            "1. Gunakan cookies browser: --cookies-from-browser chrome (atau edge / firefox)\n"
            "2. Atau download manual lagu tersebut (mp3/wav) lalu jalankan dengan file lokal:\n"
            "   python lirik2ttml.py namalagu.mp3 --lirik namalagu.txt"
        )

    title = info.get("title") or info["id"]
    slug = _slug(args_judul or title)
    work = cache / slug
    wav = work / "audio.wav"
    if not wav.exists():
        work.mkdir(parents=True, exist_ok=True)
        opts = _ydl_opts(
            cookies,
            outtmpl=str(work / "audio.%(ext)s"),
            postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([clean_url])
    return wav, title, work


def separate_vocals(audio: Path, work: Path) -> Path:
    found = list(work.glob("sep/*/*/vocals.wav"))
    if found:
        return found[0]
    try:
        subprocess.run(
            [sys.executable, "-m", "demucs", "--two-stems=vocals",
             "-o", str(work / "sep"), str(audio)],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("demucs gagal / belum terpasang. Jalankan: pip install demucs")
    return next(work.glob("sep/*/*/vocals.wav"))


def trim_audio(audio: Path, work: Path, start: float, buffer: float = 5.0) -> Path:
    """Potong audio dari (start - buffer) detik, lalu tambahkan offset ke args."""
    import subprocess
    trimmed = work / f"audio_trimmed_{start:.2f}.wav"
    if trimmed.exists():
        return trimmed
    ss = max(0.0, start - buffer)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(ss), "-i", str(audio), "-c", "copy", str(trimmed)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return trimmed
