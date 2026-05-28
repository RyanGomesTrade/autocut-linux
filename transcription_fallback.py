import os
import logging
import subprocess
import tempfile
import hashlib
import sys
from transcriber import transcribe_any

logger = logging.getLogger("transcription_fallback")

class MockSnippet:
    """ Mock object to match the interface of FetchedTranscriptSnippet """
    def __init__(self, text, start, duration):
        self.text = text
        self.start = start
        self.duration = duration

def check_external_tools():
    """ Startup validation for essential tools """
    tools = ["ffmpeg", "yt-dlp"]
    health = {}
    for tool in tools:
        try:
            res = subprocess.run([tool, "--version"], capture_output=True, text=True)
            health[tool] = res.returncode == 0
            logger.info(f"✅ {tool} detectado.")
        except FileNotFoundError:
            health[tool] = False
            logger.error(f"❌ {tool} NÃO encontrado no PATH.")
    return health

def get_audio_fingerprint(file_path):
    """ Generates a unique hash for the audio file to avoid redundant transcription """
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            buf = f.read(1024 * 1024)
            hasher.update(buf)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Erro ao gerar fingerprint: {e}")
        return "error_hash"

def download_audio_sample(video_id, intervals=None):
    """
    Downloads strategic audio samples from a YouTube video.
    Improved with better logging, stderr capture, and fallback downloader.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"sample_{video_id}.mp3")
    
    if os.path.exists(output_path):
        logger.info(f"♻️ Usando cache de áudio local: {output_path}")
        return output_path

    if not intervals:
        intervals = [("00:00:00", "60")]

    logger.info(f"📥 Baixando amostragem estratégica ({len(intervals)} segmentos) para {video_id}...")
    
    segment_files = []
    for i, (start, duration) in enumerate(intervals):
        seg_path = os.path.join(temp_dir, f"seg_{i}_{video_id}.mp3")
        
        # Estratégia 1: Direto com yt-dlp e ffmpeg postprocessor
        cmd = [
            "yt-dlp",
            "-f", "ba",
            "--extract-audio",
            "--audio-format", "mp3",
            "--external-downloader", "ffmpeg",
            "--external-downloader-args", f"ffmpeg_i:-ss {start} -t {duration}",
            "-o", seg_path,
            video_url
        ]
        
        try:
            logger.debug(f"Executando: {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if res.returncode != 0:
                logger.warning(f"⚠️ Falha no download segmentado (i={i}). Tentando fallback sem external-downloader...")
                # Estratégia 2: Fallback sem external-downloader (mais lento mas mais compatível)
                cmd_fallback = [
                    "yt-dlp", "-f", "ba", "-x", "--audio-format", "mp3",
                    "-o", seg_path, video_url
                ]
                # Nota: Aqui não conseguimos dar seek fácil sem baixar mais, 
                # mas para resiliência, tentamos baixar o início se o seek falhar.
                res = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=180)
                
            if os.path.exists(seg_path):
                segment_files.append(seg_path)
            else:
                logger.error(f"❌ Falha total ao baixar segmento {i}. Stderr: {res.stderr}")
                
        except Exception as e:
            logger.error(f"💥 Exceção no download do segmento {i}: {e}")

    if not segment_files:
        return None

    try:
        if len(segment_files) == 1:
            os.rename(segment_files[0], output_path)
        else:
            concat_list = os.path.join(temp_dir, f"concat_{video_id}.txt")
            with open(concat_list, "w") as f:
                for fpath in segment_files:
                    f.write(f"file '{fpath}'\n")
            
            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", output_path
            ]
            res_concat = subprocess.run(concat_cmd, capture_output=True, text=True)
            if res_concat.returncode != 0:
                logger.error(f"❌ Erro ao concatenar áudios: {res_concat.stderr}")
                return segment_files[0] # Retorna pelo menos o primeiro se falhar concat
            
            for fpath in segment_files:
                if os.path.exists(fpath): os.remove(fpath)
            if os.path.exists(concat_list): os.remove(concat_list)

        return output_path

    except Exception as e:
        logger.error(f"Erro final no download estratégico: {e}")
        return segment_files[0] if segment_files else None

def get_whisper_transcript(video_id, intervals=None):
    """
    Fallback transcription using Strategic Audio Sampling.
    """
    audio_path = download_audio_sample(video_id, intervals=intervals)
    if not audio_path:
        return None, None
        
    audio_hash = get_audio_fingerprint(audio_path)
    
    try:
        logger.info(f"🧠 Transcrevendo amostragem estratégica ({audio_hash[:8]})...")
        segments = transcribe_any(
            audio_path, 
            model_size="base",
            backend="faster-whisper"
        )
        
        transcript_data = []
        for s in segments:
            transcript_data.append(MockSnippet(
                text=s.get("text", ""),
                start=s.get("start", 0.0),
                duration=s.get("end", 0.0) - s.get("start", 0.0)
            ))
            
        return transcript_data, audio_hash
    except Exception as e:
        logger.error(f"❌ Erro no fallback do Whisper: {e}")
    return None, None
