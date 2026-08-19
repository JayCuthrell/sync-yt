import yt_dlp
import subprocess
import json
import os
import email.utils
import time
import argparse
from pydub import AudioSegment

# Use the ACTUAL webpage URL for your channel or playlist, NOT the XML feed URL
YOUTUBE_URL = "https://www.youtube.com/playlist?list=PLbyE_u-MMuTvTa3AYInWSZwcDTw6nL-fR"

AUDIO_DIR = "src/assets/audio"
OUTPUT_JSON = "src/_data/youtubePodcast.json"
COOKIE_FILE = "src/_data/youtube_cookies.txt"

# Setup command line arguments
parser = argparse.ArgumentParser(description="Build podcast feed and optionally optimize audio.")
parser.add_argument("--optimize-audio", action="store_true", help="Apply volume matching to audio files")
args = parser.parse_args()

# Ensure output directories exist on your Mac before saving
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

print(f"Fetching metadata for all videos in {YOUTUBE_URL}...")

# Configure yt-dlp to extract the metadata without downloading the audio just yet
ydl_opts = {
    'cookiefile': COOKIE_FILE,
    'extract_flat': False,  # False forces yt-dlp to grab full descriptions and dates for every video
    'quiet': True,
    'ignoreerrors': True,   # Skip deleted/private videos without crashing the script
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    playlist_info = ydl.extract_info(YOUTUBE_URL, download=False)

# Safety check: Did yt-dlp successfully parse the playlist?
if not playlist_info or 'entries' not in playlist_info:
    print("Error: Could not retrieve videos. Check your URL or cookies.")
    exit(1)

podcast_data = {
    "title": playlist_info.get('title', 'Fudge.org Podcast'),
    "link": "https://fudge.org",
    "items": []
}

# Filter out any 'None' entries (which happen if a video is hidden or deleted)
entries = [e for e in playlist_info['entries'] if e is not None]
print(f"Found {len(entries)} videos. Processing...")

for entry in entries:
    video_id = entry.get('id')
    audio_filename = f"{video_id}.mp3"
    audio_path = os.path.join(AUDIO_DIR, audio_filename)
    video_url = entry.get('webpage_url', f"https://www.youtube.com/watch?v={video_id}")
    
    # Download the audio using the static cookie file and Homebrew Node.js runtime
    if not os.path.exists(audio_path):
        print(f"Downloading audio for {video_id}...")
        subprocess.run([
            "yt-dlp",
            "--extract-audio", 
            "--audio-format", "mp3",
            "--cookies", COOKIE_FILE,
            "--js-runtimes", "node:/opt/homebrew/bin/node",
            "--extractor-args", "youtube:player_client=android",
            "-o", audio_path,
            video_url
        ])
    else:
        print(f"Audio for {video_id} already exists. Skipping download.")

        # Ensure the audio matches our reference dynamics and overwrite the file
        REFERENCE_FILE = "reference_podcast.mp3" # Update with your actual reference file path
        if os.path.exists(REFERENCE_FILE) and os.path.exists(audio_path):
            print(f"Applying dynamic volume matching to {audio_filename}...")
            ref_audio = AudioSegment.from_file(REFERENCE_FILE)
            current_audio = AudioSegment.from_file(audio_path)
            
            # Calculate difference and compress
            gain_adjustment = ref_audio.dBFS - current_audio.dBFS
            optimized_audio = current_audio.apply_gain(gain_adjustment).compress_dynamic_range()
            
            # Overwrite the existing MP3 without changing its name
            optimized_audio.export(audio_path, format="mp3", bitrate="192k")
    
    # Apple Podcasts requires an accurate file length in bytes
    file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    
    # Convert yt-dlp's UNIX timestamp to Apple's required RFC 2822 format
    video_timestamp = entry.get('timestamp', time.time())
    rfc2822_date = email.utils.formatdate(video_timestamp)

    podcast_data["items"].append({
        "title": entry.get('title', 'Unknown Title'),
        "link": video_url,
        "pubDate": rfc2822_date,
        "guid": video_id,
        "description": entry.get('description', ''),
        "audio_url": f"https://fudge.org/assets/audio/{audio_filename}",
        "audio_size": file_size
    })

print("Writing metadata to JSON...")
with open(OUTPUT_JSON, "w") as f:
    json.dump(podcast_data, f, indent=2)

print("Local build complete!")
