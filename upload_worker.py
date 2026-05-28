#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_worker.py — Monitora jobs DONE e faz upload automático para YouTube.
"""

import os
import time
import logging
from pathlib import Path

import database
from utils import setup_logging
from uploader import PlaywrightUploader

# Configuração de logging
logger = setup_logging(log_level="INFO", log_file="upload_worker.log")

# Configuração padrão (você pode alterar conforme necessidade)
DEFAULT_PROFILE = "default"
DEFAULT_PRIVACY = "public"
DEFAULT_HEADLESS = False  # Deixe False na primeira vez para fazer login


class UploadWorker:
    def __init__(self, profile=DEFAULT_PROFILE, headless=DEFAULT_HEADLESS):
        self.profile = profile
        self.headless = headless
        self.running = True
        self._uploader = None

    def _get_uploader(self):
        """Cria uma instância do PlaywrightUploader."""
        if not self._uploader:
            self._uploader = PlaywrightUploader(
                profile=self.profile,
                headless=self.headless,
                slow_mo=100,
            )
        return self._uploader

    def _build_title(self, job, clip_path):
        """Constrói o título usando dados do job ou segmento associado."""
        # Tenta pegar o operator_title do segmento (se houver)
        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT operator_title FROM segments 
                WHERE video_id = ? AND start_time = ? AND end_time = ?
            """, (job['video_id'], job['start_time'], job['end_time']))
            res = cursor.fetchone()
            conn.close()
            if res and res[0]:
                return res[0][:100]
        except Exception as e:
            logger.debug(f"Erro ao buscar operator_title: {e}")
        
        # Fallback: usa o nome do arquivo
        return Path(clip_path).stem[:100]

    def _build_description(self, job):
        """Constrói a descrição usando dados do job."""
        parts = []
        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT operator_notes FROM segments 
                WHERE video_id = ? AND start_time = ? AND end_time = ?
            """, (job['video_id'], job['start_time'], job['end_time']))
            res = cursor.fetchone()
            conn.close()
            if res and res[0]:
                parts.append(res[0].strip())
                parts.append("")
        except Exception as e:
            logger.debug(f"Erro ao buscar operator_notes: {e}")
        parts.append("#shorts")
        return "\n".join(parts)

    def _build_tags(self, job):
        """Extrai tags do segmento (se houver)."""
        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT operator_hashtags FROM segments 
                WHERE video_id = ? AND start_time = ? AND end_time = ?
            """, (job['video_id'], job['start_time'], job['end_time']))
            res = cursor.fetchone()
            conn.close()
            if res and res[0]:
                raw = res[0]
                return [t.strip().lstrip("#") for t in raw.replace(",", " ").split() if t.strip()]
        except Exception as e:
            logger.debug(f"Erro ao buscar operator_hashtags: {e}")
        return []

    def process_job(self, job):
        job_id = job['job_id']
        clip_path = job['output_path']
        
        logger.info(f"📤 Iniciando upload do Job {job_id}: {Path(clip_path).name}")
        
        database.update_upload_status(job_id, "UPLOADING")
        
        try:
            title = self._build_title(job, clip_path)
            description = self._build_description(job)
            tags = self._build_tags(job)
            
            uploader = self._get_uploader()
            uploaded_video_id = uploader.upload_video(
                clip_path=clip_path,
                title=title,
                description=description,
                tags=tags,
                privacy=DEFAULT_PRIVACY
            )
            
            if uploaded_video_id:
                database.update_upload_status(job_id, "UPLOADED", uploaded_video_id=uploaded_video_id)
                logger.info(f"✅ Upload concluído do Job {job_id}! YouTube ID: {uploaded_video_id}")
            else:
                database.update_upload_status(job_id, "FAILED", upload_error="Falha no upload (sem erro detalhado)")
                logger.error(f"❌ Upload falhou do Job {job_id}")
                
        except Exception as e:
            logger.error(f"💥 Erro no upload do Job {job_id}: {e}")
            database.update_upload_status(job_id, "FAILED", upload_error=str(e))

    def run(self):
        logger.info(f"🚀 Upload Worker iniciado com perfil '{self.profile}'. Monitorando jobs...")
        while self.running:
            jobs = database.get_jobs_to_upload()
            if not jobs:
                time.sleep(10)
                continue
            
            for job in jobs:
                logger.info(f"🛠️ Pegando Job {job['job_id']} para upload")
                self.process_job(job)


if __name__ == "__main__":
    worker = UploadWorker()
    worker.run()
