"""
transcriber.py - Módulo de transcrição de áudio usando Whisper / Faster-Whisper
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("viral_cutter.transcriber")


@dataclass
class TranscriptSegment:
    """Representa um segmento transcrito com timestamps."""
    start: float
    end: float
    text: str
    words: list[dict] = field(default_factory=list)  # palavra-nível se disponível

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_block_line(self) -> str:
        return f"[{self.start:.2f} - {self.end:.2f}] {self.text.strip()}"


@dataclass
class TranscriptionResult:
    """Resultado completo de uma transcrição."""
    segments: list[TranscriptSegment]
    language: str
    audio_duration: float

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)

    def get_segments_in_range(self, start: float, end: float) -> list[TranscriptSegment]:
        """Retorna segmentos dentro de um intervalo de tempo."""
        return [s for s in self.segments if s.start >= start and s.end <= end]

    def to_block_text(self, start: float, end: float) -> str:
        """Gera texto formatado com timestamps para um intervalo."""
        segs = self.get_segments_in_range(start, end)
        return "\n".join(s.to_block_line() for s in segs)


def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """
    Extrai o áudio de um vídeo usando FFmpeg.

    Args:
        video_path: Caminho do vídeo de entrada
        output_path: Caminho de saída do áudio (opcional, usa temp se None)

    Returns:
        Caminho do arquivo de áudio gerado
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()

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
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600  # 10 minutos máximo
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou: {result.stderr}")
        logger.info("Áudio extraído com sucesso.")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout ao extrair áudio (mais de 10 minutos).")


def transcribe_with_faster_whisper(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
    compute_type: str = "int8"
) -> TranscriptionResult:
    """
    Transcreve áudio usando faster-whisper (mais rápido que Whisper padrão).

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

    logger.info(f"Carregando modelo faster-whisper: {model_size} | device={device} | compute={compute_type}")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    logger.info("Iniciando transcrição...")

    transcribe_kwargs = {
        "word_timestamps": True,
        "beam_size": 5,
        "vad_filter": True,       # filtro de silêncio automático
        "vad_parameters": {
            "min_silence_duration_ms": 500,
        }
    }
    if language:
        transcribe_kwargs["language"] = language

    segments_gen, info = model.transcribe(audio_path, **transcribe_kwargs)

    detected_language = info.language
    audio_duration = info.duration
    logger.info(f"Idioma detectado: {detected_language} | Duração: {audio_duration:.1f}s")

    segments: list[TranscriptSegment] = []
    last_log_time = 0.0
    
    for seg in segments_gen:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability
                })

        segments.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            words=words
        ))
        
        # Log de progresso a cada 30 segundos de áudio
        if seg.end - last_log_time >= 30:
            percent = (seg.end / audio_duration) * 100
            logger.info(f"  > Processado: {percent:.1f}% ({int(seg.end)}s / {int(audio_duration)}s)")
            last_log_time = seg.end

    logger.info(f"Transcrição concluída: {len(segments)} segmentos")
    return TranscriptionResult(
        segments=segments,
        language=detected_language,
        audio_duration=audio_duration
    )


def transcribe_with_whisper(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu"
) -> TranscriptionResult:
    """
    Transcreve áudio usando openai-whisper (fallback).

    Args:
        audio_path: Caminho do arquivo de áudio
        model_size: Tamanho do modelo
        language: Código do idioma ou None
        device: 'cpu' ou 'cuda'

    Returns:
        TranscriptionResult com todos os segmentos
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "openai-whisper não encontrado. Instale com: pip install openai-whisper"
        )

    logger.info(f"Carregando modelo whisper: {model_size} | device={device}")
    model = whisper.load_model(model_size, device=device)

    logger.info("Iniciando transcrição (openai-whisper)...")

    options = {"word_timestamps": True}
    if language:
        options["language"] = language

    result = model.transcribe(audio_path, **options)

    detected_language = result.get("language", "unknown")
    logger.info(f"Idioma detectado: {detected_language}")

    segments: list[TranscriptSegment] = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w.get("word", ""),
                "start": w.get("start", seg["start"]),
                "end": w.get("end", seg["end"]),
                "probability": w.get("probability", 1.0)
            })

        segments.append(TranscriptSegment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"],
            words=words
        ))

    # Estima duração do áudio
    audio_duration = segments[-1].end if segments else 0.0
    logger.info(f"Transcrição concluída: {len(segments)} segmentos")

    return TranscriptionResult(
        segments=segments,
        language=detected_language,
        audio_duration=audio_duration
    )


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    language: Optional[str] = None,
    device: str = "cpu",
    backend: str = "auto"
) -> TranscriptionResult:
    """
    Transcreve áudio escolhendo automaticamente faster-whisper ou whisper padrão.

    Args:
        audio_path: Caminho do arquivo de áudio
        model_size: Tamanho do modelo
        language: Código do idioma ou None para detecção automática
        device: 'cpu' ou 'cuda'
        backend: 'auto', 'faster-whisper', ou 'whisper'

    Returns:
        TranscriptionResult
    """
    if backend == "auto" or backend == "faster-whisper":
        try:
            return transcribe_with_faster_whisper(
                audio_path, model_size, language, device
            )
        except ImportError:
            if backend == "faster-whisper":
                raise
            logger.warning("faster-whisper não disponível. Tentando openai-whisper...")

    return transcribe_with_whisper(audio_path, model_size, language, device)


def split_transcript_into_blocks(
    transcript: TranscriptionResult,
    block_duration: float = 360.0,   # 6 minutos por bloco
    overlap: float = 30.0             # 30s de overlap para contexto
) -> list[dict]:
    """
    Divide a transcrição em blocos menores para enviar ao Ollama.

    Args:
        transcript: Resultado da transcrição completa
        block_duration: Duração máxima de cada bloco em segundos
        overlap: Sobreposição entre blocos para manter contexto

    Returns:
        Lista de dicts com 'start', 'end', 'text' de cada bloco
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
            "segment_count": len(segs_in_block)
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
    """Salva a transcrição completa em arquivo de texto."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Transcrição\n")
        f.write(f"# Idioma: {transcript.language}\n")
        f.write(f"# Duração: {transcript.audio_duration:.1f}s\n\n")
        for seg in transcript.segments:
            f.write(seg.to_block_line() + "\n")
    logger.info(f"Transcrição salva em: {output_path}")