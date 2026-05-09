"""
utils.py - Funções utilitárias compartilhadas do sistema Viral Cutter

PATCH UTF-8:
  - setup_logging: StreamHandler agora usa UTF-8 explícito (evita UnicodeEncodeError
    ao logar emojis/acentos no terminal quando PYTHONIOENCODING não está definido)
  - FileHandler: encoding="utf-8" explícito
  - subprocess.run em check_ffmpeg / get_video_duration / get_video_info:
    encoding="utf-8", errors="replace" + env com PYTHONUTF8=1
  - Adicionada função _utf8_env() compartilhada
  - parse_ollama_json_response: guard defensivo para bytes inesperados
"""

import os
import re
import sys
import logging
import subprocess
import json
from pathlib import Path
from typing import Optional


# ─── Ambiente UTF-8 para subprocessos ─────────────────────────────────────────

def _utf8_env() -> dict:
    """
    Retorna cópia do ambiente atual forçando UTF-8 em subprocessos.
    Previne crash de codec ASCII quando paths têm acentos (ex: títulos do YouTube).
    """
    env = os.environ.copy()
    env.setdefault("LANG", "pt_BR.UTF-8")
    env.setdefault("LC_ALL", "pt_BR.UTF-8")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


# ─── Logging ──────────────────────────────────────────────────────────────────

def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configura e retorna um logger padronizado para o sistema.

    CORREÇÃO UTF-8:
      - StreamHandler: força encoding UTF-8 via stream reconfigure.
        Sem isso, no Void Linux com terminal LANG=C ou pipe redirecionado,
        qualquer logger.info("Iniciando transcrição...") com emoji (⬛) ou
        o nome do arquivo com acento causa:
            UnicodeEncodeError: 'ascii' codec can't encode character
      - FileHandler: encoding="utf-8" explícito.
    """
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Handler de console com UTF-8 garantido
    console_handler = logging.StreamHandler(sys.stdout)
    # Reconfigura o stream para UTF-8 se o terminal não suportar
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    console_handler.setFormatter(
        logging.Formatter(log_format, datefmt=date_format)
    )

    handlers: list = [console_handler]

    if log_file:
        # FIX: encoding="utf-8" obrigatório — sem isso o FileHandler usa o
        # codec do locale, podendo ser ASCII em sistemas sem UTF-8 configurado.
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(log_format, datefmt=date_format)
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,  # Reseta handlers existentes para evitar duplicatas
    )
    return logging.getLogger("viral_cutter")


# ─── Formatação de tempo ───────────────────────────────────────────────────────

def seconds_to_srt_time(seconds: float) -> str:
    """Converte segundos (float) para o formato de tempo SRT: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def seconds_to_hms(seconds: float) -> str:
    """Converte segundos para string legível HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# ─── Sanitização de nomes de arquivo ─────────────────────────────────────────

def sanitize_filename(name: str, max_length: int = 60) -> str:
    """
    Remove caracteres inválidos de um nome de arquivo.

    NOTA: a função original já estava correta. Mantida sem alteração funcional,
    mas agora aceita explicitamente str unicode.
    """
    # Garante que é string unicode (não bytes)
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"[^\w\-_.]", "", name)
    return name[:max_length]


# ─── Diretórios ───────────────────────────────────────────────────────────────

def ensure_dir(path) -> Path:
    """
    Garante que um diretório existe, criando-o se necessário.
    Aceita str ou Path, inclusive com caracteres UTF-8.
    """
    p = Path(str(path))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── Verificações de dependências ────────────────────────────────────────────

def check_ffmpeg() -> bool:
    """
    Verifica se o FFmpeg está disponível no sistema.

    CORREÇÃO UTF-8:
      - encoding="utf-8" + errors="replace" para que a saída de versão do
        FFmpeg (que pode conter hífens/caracteres não-ASCII) não quebre.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=_utf8_env(),
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_ollama() -> bool:
    """Verifica se o Ollama está rodando localmente."""
    try:
        import urllib.request
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        return req.status == 200
    except Exception:
        return False


# ─── Informações de vídeo ────────────────────────────────────────────────────

def get_video_duration(video_path: str) -> float:
    """
    Obtém a duração de um vídeo em segundos via FFprobe.

    CORREÇÃO UTF-8:
      - encoding="utf-8" + errors="replace" no subprocess.run.
      - video_path convertido para str (suporte a Path objects com acentos).
    """
    video_path = str(video_path)
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=_utf8_env(),
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Erro ao obter duração do vídeo: {e}")


def get_video_info(video_path: str) -> dict:
    """
    Retorna informações completas do vídeo (duração, resolução, fps, codec).

    CORREÇÃO UTF-8:
      - encoding="utf-8" + errors="replace" no subprocess.run.
      - video_path convertido para str (suporte a Path objects com acentos).
    """
    video_path = str(video_path)
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=_utf8_env(),
        )
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


# ─── Parsing da resposta do Ollama ───────────────────────────────────────────

def parse_ollama_json_response(raw_response: str) -> list:
    """
    Tenta extrair um JSON válido da resposta do Ollama.
    Lida com respostas que contenham texto antes/depois do JSON.

    CORREÇÃO UTF-8:
      - Guard defensivo: se raw_response chegar como bytes (bug de integração),
        decode para utf-8 antes de processar.
    """
    # Guard defensivo: garante str
    if isinstance(raw_response, bytes):
        raw_response = raw_response.decode("utf-8", errors="replace")

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

    raise ValueError(
        f"Não foi possível extrair JSON válido da resposta. "
        f"Início: {raw_response[:300]}"
    )


# ─── Utilitários gerais ───────────────────────────────────────────────────────

def format_size(size_bytes: int) -> str:
    """Formata tamanho em bytes para string legível."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Limita um valor entre min e max."""
    return max(min_val, min(max_val, value))