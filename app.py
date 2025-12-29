from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import threading
import time

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

progress_data = {
    "status": "idle",
    "percent": 0,
    "file": None
}


# ================= PROGRESS HOOK =================
def progress_hook(d):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)

        if total:
            progress_data["percent"] = int(downloaded / total * 100)
            progress_data["status"] = "downloading"

    elif d["status"] in ("finished", "postprocessing"):
        progress_data["percent"] = 100
        progress_data["status"] = "done"


# ================= DOWNLOAD FUNCTION =================
def download_video(url):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final_file = ydl.prepare_filename(info)
        final_file = final_file.rsplit(".", 1)[0] + ".mp3"

    progress_data["file"] = final_file


# ================= AUTO DELETE =================
def auto_delete(path, delay=60):
    time.sleep(delay)
    if os.path.exists(path):
        os.remove(path)


# ================= ROUTES =================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json()
    url = data.get("url") if data else None

    if not url:
        return jsonify({"error": "URL missing"}), 400

    progress_data.update({
        "status": "starting",
        "percent": 0,
        "file": None
    })

    threading.Thread(
        target=download_video,
        args=(url,),
        daemon=True
    ).start()

    return jsonify({"status": "started"})


@app.route("/progress")
def progress():
    return jsonify(progress_data)


@app.route("/download")
def download():
    file_path = progress_data.get("file")

    if not file_path or not os.path.exists(file_path):
        return "", 204

    threading.Thread(target=auto_delete, args=(file_path,)).start()

    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path),
        mimetype="audio/mpeg"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
