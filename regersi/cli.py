import argparse


def parser():
    ap = argparse.ArgumentParser(
        description="Link YouTube / file audio -> lirik ber-timestamp -> .ttml untuk Spicetify"
    )
    ap.add_argument("sumber", help="link YouTube, atau path file audio (mp3/wav/m4a)")
    ap.add_argument("-l", "--lyric",
                    help="file lirik .txt, satu baris per baris lirik (path, atau nama file di folder lyric/)")
    ap.add_argument("-o", "--out",
                    help="nama file output .ttml (tanpa folder = disimpan di ttml/)")
    ap.add_argument("-m", "--model", default="large-v3-turbo",
                    help="model Whisper: small / medium / large-v3 / large-v3-turbo (default: large-v3-turbo)")
    ap.add_argument("--bahasa", default="id", help="kode bahasa (default: id)")
    ap.add_argument("--pisah-vokal", action="store_true",
                    help="pisahkan vokal dari musik dulu (butuh demucs, lebih lambat tapi lebih akurat)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="geser semua waktu, dalam detik (mis. -2.5 atau 1.2)")
    ap.add_argument("--cookies-from-browser", dest="cookies", default=None,
                    help="ambil cookies dari browser (contoh: chrome, edge, firefox, brave) jika YouTube memblokir")
    ap.add_argument("--cache", default=None,
                    help="folder penyimpanan audio (default: audio/)")
    ap.add_argument("--prompt", default=None,
                    help="prompt awal untuk Whisper (contoh: 'lirik berbahasa Indonesia dialek Papua')")
    ap.add_argument("--mulai-dari", default=None,
                    help="waktu mulai lirik utama, format ss.mmm atau mm:ss.mmm atau hh:mm:ss.mmm")
    ap.add_argument("--judul", default=None,
                    help="override nama folder cache dan output (contoh: Wiro)")
    return ap
