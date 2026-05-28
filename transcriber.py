# -*- coding: utf-8 -*-
"""
transcriber.py - Módulo de transcrição de áudio usando Whisper / Faster-Whisper

PATCH UTF-8:
  - subprocess.run: adicionado encoding="utf-8", errors="replace" em extract_audio()
  - save_transcript: adicionado encoding="utf-8" explícito no open()
  - Todos os stdout/stderr tratados como UTF-8 com fallback "replace"
  - PYTHONIOENCODING e PYTHONUTF8 injetados no ambiente dos subprocessos
"""

import os
import sys
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("viral_cutter.transcriber")


# ─── Ambiente UTF-8 para subprocessos ────────────────────────────────────────

def _utf8_env() -> dict:
    """
    Retorna uma cópia do ambiente atual com variáveis que forçam UTF-8
    em todos os subprocessos (Python filho, FFmpeg, etc.).
    Essencial para Void Linux / sistemas com locale mal configurado.
    """
    env = os.environ.copy()
    env.setdefault("LANG", "pt_BR.UTF-8")
    env.setdefault("LC_ALL", "pt_BR.UTF-8")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"       # PEP 540 - força UTF-8 mode no Python >= 3.7
    return env


# ─── DataClasses ─────────────────────────────────────────────────────────────

@dataclass
class TranscriptSegment:
    """Representa um segmento transcrito com timestamps."""
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)   # palavra-nível se disponível
    # Nota: list[dict] causa SyntaxError em Python < 3.9; usando 'list' genérico

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_block_line(self) -> str:
        return f"[{self.start:.2f} - {self.end:.2f}] {self.text.strip()}"


@dataclass
class TranscriptionResult:
    """Resultado completo de uma transcrição."""
    segments: list
    language: str
    audio_duration: float

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)

    def get_segments_in_range(self, start: float, end: float) -> list:
        """Retorna segmentos dentro de um intervalo de tempo."""
        return [s for s in self.segments if s.start >= start and s.end <= end]

    def to_block_text(self, start: float, end: float) -> str:
        """Gera texto formatado com timestamps para um intervalo."""
        segs = self.get_segments_in_range(start, end)
        return "\n".join(s.to_block_line() for s in segs)


# ─── Extração de áudio ────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """
    Extrai o áudio de um vídeo usando FFmpeg.

    CORREÇÃO UTF-8:
      - encoding="utf-8" + errors="replace" no subprocess.run
      - env=_utf8_env() para garantir LC_ALL=UTF-8 no processo filho
      - stderr/stdout nunca passam por codec ASCII implícito

    Args:
        video_path: Caminho do vídeo de entrada (pode ter acentos)
        output_path: Caminho de saída do áudio (opcional, usa temp se None)

    Returns:
        Caminho do arquivo de áudio gerado
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()

    # Converte para string explicitamente (suporte a Path objects com acentos)
    video_path = str(video_path)
    output_path = str(output_path)

    logger.info(f"Extraindo áudio de: {video_path}")
    logger.info(f"Destino do áudio: {output_path}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",                    # sem vídeo
        "-acodec", "pcm_s16le",  # WAV não comprimido
        "-ar", "16000",           # 16kHz (ideal para Whisper)
        "-ac", "1",               # mono
        "-y",                     # sobrescrever
        output_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            # FIX CRÍTICO: encoding + errors evitam o crash de codec ASCII
            # quando o stderr do FFmpeg contém o nome do arquivo com acentos.
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,           # 10 minutos máximo
            env=_utf8_env(),       # FIX: garante LC_ALL=UTF-8 no processo filho
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou: {result.stderr}")
        logger.info("Áudio extraído com sucesso.")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout ao extrair áudio (mais de 10 minutos).")


# ─── Transcrição faster-whisper ───────────────────────────────────────────────

def transcribe_with_faster_whisper(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
    compute_type: str = "int8"
) -> TranscriptionResult:
    """
    Transcreve áudio usando faster-whisper (mais rápido que Whisper padrão).

    CORREÇÃO UTF-8:
      - Nenhum encode/decode explícito necessário: faster-whisper devolve str Python
        nativas (unicode). O problema era UPSTREAM: o FFmpeg sendo chamado sem
        encoding=utf-8 corrompia o pipe antes de chegar aqui.
      - Adicionado PYTHONIOENCODING no ambiente do processo pai antes de importar.

    Args:
        audio_path: Caminho do arquivo de áudio
        model_size: Tamanho do modelo (tiny, base, small, medium, large-v2, large-v3)
        language: Código do idioma (pt, en, etc.) ou None para detecção automática
        device: 'cpu' ou 'cuda'
        compute_type: 'int8', 'float16', 'float32'

    Returns:
        TranscriptionResult com todos os segmentos
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster-whisper não encontrado. Instale com: pip install faster-whisper"
        )

    # FIX: garante que o stdout/stderr do processo atual está em UTF-8
    # Necessário quando Python é iniciado sem PYTHONUTF8=1
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Alguns ambientes não suportam reconfigure

    logger.info(
        f"Carregando modelo faster-whisper: {model_size} "
        f"| device={device} | compute={compute_type}"
    )

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        cpu_threads=os.cpu_count() or 4,
        num_workers=2,
    )

    logger.info("Iniciando transcrição...")

    transcribe_kwargs = {
        "word_timestamps": True,
        "beam_size": 5,
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
        },
    }
    if language:
        transcribe_kwargs["language"] = language

    def load_audio_numpy(path: str):
        import numpy as np
        # FIX: Carrega áudio via FFmpeg puro para bypassar bug de encoding do PyAV
        cmd = [
            "ffmpeg", "-i", path,
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", "-"
        ]
        proc = subprocess.run(cmd, capture_output=True, check=True, env=_utf8_env())
        return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0

    audio_data = load_audio_numpy(audio_path)
    segments_gen, info = model.transcribe(audio_data, **transcribe_kwargs)

    detected_language = info.language
    audio_duration = info.duration
    logger.info(
        f"Idioma detectado: {detected_language} | Duração: {audio_duration:.1f}s"
    )

    segments: list = []
    last_log_time = 0.0

    for seg in segments_gen:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,           # str unicode nativa
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                })

        # FIX: seg.text já é str unicode; não há necessidade de decode,
        # mas garantimos que não seja bytes acidental
        seg_text = seg.text
        if isinstance(seg_text, bytes):
            seg_text = seg_text.decode("utf-8", errors="replace")

        segments.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg_text,
            words=words,
        ))

        if seg.end - last_log_time >= 30:
            percent = (seg.end / audio_duration) * 100
            logger.info(
                f"  > Processado: {percent:.1f}% "
                f"({int(seg.end)}s / {int(audio_duration)}s)"
            )
            last_log_time = seg.end

    logger.info(f"Transcrição concluída: {len(segments)} segmentos")
    return TranscriptionResult(
        segments=segments,
        language=detected_language,
        audio_duration=audio_duration,
    )


# ─── Transcrição openai-whisper (fallback) ────────────────────────────────────

def transcribe_with_whisper(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
) -> TranscriptionResult:
    """
    Transcreve áudio usando openai-whisper (fallback).

    CORREÇÃO UTF-8:
      - Mesma garantia de sys.stdout/stderr em UTF-8.
      - w.get("word", "") nunca retorna bytes no openai-whisper,
        mas adicionamos guard defensivo.
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "openai-whisper não encontrado. Instale com: pip install openai-whisper"
        )

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger.info(f"Carregando modelo whisper: {model_size} | device={device}")
    model = whisper.load_model(model_size, device=device)

    logger.info("Iniciando transcrição (openai-whisper)...")

    options = {"word_timestamps": True}
    if language:
        options["language"] = language

    def load_audio_numpy(path: str):
        import numpy as np
        cmd = [
            "ffmpeg", "-i", path,
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", "-"
        ]
        proc = subprocess.run(cmd, capture_output=True, check=True, env=_utf8_env())
        return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0

    audio_data = load_audio_numpy(audio_path)
    result = model.transcribe(audio_data, **options)

    detected_language = result.get("language", "unknown")
    logger.info(f"Idioma detectado: {detected_language}")

    segments: list = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []):
            word_text = w.get("word", "")
            # Guard defensivo: garante str
            if isinstance(word_text, bytes):
                word_text = word_text.decode("utf-8", errors="replace")
            words.append({
                "word": word_text,
                "start": w.get("start", seg["start"]),
                "end": w.get("end", seg["end"]),
                "probability": w.get("probability", 1.0),
            })

        seg_text = seg.get("text", "")
        if isinstance(seg_text, bytes):
            seg_text = seg_text.decode("utf-8", errors="replace")

        segments.append(TranscriptSegment(
            start=seg["start"],
            end=seg["end"],
            text=seg_text,
            words=words,
        ))

    audio_duration = segments[-1].end if segments else 0.0
    logger.info(f"Transcrição concluída: {len(segments)} segmentos")

    return TranscriptionResult(
        segments=segments,
        language=detected_language,
        audio_duration=audio_duration,
    )


# ─── Dispatcher ───────────────────────────────────────────────────────────────

def transcribe(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
    backend: str = "auto",
) -> TranscriptionResult:
    """
    Transcreve áudio escolhendo automaticamente faster-whisper ou whisper padrão.
    """
    if backend in ("auto", "faster-whisper"):
        try:
            return transcribe_with_faster_whisper(
                audio_path, model_size, language, device
            )
        except ImportError:
            if backend == "faster-whisper":
                raise
            logger.warning(
                "faster-whisper não disponível. Tentando openai-whisper..."
            )

    return transcribe_with_whisper(audio_path, model_size, language, device)


def transcribe_any(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
    backend: str = "auto",
) -> list:
    """
    Função de conveniência que retorna apenas a lista de dicionários de segmentos,
    compatível com o novo sistema de descoberta viral.
    """
    result = transcribe(audio_path, model_size, language, device, backend)
    
    # Converte TranscriptionResult para lista de dicts (formato esperado)
    segments_list = []
    for s in result.segments:
        segments_list.append({
            "start": s.start,
            "end": s.end,
            "text": s.text
        })
    return segments_list


# ─── Utilitários ──────────────────────────────────────────────────────────────

def split_transcript_into_blocks(
    transcript: TranscriptionResult,
    block_duration: float = 360.0,
    overlap: float = 30.0,
) -> list:
    """
    Divide a transcrição em blocos menores para enviar ao Ollama.
    """
    if not transcript.segments:
        return []

    total_duration = transcript.audio_duration
    blocks = []
    block_start = 0.0

    while block_start < total_duration:
        block_end = min(block_start + block_duration, total_duration)

        segs_in_block = [
            s for s in transcript.segments
            if s.start >= block_start and s.start < block_end
        ]

        if not segs_in_block:
            block_start += block_duration - overlap
            continue

        block_text = "\n".join(s.to_block_line() for s in segs_in_block)

        blocks.append({
            "start": block_start,
            "end": block_end,
            "text": block_text,
            "segment_count": len(segs_in_block),
        })

        logger.debug(
            f"Bloco {len(blocks)}: {block_start:.0f}s-{block_end:.0f}s "
            f"({len(segs_in_block)} segmentos)"
        )

        if block_end >= total_duration:
            break

        block_start += block_duration - overlap

    logger.info(f"Transcrição dividida em {len(blocks)} blocos")
    return blocks


def save_transcript(transcript: TranscriptionResult, output_path: str) -> None:
    """
    Salva a transcrição completa em arquivo de texto.

    CORREÇÃO UTF-8:
      - encoding="utf-8" explícito no open() — sem isso Python usa o codec
        do locale, que em alguns ambientes pode ser ASCII ou latin-1,
        causando UnicodeEncodeError ao escrever acentos.
    """
    output_path = str(output_path)  # suporte a Path objects
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Transcrição\n")
        f.write(f"# Idioma: {transcript.language}\n")
        f.write(f"# Duração: {transcript.audio_duration:.1f}s\n\n")
        for seg in transcript.segments:
            f.write(seg.to_block_line() + "\n")
    logger.info(f"Transcrição salva em: {output_path}")