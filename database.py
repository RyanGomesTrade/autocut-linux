import sqlite3
import json
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("database")

DB_PATH = os.path.join(os.path.dirname(__file__), "viral_engine.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    # Habilita WAL Mode para melhor concorrência entre web_app e workers
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela channels
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            channel_score REAL DEFAULT 0.0,
            avg_vph REAL DEFAULT 0.0,
            avg_views INTEGER DEFAULT 0,
            viral_cuts_count INTEGER DEFAULT 0,
            clipable_density REAL DEFAULT 0.0,
            tier TEXT DEFAULT 'B',
            last_scanned TIMESTAMP
        )
    ''')

    # Tabela videos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            channel_id TEXT,
            title TEXT,
            url TEXT,
            vph REAL DEFAULT 0.0,
            relative_vph REAL DEFAULT 1.0,
            vph_acceleration REAL DEFAULT 0.0,
            momentum_score REAL DEFAULT 0.0,
            trend_score REAL DEFAULT 0.0,
            final_viral_score REAL DEFAULT 0.0,
            confidence_score REAL DEFAULT 1.0,
            decision_trace TEXT,
            audio_hash TEXT,
            event_context TEXT,
            raw_signals_json TEXT,
            created_at TIMESTAMP,
            last_scanned TIMESTAMP,
            FOREIGN KEY(channel_id) REFERENCES channels(channel_id)
        )
    ''')

    # Tabela video_history (para calcular aceleração)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            vph REAL,
            timestamp TIMESTAMP,
            FOREIGN KEY(video_id) REFERENCES videos(video_id)
        )
    ''')

    # Tabela segments
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            start_time REAL,
            end_time REAL,
            hook_score REAL DEFAULT 0.0,
            controversy_score REAL DEFAULT 0.0,
            emotion_score REAL DEFAULT 0.0,
            authority_score REAL DEFAULT 0.0,
            total_score REAL DEFAULT 0.0,
            status TEXT DEFAULT 'DETECTED',
            operator_title TEXT,
            operator_hashtags TEXT,
            operator_notes TEXT,
            features_json TEXT,
            updated_at TIMESTAMP,
            FOREIGN KEY(video_id) REFERENCES videos(video_id)
        )
    ''')

    # Tabela comments_signals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            timestamp_str TEXT,
            likes INTEGER DEFAULT 0,
            velocity_score REAL DEFAULT 0.0,
            repeated_mentions INTEGER DEFAULT 1,
            FOREIGN KEY(video_id) REFERENCES videos(video_id)
        )
    ''')

    # Tabela generated_clips (O nascimento do modelo supervisionado)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generated_clips (
            clip_id TEXT PRIMARY KEY,
            video_id TEXT,
            segment_id INTEGER,
            predicted_score REAL,
            confidence_score REAL,
            posted_at TIMESTAMP,
            views_24h INTEGER DEFAULT 0,
            retention_rate REAL DEFAULT 0.0,
            shares_count INTEGER DEFAULT 0,
            actual_performance_score REAL DEFAULT 0.0,
            platform TEXT,
            FOREIGN KEY(video_id) REFERENCES videos(video_id)
        )
    ''')
    
    # Tabela render_jobs (Execution Layer)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS render_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            start_time REAL,
            end_time REAL,
            preset TEXT DEFAULT 'tiktok',
            priority_score REAL DEFAULT 0.0,
            status TEXT DEFAULT 'PENDING',
            output_path TEXT,
            error_log TEXT,
            metrics_json TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(video_id) REFERENCES videos(video_id)
        )
    ''')
    
    # Tabela metrics (Telemetria Operacional)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operational_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_type TEXT,
            value REAL,
            tags TEXT,
            timestamp TIMESTAMP
        )
    ''')
    
    conn.commit()
    
    # Migração para campos de escala
    try:
        cursor.execute("ALTER TABLE render_jobs ADD COLUMN priority_score REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE render_jobs ADD COLUMN expires_at TIMESTAMP")
        cursor.execute("ALTER TABLE render_jobs ADD COLUMN metrics_json TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Migração simples para bancos existentes
    try:
        cursor.execute("ALTER TABLE segments ADD COLUMN status TEXT DEFAULT 'DETECTED'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE segments ADD COLUMN updated_at TIMESTAMP")
        # Seta updated_at para registros antigos que ainda não possuem a coluna preenchida.
        cursor.execute("UPDATE segments SET updated_at = datetime('now') WHERE updated_at IS NULL")
    except sqlite3.OperationalError:
        pass # Coluna já existe

    # Campos do operador (para o Segment Review Studio)
    try:
        cursor.execute("ALTER TABLE segments ADD COLUMN operator_title TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE segments ADD COLUMN operator_hashtags TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE segments ADD COLUMN operator_notes TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE videos ADD COLUMN relative_vph REAL DEFAULT 1.0")
        cursor.execute("ALTER TABLE videos ADD COLUMN vph_acceleration REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE videos ADD COLUMN confidence_score REAL DEFAULT 1.0")
        cursor.execute("ALTER TABLE videos ADD COLUMN decision_trace TEXT")
        cursor.execute("ALTER TABLE videos ADD COLUMN audio_hash TEXT")
        cursor.execute("ALTER TABLE videos ADD COLUMN raw_signals_json TEXT")
    except sqlite3.OperationalError:
        pass # Colunas já existem

    conn.commit()
    conn.close()
    logger.info(f"Database inicializada em {DB_PATH}")

def get_video_segments(video_id):
    """ Retorna segmentos salvos para um vídeo ou [] se não houver """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, start_time, end_time, total_score FROM segments WHERE video_id = ?", (video_id,))
            rows = cursor.fetchall()
            segments = []
            for r in rows:
                segments.append({
                    "id": r[0],
                    "start": r[1],
                    "end": r[2],
                    "duration": r[2] - r[1],
                    "total_score": r[3]
                })
            return segments
        except Exception as e:
            logger.error(f"Erro ao buscar segmentos no DB: {e}")
            return []

def add_render_job(video_id, start, end, preset='tiktok', priority=0.0, expires_in_hours=48):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=expires_in_hours)).isoformat()
        cursor.execute('''
            INSERT INTO render_jobs (video_id, start_time, end_time, preset, priority_score, status, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
        ''', (video_id, start, end, preset, priority, expires_at, now.isoformat(), now.isoformat()))
        conn.commit()
        return cursor.lastrowid

def get_pending_jobs():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Ordena por prioridade descendente e data ascendente
        cursor.execute("""
            SELECT * FROM render_jobs 
            WHERE status = 'PENDING' 
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY priority_score DESC, created_at ASC
        """)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def update_job_status(job_id, status, output_path=None, error_log=None, metrics=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        metrics_json = json.dumps(metrics) if metrics else None
        cursor.execute('''
            UPDATE render_jobs 
            SET status = ?, output_path = ?, error_log = ?, metrics_json = ?, updated_at = ?
            WHERE job_id = ?
        ''', (status, output_path, error_log, metrics_json, now, job_id))
        conn.commit()

def log_operational_metric(metric_type, value, tags=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO operational_metrics (metric_type, value, tags, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (metric_type, value, json.dumps(tags or {}), now))
        conn.commit()

def get_last_vph(video_id):
    """ Retorna o último VPH registrado para calcular aceleração """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT vph, timestamp FROM video_history WHERE video_id = ? ORDER BY timestamp DESC LIMIT 1", (video_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erro ao buscar último VPH: {e}")
            return None

def get_channel_avg_vph(channel_id):
    """ Retorna a média de VPH do canal """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT avg_vph FROM channels WHERE channel_id = ?", (channel_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0.0
        except Exception as e:
            logger.error(f"Erro ao buscar média do canal: {e}")
            return 0.0

def update_channel_stats(channel_id, name, vph):
    """ Atualiza estatísticas do canal com base em um novo vídeo """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT avg_vph, viral_cuts_count FROM channels WHERE channel_id = ?", (channel_id,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("INSERT INTO channels (channel_id, name, avg_vph, last_scanned) VALUES (?, ?, ?, ?)",
                             (channel_id, name, vph, datetime.now().isoformat()))
            else:
                old_avg = row[0] or 0.0
                new_avg = (old_avg * 0.8) + (vph * 0.2)
                cursor.execute("UPDATE channels SET avg_vph = ?, name = ?, last_scanned = ? WHERE channel_id = ?",
                             (new_avg, name, datetime.now().isoformat(), channel_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Erro ao atualizar canal {channel_id}: {e}")

def save_video(video_data):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Salva histórico primeiro
        cursor.execute("INSERT INTO video_history (video_id, vph, timestamp) VALUES (?, ?, ?)",
                     (video_data['video_id'], video_data['vph'], video_data['last_scanned']))

        cursor.execute('''
            INSERT INTO videos (video_id, channel_id, title, url, vph, relative_vph, vph_acceleration, 
                              momentum_score, trend_score, final_viral_score, confidence_score, decision_trace, audio_hash, 
                              event_context, raw_signals_json, created_at, last_scanned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                vph=excluded.vph,
                relative_vph=excluded.relative_vph,
                vph_acceleration=excluded.vph_acceleration,
                momentum_score=excluded.momentum_score,
                trend_score=excluded.trend_score,
                final_viral_score=excluded.final_viral_score,
                confidence_score=excluded.confidence_score,
                decision_trace=excluded.decision_trace,
                audio_hash=excluded.audio_hash,
                event_context=excluded.event_context,
                raw_signals_json=excluded.raw_signals_json,
                last_scanned=excluded.last_scanned
        ''', (
            video_data.get('video_id'),
            video_data.get('channel_id'),
            video_data.get('title'),
            video_data.get('url'),
            video_data.get('vph', 0.0),
            video_data.get('relative_vph', 1.0),
            video_data.get('vph_acceleration', 0.0),
            video_data.get('momentum_score', 0.0),
            video_data.get('trend_score', 0.0),
            video_data.get('final_viral_score', 0.0),
            video_data.get('confidence_score', 1.0),
            json.dumps(video_data.get('decision_trace', [])),
            video_data.get('audio_hash'),
            json.dumps(video_data.get('event_context', {})),
            json.dumps(video_data.get('raw_signals', {})),
            video_data.get('created_at'),
            video_data.get('last_scanned')
        ))
        conn.commit()

def update_segment(
    segment_id,
    start_time=None,
    end_time=None,
    status=None,
    operator_title=None,
    operator_hashtags=None,
    operator_notes=None,
):
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []
        now = datetime.now(timezone.utc).isoformat()
        if start_time is not None:
            updates.append("start_time = ?")
            params.append(start_time)
        if end_time is not None:
            updates.append("end_time = ?")
            params.append(end_time)
        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if operator_title is not None:
            updates.append("operator_title = ?")
            params.append(operator_title)
        if operator_hashtags is not None:
            updates.append("operator_hashtags = ?")
            params.append(operator_hashtags)
        if operator_notes is not None:
            updates.append("operator_notes = ?")
            params.append(operator_notes)
        # updated_at ajuda o SSE a emitir eventos de forma incremental
        updates.append("updated_at = ?")
        params.append(now)
        
        if not updates:
            return
            
        params.append(segment_id)
        cursor.execute(f"UPDATE segments SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

def get_job_by_id(job_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM render_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_job(job_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM render_jobs WHERE job_id = ?", (job_id,))
        conn.commit()

def save_segments(video_id, segments):
    """
    segments = list of dicts: {
        'start_time': float,
        'end_time': float,
        'hook_score': float,
        'controversy_score': float,
        'emotion_score': float,
        'authority_score': float,
        'total_score': float,
        'features': dict
    }
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    # Limpar segmentos antigos para este vídeo caso seja um re-scan
    cursor.execute('DELETE FROM segments WHERE video_id = ?', (video_id,))
    
    for seg in segments:
        cursor.execute('''
            INSERT INTO segments (video_id, start_time, end_time, hook_score, controversy_score, emotion_score, authority_score, total_score, status, features_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id,
            seg.get('start_time'),
            seg.get('end_time'),
            seg.get('hook_score', 0.0),
            seg.get('controversy_score', 0.0),
            seg.get('emotion_score', 0.0),
            seg.get('authority_score', 0.0),
            seg.get('total_score', 0.0),
            seg.get('status', 'DETECTED'),
            json.dumps(seg.get('features', {}))
            , now
        ))
    conn.commit()
    conn.close()


def save_comments_signals(video_id, signals):
    """
    Persiste sinais de comentários (timestamp mentions) no SQLite.

    signals: lista de dicts no formato retornado por `scanner_comments.scan_comments`,
    ex:
      {
        "timestamp_str": "12:34",
        "likes": 123,
        "velocity_score": 4.56,
        "repeated_mentions": 3
      }
    """
    if not video_id:
        return
    if not signals:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM comments_signals WHERE video_id = ?", (video_id,))

        for s in signals:
            cursor.execute(
                '''
                INSERT INTO comments_signals (
                    video_id,
                    timestamp_str,
                    likes,
                    velocity_score,
                    repeated_mentions
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    video_id,
                    s.get("timestamp_str"),
                    s.get("likes", 0),
                    s.get("velocity_score", 0.0),
                    s.get("repeated_mentions", 1),
                ),
            )
        conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
