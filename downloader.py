# -*- coding: utf-8 -*-
"""
downloader.py - YouTube video downloader usando yt-dlp

PATCH UTF-8:
  - outtmpl: forçado como string UTF-8 explícita para evitar crash em
    títulos com acentos (ex: "Análise do Mercado") quando o sistema
    usa locale ASCII.
  - Adicionado 'encoding': 'utf-8' nas opções do yt-dlp onde aplicável.
  - os.path.exists / os.listdir funcionam normalmente com UTF-8 no Linux,
    mas adicionamos str() explícito em paths para segurança cross-platform.
  - Verificação de arquivo com glob mais robusta para acentos no nome.
"""

import os
import logging
import yt_dlp
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("viral_cutter.downloader")


def download_youtube_video(
    url: str,
    output_dir: str,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> str:
    """
    Faz download de um vídeo do YouTube usando yt-dlp.

    CORREÇÃO UTF-8:
      - outtmpl agora usa Path com str() explícito.
      - Adicionada opção 'encoding': 'utf-8' para yt-dlp (garante que
        nomes de arquivo em UTF-8 sejam gravados corretamente).
      - A busca de fallback por arquivo usa Path.glob para compatibilidade
        cross-platform com nomes UTF-8.

    Args:
        url: URL do YouTube.
        output_dir: Diretório para salvar o vídeo.
        progress_callback: Callback opcional para progresso.

    Returns:
        Caminho do vídeo baixado.
    """
    output_dir = str(output_dir)  # garante str (suporte a Path objects)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        # FIX: formato de saída como str explícita — yt-dlp usa os.fsencode
        # internamente, mas o template precisa ser str, não bytes.
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'progress_hooks': [progress_callback] if progress_callback else [],
        'quiet': True,
        'no_warnings': True,
        # FIX: força encoding UTF-8 nos nomes de arquivo gerados pelo yt-dlp
        'encoding': 'utf-8',
        # Restringe caracteres problemáticos em nomes de arquivo de forma segura
        'restrictfilenames': False,   # True quebraria acentos; mantemos False
        'windowsfilenames': False,    # Não restringir em Linux
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Iniciando download do YouTube: {url}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            filename = str(filename)  # garante str

            # Garante que o arquivo existe (às vezes a extensão muda)
            if not os.path.exists(filename):
                base_name = os.path.splitext(filename)[0]
                base_path = Path(output_dir)
                # FIX: glob é UTF-8 safe no Python 3 no Linux/Windows
                found = list(base_path.glob(Path(base_name).name + "*"))
                if found:
                    filename = str(found[0])
                else:
                    # Fallback: busca qualquer mp4/mkv/webm baixado recentemente
                    candidates = sorted(
                        base_path.glob("*"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    mp4_candidates = [
                        p for p in candidates
                        if p.suffix.lower() in (".mp4", ".mkv", ".webm")
                    ]
                    if mp4_candidates:
                        filename = str(mp4_candidates[0])

            logger.info(f"Download concluído: {filename}")
            return filename

    except Exception as e:
        logger.error(f"Erro ao baixar vídeo do YouTube: {e}")
        raise RuntimeError(f"Falha no download: {str(e)}")


def get_video_info(url: str) -> dict:
    """
    Obtém metadados básicos do vídeo sem baixar.

    CORREÇÃO UTF-8:
      - Adicionada opção 'encoding': 'utf-8' para garantir que títulos com
        acentos sejam retornados como str Python e não bytes.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'encoding': 'utf-8',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)