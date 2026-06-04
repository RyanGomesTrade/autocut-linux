import os
import logging
import subprocess
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timezone

import database
from utils import setup_logging, ensure_dir, seconds_to_hms
from cutter import EXPORT_PRESETS, _run_ffmpeg, detect_silence, adjust_cut_to_avoid_silence, cut_video_segment
from title_engine import AttentionTitleEngine

# Configuração de logging
logger = setup_logging(log_level="DEBUG", log_file="clip_worker.log")

class ClipWorker:
    def __init__(self, output_dir="rendered_clips"):
        self.output_dir = ensure_dir(output_dir)
        self.temp_dir = ensure_dir(os.path.join(self.output_dir, "temp"))
        self.running = True

    def download_partial_stream(self, video_id, start, end, output_path):
        """
        Baixa o vídeo completo e extrai o segmento com FFmpeg.
        Usa yt-dlp's Python API (como downloader.py) para melhor compatibilidade.
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        logger.info(f"📥 Baixando vídeo completo: {video_id}")
        
        # Caminho para o vídeo completo temporário
        full_video_path = os.path.join(self.temp_dir, f"full_{video_id}.mp4")
        
        # Primeiro, tentamos baixar o vídeo completo (se ainda não existir)
        if not os.path.exists(full_video_path):
            try:
                import yt_dlp
                ydl_opts = {
                    'format': 'bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'outtmpl': full_video_path,
                    'encoding': 'utf-8',
                    'noplaylist': True,
                    'quiet': False,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"Iniciando download do YouTube: {video_url}")
                    ydl.extract_info(video_url, download=True)
                logger.info("✅ Download completo concluído.")
            except Exception as e:
                logger.error(f"❌ Erro no download completo para {video_id}: {e}")
                return None
        
        # Agora extraímos o segmento com FFmpeg
        logger.info(f"✂️ Extraindo segmento ({seconds_to_hms(start)} -> {seconds_to_hms(end)}) com FFmpeg")
        
        try:
            # Usamos o _run_ffmpeg do cutter.py para extrair o segmento
            from cutter import _run_ffmpeg
            
            duration = end - start
            _run_ffmpeg([
                "ffmpeg",
                "-ss", str(start),
                "-i", full_video_path,
                "-t", str(duration),
                "-c", "copy",  # Copia streams, sem re-encode (rápido!)
                "-y",
                output_path
            ], description=f"extrair segmento {start}-{end}")
            
            if os.path.exists(output_path):
                logger.info(f"✅ Segmento extraído com sucesso: {output_path} ({os.path.getsize(output_path) / 1024 / 1024:.2f} MB)")
                return output_path
            else:
                logger.error("❌ FFmpeg rodou mas o arquivo de saída não foi gerado")
                return None
                
        except RuntimeError as e:
            logger.error(f"❌ Falha ao extrair segmento: {e}")
            return None

    def process_job(self, job):
        job_id = job['job_id']
        video_id = job['video_id']
        start = job['start_time']
        end = job['end_time']
        preset = job['preset']
        
        start_ts = time.time()
        metrics = {
            "download_time": 0,
            "render_time": 0,
            "total_time": 0,
            "file_size_mb": 0
        }
        
        database.update_job_status(job_id, "DOWNLOADING")
        
        raw_clip_path = os.path.join(self.temp_dir, f"raw_{video_id}_{job_id}.mp4")
        final_clip_path = os.path.join(self.output_dir, f"clip_{video_id}_{job_id}.mp4")

        try:
            # 1. Download do vídeo completo e extração do segmento
            dl_start = time.time()
            if not self.download_partial_stream(video_id, start, end, raw_clip_path):
                raise Exception("Falha ao extrair segmento do vídeo.")
            metrics["download_time"] = round(time.time() - dl_start, 2)

            # Para previews, podemos pular o ajuste de silêncio para ser mais rápido
            if preset == "preview":
                adj_start, adj_end = start, end
            else:
                database.update_job_status(job_id, "CUTTING")
                
                # 2. Ajuste de Silêncio (não precisamos mais do buffer, pois temos o vídeo completo)
                silences = detect_silence(raw_clip_path)
                adj_start, adj_end = adjust_cut_to_avoid_silence(start, end, silences)

            database.update_job_status(job_id, "RENDERING")
            
            # 3. Render Final
            render_start = time.time()
            cut_video_segment(
                input_path=raw_clip_path,
                output_path=final_clip_path,
                start=adj_start - start,  # Ajustar para a posição dentro do segmento baixado
                end=adj_end - start,
                preset=preset,
                visual_filter="vibrant" if preset != "preview" else "none",
                progress_bar=True
            )
            metrics["render_time"] = round(time.time() - render_start, 2)

            if os.path.exists(final_clip_path):
                metrics["file_size_mb"] = round(os.path.getsize(final_clip_path) / 1024 / 1024, 2)
                metrics["total_time"] = round(time.time() - start_ts, 2)
                
                database.update_job_status(job_id, "DONE", output_path=final_clip_path, metrics=metrics)
                
                # --- Geração de Títulos Operacional ---
                try:
                    engine = AttentionTitleEngine()
                    # Em v1, o clip_data é derivado do job e segment features
                    engine.generate_titles_for_job(job_id)
                    logger.info(f"💡 Títulos gerados para Job {job_id}")
                except Exception as te:
                    logger.error(f"Falha no Title Engine: {te}")

                # Métricas operacionais (a UI consome via /stream/events)
                database.log_operational_metric("render_time", metrics.get("render_time", 0.0), {"video_id": video_id})
                database.log_operational_metric("render_throughput", metrics["total_time"], {"video_id": video_id})
                logger.info(f"✨ Job {job_id} concluído em {metrics['total_time']}s!")
            else:
                raise Exception("Arquivo final não foi gerado.")

        except Exception as e:
            logger.error(f"💥 Erro no Job {job_id}: {e}")
            database.update_job_status(job_id, "FAILED", error_log=str(e))
        finally:
            # Cleanup (não deletamos o full_video para reutilizar em próximos jobs do mesmo vídeo!)
            if os.path.exists(raw_clip_path):
                os.remove(raw_clip_path)

    def run(self):
        logger.info("🚀 Clip Worker iniciado. Monitorando fila de renderização...")
        while self.running:
            jobs = database.get_pending_jobs()
            if not jobs:
                time.sleep(5)
                continue
            
            for job in jobs:
                logger.info(f"🛠️ Iniciando Job {job['job_id']} (Vídeo: {job['video_id']})")
                self.process_job(job)
                
if __name__ == "__main__":
    worker = ClipWorker()
    worker.run()
