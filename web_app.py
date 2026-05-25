# -*- coding: utf-8 -*-
# web_app.py
# Servidor backend Flask para a Web GUI do Viral Cutter Pro

import os
import sys
import json
import time
import queue
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from flask import Flask, render_template, jsonify, request, Response

# Imports do sistema
from main import run_pipeline
from downloader import download_youtube_video
from batch_processor import BatchProcessor
from playwright_uploader import PlaywrightUploader
from youtube_uploader import YouTubeUploader
from auto_list import YouTubeSearcher, save_to_list, get_existing_urls, REGIONS

app = Flask(__name__)

# Configurações globais e estado da aplicação
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORKSPACE_DIR, "web_config.json")

# Filas de logs e estados de progresso compartilhados
log_queue = queue.Queue(maxsize=1000)
active_thread = None
thread_lock = threading.Lock()
is_running = False

# Progresso global
progress_data = {
    "percent": 0,
    "status": "Inativo",
    "active_task": "none", # 'download', 'pipeline', 'batch', 'none'
    "results": []
}

# ─── Custom Logging Handler para SSE ──────────────────────────────────────────
class SSELoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            # Coloca log na fila do SSE, descarta se cheia para não travar
            try:
                log_queue.put_nowait(msg)
            except queue.Full:
                pass
        except Exception:
            self.handleError(record)

# Setup logging global para direcionar mensagens ao SSE
logger = logging.getLogger("viral_cutter")
logger.setLevel(logging.INFO)
sse_handler = SSELoggingHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
sse_handler.setFormatter(formatter)
logger.addHandler(sse_handler)

# ─── Configurações Padrão ─────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "input": "",
    "batch_list": "list.txt",
    "upload_youtube": False,
    "use_playwright": False,
    "youtube_profile_index": 0,
    "output": os.path.join(os.path.expanduser("~"), "Videos", "ViralCutter"),
    "whisper_model": "medium",
    "whisper_backend": "auto",
    "device": "cpu",
    "language": None,
    "model": "llama3",
    "ollama_host": "http://localhost:11434",
    "top_n": 10,
    "min_score": 40.0,
    "min_duration": 20.0,
    "max_duration": 65.0,
    "preset": "auto_detect",
    "no_subtitles": False,
    "soft_subtitles": False,
    "no_silence_detect": False,
    "keep_temp": False,
    "skip_transcription": None,
    "skip_analysis": None,
    "ollama_timeout": 1200,
    "analysis_engine": "heuristic",
    "log_level": "INFO",
    "subtitle_style": "high_impact",
    "visual_filter": "none",
    "bg_music": None,
    "bg_music_volume": 0.15,
    "fade_duration": 0.5,
    "progress_bar": False,
    "auto_frame": False,
    "watermark_image": None,
    "watermark_text": None,
    "watermark_position": "bottom_right",
    "watermark_opacity": 0.8,
    "watermark_scale": 1.0,
    "watermark_font_size": 40,
    "watermark_font_color": "white",
    "watermark_mode": "auto",
    "upload_interval_min": 0,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(saved)
                return merged
        except Exception as e:
            logger.warning(f"Erro ao ler web_config.json: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar web_config.json: {e}")
        return False

# ─── Background Executors ─────────────────────────────────────────────────────

def async_download_worker(url, output_dir):
    global is_running, progress_data
    try:
        progress_data["active_task"] = "download"
        progress_data["percent"] = 0
        progress_data["status"] = "Fazendo download do vídeo..."
        log_queue.put("⬇️ Iniciando download remoto do YouTube...")

        def progress_hook(d):
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').replace('%', '').strip()
                try:
                    progress_data["percent"] = int(float(p))
                except:
                    pass
            elif d['status'] == 'finished':
                progress_data["percent"] = 100

        file_path = download_youtube_video(
            url, 
            output_dir, 
            progress_callback=progress_hook
        )
        
        # Concluído com sucesso
        log_queue.put(f"✅ Download concluído: {file_path}")
        progress_data["percent"] = 100
        progress_data["status"] = "Download Concluído!"
        
        # Auto preenche a configuração com o arquivo baixado
        cfg = load_config()
        cfg["input"] = file_path
        save_config(cfg)
        
    except Exception as e:
        log_queue.put(f"❌ Erro no download: {e}")
        progress_data["status"] = f"Erro no download: {e}"
    finally:
        progress_data["active_task"] = "none"
        is_running = False

def async_pipeline_worker(cfg_dict):
    global is_running, progress_data
    try:
        progress_data["active_task"] = "pipeline"
        progress_data["percent"] = 5
        progress_data["status"] = "Executando corte único..."
        progress_data["results"] = []
        log_queue.put("⚙️ Iniciando processamento do vídeo único...")

        # Converte dicionário para Namespace
        args = SimpleNamespace(**cfg_dict)
        
        # Roda pipeline principal
        exit_code = run_pipeline(args)
        
        if exit_code == 0:
            progress_data["percent"] = 100
            progress_data["status"] = "Cortes gerados com sucesso!"
            log_queue.put("🎉 Processamento do pipeline concluído com sucesso!")
            
            # Carrega resultados
            report_path = os.path.join(args.output, "session_report.json")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report_data = json.load(f)
                    progress_data["results"] = report_data.get("exported_files", [])
            
            # Lógica de Upload integrado para Único
            if cfg_dict.get("upload_youtube"):
                run_single_upload(cfg_dict, progress_data["results"])
        else:
            progress_data["status"] = "Pipeline falhou."
            log_queue.put("❌ O pipeline retornou código de erro.")
            
    except Exception as e:
        log_queue.put(f"❌ Erro fatal: {e}")
        progress_data["status"] = f"Erro fatal: {e}"
    finally:
        progress_data["active_task"] = "none"
        is_running = False

def run_single_upload(cfg_dict, results):
    global is_running
    progress_data["status"] = "Subindo cortes para o YouTube..."
    use_playwright = cfg_dict.get("use_playwright", False)
    interval = cfg_dict.get("upload_interval_min", 0)
    
    # Descobrir nome do perfil ativo
    profile_name = "default"
    try:
        profiles_path = os.path.join(WORKSPACE_DIR, "youtube_profiles.json")
        if os.path.exists(profiles_path):
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = json.load(f)
                idx = cfg_dict.get("youtube_profile_index", 0)
                if 0 <= idx < len(profiles):
                    profile_name = profiles[idx]["name"]
    except Exception as e:
        log_queue.put(f"⚠️ Erro ao ler perfis de upload: {e}")

    for i, cut in enumerate(results):
        if not is_running: break
        if cut.get("success") and cut.get("file"):
            file_path = cut["file"]
            if not os.path.isabs(file_path):
                file_path = os.path.join(cfg_dict["output"], file_path)
            
            if i > 0 and interval > 0:
                log_queue.put(f"⏳ Aguardando {interval} minutos para próximo upload...")
                for m in range(interval * 60):
                    if not is_running: return
                    time.sleep(1)

            title = f"{os.path.basename(file_path)} #shorts"
            
            if use_playwright:
                log_queue.put(f"🚀 [Playwright] Canal: {profile_name} | Enviando: {os.path.basename(file_path)}")
                try:
                    pw = PlaywrightUploader(profile_name=profile_name)
                    pw.upload_video(file_path, title, "")
                    pw.close()
                    log_queue.put("✅ Upload concluído via Playwright!")
                except Exception as ex:
                    log_queue.put(f"❌ Falha no upload: {ex}")
            else:
                log_queue.put(f"📤 [API] Canal: {profile_name} | Enviando: {os.path.basename(file_path)}")
                try:
                    yt = YouTubeUploader()
                    yt.authenticate(cfg_dict.get("youtube_profile_index", 0))
                    yt.upload_video(file_path, title, "", privacy_status="public")
                    log_queue.put("✅ Upload concluído via API!")
                except Exception as ex:
                    log_queue.put(f"❌ Falha no upload API: {ex}")

def async_batch_worker(cfg_dict):
    global is_running, progress_data
    try:
        progress_data["active_task"] = "batch"
        progress_data["percent"] = 5
        progress_data["status"] = "Processando fila em lote..."
        log_queue.put("⚙️ Iniciando processamento em lote...")

        list_file = cfg_dict.get("batch_list", "list.txt")
        output_dir = cfg_dict.get("output", "batch_output")
        upload = cfg_dict.get("upload_youtube", False)

        # Remove campos irrelevantes para o BatchProcessor
        custom_args = cfg_dict.copy()
        if "batch_list" in custom_args: del custom_args["batch_list"]
        if "input" in custom_args: del custom_args["input"]

        processor = BatchProcessor(
            list_file=list_file,
            output_base_dir=output_dir,
            upload_to_youtube=upload,
            custom_args=custom_args
        )

        processor.process_all(custom_args)

        progress_data["percent"] = 100
        progress_data["status"] = "Processamento em lote concluído!"
        log_queue.put("🎉 Processamento em lote concluído com sucesso!")
        
    except Exception as e:
        log_queue.put(f"❌ Erro fatal no lote: {e}")
        progress_data["status"] = f"Erro fatal no lote: {e}"
    finally:
        progress_data["active_task"] = "none"
        is_running = False

# ─── Rotas HTTP / API do Flask ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        new_cfg = request.json
        if save_config(new_cfg):
            return jsonify({"status": "success", "message": "Configurações salvas!"})
        return jsonify({"status": "error", "message": "Falha ao salvar."}), 500
    return jsonify(load_config())

@app.route("/api/start", methods=["POST"])
def api_start():
    global active_thread, is_running
    with thread_lock:
        if is_running:
            return jsonify({"status": "error", "message": "Já existe uma tarefa ativa rodando."}), 400
        
        req_data = request.json or {}
        task_type = req_data.get("task_type", "pipeline") # pipeline, download, batch
        cfg = load_config()

        is_running = True
        
        if task_type == "download":
            url = req_data.get("url")
            if not url:
                is_running = False
                return jsonify({"status": "error", "message": "URL do YouTube vazia."}), 400
            active_thread = threading.Thread(target=async_download_worker, args=(url, cfg["output"]))
        elif task_type == "batch":
            active_thread = threading.Thread(target=async_batch_worker, args=(cfg,))
        else:
            active_thread = threading.Thread(target=async_pipeline_worker, args=(cfg,))

        active_thread.start()
        return jsonify({"status": "success", "message": f"Tarefa '{task_type}' iniciada!"})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    global is_running, progress_data
    with thread_lock:
        if not is_running:
            return jsonify({"status": "error", "message": "Nenhuma tarefa ativa rodando."}), 400
        
        is_running = False
        log_queue.put("🛑 Processamento interrompido pelo usuário.")
        progress_data["status"] = "Interrompido!"
        progress_data["active_task"] = "none"
        return jsonify({"status": "success", "message": "Sinal de interrupção enviado!"})

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "is_running": is_running,
        "progress": progress_data["percent"],
        "status": progress_data["status"],
        "active_task": progress_data["active_task"],
        "results": progress_data["results"]
    })

# ─── Rotas da Fila (list.txt) ─────────────────────────────────────────────────

@app.route("/api/queue", methods=["GET", "POST"])
def api_queue():
    cfg = load_config()
    filename = cfg.get("batch_list", "list.txt")
    
    if request.method == "POST":
        action = request.json.get("action")
        if action == "save":
            content = request.json.get("content", "")
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                return jsonify({"status": "success", "message": "Fila list.txt salva!"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
                
    # GET: Lê list.txt
    content = ""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"# Erro ao ler fila: {e}"
    else:
        content = "# Fila de processamento em lote vazia.\n# Adicione URLs do YouTube abaixo, uma por linha:\n"
        
    return jsonify({"filename": filename, "content": content})

# ─── Rotas do Niche Explorer (AutoList) ───────────────────────────────────────

@app.route("/api/niche/categories", methods=["GET"])
def api_niche_categories():
    categories = []
    for k, v in YouTubeSearcher.CATEGORIES.items():
        categories.append({
            "id": k,
            "name": v["name"],
            "pay": v["pay"],
            "viral": v["viral"]
        })
    return jsonify({"categories": categories, "regions": REGIONS})

@app.route("/api/niche/search", methods=["POST"])
def api_niche_search():
    req = request.json or {}
    region = req.get("region", "BR")
    category_id = req.get("category_id")
    count = req.get("count", 10)
    
    if not category_id:
        return jsonify({"status": "error", "message": "Nicho não selecionado."}), 400

    try:
        cfg = load_config()
        profile_idx = cfg.get("youtube_profile_index", 0)
        
        searcher = YouTubeSearcher(region=region, profile_index=profile_idx)
        videos = searcher.search_trending_videos(category_id, max_results=count)
        return jsonify({"status": "success", "videos": videos})
    except Exception as e:
        error_msg = str(e)
        # Se for erro de permissão ou token expirado, simplifica a mensagem
        if "invalid_grant" in error_msg.lower() or "expired" in error_msg.lower():
            error_msg = "Sessão do YouTube expirada ou revogada. Por favor, reautentique usando o client_secrets.json ou apague o token.pickle."
        
        logger.error(f"Erro em api_niche_search: {error_msg}")
        return jsonify({"status": "error", "message": error_msg}), 500

@app.route("/api/niche/add", methods=["POST"])
def api_niche_add():
    videos = request.json.get("videos", [])
    if not videos:
        return jsonify({"status": "error", "message": "Nenhum vídeo selecionado."}), 400
        
    cfg = load_config()
    filename = cfg.get("batch_list", "list.txt")
    
    added = save_to_list(videos, filename=filename)
    return jsonify({"status": "success", "added_count": added})

# ─── Rotas do YouTube / Playwright Session ────────────────────────────────────

@app.route("/api/youtube/profiles", methods=["GET"])
def api_youtube_profiles():
    try:
        yt = YouTubeUploader()
        return jsonify({"profiles": yt.profiles})
    except Exception as e:
        return jsonify({"profiles": []})

@app.route("/api/playwright/login", methods=["POST"])
def api_playwright_login():
    profile_index = request.json.get("profile_index", 0)
    
    # Roda login de forma blocante, pois abre interface visual no desktop local do usuário
    try:
        yt = YouTubeUploader()
        if 0 <= profile_index < len(yt.profiles):
            profile_name = yt.profiles[profile_index]["name"]
        else:
            profile_name = "default"

        log_queue.put(f"🖥️ Abrindo navegador Playwright Chromium para o perfil '{profile_name}'...")
        
        # Roda login em thread para não congelar o HTTP do Flask totalmente
        def run_login():
            try:
                pw = PlaywrightUploader(profile_name=profile_name)
                pw.login()
                pw.close()
                log_queue.put("✅ Navegador fechado e cookies persistidos!")
            except Exception as login_err:
                log_queue.put(f"❌ Erro ao rodar Playwright login: {login_err}")

        t = threading.Thread(target=run_login)
        t.start()

        return jsonify({"status": "success", "message": "Navegador de Login iniciado!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/playwright/reset", methods=["POST"])
def api_playwright_reset():
    profile_index = request.json.get("profile_index", 0)
    try:
        yt = YouTubeUploader()
        if 0 <= profile_index < len(yt.profiles):
            profile_name = yt.profiles[profile_index]["name"]
            pw = PlaywrightUploader(profile_name=profile_name)
            if pw.reset_session():
                return jsonify({"status": "success", "message": "Cookies limpos com sucesso!"})
        return jsonify({"status": "error", "message": "Falha ao resetar cookies."}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── Stream Server-Sent Events (SSE) ──────────────────────────────────────────

@app.route("/stream")
def stream_logs():
    def event_stream():
        # Envia primeira mensagem para ativar conexão
        yield f"data: {json.dumps({'type': 'status', 'msg': progress_data['status'], 'percent': progress_data['percent']})}\n\n"
        
        while True:
            # Pega logs acumulados na fila
            logs_to_send = []
            while not log_queue.empty():
                try:
                    logs_to_send.append(log_queue.get_nowait())
                except queue.Empty:
                    break

            if logs_to_send:
                for log in logs_to_send:
                    yield f"data: {json.dumps({'type': 'log', 'msg': log})}\n\n"

            # Envia status de tempos em tempos
            yield f"data: {json.dumps({'type': 'status', 'msg': progress_data['status'], 'percent': progress_data['percent'], 'active_task': progress_data['active_task']})}\n\n"
            
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")

# ─── Ponto de Entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print("      VIRAL CUTTER PRO // WEB INTERFACE STARTING")
    print("      Acesse: http://localhost:5000 no seu navegador")
    print("="*50 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
