"""
utils.py - Funções utilitárias compartilhadas do sistema Viral Cutter
"""

import os
import re
import logging
import subprocess
import json
from pathlib import Path
from typing import Optional


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Configura e retorna um logger padronizado para o sistema.
    """
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )
    return logging.getLogger("viral_cutter")


def seconds_to_srt_time(seconds: float) -> str:
    """
    Converte segundos (float) para o formato de tempo SRT: HH:MM:SS,mmm
    """
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def seconds_to_hms(seconds: float) -> str:
    """
    Converte segundos para string legível HH:MM:SS
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(name: str, max_length: int = 60) -> str:
    """
    Remove caracteres inválidos de um nome de arquivo.
    """
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"[^\w\-_.]", "", name)
    return name[:max_length]


def ensure_dir(path: str | Path) -> Path:
    """
    Garante que um diretório existe, criando-o se necessário.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def check_ffmpeg() -> bool:
    """
    Verifica se o FFmpeg está disponível no sistema.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_ollama() -> bool:
    """
    Verifica se o Ollama está rodando localmente.
    """
    try:
        import urllib.request
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        return req.status == 200
    except Exception:
        return False


def get_video_duration(video_path: str) -> float:
    """
    Obtém a duração de um vídeo em segundos via FFprobe.
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Erro ao obter duração do vídeo: {e}")


def get_video_info(video_path: str) -> dict:
    """
    Retorna informações completas do vídeo (duração, resolução, fps, codec).
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        data = json.loads(result.stdout)

        info = {
            "duration": float(data["format"].get("duration", 0)),
            "size_bytes": int(data["format"].get("size", 0)),
            "width": None,
            "height": None,
            "fps": None,
            "video_codec": None,
            "audio_codec": None,
        }

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                info["width"] = stream.get("width")
                info["height"] = stream.get("height")
                info["video_codec"] = stream.get("codec_name")
                fps_str = stream.get("r_frame_rate", "0/1")
                try:
                    num, den = fps_str.split("/")
                    info["fps"] = round(int(num) / int(den), 2)
                except Exception:
                    pass
            elif stream.get("codec_type") == "audio":
                info["audio_codec"] = stream.get("codec_name")

        return info
    except Exception as e:
        raise RuntimeError(f"Erro ao obter informações do vídeo: {e}")


def parse_ollama_json_response(raw_response: str) -> list[dict]:
    """
    Tenta extrair um JSON válido da resposta do Ollama.
    Lida com respostas que contenham texto antes/depois do JSON.
    """
    raw_response = raw_response.strip()

    # Tenta parse direto
    try:
        data = json.loads(raw_response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    # Tenta encontrar array JSON dentro do texto
    pattern = r'\[\s*\{.*?\}\s*\]'
    matches = re.findall(pattern, raw_response, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    # Tenta encontrar objeto JSON isolado
    pattern_obj = r'\{[^{}]*\}'
    objects = re.findall(pattern_obj, raw_response, re.DOTALL)
    parsed_objects = []
    for obj in objects:
        try:
            parsed_objects.append(json.loads(obj))
        except json.JSONDecodeError:
            continue

    if parsed_objects:
        return parsed_objects

    raise ValueError(f"Não foi possível extrair JSON válido da resposta. Início: {raw_response[:300]}")


def format_size(size_bytes: int) -> str:
    """
    Formata tamanho em bytes para string legível.
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Limita um valor entre min e max."""
    return max(min_val, min(max_val, value))