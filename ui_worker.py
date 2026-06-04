# -*- coding: utf-8 -*-
# ui_worker.py - Worker thread for Viral Cutter pipeline

import os
import json
import logging
import sys
import time
from types import SimpleNamespace
from PySide6.QtCore import QThread, Signal, QObject

# Import the main pipeline function
from main import run_pipeline
from downloader import download_youtube_video
from batch_processor import BatchProcessor
from playwright_uploader import PlaywrightUploader
from youtube_uploader import YouTubeUploader

class SignallingHandler(logging.Handler):
    """
    Custom logging handler that emits a signal for every log record.
    """
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class PipelineWorker(QThread):
    """
    Worker thread that executes the Viral Cutter pipeline.
    """
    progress_signal = Signal(int)
    status_signal = Signal(str)
    log_signal = Signal(str)
    finished_signal = Signal(bool, str) # success, report_path
    results_ready_signal = Signal(list) # List of cuts results

    def __init__(self, config_dict):
        super().__init__()
        self.config_dict = config_dict
        self._is_running = True

    def run(self):
        # Create a mock Namespace object for the run_pipeline function
        args = SimpleNamespace(**self.config_dict)
        
        # Setup logging to redirect to UI
        logger = logging.getLogger("viral_cutter")
        logger.setLevel(logging.INFO) # Garantir que o nível seja INFO
        
        handler = SignallingHandler(self.log_signal)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        handler.setFormatter(formatter)
        
        # Evitar duplicatas se o worker for reiniciado
        if not any(isinstance(h, SignallingHandler) for h in logger.handlers):
            logger.addHandler(handler)
        
        try:
            self.status_signal.emit("Iniciando pipeline...")
            self.log_signal.emit("--- Iniciando Processamento ---")
            
            # Verifica se deve pular transcrição
            if hasattr(args, 'skip_transcription') and args.skip_transcription:
                self.log_signal.emit(f"⚙️ Modo Retomada: Usando transcrição cacheada")
                self.log_signal.emit(f"  > Arquivo: {os.path.basename(args.skip_transcription)}")
            
            self.progress_signal.emit(5)
            
            # Run the pipeline
            # Note: run_pipeline returns 0 on success, 1 on failure
            exit_code = run_pipeline(args)
            
            if exit_code == 0:
                self.progress_signal.emit(100)
                self.status_signal.emit("Processamento concluído com sucesso!")
                
                # Try to find the session report
                report_path = os.path.join(args.output, "session_report.json")
                results = []
                if os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as f:
                        report_data = json.load(f)
                        results = report_data.get("exported_files", [])
                
                self.results_ready_signal.emit(results)
                
                # NOVO: Lógica de Upload para Vídeo Único
                if self.config_dict.get("upload_youtube"):
                    self.status_signal.emit("Iniciando upload automático...")
                    use_playwright = self.config_dict.get("use_playwright", False)
                    
                    interval = self.config_dict.get("upload_interval_min", 0)
                    
                    for idx, cut in enumerate(results):
                        if cut.get("success") and cut.get("file"):
                            # Se não for o primeiro vídeo e houver intervalo, espera
                            if idx > 0 and interval > 0:
                                self.log_signal.emit(f"⏳ Aguardando {interval} minutos para o próximo upload...")
                                for m in range(interval, 0, -1):
                                    self.status_signal.emit(f"Próximo post em {m} min...")
                                    for _ in range(60): # espera 60 segundos (1 min)
                                        time.sleep(1)
                                        if not self._is_running: return

                            file_path = cut["file"]
                            if not os.path.isabs(file_path):
                                file_path = os.path.join(args.output, file_path)
                            
                            title = f"{os.path.basename(file_path)} #shorts"
                            description = ""
                            
                            if use_playwright:
                                # ... (resto do código de upload) ...
                                profile_name = "default"
                                try:
                                    import json
                                    profiles_path = "youtube_profiles.json"
                                    if os.path.exists(profiles_path):
                                        with open(profiles_path, "r", encoding="utf-8") as f:
                                            profiles = json.load(f)
                                            profile_index = self.config_dict.get("youtube_profile_index", 0)
                                            if 0 <= profile_index < len(profiles):
                                                profile_name = profiles[profile_index]["name"]
                                except:
                                    pass

                                self.log_signal.emit(f"🚀 [PLAYWRIGHT] Perfil: {profile_name} | Enviando: {os.path.basename(file_path)}")
                                try:
                                    pw_uploader = PlaywrightUploader(profile_name=profile_name)
                                    pw_uploader.upload_video(file_path, title, description)
                                    pw_uploader.close()
                                    self.log_signal.emit(f"✅ Upload concluído!")
                                except Exception as e:
                                    self.log_signal.emit(f"❌ Erro no upload Playwright: {e}")
                            else:
                                self.log_signal.emit(f"📤 Upload via API: {title}")
                                try:
                                    yt_uploader = YouTubeUploader()
                                    yt_uploader.authenticate(self.config_dict.get("youtube_profile_index", 0))
                                    yt_uploader.upload_video(file_path, title, description, privacy_status="public")
                                    self.log_signal.emit(f"✅ Upload concluído!")
                                except Exception as e:
                                    self.log_signal.emit(f"❌ Erro no upload API: {e}")

                self.finished_signal.emit(True, report_path)
            else:
                self.status_signal.emit("Ocorreu um erro durante o processamento.")
                self.finished_signal.emit(False, "")
                
        except Exception as e:
            self.log_signal.emit(f"CRITICAL ERROR: {str(e)}")
            self.status_signal.emit(f"Erro fatal: {str(e)}")
            self.finished_signal.emit(False, "")
        finally:
            logger.removeHandler(handler)

    def stop(self):
        self._is_running = False
        self.terminate()

class DownloadWorker(QThread):
    """
    Worker thread that downloads a video from YouTube.
    """
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str) # success, file_path

    def __init__(self, url, output_dir):
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self):
        def progress_hook(d):
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').replace('%', '')
                try:
                    self.progress_signal.emit(int(float(p)))
                except:
                    pass
            elif d['status'] == 'finished':
                self.progress_signal.emit(100)

        try:
            file_path = download_youtube_video(
                self.url, 
                self.output_dir, 
                progress_callback=progress_hook
            )
            self.finished_signal.emit(True, file_path)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class BatchPipelineWorker(QThread):
    """
    Worker thread that executes the batch processing pipeline.
    """
    progress_signal = Signal(int)
    status_signal = Signal(str)
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)
    results_ready_signal = Signal(list)

    def __init__(self, config_dict):
        super().__init__()
        self.config_dict = config_dict
        self._is_running = True

    def run(self):
        logger = logging.getLogger("viral_cutter")
        logger.setLevel(logging.INFO)
        
        handler = SignallingHandler(self.log_signal)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        handler.setFormatter(formatter)
        
        if not any(isinstance(h, SignallingHandler) for h in logger.handlers):
            logger.addHandler(handler)
        
        try:
            self.status_signal.emit("Iniciando processamento em lote...")
            self.log_signal.emit("--- Iniciando Batch ---")
            self.progress_signal.emit(5)
            
            list_file = self.config_dict.get("batch_list")
            jobs = self.config_dict.get("batch_jobs")
            upload = self.config_dict.get("upload_youtube", False)
            output_dir = self.config_dict.get("output", "batch_output")
            
            # Repassar parâmetros customizados
            custom_args = dict(self.config_dict)
            if "batch_list" in custom_args: del custom_args["batch_list"]
            if "batch_jobs" in custom_args: del custom_args["batch_jobs"]
            if "input" in custom_args: del custom_args["input"]
            
            processor = BatchProcessor(
                list_file=list_file or "list.txt",
                output_base_dir=output_dir,
                upload_to_youtube=upload,
                custom_args=custom_args
            )
            
            if jobs:
                processor.process_jobs(jobs, custom_args)
            else:
                processor.process_all(custom_args)
            
            self.progress_signal.emit(100)
            self.status_signal.emit("Lote concluído com sucesso!")
            
            # Pega o arquivo de progresso
            report_path = processor.progress_file
            self.results_ready_signal.emit([]) # Pode implementar depois para mostrar os cortes
            self.finished_signal.emit(True, report_path)
            
        except Exception as e:
            self.log_signal.emit(f"CRITICAL ERROR (BATCH): {str(e)}")
            self.status_signal.emit(f"Erro fatal no lote: {str(e)}")
            self.finished_signal.emit(False, "")
        finally:
            logger.removeHandler(handler)

    def stop(self):
        self._is_running = False
        self.terminate()

