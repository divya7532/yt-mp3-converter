from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import threading
import time

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
progress_data = {"status": "idle", "percent": 0, "file": None}

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)


# 🔹 REAL PROGRESS HOOK
def progress_hook(d):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        if total:
            progress_data["percent"] = int(downloaded / total * 100)
            progress_data["status"] = "downloading"

    elif d["status"] == "finished":
        progress_data["percent"] = 100
        progress_data["status"] = "finished"


# 🔹 DOWNLOAD FUNCTION
def download_video(url):
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
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


# 🔹 AUTO DELETE FUNCTION
def auto_delete(path, delay=30):
    time.sleep(delay)
    if os.path.exists(path):
        os.remove(path)
        print("Deleted:", path)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    url = request.form["url"]

    progress_data["percent"] = 0
    progress_data["status"] = "starting"
    progress_data["file"] = None

    threading.Thread(target=download_video, args=(url,)).start()

    return jsonify({"started": True})


@app.route("/progress")
def progress():
    return jsonify(progress_data)

@app.route("/download")
def download():
    file_path = progress_data.get("file")

    if not file_path or not os.path.exists(file_path):
        # Tell frontend to retry
        return "", 204  # No Content (important)

    filename = os.path.basename(file_path)

    threading.Thread(target=auto_delete, args=(file_path,)).start()

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype="audio/mpeg"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
