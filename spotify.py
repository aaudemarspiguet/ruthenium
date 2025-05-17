import os
import yt_dlp as youtube_dl
import eyed3
import urllib.request
from pathvalidate import sanitize_filename
import tekore as tk


def songs_downloader(sp: tk.Spotify, folder: str, tracks: list, quality= '320'):
    """
    Download and tag a list of Spotify tracks as MP3s.

    sp:      Authenticated tekore.Spotify client
    folder: Top-level folder to place downloads
    tracks: List of tekore.FullTrack objects
    quality: Audio quality ('190' or '320')
    """
    # Configure yt-dlp options per call
    ydl_opts = {
        'ffmpeg_location': 'ffmpeg.exe',
        'format': 'bestaudio/best',
        'extractaudio': True,
        'addmetadata': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'logger': None,
    }

    for index, track in enumerate(tracks, start=1):
        title  = sanitize_filename(track.name)
        artist = sanitize_filename(track.artists[0].name)
        album  = sanitize_filename(track.album.name)

        print(f"[{index}/{len(tracks)}] Downloading: {artist} - {title}")
        ydl_opts['outtmpl'] = f"{artist} - {title}.%(ext)s"

        dest_dir   = folder
        tmp_fname  = f"{artist} - {title}.mp3"
        final_path = os.path.join(dest_dir, tmp_fname)

        if os.path.exists(final_path):
            print(" → already exists, skipping")
            continue

        os.makedirs(dest_dir, exist_ok=True)
        try:
            # Download via YouTube search
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"ytsearch1:{title} {artist}"])

            # Load and tag MP3
            audiofile = eyed3.load(tmp_fname)
            if not audiofile.tag:
                audiofile.initTag()

            audiofile.tag.artist       = artist
            audiofile.tag.title        = title
            audiofile.tag.album        = album
            audiofile.tag.album_artist = track.album.artists[0].name

            # Genre from Spotify metadata
            genres = sp.artist(track.artists[0].id).genres
            if genres:
                audiofile.tag.genre = genres[-1]

            audiofile.tag.track_num = track.track_number

            # Embed album art
            img_data = urllib.request.urlopen(track.album.images[0].url).read()
            audiofile.tag.images.set(3, img_data, 'image/jpeg')
            audiofile.tag.save()

            # Move final file into place
            os.replace(tmp_fname, final_path)
            print(f" → saved to {final_path}")

        except Exception as e:
            print(f"   ▶ Error on '{artist} - {title}': {e}")


def list_playlists(sp: tk.Spotify) -> list:
    """
    Return the user's playlists (list of tekore.PlaylistSimple).
    """
    return sp.playlists(sp.current_user().id).items


def get_playlist_tracks(sp: tk.Spotify, playlist) -> list:
    """
    Given a tekore.PlaylistSimple, return all tracks (list of tekore.PlaylistTrack).
    """
    items = []
    uri_id = playlist.uri.split(':')[-1]
    results = sp.playlist_items(uri_id)
    items.extend(results.items)
    while results.next:
        results = sp.next(results)
        items.extend(results.items)
    return items


def list_liked_songs(sp: tk.Spotify) -> list:
    """
    Return all saved ("Liked") tracks for the user.
    """
    items = []
    results = sp.saved_tracks()
    items.extend(results.items)
    while results.next:
        results = sp.next(results)
        items.extend(results.items)
    return items


def playlist_tracks_to_tracks(items: list) -> list:
    """
    Convert a list of tekore.PlaylistTrack to a list of tekore.FullTrack.
    """
    return [pt.track for pt in items]


def get_yt_track_url(track) -> str:
    """
    (Optional) Return the first YouTube search result URL for a track.
    """
    query = f"ytsearch1:{track.name} {track.artists[0].name}"
    with youtube_dl.YoutubeDL({'format': 'bestaudio'}) as ydl:
        info = ydl.extract_info(query, download=False)
        return info['entries'][0]['webpage_url']
