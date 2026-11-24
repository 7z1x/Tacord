import argparse


def parser():
    ap = argparse.ArgumentParser(
        description="YouTube link / audio file -> timestamped lyrics -> .ttml for Spicetify"
    )
    ap.add_argument("source", help="YouTube link, or path to a local audio file (mp3/wav/m4a)")
    ap.add_argument("-l", "--lyric",
                    help="lyric file (.txt), one line per lyric line (full path, or filename in lyric/)")
    ap.add_argument("-o", "--out",
                    help="output .ttml filename (without folder = saved to ttml/)")
    ap.add_argument("-m", "--model", default="large-v3-turbo",
                    help="Whisper model: small / medium / large-v3 / large-v3-turbo (default: large-v3-turbo)")
    ap.add_argument("--language", default="id", help="language code (default: id)")
    ap.add_argument("--separate-vocals", action="store_true",
                    help="isolate vocals from music first (requires demucs, slower but more accurate)")
    ap.add_argument("--verify", action="store_true",
                    help="transcribe audio to detect vocal regions, then flag aligned lines that fall "
                         "outside them (marks with (?)). Slower (runs an extra transcribe pass).")
    ap.add_argument("--fetch-lyrics", action="store_true",
                    help="when no --lyric is given, fetch lyrics from the web (raplib.com etc.) using "
                         "the 9router LLM to interpret the video title. The result is saved to lyric/ "
                         "and aligned to the audio instead of producing a draft.")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="shift all timestamps, in seconds (e.g. -2.5 or 1.2)")
    ap.add_argument("--cookies-from-browser", dest="cookies", default=None,
                    help="extract cookies from a browser (e.g. chrome, edge, firefox, brave) if YouTube blocks the download")
    ap.add_argument("--cache", default=None,
                    help="audio cache directory (default: audio/)")
    ap.add_argument("--prompt", default=None,
                    help="initial prompt for Whisper (e.g. 'Indonesian lyrics with Papuan dialect')")
    ap.add_argument("--segmented", action="store_true",
                    help="segmented alignment: transcribe first to locate vocal regions, then align "
                         "each region separately. Solves long instrumental gaps and dense mixes. "
                         "Recommended for songs with random structure (intro instrument, vocals, gap, vocals).")
    ap.add_argument("--merge-gap", type=float, default=6.0,
                    help="segmented mode: merge vocal segments within N seconds into one region "
                         "(default: 6.0). Larger = fewer, bigger regions; smaller = more regions.")
    ap.add_argument("--start-from", default=None,
                    help="start time of the main lyrics, format ss.mmm or mm:ss.mmm or hh:mm:ss.mmm")
    ap.add_argument("--title", default=None,
                    help="override the cache folder name and output filename (e.g. Wiro)")
    return ap
