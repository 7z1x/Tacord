"""Fetch lyrics from the web using the 9router LLM as a guide.

When no lyric file is provided, this module tries to find the lyrics of the
song based on the YouTube/video title:

    1. Ask the LLM (cbai/kimi-k2.7 via 9router) to extract a clean
       "Artist - Title" from the raw video title.
    2. Build a list of candidate lyric-site URLs (raplib.com, musixmatch,
       genius, etc.) and fetch them.
    3. If scraping fails, fall back to asking the LLM directly for the
       lyrics text (best-effort).

The result is a plain list of lyric lines (no [Verse] tags, no blanks),
the same shape returned by `regersi.lyrics.read_lyrics`.
"""

import os
import re
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_BASE = Path(__file__).resolve().parent.parent
_ENV_FILE = _BASE / ".env"


def _load_env():
    if load_dotenv and _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)


# ---------------------------------------------------------------------------
# 9router LLM helpers
# ---------------------------------------------------------------------------

def _llm_config():
    _load_env()
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:20128/v1")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "cbai/kimi-k2.7")
    return base, key, model


def _llm_chat(messages, timeout: int = 60):
    """Call the 9router OpenAI-compatible /chat/completions endpoint."""
    base, key, model = _llm_config()
    url = f"{base.rstrip('/')}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------

def clean_song_title(raw_title: str):
    """Use the LLM to turn a messy video title into 'Artist - Title'."""
    raw = raw_title.strip()
    # Quick local cleanup first: drop (Official Video), [Lyric], feat., etc.
    local = re.sub(r"\s*[\(\[].*?[\)\]]\s*", "", raw)
    local = re.sub(r"\s*\b(official|audio|video|lyric|lyrics|hd|4k|mv|m/v)\b.*$",
                   "", local, flags=re.IGNORECASE).strip(" -|")
    prompt = (
        "You extract clean song titles from messy YouTube video titles.\n"
        "Return ONLY the result as 'Artist - Title' (no quotes, no extra text).\n"
        "If the artist is unknown, return just the title.\n"
        f"Video title: {raw}"
    )
    out = _llm_chat([{"role": "user", "content": prompt}])
    if not out:
        return local or raw
    # strip surrounding quotes / markdown
    out = out.strip().strip('"`').strip()
    # if the model returned multiple lines, take the first non-empty one
    for line in out.splitlines():
        line = line.strip()
        if line:
            return line
    return local or raw


# ---------------------------------------------------------------------------
# Lyric scraping
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}


def _strip_tags(text: str) -> list:
    """Split text into clean lyric lines: drop [Verse] tags and blank lines."""
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or re.fullmatch(r"\[[^\]]*\]", s):
            continue
        # drop leading [Verse 1] style inline tags
        s = re.sub(r"^\[[^\]]*\]\s*", "", s)
        lines.append(s)
    return lines


def _fetch_raplib(query: str):
    """Search raplib.com and parse the first result page."""
    try:
        search = f"https://raplib.com/search?q={requests.utils.quote(query)}"
        r = requests.get(search, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        # find a lyric link
        m = re.search(r'href="(/lyric/[0-9]+/[^"]+)"', r.text)
        if not m:
            return None
        page = f"https://raplib.com{m.group(1)}"
        r2 = requests.get(page, headers=_HEADERS, timeout=15)
        r2.raise_for_status()
        # lyrics are usually inside <div class="lyric-body"> or similar
        body = r2.text
        m2 = re.search(r'<div[^>]*class="[^"]*lyric[^"]*"[^>]*>(.*?)</div>',
                       body, re.DOTALL | re.IGNORECASE)
        chunk = m2.group(1) if m2 else body
        text = re.sub(r"<[^>]+>", "\n", chunk)
        lines = _strip_tags(text)
        return lines if lines else None
    except Exception as e:
        print(f"raplib fetch failed: {e}")
        return None


def _fetch_generic(query: str):
    """Try musixmatch / genius via a quick search."""
    for base, pattern in [
        ("https://www.musixmatch.com/search/", r'href="(/lyrics/[^"]+)"'),
        ("https://genius.com/search?q=", r'href="(https://genius\.com/[^"]*-lyrics)"'),
    ]:
        try:
            r = requests.get(base + requests.utils.quote(query),
                             headers=_HEADERS, timeout=15)
            r.raise_for_status()
            m = re.search(pattern, r.text)
            if not m:
                continue
            link = m.group(1)
            if link.startswith("/"):
                link = "https://www.musixmatch.com" + link
            r2 = requests.get(link, headers=_HEADERS, timeout=15)
            r2.raise_for_status()
            text = re.sub(r"<[^>]+>", "\n", r2.text)
            lines = _strip_tags(text)
            if lines:
                return lines
        except Exception as e:
            print(f"{base} fetch failed: {e}")
            continue
    return None


def _llm_fetch_lyrics(song: str):
    """Last-resort: ask the LLM to output the lyrics directly."""
    prompt = (
        f"Write the full lyrics of the song \"{song}\".\n"
        "Output ONLY the lyrics, one line per line, no headers, no [Verse] tags, "
        "no commentary. If you are unsure of a word, write it followed by (?)."
    )
    out = _llm_chat([{"role": "user", "content": prompt}], timeout=90)
    if not out:
        return None
    lines = _strip_tags(out)
    return lines if lines else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_lyrics(raw_title: str):
    """Try to obtain lyric lines for a song given a raw video title.

    Returns a list of lyric lines, or None if every strategy failed.
    """
    if not raw_title:
        return None

    print(f"Fetching lyrics for: \"{raw_title}\" ...")
    song = clean_song_title(raw_title)
    print(f"Clean title: \"{song}\"")

    # 1) Try scraping raplib first
    lyrics = _fetch_raplib(song)
    if lyrics:
        print(f"Lyrics found via raplib.com ({len(lyrics)} lines).")
        return lyrics

    # 2) Try generic sites (musixmatch / genius)
    lyrics = _fetch_generic(song)
    if lyrics:
        print(f"Lyrics found via generic search ({len(lyrics)} lines).")
        return lyrics

    # 3) LLM fallback
    print("Web scraping failed; asking the LLM for lyrics directly (best-effort)...")
    lyrics = _llm_fetch_lyrics(song)
    if lyrics:
        print(f"Lyrics produced by LLM ({len(lyrics)} lines). Review recommended.")
        return lyrics

    print("Could not find lyrics for this song.")
    return None


def save_fetched_lyrics(lyrics, stem: str) -> Path:
    """Save fetched lyrics to lyric/<stem>.fetched.txt and return its path."""
    lyric_dir = _BASE / "lyric"
    lyric_dir.mkdir(parents=True, exist_ok=True)
    out = lyric_dir / f"{stem}.fetched.txt"
    out.write_text("\n".join(lyrics) + "\n", encoding="utf-8")
    return out
