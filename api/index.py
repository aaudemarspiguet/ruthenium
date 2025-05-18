# ─── Imports ───────────────────────────────────────────────────
from flask import (
    Flask, render_template, send_from_directory, session,
    redirect, request, url_for, flash, send_file
)
from spotify import (
    list_playlists,
    get_playlist_tracks,
    playlist_tracks_to_tracks,
    list_liked_songs,
    songs_downloader,
)
import os
import tekore as tk
from dotenv import load_dotenv
import threading
import uuid
import zipfile
from math import ceil
import shutil
from pathvalidate import sanitize_filename
import redis

# ─── flask config ──────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET')

# ─── download directory ─────────────────────────────────────────────
BASE_DOWNLOAD_DIR = os.path.join(app.root_path, 'downloaded')
os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

# ─── redis client ───────────────────────────────────────────────────
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ─── spotify credentials ────────────────────────────────────────────
CLIENT_ID     = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
CALLBACK_URI  = os.getenv('CALLBACK_URI')
cred = tk.Credentials(CLIENT_ID, CLIENT_SECRET, CALLBACK_URI)

# ─── make `logged_in` available in every template ──────────────────
@app.context_processor
def inject_login():
    return dict(logged_in=('refresh_token' in session))

# ─── prefetch songs in cache and load in background ───────────────
_liked_cache      = []
_liked_cache_lock = threading.Lock()
_cache_warming    = False

def _warm_liked_cache(sp, total_pages):
    """
    Fetch pages 2–6 of saved_tracks (up to 50 more) in the background.
    """
    global _liked_cache, _cache_warming
    per_page = 10
    max_page = min(total_pages, 6)
    for p in range(2, max_page + 1):
        offset = (p - 1) * per_page
        results = sp.saved_tracks(limit=per_page, offset=offset)
        batch   = [item.track for item in results.items]
        with _liked_cache_lock:
            _liked_cache.extend(batch)
    _cache_warming = False

# ─── Helpers ───────────────────────────────────────────────────────
def ensure_token():
    if 'refresh_token' not in session:
        return redirect(url_for('login'))
    return None

def get_spotify():
    """
    Exchange the saved refresh_token for a fresh Spotify client.
    """
    refresh = session.get('refresh_token')
    if not refresh:
        return None
    token = cred.refresh_user_token(refresh)
    session['refresh_token'] = token.refresh_token
    return tk.Spotify(token)

# ─── Worker functions ──────────────────────────────────────────────
def download_and_zip(job_id, sp, download_path, tracks, quality):
    """
    Download all `tracks` into download_path, zip them to BASE_DOWNLOAD_DIR,
    and update job status in Redis at each step.
    """
    folder_name = os.path.basename(download_path)
    zip_fname   = f"{folder_name}.zip"
    zip_path    = os.path.join(BASE_DOWNLOAD_DIR, zip_fname)

    # Download phase
    r.hset(f"job:{job_id}", 'status', 'downloading')
    for track in tracks:
        if r.hget(f"job:{job_id}", 'status') == 'cancelled':
            r.hset(f"job:{job_id}", 'status', 'cancelled')
            return
        songs_downloader(sp, download_path, [track], quality)

    # Zipping phase
    r.hset(f"job:{job_id}", 'status', 'zipping')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(download_path):
            for fname in files:
                full = os.path.join(root, fname)
                arc  = os.path.join(folder_name, fname)
                zf.write(full, arc)

    # Done
    r.hset(f"job:{job_id}", mapping={'status': 'done', 'zip_path': zip_path})

    # Cleanup after 2 minutes
    def _cleanup():
        shutil.rmtree(download_path, ignore_errors=True)
        try:
            os.remove(zip_path)
        except OSError:
            pass
        r.delete(f"job:{job_id}")
    threading.Timer(120, _cleanup).start()


def enqueue_download(job_id, refresh_token, kind, idx_list, quality):
    """
    Rehydrate a Spotify client, resolve tracks/folder, then run download_and_zip.
    """
    token = cred.refresh_user_token(refresh_token)
    sp    = tk.Spotify(token)

    if kind == 'playlist':
        pl     = list_playlists(sp)[int(idx_list[0])]
        items  = get_playlist_tracks(sp, pl)
        tracks = playlist_tracks_to_tracks(items)
        folder = pl.name
    else:
        all_liked = [item.track for item in list_liked_songs(sp)]
        tracks     = [all_liked[int(i)] for i in idx_list] if idx_list else all_liked
        folder     = "Liked Songs"

    # Prepare and update status
    r.hset(f"job:{job_id}", 'status', 'downloading')
    download_path = os.path.join(
        BASE_DOWNLOAD_DIR,
        f"{job_id}_{sanitize_filename(folder)}"
    )
    os.makedirs(download_path, exist_ok=True)

    download_and_zip(job_id, sp, download_path, tracks, quality)

# ─── App Routes ────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    auth_url = cred.user_authorisation_url(
        scope=tk.scope.every,
        show_dialog=True,
        state=None
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code  = request.args.get('code')
    error = request.args.get('error')
    if error or not code:
        flash('Spotify authorization failed', 'danger')
        return redirect(url_for('index'))

    token = cred.request_user_token(code)
    session['refresh_token'] = token.refresh_token
    flash('Logged in successfully!', 'success')
    return redirect(url_for('playlists'))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Signed out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/playlists')
def playlists():
    if redirect_to := ensure_token():
        return redirect_to
    sp   = get_spotify()
    user = sp.current_user()

    page, per_page = int(request.args.get('page', 1)), 15
    offset = (page - 1) * per_page

    results     = sp.playlists(user.id, limit=per_page, offset=offset)
    page_items  = results.items
    total       = results.total
    total_pages = ceil(total / per_page)

    return render_template(
        'playlists.html',
        playlists=page_items,
        page=page,
        total_pages=total_pages
    )

@app.route('/liked')
def liked():
    if redirect_to := ensure_token():
        return redirect_to

    sp       = get_spotify()
    page     = int(request.args.get('page', 1))
    per_page = 10
    query    = request.args.get('search', '').strip().lower()

    if query:
        # full synchronous search
        all_tracks = []
        limit, offset = 50, 0
        while True:
            results = sp.saved_tracks(limit=limit, offset=offset)
            batch   = [item.track for item in results.items]
            all_tracks.extend(batch)
            if not results.next:
                break
            offset += limit

        filtered    = [t for t in all_tracks
                         if query in t.name.lower()
                         or any(query in a.name.lower() for a in t.artists)]
        total       = len(filtered)
        total_pages = ceil(total / per_page)
        start, end  = (page-1)*per_page, (page-1)*per_page + per_page
        page_items  = filtered[start:end]
    else:
        # fast first page + background cache warming
        offset     = (page - 1) * per_page
        results    = sp.saved_tracks(limit=per_page, offset=offset)
        page_items = [item.track for item in results.items]
        total      = results.total
        total_pages = ceil(total / per_page)

        # seed & warm cache
        with _liked_cache_lock:
            _liked_cache.clear()
            _liked_cache.extend(page_items)
        global _cache_warming
        if not _cache_warming:
            _cache_warming = True
            threading.Thread(
                target=_warm_liked_cache,
                args=(sp, total_pages),
                daemon=True
            ).start()

    return render_template(
        'download.html',
        items=page_items,
        page=page,
        total_pages=total_pages,
        search=query
    )

@app.route('/download', methods=['POST'])
def do_download():
    if redirect_to := ensure_token():
        return redirect_to

    refresh_token = session['refresh_token']
    kind          = request.form['kind']
    idx_list      = request.form.getlist('idx')
    quality       = request.form.get('quality', '320')
    job_id        = str(uuid.uuid4())

    # enqueue job
    r.hset(f"job:{job_id}", mapping={'status': 'queued'})
    threading.Thread(
        target=enqueue_download,
        args=(job_id, refresh_token, kind, idx_list, quality),
        daemon=True
    ).start()

    return redirect(url_for('status_page', job_id=job_id))

@app.route('/status/<job_id>')
def status_page(job_id):
    if not r.exists(f"job:{job_id}"):
        flash("Unknown download job.", "danger")
        return redirect(url_for('index'))
    return render_template('status.html', job_id=job_id)

@app.route('/status/<job_id>/json')
def status_json(job_id):
    data = r.hgetall(f"job:{job_id}")
    if not data:
        return {"error": "not found"}, 404
    return {"status": data.get("status", "")}

@app.route('/download/<job_id>')
def download_zip(job_id):
    data = r.hgetall(f"job:{job_id}")
    if data.get("status") != 'done':
        flash("Your download isn’t ready yet. Please wait.", "warning")
        return redirect(url_for('status_page', job_id=job_id))

    zip_path = data.get('zip_path')
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=os.path.basename(zip_path)
    )

@app.route('/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    if r.exists(f"job:{job_id}") and r.hget(f"job:{job_id}", 'status') not in ('done','cancelled'):
        r.hset(f"job:{job_id}", 'status', 'cancelled')
        flash("Download cancelled.", "info")
    return redirect(url_for('playlists'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'assets'),
        'favicon.ico',
        mimetype='image/x-icon'
    )
