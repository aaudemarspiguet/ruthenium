import os
import yt_dlp as youtube_dl
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import Picture
import urllib.request
from pathvalidate import sanitize_filename
import tekore as tk


def songs_downloader(sp: tk.Spotify, folder: str, tracks: list, quality='320'):
    """
    Download and tag a list of Spotify tracks as audio files (mp3, m4a, webm, etc.).

    sp:      Authenticated tekore.Spotify client
    folder: Top-level folder to place downloads
    tracks: List of tekore.FullTrack objects
    quality: Audio quality ('190' or '320')
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': None,  # set per track
        'logger': None,
    }

    for index, track in enumerate(tracks, start=1):
        title  = sanitize_filename(track.name)
        artist = sanitize_filename(track.artists[0].name)
        album  = sanitize_filename(track.album.name)

        print(f"[{index}/{len(tracks)}] Downloading: {artist} - {title}")
        ydl_opts['outtmpl'] = os.path.join(folder, f"{artist} - {title}.%(ext)s")

        os.makedirs(folder, exist_ok=True)
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"ytsearch1:{title} {artist}", download=True)
                info = result['entries'][0] if 'entries' in result else result
                downloaded_file = ydl.prepare_filename(info)
        except Exception as e:
            print(f"   ▶ Error downloading '{artist} - {title}': {e}")
            continue

        # Tagging with mutagen
        try:
            audio = MutagenFile(downloaded_file, easy=True)
            if audio is None:
                print(f"   ▶ Could not open file for tagging: {downloaded_file}")
                continue

            # Universal tags
            audio['title'] = title
            audio['artist'] = artist
            audio['album'] = album
            audio['albumartist'] = track.album.artists[0].name
            genres = sp.artist(track.artists[0].id).genres
            if genres:
                audio['genre'] = genres[-1]
            audio['tracknumber'] = str(track.track_number)
            audio.save()

            # Add cover art (format-specific)
            img_url = track.album.images[0].url if track.album.images else None
            if img_url:
                img_data = urllib.request.urlopen(img_url).read()
                ext = os.path.splitext(downloaded_file)[1].lower()
                if ext == '.mp3':
                    id3 = ID3(downloaded_file)
                    id3.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data
                    ))
                    id3.save()
                elif ext == '.m4a':
                    mp4 = MP4(downloaded_file)
                    mp4['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                    mp4.save()
                elif ext == '.flac':
                    flac = MutagenFile(downloaded_file)
                    pic = Picture()
                    pic.data = img_data
                    pic.type = 3
                    pic.mime = 'image/jpeg'
                    flac.add_picture(pic)
                    flac.save()
                # webm/opus/ogg: cover art not widely supported

            print(f" → saved to {downloaded_file}")
        except Exception as e:
            print(f"   ▶ Error tagging '{artist} - {title}': {e}")


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
