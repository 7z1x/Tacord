<p align="center">
  <img src="web/static/img/logo.png" alt="Tacord" width="120">
</p>

<h1 align="center">Tacord</h1>

<p align="center">
  Generate synchronized TTML lyrics from YouTube or local audio using Whisper AI.<br>
  <strong><a href="#usage">Explore Tacord usage »</a></strong>
  <br><br>
  <a href="https://github.com/7z1x/Tacord/issues/new?labels=bug&template=bug_report.md">Report bug</a>
  ·
  <a href="https://github.com/7z1x/Tacord/issues/new?labels=enhancement&template=feature_request.md">Request feature</a>
  ·
  <a href="https://github.com/7z1x/Tacord">Repository</a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python"></a>
  <a href="https://github.com/openai/whisper"><img src="https://img.shields.io/badge/Engine-stable--ts-success" alt="Engine"></a>
  <a href="https://github.com/yt-dlp/yt-dlp"><img src="https://img.shields.io/badge/Audio%20source-yt--dlp-red" alt="Audio source"></a>
  <a href="https://flask.palletsprojects.com/"><img src="https://img.shields.io/badge/UI-Flask-black" alt="UI"></a>
</p>

---

## Overview

**Tacord** is a tool that turns any song into **time-synced TTML lyrics** — the format used by Apple Music, Spicetify, and AMLL (Apple Music Like Lyrics). It downloads audio from a YouTube link (or accepts a local file), transcribes or aligns the lyrics using [stable-ts](https://github.com/jianfcheng/stable-ts) (a stable Whisper implementation), and exports a ready-to-use `.ttml` file.

Tacord ships with a **built-in web Studio** (`http://127.0.0.1:5000/studio`) so you can generate lyrics without touching the terminal. It also includes a full **command-line interface** for scripting and automation.

### How it works

1. **Audio input** — Provide a YouTube URL or a local audio file (mp3/wav/m4a). Tacord uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download and convert the audio to WAV.
2. **Lyric input** — Either import your own lyric file (`.txt` / `.lrc`, one line per lyric line) or let Whisper transcribe the audio and produce a draft.
3. **Alignment** — When a lyric file is provided, Whisper **aligns** the known text to the audio, producing precise word-level timestamps. When no lyric is provided, Whisper **transcribes** the audio from scratch.
4. **Output** — The result is written as a `.ttml` file in the `ttml/` directory, ready for Spicetify, Apple Music, or AMLL.

---

## Files

This distribution of Tacord consists of the following files and directories:

- **[README.md](README.md)** — the file you are currently reading.
- **[requirements.txt](requirements.txt)** — the Python dependencies required to run Tacord.
- **[regersi/](regersi/)** — the core engine, a subdirectory containing the full source code:
  - `lyric2ttml.py` — CLI entry point.
  - `main.py` — orchestrator: ties together audio download, lyric loading, alignment, and TTML export.
  - `audio.py` — YouTube download via yt-dlp, WAV conversion, optional vocal separation (Demucs), and audio trimming.
  - `ai.py` — Whisper model loading, lyric-to-audio alignment, and transcription.
  - `lyrics.py` — lyric file parsing (strips `[Verse]` tags and blank lines) and word-to-line mapping.
  - `ttml.py` — TTML document construction and timestamp tidying.
  - `cli.py` — argparse definitions for all command-line options.
- **[web/](web/)** — the Flask web application:
  - `app.py` — server with `/studio`, `/api/run`, `/api/upload-lyric`, `/api/status`, and `/riwayat` endpoints.
  - `templates/` — Jinja2 HTML templates (studio, landing, riwayat).
  - `static/` — frontend assets (JavaScript, CSS, images).
- **audio/** — cache directory for downloaded WAV files (auto-created).
- **lyric/** — directory for imported lyric files (`.txt`, `.lrc`) and generated drafts.
- **ttml/** — output directory for generated `.ttml` files.

---

## Requirements

- **Python 3.9+**
- **[FFmpeg](https://ffmpeg.org/)** — required by yt-dlp for audio conversion and by Whisper for audio decoding.
- **A GPU is recommended** but not required. Whisper runs significantly faster on CUDA; it will fall back to CPU automatically.

### Python dependencies

| Package | Purpose |
|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Download audio from YouTube |
| [stable-ts](https://github.com/jianfcheng/stable-ts) | Whisper-based transcription & alignment |
| [demucs](https://github.com/facebookresearch/demucs) | Optional vocal isolation for better accuracy |
| [soundfile](https://github.com/bastibe/python-soundfile) | Audio file I/O |
| [flask](https://flask.palletsprojects.com/) | Web Studio UI |

---

## Installing

```bash
git clone https://github.com/7z1x/Tacord.git
cd Tacord
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Make sure **FFmpeg** is installed and available on your system `PATH`:

- **Windows:** `winget install FFmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

---

## Usage

### Option A — Web Studio (recommended)

Launch the built-in web interface:

```bash
python web/app.py
```

Then open your browser at:

```
http://127.0.0.1:5000/studio
```

From the Studio you can:

1. Paste a **YouTube URL** or a path to a local audio file.
2. Select or **import a lyric file** (`.txt` / `.lrc`). If none is provided, Whisper will transcribe the audio and produce a draft.
3. Pick a **Whisper model** (`tiny` → `large-v3-turbo`). Larger models are more accurate but slower.
4. Toggle **vocal isolation** (Demucs) for cleaner alignment on dense mixes.
5. Click **Generate TTML**. Progress and logs stream live in the terminal panel.
6. Download the resulting `.ttml` file, or review all past outputs under **Riwayat**.

### Option B — Command Line

```bash
# Align an imported lyric file with audio from YouTube
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..." --lyric mysong.txt

# Let Whisper transcribe the audio and produce a draft
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..."

# Use a local audio file instead of YouTube
python regersi/lyric2ttml.py "C:\music\mysong.mp3" --lyric mysong.txt

# Separate vocals first for better accuracy on dense mixes
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..." --lyric mysong.txt --separate-vocals

# Trim audio to start from a specific timestamp
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..." --lyric mysong.txt --start-from 00:12.500

# Override the output title
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..." --lyric mysong.txt --title "My Song"
```

#### CLI options

| Flag | Description |
|---|---|
| `source` *(positional)* | YouTube URL or path to a local audio file (mp3/wav/m4a). |
| `-l`, `--lyric` | Lyric file (`.txt` / `.lrc`). Can be a full path or just a filename in `lyric/`. |
| `-o`, `--out` | Output `.ttml` filename (without folder = saved to `ttml/`). |
| `-m`, `--model` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` *(default)*. |
| `--language` | Language code *(default: `id`)*. |
| `--separate-vocals` | Isolate vocals from instrumentals using Demucs (slower but more accurate). |
| `--offset` | Shift all timestamps by N seconds (e.g. `-2.5` or `1.2`). |
| `--start-from` | Start time of the lyrics, format `ss.mmm`, `mm:ss.mmm`, or `hh:mm:ss.mmm`. |
| `--title` | Override the cache folder name and output filename. |
| `--prompt` | Initial prompt for Whisper (e.g. dialect or vocabulary hints). |
| `--cookies-from-browser` | Extract cookies from a browser (`chrome`, `edge`, `firefox`, `brave`) if YouTube blocks the download. |
| `--cache` | Custom audio cache directory *(default: `audio/`)*. |

### Draft workflow

When you generate **without** a lyric file, Tacord produces two things:

1. A `.ttml` file with Whisper's best-guess transcription.
2. A `.draft.txt` file in `lyric/` containing the transcribed text, one line per lyric line.

You can review the draft, fix any transcription errors, and re-run with `--lyric` for a properly aligned result:

```bash
# After reviewing mysong.draft.txt:
python regersi/lyric2ttml.py "https://www.youtube.com/watch?v=..." --lyric "mysong.draft.txt"
```

---

## Terms of use

**Note:** Tacord downloads audio from YouTube for personal, non-commercial use (e.g., creating synced lyrics for your own music library). Ensure you comply with YouTube's Terms of Service and applicable copyright laws in your jurisdiction.

---

## Acknowledgements

Tacord is built on top of several outstanding open-source projects:

- **[stable-ts](https://github.com/jianfcheng/stable-ts)** — the stable Whisper implementation that powers transcription and alignment.
- **[OpenAI Whisper](https://github.com/openai/whisper)** — the foundational speech recognition model.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — the audio downloader that makes YouTube sourcing possible.
- **[Demucs](https://github.com/facebookresearch/demucs)** — Facebook Research's vocal separation engine.
- **[Flask](https://flask.palletsprojects.com/)** — the lightweight web framework powering the Studio UI.

TTML output follows the format expected by **[Spicetify](https://spicetify.app/)** and **[AMLL (Apple Music Like Lyrics)](https://github.com/Steve-Mr/AppleMusicLikeLyrics)**.
