import os
import yt_dlp as youtube_dl
import eyed3
import urllib.request
from pathvalidate import sanitize_filename
import tekore as tk


def songs_downloader(sp: tk.Spotify, folder: str, tracks: list, quality: str = '320'):
    """
    Download and tag a list of Spotify tracks as MP3s.

    sp:      Authenticated tekore.Spotify client
    folder:  Top-level folder to place downloads
    tracks:  List of tekore.FullTrack objects
    quality: Audio quality ('190' or '320')
    """
    os.makedirs(folder, exist_ok=True)

    for idx, track in enumerate(tracks, start=1):
        artist = sanitize_filename(track.artists[0].name)
        title  = sanitize_filename(track.name)
        album  = sanitize_filename(track.album.name)

        outtmpl = os.path.join(folder, f"{artist} - {title}.%(ext)s")
        final_mp3 = os.path.join(folder, f"{artist} - {title}.mp3")

        if os.path.exists(final_mp3):
            print(f"[{idx}/{len(tracks)}] → '{artist} - {title}' already exists, skipping")
            continue

        print(f"[{idx}/{len(tracks)}] Downloading: {artist} - {title}")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'addmetadata': True,
            'logger': None,
        }

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"ytsearch1:{title} {artist}"])

            audiofile = eyed3.load(final_mp3)
            if not audiofile.tag:
                audiofile.initTag()

            audiofile.tag.artist       = artist
            audiofile.tag.title        = title
            audiofile.tag.album        = album
            audiofile.tag.album_artist = track.album.artists[0].name
            audiofile.tag.track_num    = track.track_number

            genres = sp.artist(track.artists[0].id).genres
            if genres:
                audiofile.tag.genre = genres[-1]

            # Embed album art
            img_data = urllib.request.urlopen(track.album.images[0].url).read()
            audiofile.tag.images.set(3, img_data, 'image/jpeg')
            audiofile.tag.save()

            print(f"[{idx}/{len(tracks)}] → saved '{artist} - {title}.mp3'")

        except Exception as e:
            print(f"[{idx}/{len(tracks)}] ▶ Error on '{artist} - {title}': {e}")

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
