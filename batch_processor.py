# -*- coding: utf-8 -*-
import utf8_bootstrap
import os
import json
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from main import run_pipeline, DEFAULT_CONFIG
from downloader import download_youtube_video
from youtube_uploader import YouTubeUploader
from playwright_uploader import PlaywrightUploader
from utils import setup_logging, ensure_dir

# Diretório raiz do projeto
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuração de logging
logger = setup_logging(log_level="INFO", log_file="batch_processing.log")

class BatchProcessor:
    def __init__(self, list_file: str, output_base_dir: str = "batch_output", upload_to_youtube: bool = False, custom_args: dict = None):
        self.list_file = list_file
        self.output_base_dir = ensure_dir(output_base_dir)
        self.upload_to_youtube = upload_to_youtube
        self.progress_file = os.path.join(output_base_dir, "batch_progress.json")
        self.uploader = None
        self.playwright_uploader = None
        
        # Agendamento
        self.schedule_interval = 0
        self.last_scheduled_time = None
        
        if upload_to_youtube:
            if custom_args and custom_args.get("use_playwright"):
                try:
                    profile_index = custom_args.get("youtube_profile_index", 0)
                    profile_name = "default"
                    temp_uploader = YouTubeUploader()
                    if profile_index < len(temp_uploader.profiles):
                        profile_name = temp_uploader.profiles[profile_index]["name"]
                    self.playwright_uploader = PlaywrightUploader(profile_name=profile_name)
                    logger.info(f"Uploader Playwright inicializado para o perfil: {profile_name}")
                except Exception as e:
                    logger.error(f"Falha ao inicializar Playwright: {e}")

            try:
                self.uploader = YouTubeUploader()
            except Exception as e:
                logger.error(f"Falha ao inicializar o uploader do YouTube (API): {e}")
                if not self.playwright_uploader:
                    logger.warning("O processamento continuará sem upload automático (API e Playwright falharam).")
                    self.upload_to_youtube = False
                else:
                    logger.info("API falhou, mas Playwright está disponível. Upload continuará via Playwright.")

        self.progress = self.load_progress()

    def load_progress(self):
        if os.path.exists(self.progress_file):
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"completed_urls": [], "failed_urls": {}}

    def save_progress(self):
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)

    def get_urls(self):
        if not os.path.exists(self.list_file):
            logger.error(f"Arquivo de lista não encontrado: {self.list_file}")
            return []
        urls = []
        with open(self.list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    url = line.split('#')[0].strip()
                    if url:
                        urls.append(url)
        return urls

    def process_jobs(self, jobs, custom_args=None):
        """
        Processa uma lista de objetos job: {"url": "...", "preset": "...", "title_prefix": "..."}
        """
        total = len(jobs)
        logger.info(f"Iniciando processamento de fila customizada com {total} vídeos.")

        self.schedule_interval = custom_args.get("schedule_interval", 0) if custom_args else 0
        
        if self.upload_to_youtube and self.uploader:
            initial_profile = custom_args.get("youtube_profile_index", 0) if custom_args else 0
            if initial_profile < len(self.uploader.profiles):
                self.uploader.authenticate(initial_profile)

        if self.schedule_interval > 0:
            self.last_scheduled_time = datetime.now(timezone.utc)
            logger.info(f"Agendamento ativado (UTC): intervalo de {self.schedule_interval}h entre vídeos.")

        for i, job in enumerate(jobs, 1):
            url = job.get("url")
            if not url:
                continue
            
            if url in self.progress["completed_urls"]:
                logger.info(f"[{i}/{total}] Pulando URL já concluída: {url}")
                continue

            # ── FIX: Preset por job tem prioridade sobre o global ──────────────
            # O frontend pode mandar o campo como "preset" ou "preset_id".
            # Se nenhum dos dois estiver definido no job, usa o preset global
            # (custom_args["preset"]). Se o global também não existir, usa
            # "landscape" como fallback seguro (evita auto_detect forçar shorts).
            job_preset = job.get("preset") or job.get("preset_id")
            global_preset = (custom_args or {}).get("preset", "landscape")
            effective_preset = job_preset if job_preset else global_preset

            logger.info(
                f"[{i}/{total}] Processando: {url} | "
                f"Preset: {effective_preset} "
                f"({'job' if job_preset else 'global'})"
            )

            try:
                # Mescla: args globais primeiro, job sobrescreve campos específicos.
                # Depois força "preset" com o valor resolvido acima para garantir
                # que auto_detect do global não sobrescreva o preset individual.
                job_args = dict(custom_args) if custom_args else {}
                job_args.update(job)
                job_args["preset"] = effective_preset  # ← sempre o valor resolvido

                self.process_single_url(url, job_args)
                self.progress["completed_urls"].append(url)
                logger.info(f"[{i}/{total}] Sucesso: {url}")
            except Exception as e:
                logger.error(f"[{i}/{total}] Erro ao processar {url}: {e}")
                self.progress["failed_urls"][url] = str(e)
            
            self.save_progress()

    def process_single_url(self, url, custom_args=None):
        # 1. Download
        video_dir = ensure_dir(os.path.join(self.output_base_dir, "downloads"))
        video_path = download_youtube_video(url, str(video_dir))
        
        # 2. Setup Args for Pipeline
        class ArgsNamespace:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            def __getattr__(self, name):
                return DEFAULT_CONFIG.get(name)

        video_name = Path(video_path).stem
        current_output = ensure_dir(os.path.join(self.output_base_dir, "results", video_name))
        
        args_dict = dict(custom_args) if custom_args else {}
        args_dict["input"] = video_path
        args_dict["output"] = str(current_output)
        
        pipeline_args = ArgsNamespace(**args_dict)

        # 3. Run Pipeline
        logger.info(f"Iniciando pipeline de corte para: {video_name} | Preset: {args_dict.get('preset')}")
        run_pipeline(pipeline_args)

        # 4. Upload to YouTube
        if self.upload_to_youtube and (self.uploader or self.playwright_uploader):
            self.upload_results(current_output, video_name, custom_args)

    def upload_results(self, output_dir, original_title, custom_args=None):
        report_path = os.path.join(output_dir, "session_report.json")
        if not os.path.exists(report_path):
            logger.warning(f"Relatório não encontrado em {output_dir}. Pulando upload.")
            return

        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        hook_map = {c.get("start"): c.get("hook") for c in report.get("cuts", [])}

        for cut in report.get("exported_files", []):
            if cut.get("success") and cut.get("file"):
                file_path = cut["file"]
                if not os.path.isabs(file_path):
                    file_path = os.path.join(output_dir, file_path)
                
                hook = hook_map.get(cut.get("start"))
                title_prefix = custom_args.get("title_prefix", "") if custom_args else ""
                
                generic_hooks = ["Trecho selecionado via análise heurística", "Trecho interessante", "Corte"]
                is_valid_hook = hook and hook.strip() and hook not in generic_hooks
                
                if is_valid_hook:
                    title = f"{title_prefix + ' ' if title_prefix else ''}{hook} #shorts"
                else:
                    title = f"{title_prefix + ' ' if title_prefix else ''}{original_title} - Parte {cut['cut_index']} #shorts"
                
                description = f"{hook if hook else ''}"
                
                publish_at = None
                if self.schedule_interval > 0:
                    self.last_scheduled_time += timedelta(hours=self.schedule_interval)
                    publish_at = self.last_scheduled_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                    logger.info(f"Agendando vídeo '{title}' para: {publish_at}")

                clean_title = original_title.split("|")[0].split("-")[0].strip()
                dynamic_title = f"{clean_title} #shorts #viral #curiosidades"
                if len(dynamic_title) > 100:
                    dynamic_title = dynamic_title[:90] + "..."
                
                final_title = dynamic_title

                if custom_args and custom_args.get("use_playwright") and self.playwright_uploader:
                    try:
                        success = self.playwright_uploader.upload_video(
                            file_path=file_path,
                            title=final_title,
                            description=description,
                            publish_at=publish_at
                        )
                        if success:
                            logger.info(f"Upload via Playwright concluído: {final_title}")
                            continue
                    except Exception as e:
                        logger.error(f"Erro no upload via Playwright do corte {cut['cut_index']}: {e}")
                 
                if self.uploader:
                    try:
                        video_id = self.uploader.upload_video(
                            file_path=file_path,
                            title=final_title,
                            description=description,
                            privacy_status="public",
                            publish_at=publish_at
                        )
                        cut["youtube_id"] = video_id
                    except Exception as e:
                        logger.error(f"Erro no upload do corte {cut['cut_index']}: {e}")

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def process_all(self, custom_args=None):
        """
        Processa todas as URLs do arquivo list.txt (sem preset individual por job).
        """
        urls = self.get_urls()
        jobs = [{"url": url} for url in urls]
        self.process_jobs(jobs, custom_args)


def main():
    parser = argparse.ArgumentParser(description="Batch Processor para Viral Cutter")
    parser.add_argument("--list", "-l", default="list.txt", help="Arquivo com URLs do YouTube")
    parser.add_argument("--output", "-o", default="batch_output", help="Diretório base de saída")
    parser.add_argument("--upload", action="store_true", help="Ativar upload automático para YouTube")
    parser.add_argument("--preset", default="shorts", choices=["landscape", "tiktok", "reels", "shorts", "square"], help="Preset de vídeo")
    
    args = parser.parse_args()

    custom_pipeline_args = {
        "preset": args.preset,
        "top_n": 5,
    }

    processor = BatchProcessor(
        list_file=args.list, 
        output_base_dir=args.output, 
        upload_to_youtube=args.upload
    )
    processor.process_all(custom_pipeline_args)

if __name__ == "__main__":
    main()