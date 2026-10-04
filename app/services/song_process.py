import json
import tempfile
import time
import ffmpeg
from shazamio import Shazam
import yt_dlp
import httpx
import asyncio
import os
import eyed3
from functools import partial
from ytmusicapi import YTMusic

from app.config import config


class YtDownload():
    def __init__(self, data):
        self.data = data
        self.name = data["title"].replace("/", "-").replace(" ", "_").replace(".", "").lower()
        self.path = f"songs/{self.name}_{int(time.time())}.m4a"

    async def download_audio_from_id(self, video_id):
        loop = asyncio.get_running_loop()
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]',
            'outtmpl': self.path,
            'no_warnings': True,
            'noplaylist': True,
            'cookies': config.COOKIES_PATH,
            'ratelimit': 5_000_000,
            'throttled_rate': 2_000_000,
            'concurrent_fragment_downloads': 5,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            },
            'external_downloader': 'aria2c',
            'external_downloader_args': ['-x', '8', '-s', '8', '-k', '1M'],
            'geo_bypass': False,
            'noprogress': True,
            'nopart': True,
            'skip_download': False,
            'player_skip': ['web', 'ios', 'm3u8'],
            'extractor_args': {'youtube': {'player_client': ['tv']}}
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            download_func = partial(ydl.download, [video_url])
            await loop.run_in_executor(None, download_func)
    
    @staticmethod
    def is_supported(url):
        if config.IS_GENERIC_URL_OK:
            return True
        
        extractors = yt_dlp.extractor.gen_extractors()
        for e in extractors:
            if e.suitable(url) and e.IE_NAME != 'generic':
                return True
        return False
    
    @staticmethod
    async def download_audio_from_url(url, path):
        if not YtDownload.is_supported(url) or config.DOWNLOAD_URL_SIZE_IN_MG == 0:
            return None
        
        loop = asyncio.get_running_loop()
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': path.split(".")[0],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'max_filesize': config.DOWNLOAD_URL_SIZE_IN_MG * 1024 * 1024,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_func = partial(ydl.download, [url])
            await loop.run_in_executor(None, download_func)
            
        return path
            
    def get(self):
        return open(self.path, "rb")
    
    def remove(self):
        os.remove(self.path)


class Song:
    def __init__(self):
        pass
    
    @staticmethod
    async def extract_audio_from_video(video_path, delete=True):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
            temp_audio_path = temp_audio.name

        await asyncio.to_thread(
            lambda: ffmpeg.input(video_path)
            .output(temp_audio_path, format="mp3", acodec="mp3", audio_bitrate="128k")
            .run(overwrite_output=True, quiet=True)
        )
        
        if delete:
            os.remove(video_path)

        return temp_audio_path
    
    @staticmethod
    async def recognize(file_path, delete=True):
        shazam = Shazam()
        result = await shazam.recognize(file_path)
        
        if delete:
            os.remove(file_path)
            
        return result
    
    @staticmethod
    async def search(query, limit=10, offset=0):
        ytmusic = YTMusic()
        loop = asyncio.get_running_loop()
        
        if offset > 5:
            offset = 5

        adjusted_limit = limit * (offset + 1)

        results = await loop.run_in_executor(None, ytmusic.search, query, "songs", None, adjusted_limit)

        if not results:
            return [], False

        filtered_results = results[offset * limit:(offset + 1) * limit]

        video_ids = [song for song in filtered_results if "videoId" in song and song["duration_seconds"] < 700]
        
        has_more = len(results) >= adjusted_limit
        if offset == 4:
            has_more = False
            
        with open("test.json", "w") as f:
            f.write(json.dumps(video_ids, indent=4))

        return video_ids, has_more

    @staticmethod
    async def get(song):
        ytmusic = YTMusic()
        
        loop = asyncio.get_running_loop()
        search_results = await loop.run_in_executor(None, ytmusic.search, song, "songs")
        
        if search_results:
            song_info = search_results[0]
                
            return song_info
        
        return None
    
    @staticmethod
    async def get_lyrics(song_id):
        ytmusic = YTMusic()
        
        loop = asyncio.get_running_loop()
        search_info = await loop.run_in_executor(None, ytmusic.get_watch_playlist, song_id)
        if "lyrics" not in search_info:
            return None
        
        if not search_info["lyrics"]:
            return None
        
        result = await loop.run_in_executor(None, ytmusic.get_lyrics, search_info["lyrics"])
        lyrics = result["lyrics"]
        
        return lyrics
