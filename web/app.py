import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, flash, redirect, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from regersi import BASE

app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static"),
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.context_processor
def cache_bust():
    """Append ?v=<mtime> to static URLs so the browser always fetches the latest file."""
    _url_for = app.jinja_env.globals["url_for"]

    def versioned_url_for(endpoint, **values):
        if endpoint == "static":
            fname = values.get("filename")
            if fname:
                fpath = os.path.join(app.static_folder, fname)
                try:
                    values["v"] = int(os.stat(fpath).st_mtime)
                except OSError:
                    pass
        return _url_for(endpoint, **values)

    return dict(url_for=versioned_url_for)

# Global status for simple progress tracking
JOB = {"running": False, "log": [], "result": None, "error": None}


def log(msg):
    JOB["log"].append(msg)
    print(msg)


ALLOWED_LYRIC_EXT = {".txt", ".lrc"}


def list_lyrics():
    lyric_dir = BASE / "lyric"
    if not lyric_dir.exists():
        return []
    return sorted([f.name for f in lyric_dir.iterdir() if f.suffix.lower() in ALLOWED_LYRIC_EXT])


def list_results():
    ttml_dir = BASE / "ttml"
    if not ttml_dir.exists():
        return []
    return sorted([f.name for f in ttml_dir.iterdir() if f.suffix == ".ttml"], reverse=True)


def list_results_info():
    ttml_dir = BASE / "ttml"
    if not ttml_dir.exists():
        return []
    files = [f for f in ttml_dir.iterdir() if f.suffix == ".ttml"]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {"name": f.name, "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")}
        for f in files
    ]


def run_job(data):
    JOB["running"] = True
    JOB["log"] = []
    JOB["result"] = None
    JOB["error"] = None

    try:
        cmd = [
            sys.executable,
            str(BASE / "regersi" / "lyric2ttml.py"),
            data["source"],
            "--model", data.get("model", "large-v3-turbo"),
        ]

        lyric_val = data.get("lyric")
        if lyric_val:
            cmd.extend(["--lyric", lyric_val])

        if data.get("separate_vocals"):
            cmd.append("--separate-vocals")
        if data.get("offset"):
            cmd.extend(["--offset", str(data["offset"])])
        if data.get("start_from"):
            cmd.extend(["--start-from", data["start_from"]])
        if data.get("prompt"):
            cmd.extend(["--prompt", data["prompt"]])
        if data.get("title"):
            cmd.extend(["--title", data["title"]])

        log(f"Running: {' '.join(cmd[:5])} ...")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(BASE),
        )

        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            output_lines.append(line)
            log(line)

        process.wait()

        if process.returncode != 0:
            JOB["error"] = "Process failed. See log above."
        else:
            # Find the 'Done:' line to extract the result path
            result_file = None
            for line in output_lines:
                m = re.search(r"Done:\s+(.+?)\s+\(", line)
                if m:
                    result_file = Path(m.group(1)).name
            JOB["result"] = result_file
            log("Done.")

    except Exception as e:
        JOB["error"] = str(e)
        log(f"Error: {e}")
    finally:
        JOB["running"] = False


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/studio")
def studio():
    return render_template(
        "studio.html",
        lyrics=list_lyrics(),
        models=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
    )


@app.route("/riwayat")
def riwayat():
    return render_template("riwayat.html", results=list_results_info())


@app.route("/api/run", methods=["POST"])
def api_run():
    if JOB["running"]:
        return jsonify({"ok": False, "error": "A process is already running."})

    data = request.json
    if not data.get("source"):
        return jsonify({"ok": False, "error": "Audio source is required."})

    thread = threading.Thread(target=run_job, args=(data,))
    thread.start()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify({
        "running": JOB["running"],
        "log": JOB["log"],
        "result": JOB["result"],
        "error": JOB["error"],
    })


@app.route("/api/results")
def api_results():
    return jsonify(list_results_info())


@app.route("/api/upload-lyric", methods=["POST"])
def upload_lyric():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded."})

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"ok": False, "error": "Filename is empty."})

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_LYRIC_EXT:
        return jsonify({"ok": False, "error": f"Unsupported format: {ext}. Only .txt and .lrc"})

    lyric_dir = BASE / "lyric"
    lyric_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^\w\s.-]", "_", file.filename)
    dest = lyric_dir / safe_name

    try:
        file.save(dest)
        return jsonify({"ok": True, "filename": safe_name, "lyrics": list_lyrics()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/ttml/<path:filename>")
def download_result(filename):
    return send_from_directory(BASE / "ttml", filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
