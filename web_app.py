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
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from flask import Flask, render_template, jsonify, request, Response, send_from_directory

# Imports do sistema
import database
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

# Blacklist em memória: vídeos deletados nesta sessão
_deleted_video_ids = set()

# Flag para pausar o SSE durante operações de escrita críticas
_sse_pause = threading.Event()
_sse_pause.set()  # começa "liberado" (set = pode rodar)

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

    # Salva no banco para aparecer no Trend Monitor (Attention Ops)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    for v in videos:
        try:
            url = v.get("url", "")
            # Extrai o video_id da URL (ex: ?v=abc123)
            video_id = None
            if "v=" in url:
                video_id = url.split("v=")[-1].split("&")[0]
            if not video_id:
                continue

            database.save_video({
                "video_id":          video_id,
                "channel_id":        v.get("channel", "unknown"),
                "title":             v.get("title", ""),
                "url":               url,
                "vph":               0.0,
                "relative_vph":      1.0,
                "vph_acceleration":  0.0,
                "momentum_score":    0.0,
                "trend_score":       0.5,
                "final_viral_score": 0.5,  # Score inicial para passar no filtro > 0.1
                "confidence_score":  1.0,
                "decision_trace":    [],
                "audio_hash":        None,
                "event_context":     {},
                "raw_signals":       {},
                "created_at":        now,
                "last_scanned":      now,
            })
        except Exception as e:
            logger.error(f"Erro ao salvar vídeo {v.get('url')} no banco: {e}")

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

# ─── Nova API Operacional (Attention Operations Dashboard) ────────────────────

# ─── Attention Operations Dashboard API ──────────────────────────────────────

@app.route("/api/ops/dashboard", methods=["GET"])
def api_ops_dashboard():
    """ Resumo de alto nível do sistema """
    try:
        with database.get_connection() as conn:
            cursor = conn.cursor()
            
            # Jobs ativos (PENDING, DOWNLOADING, CUTTING, RENDERING)
            cursor.execute("SELECT COUNT(*) FROM render_jobs WHERE status IN ('PENDING', 'DOWNLOADING', 'CUTTING', 'RENDERING')")
            active_jobs = cursor.fetchone()[0]
            
            # Jobs falhados
            cursor.execute("SELECT COUNT(*) FROM render_jobs WHERE status = 'FAILED'")
            failed_jobs = cursor.fetchone()[0]
            
            # Queue size (PENDING)
            cursor.execute("SELECT COUNT(*) FROM render_jobs WHERE status = 'PENDING'")
            queue_size = cursor.fetchone()[0]
            
            # Clips renderizados (DONE)
            cursor.execute("SELECT COUNT(*) FROM render_jobs WHERE status = 'DONE'")
            clips_rendered = cursor.fetchone()[0]
            
            # Throughput (últimas 24h)
            cursor.execute("SELECT COUNT(*) FROM render_jobs WHERE status = 'DONE' AND updated_at > datetime('now', '-1 day')")
            throughput_24h = cursor.fetchone()[0]
            
            # Vídeos em tendência (score > 0.6)
            cursor.execute("SELECT COUNT(*) FROM videos WHERE final_viral_score > 0.6")
            trending_count = cursor.fetchone()[0]

            return jsonify({
                "active_jobs": active_jobs,
                "failed_jobs": failed_jobs,
                "queue_size": queue_size,
                "clips_rendered": clips_rendered,
                "throughput_24h": throughput_24h,
                "trending_videos": trending_count,
                "pipeline_status": "Discovery → Queue → Render → Upload"
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/jobs", methods=["GET"])
def api_ops_jobs():
    """ Lista detalhada de jobs na fila """
    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT j.*, v.title 
                FROM render_jobs j 
                LEFT JOIN videos v ON j.video_id = v.video_id 
                WHERE j.status NOT IN ('CANCELLED', 'DONE')
                ORDER BY j.created_at DESC LIMIT 50
            """)
            jobs = [dict(row) for row in cursor.fetchall()]
            return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/trends", methods=["GET"])
def api_ops_trends():
    """ Monitor de tendências detectadas """
    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM videos 
                WHERE final_viral_score > 0.0 
                ORDER BY final_viral_score DESC LIMIT 30
            """)
            trends = [dict(row) for row in cursor.fetchall()]
            
            # Filtra vídeos deletados nesta sessão que ainda possam aparecer
            trends = [t for t in trends if t["video_id"] not in _deleted_video_ids]

            # Processar decision_trace de JSON para objeto
            for t in trends:
                if t.get('decision_trace'):
                    try:
                        t['decision_trace'] = json.loads(t['decision_trace'])
                    except:
                        pass
                if t.get('raw_signals_json'):
                    try:
                        t['raw_signals'] = json.loads(t['raw_signals_json'])
                    except:
                        pass
                        
            return jsonify(trends)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/trends/<video_id>", methods=["DELETE"])
def api_ops_trends_delete(video_id):
    try:
        _sse_pause.clear()          # pausa o SSE
        time.sleep(1.5)             # espera o SSE soltar a conexão atual
        database.delete_video(video_id)
        _deleted_video_ids.add(video_id)
        return jsonify({"status": "success", "message": "Tendência removida com sucesso!"})
    except Exception as e:
        logger.error(f"Erro ao deletar trend {video_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        _sse_pause.set()            # libera o SSE

@app.route("/api/ops/segments/<video_id>", methods=["GET"])
def api_ops_segments(video_id):
    """ Segment Inspector: Por que escolheu um segmento? """
    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Info do vídeo
            cursor.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
            video_row = cursor.fetchone()
            video = dict(video_row) if video_row else {}
            
            # Segmentos
            cursor.execute("SELECT * FROM segments WHERE video_id = ? ORDER BY total_score DESC", (video_id,))
            segments = [dict(row) for row in cursor.fetchall()]
            
            # Processar features_json
            for s in segments:
                if s.get('features_json'):
                    try:
                        s['features'] = json.loads(s['features_json'])
                    except:
                        pass
            
            return jsonify({
                "video": video,
                "segments": segments
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue/add", methods=["POST"])
def api_queue_add():
    """
    Adiciona um vídeo à fila de renderização (operational loop).
    Recebe: { trend_id: "video_id" }
    """
    try:
        data = request.get_json()
        trend_id = data.get("trend_id")
        if not trend_id:
            return jsonify({"error": "trend_id is required"}), 400

        # 1. Buscar segmentos do vídeo
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM segments WHERE video_id = ? ORDER BY total_score DESC LIMIT 10", (trend_id,))
            segments = [dict(r) for r in cursor.fetchall()]

            if not segments:
                # Se não houver segmentos, criar um job genérico de todo o vídeo
                job_id = database.add_render_job(
                    video_id=trend_id,
                    start=0.0,
                    end=60.0,
                    preset="tiktok",
                    priority=1.0
                )
                return jsonify({
                    "job_id": job_id,
                    "status": "queued",
                    "message": "Job created (full video)"
                }), 201

            # 2. Criar job para cada segmento
            created_jobs = []
            for seg in segments:
                job_id = database.add_render_job(
                    video_id=trend_id,
                    start=seg.get("start_time"),
                    end=seg.get("end_time"),
                    preset="tiktok",
                    priority=seg.get("total_score")
                )
                created_jobs.append(job_id)

            return jsonify({
                "jobs": created_jobs,
                "status": "queued",
                "message": f"{len(created_jobs)} jobs created"
            }), 201

    except Exception as e:
        logger.error(f"Error adding to queue: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/pause", methods=["POST"])
def api_jobs_pause():
    """Pausa um job em execução."""
    try:
        data = request.get_json()
        job_id_raw = data.get("job_id")
        if not job_id_raw:
            return jsonify({"error": "job_id is required"}), 400
        job_id = int(job_id_raw.replace("job_", ""))
        
        database.update_job_status(job_id, "PAUSED")
        return jsonify({"status": "paused", "job_id": job_id}), 200
    except Exception as e:
        logger.error(f"Error pausing job: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/cancel", methods=["POST"])
def api_jobs_cancel():
    """Cancela um job."""
    try:
        data = request.get_json()
        job_id_raw = data.get("job_id")
        logger.info(f"[Cancel Job] Recebido job_id_raw: {job_id_raw}")
        if not job_id_raw:
            return jsonify({"error": "job_id is required"}), 400
        job_id = int(job_id_raw.replace("job_", ""))
        logger.info(f"[Cancel Job] Job ID limpo: {job_id}")
        
        database.update_job_status(job_id, "CANCELLED")
        logger.info(f"[Cancel Job] Job {job_id} atualizado para CANCELLED")
        
        return jsonify({"status": "cancelled", "job_id": job_id}), 200
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ops/comments/<video_id>", methods=["GET"])
def api_ops_comments(video_id):
    """
    Retorna sinais de comentários (timestamp mentions) e clusters temporais
    para a explicabilidade do Segment Inspector.
    """
    def ts_to_seconds(ts):
        # Suporta "MM:SS" ou "HH:MM:SS"
        if not ts:
            return 0.0
        parts = str(ts).split(":")
        try:
            if len(parts) == 2:
                mm = int(parts[0])
                ss = int(parts[1])
                return mm * 60 + ss
            if len(parts) == 3:
                hh = int(parts[0])
                mm = int(parts[1])
                ss = int(parts[2])
                return hh * 3600 + mm * 60 + ss
        except Exception:
            return 0.0
        return 0.0

    def seconds_to_mmss(seconds):
        seconds = int(seconds)
        mm = seconds // 60
        ss = seconds % 60
        return f"{mm:02d}:{ss:02d}"

    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT timestamp_str, likes, velocity_score, repeated_mentions
                FROM comments_signals
                WHERE video_id = ?
                ORDER BY repeated_mentions DESC, likes DESC
                LIMIT 80
            """, (video_id,))
            signals = [dict(r) for r in cursor.fetchall()]

            if not signals:
                return jsonify({
                    "comments_signals": [],
                    "clusters": [],
                    "comment_velocity_summary": {
                        "max_velocity_score": 0,
                        "avg_velocity_score": 0,
                        "signal_count": 0
                    }
                })

            max_velocity = max(float(s.get("velocity_score") or 0) for s in signals)
            avg_velocity = sum(float(s.get("velocity_score") or 0) for s in signals) / len(signals)

            # Clusters: bin de 10s (aprox.) para agrupar menções próximas
            bin_size = 10
            clusters_map = {}  # binStartSeconds -> cluster
            for s in signals:
                sec = ts_to_seconds(s.get("timestamp_str"))
                if sec <= 0:
                    continue
                bin_start = (sec // bin_size) * bin_size
                if bin_start not in clusters_map:
                    clusters_map[bin_start] = {
                        "bin_start_seconds": bin_start,
                        "timestamp_cluster": seconds_to_mmss(bin_start),
                        "repeated_mentions": 0,
                        "likes": 0,
                        "max_velocity_score": 0.0,
                    }
                c = clusters_map[bin_start]
                c["repeated_mentions"] += int(s.get("repeated_mentions") or 0)
                c["likes"] += int(s.get("likes") or 0)
                c["max_velocity_score"] = max(
                    c["max_velocity_score"],
                    float(s.get("velocity_score") or 0),
                )

            clusters = sorted(
                clusters_map.values(),
                key=lambda x: x["repeated_mentions"],
                reverse=True
            )[:10]

            return jsonify({
                "comments_signals": signals,
                "clusters": clusters,
                "comment_velocity_summary": {
                    "max_velocity_score": max_velocity,
                    "avg_velocity_score": avg_velocity,
                    "signal_count": len(signals)
                }
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/metrics", methods=["GET"])
def api_ops_metrics():
    """ Telemetria e Performance """
    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Pegar métricas das últimas 24h
            cursor.execute("""
                SELECT metric_type, AVG(value) as avg_value, MAX(value) as max_value, COUNT(*) as count 
                FROM operational_metrics 
                WHERE timestamp > datetime('now', '-1 day')
                GROUP BY metric_type
            """)
            metrics = [dict(row) for row in cursor.fetchall()]
            return jsonify(metrics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/clips", methods=["GET"])
def api_ops_clips():
    """ Feedback Loop: Performance Real vs Prevista """
    try:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, v.title 
                FROM generated_clips c
                JOIN videos v ON c.video_id = v.video_id
                ORDER BY c.posted_at DESC LIMIT 50
            """)
            clips = [dict(row) for row in cursor.fetchall()]
            return jsonify(clips)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ops/segments/update", methods=["POST"])
def api_ops_segments_update():
    """Atualiza timestamps, status e metadados do operador de um segmento."""
    try:
        req = request.json or {}
        seg_id = req.get("id")
        start = req.get("start")
        end = req.get("end")
        status = req.get("status")

        operator_title = req.get("operator_title")
        operator_hashtags = req.get("operator_hashtags")
        operator_notes = req.get("operator_notes")
        
        if not seg_id:
            return jsonify({"status": "error", "message": "ID do segmento não fornecido."}), 400
            
        database.update_segment(
            seg_id,
            start_time=start,
            end_time=end,
            status=status,
            operator_title=operator_title,
            operator_hashtags=operator_hashtags,
            operator_notes=operator_notes,
        )
        return jsonify({"status": "success", "message": "Segmento atualizado!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ops/jobs/add", methods=["POST"])
def api_ops_jobs_add():
    """ Adiciona um novo job de renderização """
    try:
        req = request.json or {}
        video_id = req.get("video_id")
        start = req.get("start")
        end = req.get("end")
        preset = req.get("preset", "tiktok")
        priority = req.get("priority", 0.0)
        
        if not all([video_id, start is not None, end is not None]):
            return jsonify({"status": "error", "message": "Dados incompletos para o job."}), 400
            
        job_id = database.add_render_job(video_id, start, end, preset=preset, priority=priority)
        return jsonify({"status": "success", "job_id": job_id, "message": "Job adicionado à fila!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ops/jobs/control", methods=["POST"])
def api_ops_jobs_control():
    """ Controle de jobs (cancelar, retry, etc.) """
    try:
        req = request.json or {}
        job_id = req.get("job_id")
        action = req.get("action") # cancel, retry, delete
        
        if not job_id or not action:
            return jsonify({"status": "error", "message": "Job ID e ação são obrigatórios."}), 400
            
        if action == "cancel":
            database.update_job_status(job_id, "CANCELLED")
        elif action == "retry":
            database.update_job_status(job_id, "PENDING")
        elif action == "delete":
            database.delete_job(job_id)
        else:
            return jsonify({"status": "error", "message": f"Ação '{action}' desconhecida."}), 400
            
        return jsonify({"status": "success", "message": f"Job {job_id}: Ação '{action}' executada!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ops/strategy/update", methods=["POST"])
def api_ops_strategy_update():
    """ Atualiza thresholds de descoberta em tempo real """
    try:
        req = request.json or {}
        # Aqui poderíamos atualizar o web_config.json ou uma tabela de config no banco
        cfg = load_config()
        for key in ["min_score", "min_duration", "max_duration", "analysis_engine"]:
            if key in req:
                cfg[key] = req[key]
        
        if save_config(cfg):
            return jsonify({"status": "success", "message": "Estratégia atualizada!"})
        return jsonify({"status": "error", "message": "Falha ao salvar estratégia."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ops/download/<path:filename>")
def api_ops_download(filename):
    """ Serve arquivos renderizados para download """
    cfg = load_config()
    output_dir = cfg.get("output")
    return send_from_directory(output_dir, filename, as_attachment=True)

@app.route("/api/ops/preview", methods=["POST"])
def api_ops_preview():
    """ Gatilho para render de preview (mini-render 480p) """
    try:
        req = request.json or {}
        video_id = req.get("video_id")
        start = req.get("start")
        end = req.get("end")
        
        if not all([video_id, start is not None, end is not None]):
            return jsonify({"status": "error", "message": "Dados incompletos para o preview."}), 400
            
        # Adiciona um job especial de preview
        # Por enquanto, usamos o mesmo sistema de jobs mas com um preset 'preview'
        job_id = database.add_render_job(video_id, start, end, preset="preview", priority=10.0)
        return jsonify({"status": "success", "job_id": job_id, "message": "Preview solicitado!"})
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

# ─── Attention OS Extended SSE (events stream) ─────────────────────────────

def _safe_json_loads(maybe_json):
    if maybe_json is None:
        return None
    if isinstance(maybe_json, (dict, list)):
        return maybe_json
    try:
        return json.loads(maybe_json)
    except Exception:
        return None


def _iso_utc_epoch():
    return "1970-01-01T00:00:00+00:00"


@app.route("/stream/events")
def stream_events():
    """
    SSE estendido: empurra snapshot inicial + eventos granulares.

    FASE 1 (sem WebSockets): monitora o SQLite por "watermarks" em timestamps
    para detectar mudanças sem bidirecionalidade.
    """

    def event_stream():
        # Watermarks (por conexão) para evitar reenviar eventos
        last_job_updated_at = _iso_utc_epoch()
        last_job_created_at = _iso_utc_epoch()
        last_video_last_scanned = _iso_utc_epoch()
        last_segment_updated_at = _iso_utc_epoch()
        last_title_created_at = _iso_utc_epoch()
        last_metric_timestamp = _iso_utc_epoch()

        last_heartbeat = 0.0

        def emit(event_type, id_val=None, payload=None, patch=None):
            msg = {
                "type": event_type,
                "timestamp": time.time(),
            }
            if id_val is not None:
                msg["id"] = id_val
            if payload is not None:
                msg["payload"] = payload
            if patch is not None:
                msg["patch"] = patch
            return f"data: {json.dumps(msg)}\n\n"

        # Loop principal
        while True:
            try:
                # Pausa se uma operação de escrita está em andamento
                _sse_pause.wait(timeout=5)  # espera até 5s pela liberação
                if not _sse_pause.is_set():
                    time.sleep(0.5)
                    continue

                now = time.time()
                if now - last_heartbeat >= 10.0:
                    last_heartbeat = now
                    yield emit("WORKER_HEARTBEAT", id_val="system_worker", patch={"status": "active", "load": 0.0})

                with database.get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    # Aumenta o timeout para evitar interrupções de leitura no SSE
                    conn.execute("PRAGMA busy_timeout = 10000")

                    # ── Jobs (render_jobs) ──
                    cur.execute("""
                        SELECT *
                        FROM render_jobs
                        WHERE updated_at > ?
                        ORDER BY updated_at ASC
                        LIMIT 200
                    """, (last_job_updated_at,))
                    job_rows = cur.fetchall()

                    if job_rows:
                        for r in job_rows:
                            job_id = f"job_{r['job_id']}"
                            created_at = r["created_at"] or _iso_utc_epoch()
                            updated_at = r["updated_at"] or _iso_utc_epoch()
                            status = r["status"]

                            payload = dict(r)
                            if payload.get("metrics_json"):
                                payload["metrics"] = _safe_json_loads(payload.get("metrics_json"))

                            # 1) Creation
                            if created_at > last_job_created_at:
                                yield emit(
                                    "JOB_QUEUED",
                                    id_val=job_id,
                                    payload={
                                        "video_id": r.get("video_id"),
                                        "start_time": r.get("start_time"),
                                        "end_time": r.get("end_time"),
                                        "preset": r.get("preset"),
                                        "priority": r.get("priority_score"),
                                        "status": status,
                                        "upload_status": r.get("upload_status"),
                                        "uploaded_video_id": r.get("uploaded_video_id"),
                                        "upload_error": r.get("upload_error"),
                                        "created_at": created_at
                                    }
                                )
                                last_job_created_at = max(last_job_created_at, created_at)

                            # 2) Status Updates (Patch-only) — apenas para jobs já existentes
                            else:
                                et = "JOB_PROGRESS"
                                if status == "DONE":
                                    et = "JOB_COMPLETED"
                                elif status == "FAILED":
                                    et = "JOB_ERROR"
                                    yield emit(
                                        "ALERT_TRIGGERED",
                                        id_val=f"alert_{job_id}",
                                        payload={
                                            "level": "error",
                                            "message": f"Job {job_id} failed: {r.get('error_log')}",
                                            "job_id": job_id
                                        }
                                    )
                                elif status == "PAUSED":
                                    et = "JOB_PAUSED"
                                elif status == "CANCELLED":
                                    et = "JOB_CANCELLED"

                                # Adiciona campos de upload ao patch
                                upload_status = r.get("upload_status")
                                patch_data = {
                                    "status": status.lower(),
                                    "output_path": r.get("output_path"),
                                    "error_log": r.get("error_log"),
                                    "metrics": payload.get("metrics"),
                                    "upload_status": upload_status,
                                    "uploaded_video_id": r.get("uploaded_video_id"),
                                    "upload_error": r.get("upload_error"),
                                }

                                # Emitir eventos específicos de upload, se houver mudança
                                if upload_status == "UPLOADING":
                                    yield emit("JOB_UPLOADING", id_val=job_id, patch=patch_data)
                                elif upload_status == "UPLOADED":
                                    yield emit("JOB_UPLOADED", id_val=job_id, patch=patch_data)
                                elif upload_status == "FAILED":
                                    yield emit("ALERT_TRIGGERED", id_val=f"alert_{job_id}", payload={
                                        "level": "warning",
                                        "message": f"Job {job_id} upload failed: {r.get('upload_error')}",
                                        "job_id": job_id
                                    })

                                # Sempre emitir o evento principal
                                yield emit(et, id_val=job_id, patch=patch_data)

                        # Avança watermark (máximo updated_at enviado)
                        last_job_updated_at = max(
                            r["updated_at"] or last_job_updated_at for r in job_rows
                        )

                    # ── Generated Titles ──
                    cur.execute("""
                        SELECT * FROM generated_titles
                        WHERE created_at > ?
                        ORDER BY created_at ASC
                        LIMIT 100
                    """, (last_title_created_at,))
                    title_rows = cur.fetchall()
                    if title_rows:
                        # Agrupar títulos por job_id para o frontend
                        by_job = {}
                        for r in title_rows:
                            jid = r['job_id']
                            if jid not in by_job: by_job[jid] = []
                            by_job[jid].append(dict(r))
                        
                        for jid, titles in by_job.items():
                            yield emit("TITLES_GENERATED", id_val=f"job_{jid}", payload={
                                "best_title": titles[0]['title'],
                                "titles": titles
                            })
                        last_title_created_at = max(r['created_at'] for r in title_rows)

                    # ── Trends (videos) ──
                    cur.execute("""
                        SELECT *
                        FROM videos
                        WHERE last_scanned > ?
                          AND final_viral_score > 0.0
                        ORDER BY last_scanned ASC
                        LIMIT 100
                    """, (last_video_last_scanned,))
                    video_rows = cur.fetchall()

                    if video_rows:
                        for r in video_rows:
                            t = dict(r)
                            video_id = f"trend_{t.get('video_id')}"
                            last_scanned = t.get("last_scanned") or _iso_utc_epoch()
                            
                            yield emit(
                                "TREND_CREATED",
                                id_val=video_id,
                                payload={
                                    "title": t.get("title"),
                                    "url": t.get("url"),
                                    "score": t.get("final_viral_score"),
                                    "relative_vph": t.get("relative_vph"),
                                    "vph_acceleration": t.get("vph_acceleration"),
                                    "last_scanned": last_scanned,
                                }
                            )

                        last_video_last_scanned = max(
                            r["last_scanned"] or last_video_last_scanned for r in video_rows
                        )

                    # ── Segments (segments) ──
                    cur.execute("""
                        SELECT *
                        FROM segments
                        WHERE updated_at > ?
                        ORDER BY updated_at ASC
                        LIMIT 200
                    """, (last_segment_updated_at,))
                    seg_rows = cur.fetchall()

                    if seg_rows:
                        for r in seg_rows:
                            s = dict(r)
                            updated_at = s.get("updated_at") or _iso_utc_epoch()
                            if s.get("features_json"):
                                s["features"] = _safe_json_loads(s.get("features_json"))

                            status = s.get("status")
                            if status == "APPROVED":
                                et = "SEGMENT_APPROVED"
                            elif status == "REJECTED":
                                et = "SEGMENT_REJECTED"
                            else:
                                et = "SEGMENT_UPDATED"

                            yield emit(
                                et,
                                id_val=f"seg_{s.get('id')}",
                                payload={
                                    "video_id": s.get("video_id"),
                                    "start_time": s.get("start_time"),
                                    "end_time": s.get("end_time"),
                                    "total_score": s.get("total_score"),
                                    "status": status,
                                    "hook_score": s.get("hook_score"),
                                    "controversy_score": s.get("controversy_score"),
                                    "emotion_score": s.get("emotion_score"),
                                    "authority_score": s.get("authority_score"),
                                    "features": s.get("features"),
                                    "updated_at": updated_at,
                                }
                            )

                        last_segment_updated_at = max(
                            r["updated_at"] or last_segment_updated_at for r in seg_rows
                        )

                    # ── Operational metrics ──
                    cur.execute("""
                        SELECT metric_type, value, tags, timestamp
                        FROM operational_metrics
                        WHERE timestamp > ?
                        ORDER BY timestamp ASC
                        LIMIT 200
                    """, (last_metric_timestamp,))
                    metric_rows = cur.fetchall()

                    if metric_rows:
                        for r in metric_rows:
                            ts = r["timestamp"] or _iso_utc_epoch()
                            yield emit(
                                "TELEMETRY_UPDATE",
                                id_val=f"metric_{r.get('metric_type')}",
                                payload={
                                    "metric_type": r["metric_type"],
                                    "value": r["value"],
                                    "tags": _safe_json_loads(r["tags"]),
                                    "timestamp": ts,
                                }
                            )

                        last_metric_timestamp = max(
                            r["timestamp"] or last_metric_timestamp for r in metric_rows
                        )

            except GeneratorExit:
                break
            except sqlite3.OperationalError as e:
                yield f"data: {json.dumps({'type':'SQLITE_LOCK','ts':time.time(),'error':str(e)})}\n\n"
                time.sleep(1.0)
            except Exception as e:
                yield emit("STREAM_ERROR", payload={"error": str(e)})
                time.sleep(1.0)

            # descanso entre iterações
            time.sleep(1.0)

    return Response(event_stream(), mimetype="text/event-stream")

# ─── Ponto de Entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print("      VIRAL CUTTER PRO // WEB INTERFACE STARTING")
    print("      Acesse: http://localhost:5000 no seu navegador")
    print("="*50 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
