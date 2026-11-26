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
    ap.add_argument("--offset", type=float, default=0.0,
                    help="shift all timestamps, in seconds (e.g. -2.5 or 1.2)")
    ap.add_argument("--cookies-from-browser", dest="cookies", default=None,
                    help="extract cookies from a browser (e.g. chrome, edge, firefox, brave) if YouTube blocks the download")
    ap.add_argument("--cache", default=None,
                    help="audio cache directory (default: audio/)")
    ap.add_argument("--prompt", default=None,
                    help="initial prompt for Whisper (e.g. 'Indonesian lyrics with Papuan dialect')")
    ap.add_argument("--start-from", default=None,
                    help="start time of the main lyrics, format ss.mmm or mm:ss.mmm or hh:mm:ss.mmm")
    ap.add_argument("--title", default=None,
                    help="override the cache folder name and output filename (e.g. Wiro)")
    return ap
