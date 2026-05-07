# downloader.py - YouTube video downloader using yt-dlp

import os
import logging
import yt_dlp
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("viral_cutter.downloader")

def download_youtube_video(
    url: str, 
    output_dir: str, 
    progress_callback: Optional[Callable[[dict], None]] = None
) -> str:
    """
    Downloads a video from YouTube using yt-dlp.
    
    Args:
        url: The YouTube URL.
        output_dir: Directory to save the video.
        progress_callback: Optional callback for progress updates.
        
    Returns:
        The path to the downloaded video.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Configurações do yt-dlp
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'progress_hooks': [progress_callback] if progress_callback else [],
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Iniciando download do YouTube: {url}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Garante que o arquivo existe (às vezes a extensão muda ligeiramente)
            if not os.path.exists(filename):
                # Tenta encontrar o arquivo na pasta
                base_name = os.path.splitext(filename)[0]
                for f in os.listdir(output_dir):
                    if f.startswith(os.path.basename(base_name)):
                        filename = os.path.join(output_dir, f)
                        break
            
            logger.info(f"Download concluído: {filename}")
            return filename
            
    except Exception as e:
        logger.error(f"Erro ao baixar vídeo do YouTube: {e}")
        raise RuntimeError(f"Falha no download: {str(e)}")

def get_video_info(url: str) -> dict:
    """
    Obtém metadados básicos do vídeo sem baixar.
    """
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)
