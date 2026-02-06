from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import threading
import re
import uuid
import time
import glob

app = Flask(__name__)

# 1. SETUP DIRECTORIES
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")
TEMPLATE_FOLDER = os.path.join(BASE_DIR, "templates")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

# Explicitly tell Flask where folders are
app = Flask(__name__, template_folder=TEMPLATE_FOLDER)
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

def try_download(ydl_opts, url, task_id):
    """Helper to try downloading with specific options"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
        return True
    except Exception as e:
        print(f"Attempt failed: {e}")
        return False

def download_audio(task_id, url, quality):
    task = tasks[task_id]
    
    # Define the output template
    out_tmpl = os.path.join(DOWNLOAD_FOLDER, f"{task_id}_%(title)s.%(ext)s")
    
    # Base Options
    base_opts = {
        "outtmpl": out_tmpl,
        "restrictfilenames": True, 
        "progress_hooks": [lambda d: hook(d, task_id)],
        "quiet": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 3,
        "retries": 10,
        "nocheckcertificate": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
    }

    success = False
    
    # --- STRATEGY 1: COOKIES (Best for Cloud) ---
    if os.path.exists(COOKIES_FILE):
        print("Strategy 1: Using Cookies...")
        opts = base_opts.copy()
        opts["cookiefile"] = COOKIES_FILE
        opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}
        if try_download(opts, url, task_id): success = True

    # --- STRATEGY 2: ANDROID (Best for Local) ---
    if not success:
        print("Strategy 2: Fallback to Android...")
        opts = base_opts.copy()
        opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
        if try_download(opts, url, task_id): success = True

    # --- STRATEGY 3: iOS (Last Resort) ---
    if not success:
        print("Strategy 3: Fallback to iOS...")
        opts = base_opts.copy()
        opts["extractor_args"] = {"youtube": {"player_client": ["ios"]}}
        opts["format"] = "best" # iOS needs video sometimes
        if try_download(opts, url, task_id): success = True

    if success:
        # Find the file safely
        time.sleep(1)
        # Search for any file starting with the task_id
        search_pattern = os.path.join(DOWNLOAD_FOLDER, f"{task_id}_*.mp3")
        files = glob.glob(search_pattern)
        
        if files:
            task["filename"] = os.path.basename(files[0])
            task["status"] = "done"
        else:
            task["status"] = "error"
            task["error_msg"] = "Download succeeded but file is missing."
    else:
        task["status"] = "error"
        task["error_msg"] = "YouTube blocked all download attempts (403)."

@app.route("/")
def index():
    # Debug: Check if template exists
    if not os.path.exists(os.path.join(TEMPLATE_FOLDER, "index.html")):
        return "ERROR: index.html not found in templates folder!", 500
    return render_template("index.html")

@app.route("/info", methods=["POST"])
def info():
    url = request.json.get("url")
    if not url: return jsonify({"error": "no url"}), 400
    try:
        opts = {"quiet": True, "skip_download": True}
        if os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
        
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
    
    # Clean up name for user
    display_name = safe_name.split('_', 1)[-1] if '_' in safe_name else safe_name
    return send_file(path, as_attachment=True, download_name=display_name, mimetype="audio/mpeg")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Print debug info
    print(f"Server starting...")
    print(f"Looking for templates in: {TEMPLATE_FOLDER}")
    print(f"Looking for cookies in: {COOKIES_FILE}")
    if os.path.exists(COOKIES_FILE): print("SUCCESS: Cookies.txt found!")
    else: print("WARNING: Cookies.txt NOT found!")
    
    app.run(host='0.0.0.0', port=port, debug=False)
