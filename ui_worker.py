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
