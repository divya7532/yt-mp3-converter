from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import threading
import re
import uuid
import time

app = Flask(__name__)

# Ensure directories exist
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Store active tasks
tasks = {}

def clean_str(s):
    if not s: return ""
    # Remove ANSI color codes
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(s)).strip()

def hook(d, task_id):
    task = tasks.get(task_id)
    if not task: return

    if d["status"] == "downloading":
        p_str = clean_str(d.get("_percent_str", "0%")).replace("%", "")
        try:
            task["percent"] = float(p_str)
        except:
            task["percent"] = 0
        
        task["speed"] = clean_str(d.get("_speed_str", "0 KB/s"))
        task["status"] = "downloading"

    elif d["status"] == "finished":
        task["status"] = "processing"
        task["percent"] = 100
        task["speed"] = "Finalizing..."

def download_audio(task_id, url, quality):
    task = tasks[task_id]
    
    # Check if cookies exist
    cookie_file = "cookies.txt"
    use_cookies = os.path.exists(cookie_file)
    
    ydl_opts = {
        # 'best' format is safer than 'bestaudio' for preventing 403s on some clients
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, f"{task_id}_%(title)s.%(ext)s"),
        "restrictfilenames": True, 
        "progress_hooks": [lambda d: hook(d, task_id)],
        "quiet": True,
        "noplaylist": True,
        
        # --- ANTI-BLOCK CONFIGURATION ---
        "concurrent_fragment_downloads": 3,
        "retries": 10,
        "nocheckcertificate": True,
        
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
    }

    # 1. IF COOKIES EXIST: Use them with the standard Web client (Most reliable)
    if use_cookies:
        print("Using Cookies for Authentication...")
        ydl_opts["cookiefile"] = cookie_file
        ydl_opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}
    
    # 2. IF NO COOKIES: Use iOS client (Often bypasses 403 better than Android)
    else:
        print("No Cookies found - Attempting fallback client...")
        ydl_opts["extractor_args"] = {"youtube": {"player_client": ["ios", "android"]}}
        # iOS sometimes fails if we demand audio-only, so we allow video downloads and convert them
        ydl_opts["format"] = "best" 

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
            
            # SEARCH FOR THE FILE
            found_file = None
            time.sleep(0.5) # Allow FS sync
            for f in os.listdir(DOWNLOAD_FOLDER):
                if f.startswith(task_id) and f.endswith(".mp3"):
                    found_file = f
                    break
            
            if found_file:
                task["filename"] = found_file
                task["status"] = "done"
            else:
                raise Exception("File not found on disk after download.")

    except Exception as e:
        clean_error = clean_str(str(e))
        if "ERROR:" in clean_error:
            clean_error = clean_error.split("ERROR:", 1)[-1].strip()
        print(f"Error for {task_id}: {clean_error}")
        task["status"] = "error"
        task["error_msg"] = clean_error

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/info", methods=["POST"])
def info():
    url = request.json.get("url")
    if not url: return jsonify({"error": "no url"}), 400
    try:
        # Use cookies for info fetching too if available
        opts = {"quiet": True, "skip_download": True}
        if os.path.exists("cookies.txt"):
            opts["cookiefile"] = "cookies.txt"
            
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
        return jsonify({"thumbnail": data.get("thumbnail"), "title": data.get("title")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert", methods=["POST"])
def convert():
    data = request.json
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "starting", "percent": 0, "speed": "Waiting...", "filename": None}
    
    threading.Thread(
        target=download_audio, 
        args=(task_id, data["url"], data.get("quality", "192")), 
        daemon=True
    ).start()
    
    return jsonify({"task_id": task_id})

@app.route("/progress/<task_id>")
def progress(task_id):
    return jsonify(tasks.get(task_id, {"status": "error", "error_msg": "Task not found"}))

@app.route("/download/<filename>")
def download(filename):
    safe_name = os.path.basename(filename)
    path = os.path.join(DOWNLOAD_FOLDER, safe_name)
    
    if not os.path.exists(path): return "File not found", 404
    
    display_name = safe_name.split('_', 1)[-1] if '_' in safe_name else safe_name

    return send_file(
        path, 
        as_attachment=True, 
        download_name=display_name, 
        mimetype="audio/mpeg"
    )

if __name__ == "__main__":
    # Render support
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
