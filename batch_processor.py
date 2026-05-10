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
from utils import setup_logging, ensure_dir

# Diretório raiz do projeto
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuração de logging
logger = setup_logging(log_level="INFO", log_file="batch_processing.log")

class BatchProcessor:
    def __init__(self, list_file: str, output_base_dir: str = "batch_output", upload_to_youtube: bool = False):
        self.list_file = list_file
        self.output_base_dir = ensure_dir(output_base_dir)
        self.upload_to_youtube = upload_to_youtube
        self.progress_file = os.path.join(output_base_dir, "batch_progress.json")
        self.uploader = None
        
        # Agendamento
        self.schedule_interval = 0 # em horas
        self.last_scheduled_time = None
        
        if upload_to_youtube:
            try:
                # Agora o YouTubeUploader gerencia seus próprios perfis via youtube_profiles.json
                self.uploader = YouTubeUploader()
            except Exception as e:
                logger.error(f"Falha ao inicializar o uploader do YouTube: {e}")
                logger.warning("O processamento continuará sem upload automático.")
                self.upload_to_youtube = False

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
                    # Pega apenas a parte antes do comentário #
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

        # Inicializa o tempo de agendamento apenas no início do lote
        self.schedule_interval = custom_args.get("schedule_interval", 0) if custom_args else 0
        
        # Define o perfil inicial do YouTube se o upload estiver ativado
        if self.upload_to_youtube and self.uploader:
            initial_profile = custom_args.get("youtube_profile_index", 0) if custom_args else 0
            if initial_profile < len(self.uploader.profiles):
                self.uploader.authenticate(initial_profile)

        if self.schedule_interval > 0:
            # YouTube API exige horário em UTC
            self.last_scheduled_time = datetime.now(timezone.utc)
            logger.info(f"Agendamento ativado (UTC): intervalo de {self.schedule_interval}h entre vídeos.")

        for i, job in enumerate(jobs, 1):
            url = job.get("url")
            if not url: continue
            
            if url in self.progress["completed_urls"]:
                logger.info(f"[{i}/{total}] Pulando URL já concluída: {url}")
                continue

            logger.info(f"[{i}/{total}] Processando: {url} (Formato: {job.get('preset')})")
            try:
                # Mescla os argumentos globais com os específicos do job
                job_args = dict(custom_args) if custom_args else {}
                job_args.update(job)
                
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
        # Usamos o DEFAULT_CONFIG como base e sobrescrevemos o necessário
        class ArgsNamespace:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            def __getattr__(self, name):
                return DEFAULT_CONFIG.get(name)

        # Nome da pasta de saída baseado no nome do arquivo do vídeo
        video_name = Path(video_path).stem
        current_output = ensure_dir(os.path.join(self.output_base_dir, "results", video_name))
        
        args_dict = dict(custom_args) if custom_args else {}
        args_dict["input"] = video_path
        args_dict["output"] = str(current_output)
        
        pipeline_args = ArgsNamespace(**args_dict)

        # 3. Run Pipeline
        logger.info(f"Iniciando pipeline de corte para: {video_name}")
        run_pipeline(pipeline_args)

        # 4. Upload to YouTube
        if self.upload_to_youtube and self.uploader:
            self.upload_results(current_output, video_name, custom_args)

    def upload_results(self, output_dir, original_title, custom_args=None):
        report_path = os.path.join(output_dir, "session_report.json")
        if not os.path.exists(report_path):
            logger.warning(f"Relatório não encontrado em {output_dir}. Pulando upload.")
            return

        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        # Cria um mapa de hooks para fácil acesso
        hook_map = {c.get("start"): c.get("hook") for c in report.get("cuts", [])}

        for cut in report.get("exported_files", []):
            if cut.get("success") and cut.get("file"):
                file_path = cut["file"]
                if not os.path.isabs(file_path):
                    file_path = os.path.join(output_dir, file_path)
                
                # Tenta pegar o hook da IA, se não tiver ou for genérico, usa o título original
                hook = hook_map.get(cut.get("start"))
                title_prefix = custom_args.get("title_prefix", "") if custom_args else ""
                
                # Lista de hooks genéricos a evitar como título principal
                generic_hooks = ["Trecho selecionado via análise heurística", "Trecho interessante", "Corte"]
                
                is_valid_hook = hook and hook.strip() and hook not in generic_hooks
                
                if is_valid_hook:
                    title = f"{title_prefix + ' ' if title_prefix else ''}{hook} #shorts"
                else:
                    title = f"{title_prefix + ' ' if title_prefix else ''}{original_title} - Parte {cut['cut_index']} #shorts"
                
                description = f"{hook if hook else ''}\n\nCorte automático gerado pelo Viral Cutter.\nOriginal: {report['input_video']}"
                
                # Lógica de Agendamento
                publish_at = None
                if self.schedule_interval > 0:
                    # Incrementa o tempo ANTES de cada vídeo para garantir que o primeiro também seja agendado no futuro
                    self.last_scheduled_time += timedelta(hours=self.schedule_interval)
                    publish_at = self.last_scheduled_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                    logger.info(f"Agendando vídeo '{title}' para: {publish_at}")

                try:
                    video_id = self.uploader.upload_video(
                        file_path=file_path,
                        title=title[:100], # Limite do YouTube
                        description=description,
                        privacy_status="public", # Agora os vídeos sobem direto como Públicos
                        publish_at=publish_at
                    )
                    cut["youtube_id"] = video_id
                except Exception as e:
                    logger.error(f"Erro no upload do corte {cut['cut_index']}: {e}")

        # Atualiza o relatório com os IDs do YouTube
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def process_all(self, custom_args=None):
        """
        Processa todas as URLs do arquivo list.txt
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
        "top_n": 5, # Exemplo: 5 cortes por vídeo
    }

    processor = BatchProcessor(
        list_file=args.list, 
        output_base_dir=args.output, 
        upload_to_youtube=args.upload
    )
    processor.process_all(custom_pipeline_args)

if __name__ == "__main__":
    main()
