import logging
import json
import threading
import queue
import time
from datetime import datetime, timezone, timedelta
import database
from auto_list import YouTubeSearcher
from scanner_transcript import process_video_transcript
from scanner_comments import scan_comments
from transcription_fallback import check_external_tools
from segment_deduplicator import deduplicate_segments

logger = logging.getLogger("discovery_engine")

# Gerenciamento de Fila para Whisper (Resource Management)
whisper_queue = queue.Queue()
def whisper_worker():
    while True:
        task = whisper_queue.get()
        if task is None: break
        video_id, intervals, callback = task
        try:
            segments, audio_hash = process_video_transcript(video_id, use_fallback=True, intervals=intervals)
            callback(segments, audio_hash)
        except Exception as e:
            logger.error(f"❌ Erro no worker do Whisper para {video_id}: {e}")
            callback([], None)
        whisper_queue.task_done()

threading.Thread(target=whisper_worker, daemon=True).start()

# Event Context mapping (Trends)
CURRENT_EVENTS = [
    {"entity": "Neymar", "event": "lesão", "strength": 0.9, "source": "google_trends"},
    {"entity": "Marçal", "event": "debate", "strength": 0.95, "source": "twitter"},
    {"entity": "Bolsonaro", "event": "polêmica", "strength": 0.85, "source": "tiktok"}
]

def parse_yt_date(date_str):
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))

def calculate_vph(view_count, published_at):
    now = datetime.now(timezone.utc)
    hours = (now - published_at).total_seconds() / 3600.0
    if hours < 0.1: hours = 0.1
    return view_count / hours

def get_cooldown_hours(final_score):
    if final_score >= 0.8: return 0.5   
    if final_score >= 0.4: return 6.0   
    return 24.0                         

def scan_channel_videos(youtube, channel_id, channel_name):
    try:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=10,
            order="date",
            type="video"
        )
        res = request.execute()
        return res.get("items", [])
    except Exception as e:
        logger.error(f"❌ Erro buscando canal {channel_name}: {e}")
        return []

def parse_yt_duration(duration_str):
    import re
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration_str)
    if not match: return 0
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)

def get_strategic_intervals(duration_seconds):
    """
    Gera intervalos estratégicos multi-segmento baseados na duração.
    Garante resiliência e amostragem representativa.
    """
    if duration_seconds < 600: # < 10 min: 2 segmentos
        return [("00:00:10", "60"), (f"{int(duration_seconds*0.7)//60:02}:{int(duration_seconds*0.7)%60:02}", "60")]
    
    # 10-60 min: 3 segmentos (início, meio, fim)
    intervals = [
        ("00:00:10", "60"), 
        (f"{int(duration_seconds*0.5)//3600:02}:{(int(duration_seconds*0.5)%3600)//60:02}:{int(duration_seconds*0.5)%60:02}", "60"),
        (f"{int(duration_seconds*0.8)//3600:02}:{(int(duration_seconds*0.8)%3600)//60:02}:{int(duration_seconds*0.8)%60:02}", "60")
    ]
    
    # > 60 min: 5 segmentos
    if duration_seconds > 3600:
        p25 = int(duration_seconds * 0.25)
        p75 = int(duration_seconds * 0.75)
        intervals.insert(1, (f"{p25//3600:02}:{(p25%3600)//60:02}:{p25%60:02}", "60"))
        intervals.insert(3, (f"{p75//3600:02}:{(p75%3600)//60:02}:{p75%60:02}", "60"))
        
    return intervals

def evaluate_video(youtube, video_id, snippet):
    start_time = time.time()
    
    # --- 1. Inicialização Defensiva (Imparável) ---
    clip_density = 0.0
    momentum_score = 0.0
    trend_score = 0.0
    comments_score = 0.0
    confidence = 0.3
    comments_signals = []
    segments = []
    audio_hash = None
    decision_trace = ["start_analysis"]
    
    logger.info(f"\n🔍 Analisando: {video_id}...")

    try:
        # --- 2. Startup Health Check ---
        health = check_external_tools()
        if not health.get("ffmpeg") or not health.get("yt-dlp"):
            decision_trace.append("external_tools_missing")
            logger.warning("⚠️ Ferramentas externas ausentes. Fallback Whisper desativado.")

        # --- 3. Metadados e VPH (Fase 1) ---
        req = youtube.videos().list(part="statistics,snippet,contentDetails", id=video_id)
        stat_res = req.execute()
        if not stat_res.get("items"): 
            decision_trace.append("video_not_found")
            return None
        
        item = stat_res["items"][0]
        view_count = int(item["statistics"].get("viewCount", 0))
        published_at = parse_yt_date(item["snippet"]["publishedAt"])
        duration_sec = parse_yt_duration(item["contentDetails"].get("duration", "PT0S"))
        channel_id = item["snippet"]["channelId"]
        channel_name = item["snippet"]["channelTitle"]
        
        vph = calculate_vph(view_count, published_at)
        avg_vph = database.get_channel_avg_vph(channel_id)
        relative_vph = vph / avg_vph if avg_vph > 0 else 1.0
        
        last_vph_data = database.get_last_vph(video_id)
        acceleration = 0.0
        if last_vph_data:
            old_vph, last_time = last_vph_data
            time_diff = (time.time() - datetime.fromisoformat(last_time).timestamp()) / 3600.0
            if time_diff > 0.1:
                acceleration = (vph - old_vph) / time_diff
        
        momentum_score = min((relative_vph / 3.0) * 0.7 + (min(acceleration, 500) / 500.0) * 0.3, 1.0)
        database.update_channel_stats(channel_id, channel_name, vph)
        logger.info(f"🔥 Relative VPH: {relative_vph:.2f} | Accel: {acceleration:.1f}")

        # --- 4. Cache Check ---
        existing_segments = database.get_video_segments(video_id)
        if existing_segments:
            decision_trace.append("cache_hit")
            logger.info("♻️ Usando cache de segmentos do banco.")
            segments = existing_segments
        else:
            # --- 5. Transcrição (Fase 2) ---
            logger.info("🧠 Fase 2: Buscando Transcrição...")
            segments, _ = process_video_transcript(video_id, use_fallback=False)
            
            if segments:
                decision_trace.append("official_transcript_success")
                confidence = 1.0
                logger.info("✅ Transcrição oficial obtida.")
            else:
                decision_trace.append("official_transcript_failed")
                logger.info("⚠️ Transcrição oficial indisponível. Avaliando Fallback...")
                
                # --- 6. Comentários (Antecipado para Decisão) ---
                comments_signals = scan_comments(youtube, video_id)
                database.save_comments_signals(video_id, comments_signals)
                comments_score = min(len(comments_signals) * 0.1, 1.0)
                
                if (relative_vph > 2.0 or comments_score > 0.3 or vph > 2000) and health.get("yt-dlp"):
                    decision_trace.append("whisper_fallback_triggered")
                    intervals = get_strategic_intervals(duration_sec)
                    
                    res_event = threading.Event()
                    result_container = {}
                    def callback(s, h):
                        result_container['segments'] = s
                        result_container['hash'] = h
                        res_event.set()
                    
                    whisper_queue.put((video_id, intervals, callback))
                    if res_event.wait(timeout=300):
                        segments = result_container.get('segments', [])
                        audio_hash = result_container.get('hash')
                        if segments:
                            decision_trace.append("whisper_fallback_success")
                            confidence = 0.8
                            logger.info("🧠 Fallback Whisper concluído com sucesso.")
                        else:
                            decision_trace.append("whisper_fallback_empty")
                    else:
                        decision_trace.append("whisper_fallback_timeout")
                        logger.error("⏱️ Timeout no fallback Whisper.")
                else:
                    decision_trace.append("fallback_skipped")
                    logger.info("📉 Sinais baixos para Whisper. Entrando em Modo Parcial.")

        # --- 7. Comentários (Se não rodou antes) ---
        if not comments_signals:
            try:
                comments_signals = scan_comments(youtube, video_id)
                database.save_comments_signals(video_id, comments_signals)
                comments_score = min(len(comments_signals) * 0.1, 1.0)
                decision_trace.append("comments_success")
            except Exception:
                decision_trace.append("comments_failed")
                logger.warning("⚠️ Falha ao buscar comentários.")

        # --- 8. Clip Density e Trends ---
        if segments:
            segments = sorted(segments, key=lambda x: x.get("total_score", 0), reverse=True)
            top_scores = [s.get("total_score", 0) for s in segments[:3]]
            clip_density = sum(top_scores) / len(top_scores) if top_scores else 0.0
        
        title_desc = (item["snippet"]["title"] + " " + item["snippet"]["description"]).lower()
        event_match = None
        for ev in CURRENT_EVENTS:
            if ev["entity"].lower() in title_desc:
                event_match = ev
                trend_score = ev["strength"]
                decision_trace.append(f"trend_match_{ev['entity']}")
                break

        # --- 9. Final Score (Graceful Degradation) ---
        if not segments:
            decision_trace.append("partial_intelligence_mode")
            final_score = (momentum_score * 0.6) + (comments_score * 0.3) + (trend_score * 0.1)
            confidence = min(confidence, 0.5)
        else:
            final_score = (clip_density * 0.4) + (momentum_score * 0.3) + (trend_score * 0.2) + (comments_score * 0.1)

        # --- 10. Persistência e Observabilidade ---
        video_data = {
            'video_id': video_id,
            'channel_id': channel_id,
            'title': item["snippet"]["title"],
            'url': f"https://www.youtube.com/watch?v={video_id}",
            'vph': round(vph, 2),
            'relative_vph': round(relative_vph, 2),
            'vph_acceleration': round(acceleration, 2),
            'momentum_score': round(momentum_score, 2),
            'trend_score': round(trend_score, 2),
            'final_viral_score': round(final_score, 2),
            'confidence_score': round(confidence, 2),
            'decision_trace': decision_trace,
            'audio_hash': audio_hash,
            'event_context': event_match or {},
            'raw_signals': {
                'views': view_count,
                'comments': len(comments_signals),
                'duration': duration_sec,
                'time_taken': round(time.time() - start_time, 2)
            },
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_scanned': datetime.now(timezone.utc).isoformat()
        }
        
        database.save_video(video_data)
        if segments and not existing_segments:
            # --- 11. Deduplicação e Orquestração Automática (Scaling Logic) ---
            # Remove sobreposições com segmentos já existentes ou entre os novos
            unique_segments = deduplicate_segments(video_id, segments)
            
            if unique_segments:
                database.save_segments(video_id, unique_segments)
                
                # Se o vídeo for realmente promissor (> 0.6) 
                # agendamos jobs com prioridade dinâmica
                if final_score > 0.6:
                    # Prioridade = viral_score (40%) + momentum (30%) + trends (20%) + confidence (10%)
                    priority = (final_score * 0.4) + (momentum_score * 0.3) + (trend_score * 0.2) + (confidence * 0.1)
                    
                    logger.info(f"🚀 Score alto ({final_score:.2f}). Agendando jobs com prioridade {priority:.2f}...")
                    
                    # Agendamos apenas os melhores segmentos únicos
                    for seg in unique_segments[:2]: 
                        database.add_render_job(
                            video_id, 
                            seg['start'], 
                            seg['end'], 
                            preset='tiktok',
                            priority=priority,
                            expires_in_hours=24 if trend_score > 0.5 else 72 # Trends expiram mais rápido
                        )
            else:
                logger.info(f"✂️ Todos os segmentos de {video_id} foram deduplicados. Job ignorado.")
        
        logger.info(f"✅ Finalizado em {video_data['raw_signals']['time_taken']}s | Score: {final_score:.2f} | Conf: {confidence:.2f}")
        return video_data

    except Exception as e:
        logger.error(f"💥 Falha catastrófica em {video_id}: {e}", exc_info=True)
        return None

def run_discovery(youtube, nicho=None, channel_ids=None):
    """
    Orquestrador principal do Motor de Descoberta Viral.
    """
    logger.info("🚀 Iniciando Motor de Descoberta Viral (Fase 1)...")
    database.init_db()
    
    videos_to_scan = []
    
    if channel_ids:
        for cid in channel_ids:
            videos_to_scan.extend(scan_channel_videos(youtube, cid, cid))
    elif nicho:
        logger.info(f"🔎 Buscando por nicho: {nicho}")
        request = youtube.search().list(
            part="snippet",
            q=nicho,
            maxResults=15,
            order="relevance",
            type="video"
        )
        res = request.execute()
        videos_to_scan = res.get("items", [])
    else:
        # Fallback para canais padrão se nada for informado
        default_channels = [
            {"id": "UCm0WfH2M2O_S6P8PzYwXp7g", "name": "Podpah"},
            {"id": "UC6o_9U9uFmS9P9X6X6X6X6A", "name": "Flow Podcast"},
            {"id": "UCU4I9rW8I3z3a5x3x3x3x3x", "name": "Cortes do Flow"} 
        ]
        logger.info("📡 Varrendo vídeos em alta por nicho (Trending Fallback)...")
        # Se canais derem zero, tenta uma busca geral por "podcast cortes"
        request = youtube.search().list(
            part="snippet",
            q="podcast cortes brasil",
            maxResults=10,
            order="date",
            type="video"
        )
        res = request.execute()
        videos_to_scan = res.get("items", [])
        logger.info(f"🔎 Encontrados {len(videos_to_scan)} vídeos para análise.")

    results = []
    for item in videos_to_scan:
        video_id = item["id"].get("videoId") or item["id"]
        if not video_id: continue
        
        data = evaluate_video(youtube, video_id, item["snippet"])
        if data:
            results.append(data)
            
    logger.info(f"\n✅ Busca Viral concluída. {len(results)} vídeos processados.")
    return results
