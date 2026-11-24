import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

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


ALLOWED_LYRIC_EXT = {".txt", ".lrc"}


def list_lyrics():
    lyric_dir = BASE / "lyric"
    if not lyric_dir.exists():
        return []
    return sorted([f.name for f in lyric_dir.iterdir() if f.suffix.lower() in ALLOWED_LYRIC_EXT])


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


# ===== Queue system =====
QUEUE_LOCK = threading.Lock()
QUEUE = []
WORKER_ALIVE = False


def make_job(data):
    """Create a job dict from form data."""
    return {
        "id": str(uuid.uuid4())[:8],
        "data": data,
        "status": "pending",
        "log": [],
        "result": None,
        "error": None,
        "added_at": datetime.now().strftime("%H:%M:%S"),
    }


def get_job(job_id):
    with QUEUE_LOCK:
        for j in QUEUE:
            if j["id"] == job_id:
                return j
    return None


def remove_pending_job(job_id):
    with QUEUE_LOCK:
        for i, j in enumerate(QUEUE):
            if j["id"] == job_id and j["status"] == "pending":
                QUEUE.pop(i)
                return True
    return False


def clear_completed_jobs():
    with QUEUE_LOCK:
        QUEUE[:] = [j for j in QUEUE if j["status"] in ("pending", "running")]


def run_job_process(job):
    """Run a single job's subprocess."""
    data = job["data"]

    try:
        cmd = [
            sys.executable,
            str(BASE / "regersi" / "lyric2ttml.py"),
            data["source"],
            "--model", data.get("model", "large-v3-turbo"),
        ]

        if data.get("lyric"):
            cmd.extend(["--lyric", data["lyric"]])
        if data.get("separate_vocals"):
            cmd.append("--separate-vocals")
        if data.get("verify"):
            cmd.append("--verify")
        if data.get("fetch_lyrics"):
            cmd.append("--fetch-lyrics")
        if data.get("offset"):
            cmd.extend(["--offset", str(data["offset"])])
        if data.get("start_from"):
            cmd.extend(["--start-from", data["start_from"]])
        if data.get("prompt"):
            cmd.extend(["--prompt", data["prompt"]])
        if data.get("segmented"):
            cmd.append("--segmented")
        if data.get("merge_gap") is not None:
            cmd.extend(["--merge-gap", str(data["merge_gap"])])
        if data.get("title"):
            cmd.extend(["--title", data["title"]])

        def log(msg):
            job["log"].append(msg)
            print(msg)

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
            job["error"] = "Process failed. See log above."
        else:
            result_file = None
            for line in output_lines:
                m = re.search(r"Done:\s+(.+?)\s+\(", line)
                if m:
                    result_file = Path(m.group(1)).name
            job["result"] = result_file
            log("Done.")

    except Exception as e:
        job["error"] = str(e)
        print(f"Error: {e}")


def queue_worker():
    """Background worker that processes jobs from the queue sequentially."""
    global WORKER_ALIVE
    while True:
        with QUEUE_LOCK:
            job = None
            for j in QUEUE:
                if j["status"] == "pending":
                    j["status"] = "running"
                    job = j
                    break

        if job is None:
            break

        run_job_process(job)

        with QUEUE_LOCK:
            job["status"] = "error" if job["error"] else "done"

    with QUEUE_LOCK:
        WORKER_ALIVE = False


def ensure_worker():
    """Start the worker thread if not already running."""
    global WORKER_ALIVE
    with QUEUE_LOCK:
        if not WORKER_ALIVE:
            WORKER_ALIVE = True
            t = threading.Thread(target=queue_worker, daemon=True)
            t.start()


# ===== Routes =====

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
    data = request.json
    if not data.get("source"):
        return jsonify({"ok": False, "error": "Audio source is required."})

    job = make_job(data)
    with QUEUE_LOCK:
        QUEUE.append(job)
    ensure_worker()
    return jsonify({"ok": True, "job_id": job["id"]})


@app.route("/api/queue")
def api_queue():
    with QUEUE_LOCK:
        jobs = [
            {
                "id": j["id"],
                "status": j["status"],
                "source": j["data"].get("source", ""),
                "lyric": j["data"].get("lyric") or "",
                "model": j["data"].get("model", "large-v3-turbo"),
                "separate_vocals": j["data"].get("separate_vocals", False),
                "result": j["result"],
                "error": j["error"],
                "added_at": j["added_at"],
            }
            for j in QUEUE
        ]
        worker_running = WORKER_ALIVE
    return jsonify({"queue": jobs, "worker_running": worker_running})


@app.route("/api/queue/<job_id>")
def api_queue_job(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    with QUEUE_LOCK:
        return jsonify({
            "id": job["id"],
            "status": job["status"],
            "source": job["data"].get("source", ""),
            "lyric": job["data"].get("lyric") or "",
            "log": list(job["log"]),
            "result": job["result"],
            "error": job["error"],
        })


@app.route("/api/queue/<job_id>", methods=["DELETE"])
def api_queue_remove(job_id):
    if remove_pending_job(job_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Can only remove pending jobs."})


@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    clear_completed_jobs()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    """Backward compat — returns the currently running job."""
    with QUEUE_LOCK:
        for j in QUEUE:
            if j["status"] == "running":
                return jsonify({
                    "running": True,
                    "log": list(j["log"]),
                    "result": j["result"],
                    "error": j["error"],
                })
    return jsonify({"running": False, "log": [], "result": None, "error": None})


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
