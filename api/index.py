# ─── Imports ───────────────────────────────────────────────────
from flask import (
    Flask, render_template, session, redirect, request,
    url_for, flash, send_file
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
import tempfile

# ─── Flask app setup ──────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET')

jobs = {}  # job_id -> { status: 'queued'|'downloading'|'zipping'|'done' }

CLIENT_ID     = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
CALLBACK_URI  = os.getenv('CALLBACK_URI')

# Tekore will handle token  for us
cred = tk.Credentials(CLIENT_ID, CLIENT_SECRET, CALLBACK_URI)

# ─── Make `logged_in` available in every template ──────────────────
@app.context_processor
def inject_login():
    return dict(logged_in=('refresh_token' in session))

# ─── In-memory cache/globals ──────────────────────────────────────
_liked_cache       = []            # will hold Track objects
_liked_cache_lock  = threading.Lock()
_cache_warming     = False

def _warm_liked_cache(sp, total_pages):
    """
    Fetch pages 2–6 of saved_tracks (up to 50 more) in the background.
    """
    global _liked_cache, _cache_warming
    per_page = 10
    max_page = min(total_pages, 6)   # pages 1–6 total
    for p in range(2, max_page + 1):
        offset = (p - 1) * per_page
        results = sp.saved_tracks(limit=per_page, offset=offset)
        batch   = [item.track for item in results.items]
        with _liked_cache_lock:
            _liked_cache.extend(batch)
    _cache_warming = False

# ─── Helpers ──────────────────────────────────────────────────────
def ensure_token():
    if 'refresh_token' not in session:
        return redirect(url_for('login'))
    return None

def get_spotify():
    refresh = session.get('refresh_token')
    if not refresh:
        return None
    # Exchange the saved refresh_token for a fresh Token
    token = cred.refresh_user_token(refresh)
    # Build a standard (sync) Spotify client with that token
    return tk.Spotify(token)

def get_spotify():
    refresh = session.get('refresh_token')
    if not refresh:
        return None
    token = cred.refresh_user_token(refresh)
    # Store the new refresh_token back in case it rotated
    session['refresh_token'] = token.refresh_token
    return tk.Spotify(token)

def download_and_zip(job_id, sp, download_path, tracks, quality):
    base_dir    = os.path.dirname(download_path)    # "downloaded"
    folder_name = os.path.basename(download_path)   # e.g. "My Playlist"

    # 1) Download
    jobs[job_id]['status'] = 'downloading'
    for track in tracks:
        if jobs[job_id].get('cancelled'):
            jobs[job_id]['status'] = 'cancelled'
            return
        songs_downloader(sp, download_path, [track], quality)  # Pass quality here!

    # 2) Zip
    jobs[job_id]['status'] = 'zipping'
    zip_path = os.path.join(base_dir, f"{folder_name}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(download_path):
            for fname in files:
                full = os.path.join(root, fname)
                arc  = os.path.relpath(full, start=base_dir)
                zf.write(full, arc)

    # 3) Mark done and hand back the zip path
    jobs[job_id]['status']   = 'done'
    jobs[job_id]['zip_path'] = zip_path

    # 4) Schedule cleanup of both folder and zip after 5 minutes
    def _cleanup():
        try:
            shutil.rmtree(download_path)
        except Exception:
            pass
        try:
            os.remove(zip_path)
        except Exception:
            pass

    # 120 sec = 2 min grace period
    threading.Timer(120, _cleanup).start()

# ─── Routes ───────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    # Redirect user to Spotify’s consent page
    auth_url = cred.user_authorisation_url(
        scope=tk.scope.every,
        show_dialog=True,
        state=None  # you can pass a CSRF token here
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    error = request.args.get('error')
    if error or not code:
        flash('Spotify authorization failed', 'danger')
        return redirect(url_for('index'))

    # Exchange code for a token + refresh token
    token = cred.request_user_token(code)
    # Store *that user’s* refresh_token in *their* session
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

    # 1) read `page` query param or default to 1
    page     = int(request.args.get('page', 1))
    per_page =  fifteen = 15 
    offset   = (page - 1) * per_page

    # 2) fetch exactly this slice
    results     = sp.playlists(user.id, limit=per_page, offset=offset)
    page_items  = results.items
    total       = results.total
    total_pages = ceil(total / per_page)

    # 3) render with pagination variables
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

    sp        = get_spotify()
    page      = int(request.args.get('page', 1))
    per_page  = 10
    query     = request.args.get('search', '').strip().lower()

    # If there's a search, fetch *all* saved tracks synchronously
    if query:
        all_tracks = []
        limit, offset = 50, 0

        # load every batch
        while True:
            results = sp.saved_tracks(limit=limit, offset=offset)
            batch   = [item.track for item in results.items]
            all_tracks.extend(batch)
            if not results.next:
                break
            offset += limit

        # filter on name or any artist
        filtered = [
            t for t in all_tracks
            if query in t.name.lower()
               or any(query in a.name.lower() for a in t.artists)
        ]

        total       = len(filtered)
        total_pages = ceil(total / per_page)
        start, end  = (page-1)*per_page, (page-1)*per_page + per_page
        page_items  = filtered[start:end]

    else:
        # No search: fast first‐page + background prefetch as before
        offset     = (page - 1) * per_page
        results    = sp.saved_tracks(limit=per_page, offset=offset)
        page_items = [item.track for item in results.items]
        total      = results.total
        total_pages = ceil(total / per_page)

        # seed & warm cache here (omitted for brevity)

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

    sp = get_spotify()
    kind = request.form['kind']

    if kind == 'playlist':
        idx = int(request.form['idx'][0])
        pl = list_playlists(sp)[idx]
        items = get_playlist_tracks(sp, pl)
        tracks = playlist_tracks_to_tracks(items)
        folder_name = pl.name
    else:
        all_liked = [item.track for item in list_liked_songs(sp)]
        idx_list = request.form.getlist('idx')
        if idx_list:
            tracks = [all_liked[int(i)] for i in idx_list]
        else:
            tracks = all_liked
        folder_name = "Liked Songs"

    # special case: no tracks
    if not tracks:
        flash("No tracks found to download.", "warning")
        return redirect(url_for('playlists'))
    
    # special case: single‐track
    # singleton shortcut
    if len(tracks) == 1:
        track = tracks[0]
        # 1) download into a temp dir you control
        tmpdir = tempfile.mkdtemp(prefix="spotifydl_")
        songs_downloader(sp, tmpdir, [track])

        # 2) find the single .mp3
        mp3s = [f for f in os.listdir(tmpdir) if f.lower().endswith('.mp3')]
        if not mp3s:
            flash("Download failed.", "danger")
            return redirect(url_for('playlists'))
        mp3_path = os.path.join(tmpdir, mp3s[0])

        # 3) schedule cleanup in 5 minutes
        def cleanup():
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass
        threading.Timer(120, cleanup).start()

        # 4) send it immediately
        return send_file(
            mp3_path,
            as_attachment=True,
            download_name=mp3s[0]
        )    
        
    # otherwise, we need to download multiple tracks
    base_dir = "downloaded"
    download_path = os.path.join(base_dir, folder_name)
    os.makedirs(download_path, exist_ok=True)

     # Pick up the user’s choice
    quality = request.form.get('quality', '320')

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'queued'}
    threading.Thread(
        target=download_and_zip,
        args=(job_id, sp, download_path, tracks, quality),
        daemon=True
    ).start()

    return redirect(url_for('status_page', job_id=job_id))

@app.route('/status/<job_id>')
def status_page(job_id):
    if job_id not in jobs:
        flash("Unknown download job.", "danger")
        return redirect(url_for('index'))
    return render_template('status.html', job_id=job_id)

@app.route('/status/<job_id>/json')
def status_json(job_id):
    job = jobs.get(job_id)
    if not job:
        return {"error": "not found"}, 404
    return {"status": job['status']}

@app.route('/download/<job_id>')
def download_zip(job_id):
    job = jobs.get(job_id)
    if not job or job.get('status') != 'done':
        flash("Your download isn’t ready yet. Please wait.", "warning")
        return redirect(url_for('status_page', job_id=job_id))

    return send_file(
        job['zip_path'],
        as_attachment=True,
        download_name=os.path.basename(job['zip_path'])
    )

@app.route('/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    job = jobs.get(job_id)
    if job and job.get('status') not in ('done', 'cancelled'):
        job['cancelled'] = True
        flash("Download cancelled.", "info")
    return redirect(url_for('playlists'))
