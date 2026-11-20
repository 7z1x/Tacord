import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

from regersi import BASE

PROMPT_RAPIKAN = (
    "Kamu membantu merapikan draft lirik hasil transkripsi otomatis (Whisper) dari lagu "
    "berbahasa Indonesia dialek Papua. Kata dialek yang BENAR dan harus dipertahankan: "
    "sa, ko, dong, kitong, kitorang, pung, su, tara, tra, trada, ade, kaka, mama, nona, "
    "pace, mace, bale, pi, pigi, ni, tu. Bagian berbahasa Inggris dibiarkan.\n"
    "Aturan:\n"
    "1. Perbaiki ejaan dan salah ketik yang jelas saja.\n"
    "2. JANGAN mengubah dialek Papua menjadi bahasa baku.\n"
    "3. JANGAN menambah, menghapus, atau menggabung baris: jumlah baris keluaran harus "
    "sama persis dengan masukan.\n"
    "4. Kalau ragu pada suatu kata, biarkan apa adanya dan tambahkan (?) setelah kata itu.\n"
    "5. Keluarkan hanya liriknya, tanpa penjelasan, tanpa nomor, tanpa pagar kode."
)


def load_env():
    f = BASE / ".env"
    if not f.is_file():
        return
    for raw in f.read_text(encoding="utf-8-sig").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def llm_rapikan(lines):
    base = os.environ.get("LLM_BASE_URL", "http://localhost:20128/v1").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not model:
        sys.exit("LLM_MODEL belum diisi. Buat file .env di folder proyek (lihat petunjuk).")

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": PROMPT_RAPIKAN},
            {"role": "user", "content": "\n".join(lines)},
        ],
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    if urlparse(base).hostname in ("localhost", "127.0.0.1", "::1"):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
    try:
        with opener.open(req, timeout=300) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"LLM menjawab error {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"Gagal menghubungi {base}: {e}\nPastikan 9router sedang berjalan.")

    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        sys.exit(f"Format jawaban LLM tidak dikenali: {str(data)[:300]}")

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # ponytail: reasoning_content kadang kosong tapi tetap muncul di content;
    # kalau content kosong setelah strip, anggap gagal.
    text = text.strip()
    if not text:
        sys.exit("LLM mengembalikan jawaban kosong.")
    return [l.strip() for l in text.splitlines()
            if l.strip() and not l.strip().startswith("```")]
