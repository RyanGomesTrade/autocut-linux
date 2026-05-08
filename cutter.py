"""
cutter.py - Corte de vídeo e embutição de legendas usando FFmpeg
"""

import os
import re
import logging
import subprocess
from pathlib import Path
from typing import Optional

from utils import ensure_dir, sanitize_filename, seconds_to_hms, clamp
import random

logger = logging.getLogger("viral_cutter.cutter")


# Presets de exportação para diferentes redes sociais
EXPORT_PRESETS = {
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 23,
    },
    "reels": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 23,
    },
    "shorts": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 23,
    },
    "landscape": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "video_bitrate": "5M",
        "audio_bitrate": "192k",
        "crf": 20,
    },
    "square": {
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 22,
    },
    "podcast_split": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 23,
    },
    "social_frame": {
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 22,
    },
    "shorts_blur": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_bitrate": "4M",
        "audio_bitrate": "192k",
        "crf": 23,
    },
}


def _run_ffmpeg(cmd: list[str], description: str = "", timeout: int = 300) -> subprocess.CompletedProcess:
    """
    Executa um comando FFmpeg com tratamento de erro padronizado.
    """
    logger.debug(f"FFmpeg: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg falhou ({description}):\n{result.stderr[-2000:]}")
            raise RuntimeError(
                f"FFmpeg retornou código {result.returncode}: {result.stderr[-500:]}"
            )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout ({timeout}s) ao executar: {description}")


def detect_silence(
    video_path: str,
    noise_threshold: float = -35.0,  # dBFS
    min_silence_duration: float = 0.5,  # segundos
) -> list[tuple[float, float]]:
    """
    Detecta intervalos de silêncio no áudio usando FFmpeg silencedetect.

    Returns:
        Lista de tuplas (silence_start, silence_end)
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}",
        "-f", "null", "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        stderr = result.stderr

        silences = []
        starts = re.findall(r"silence_start: ([\d.]+)", stderr)
        ends = re.findall(r"silence_end: ([\d.]+)", stderr)

        for s, e in zip(starts, ends):
            silences.append((float(s), float(e)))

        logger.info(f"Detectados {len(silences)} intervalos de silêncio")
        return silences
    except Exception as e:
        logger.warning(f"Erro ao detectar silêncio: {e}")
        return []


def adjust_cut_to_avoid_silence(
    start: float,
    end: float,
    silences: list[tuple[float, float]],
    tolerance: float = 1.5,
) -> tuple[float, float]:
    """
    Ajusta o início/fim de um corte para evitar começar/terminar em silêncio.

    Args:
        start: Início proposto
        end: Fim proposto
        silences: Lista de (silence_start, silence_end)
        tolerance: Segundos de margem para ajustar

    Returns:
        (start_ajustado, end_ajustado)
    """
    adjusted_start = start
    adjusted_end = end

    for s_start, s_end in silences:
        # Evita começar no meio de um silêncio
        if s_start <= start <= s_end:
            adjusted_start = s_end + 0.1
            logger.debug(f"Início ajustado de {start:.2f}s para {adjusted_start:.2f}s (pós-silêncio)")

        # Evita terminar no meio de um silêncio
        if s_start <= end <= s_end:
            adjusted_end = s_start - 0.1
            logger.debug(f"Fim ajustado de {end:.2f}s para {adjusted_end:.2f}s (pré-silêncio)")

    # Garante que o corte ainda tem duração mínima
    if adjusted_end - adjusted_start < 10:
        logger.warning("Ajuste de silêncio resultaria em corte muito curto. Mantendo original.")
        return start, end

    return adjusted_start, adjusted_end


def get_face_center_relative(video_path: str, start: float, duration: float) -> Optional[float]:
    """
    Retorna a posição X relativa (0.0 a 1.0) do rosto dominante no segmento de vídeo.
    Se nenhum rosto for encontrado, retorna None.
    """
    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV não instalado. Face tracking não disponível.")
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30
    orig_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    if orig_w <= 0: return None

    start_frame = int(start * fps)
    
    # Amostra até 5 frames
    frames_to_sample = 5
    step = max(1, int((duration * fps) / frames_to_sample))
    
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        logger.warning("Haar Cascade não encontrado.")
        return None

    face_centers = []
    
    for i in range(frames_to_sample):
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame + i * step)
        ret, frame = cap.read()
        if not ret: break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
        
        if len(faces) > 0:
            # Pega o maior rosto (área)
            faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
            x, y, w, h = faces[0]
            center_x = x + w / 2.0
            face_centers.append(center_x)

    cap.release()

    if not face_centers:
        return None
        
    avg_x = sum(face_centers) / len(face_centers)
    return avg_x / orig_w


def cut_video_segment(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    video_info: Optional[dict] = None,
    preset: str = "landscape",
    add_padding: float = 0.1,
    visual_filter: str = "none", # 'none', 'vibrant', 'cinematic', 'warm'
    fade_duration: float = 0.5,
    progress_bar: bool = False,
    auto_frame: bool = False,
) -> str:
    """
    Corta um segmento do vídeo com re-encoding para qualidade ideal.

    Args:
        input_path: Caminho do vídeo original
        output_path: Caminho de saída
        start: Tempo de início em segundos
        end: Tempo de fim em segundos
        video_info: Informações do vídeo (opcional, para detectar orientação)
        preset: Nome do preset de exportação
        add_padding: Segundos adicionais no início/fim para suavizar transições

    Returns:
        Caminho do vídeo gerado
    """
    duration = end - start
    actual_start = max(0.0, start - add_padding)
    actual_end = end + add_padding

    cfg = EXPORT_PRESETS.get(preset, EXPORT_PRESETS["landscape"])

    # Detecta orientação do vídeo original
    is_vertical = False
    if video_info:
        w = video_info.get("width", 1920)
        h = video_info.get("height", 1080)
        if h > w:
            is_vertical = True

    # Ajusta preset se o vídeo for horizontal e o preset for vertical
    effective_cfg = cfg.copy()
    if is_vertical and preset in ("tiktok", "reels", "shorts"):
        # Mantém vertical
        pass
    elif not is_vertical and preset in ("tiktok", "reels", "shorts"):
        # Converte horizontal para vertical com crop/pad
        pass

    # Filtro de vídeo: escala e centraliza
    vf_filters = []

    if preset == "podcast_split":
        target_w = effective_cfg["width"]
        target_h = effective_cfg["height"]
        if is_vertical:
            vf_filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease")
            vf_filters.append(f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black")
        else:
            # Podcast Split Premium: Fundo desfocado, e as duas câmeras com bordas
            vf_filters.append(
                f"split=3[bg][left_cam][right_cam];"
                f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=25:5[bg_blurred];"
                f"[left_cam]crop=iw/2:ih:0:0,scale=-2:850,pad=iw+16:ih+16:8:8:color=0x212121[top_cam];"
                f"[right_cam]crop=iw/2:ih:iw/2:0,scale=-2:850,pad=iw+16:ih+16:8:8:color=0x212121[bottom_cam];"
                f"[bg_blurred][top_cam]overlay=(W-w)/2:80[bg_t];"
                f"[bg_t][bottom_cam]overlay=(W-w)/2:H-h-80"
            )
    elif preset in ("tiktok", "reels", "shorts"):
        # Para vídeos verticais (9:16)
        target_w = effective_cfg["width"]
        target_h = effective_cfg["height"]
        if is_vertical:
            vf_filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease")
            vf_filters.append(f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black")
        else:
            # Converte horizontal -> vertical com crop centralizado ou auto-frame
            vf_filters.append(f"scale=-2:{target_h}")
            
            crop_filter = f"crop={target_w}:{target_h}"
            if auto_frame:
                rel_x = get_face_center_relative(input_path, actual_start, duration + add_padding*2)
                if rel_x is not None:
                    logger.info(f"Auto-Frame detectado no X relativo: {rel_x:.2f}")
                    if video_info:
                        orig_w = video_info.get("width", 1920)
                        orig_h = video_info.get("height", 1080)
                    else:
                        orig_w, orig_h = 1920, 1080
                    
                    new_w = int(orig_w * (target_h / orig_h))
                    crop_x = int((rel_x * new_w) - (target_w / 2))
                    crop_x = max(0, min(new_w - target_w, crop_x))
                    
                    crop_filter = f"crop={target_w}:{target_h}:{crop_x}:0"
            
            vf_filters.append(crop_filter)
            vf_filters.append(f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black")
    elif preset == "shorts_blur":
        # Shorts com fundo desfocado (sem corte lateral)
        target_w = effective_cfg["width"]
        target_h = effective_cfg["height"]
        vf_filters.append(
            f"split=2[bg][fg];"
            f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=25:5[blurred];"
            f"[fg]scale={target_w}:-2[scaled];"
            f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
        )
    elif preset == "social_frame":
        # Estilo Social Media: Vídeo centralizado com fundo desfocado
        target_w = effective_cfg["width"]
        target_h = effective_cfg["height"]
        # Reduz o vídeo para 90% da largura para criar a 'moldura'
        inner_w = int(target_w * 0.95)
        vf_filters.append(
            f"split=2[bg][fg];"
            f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=20:5[blurred];"
            f"[fg]scale={inner_w}:-2[scaled];"
            f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        # Para vídeos landscape
        target_w = effective_cfg["width"]
        target_h = effective_cfg["height"]
        vf_filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease")
        vf_filters.append(f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black")

    # --- NOVOS FILTROS E EFEITOS ---
    
    # 1. Filtros Visuais
    if visual_filter == "vibrant":
        vf_filters.append("eq=saturation=1.3:contrast=1.1:brightness=0.02")
    elif visual_filter == "cinematic":
        vf_filters.append("eq=contrast=1.2:saturation=0.9,hue=s=0.8:h=5")
    elif visual_filter == "warm":
        vf_filters.append("hue=s=1.1:h=0,eq=gamma_r=1.1:gamma_g=1.0:gamma_b=0.9")
    elif visual_filter == "cinematic_pro":
        # Contraste premium, vinheta suave
        vf_filters.append("eq=contrast=1.15:saturation=1.1,vignette=PI/4")
    elif visual_filter == "film_grain":
        # Ruído de granulação de filme
        vf_filters.append("noise=alls=10:allf=t+u,eq=contrast=1.05:saturation=0.9")

    # 2. Transições (Fade)
    if fade_duration > 0:
        vf_filters.append(f"fade=t=in:st=0:d={fade_duration}")
        vf_filters.append(f"fade=t=out:st={duration + add_padding*2 - fade_duration}:d={fade_duration}")

    # 3. Barra de Progresso Premium
    if progress_bar:
        # Desenha uma barra de progresso no topo (estilo TikTok premium) ou rodapé, com fundo translúcido
        bar_h = 10
        # Fundo da barra (preto translúcido)
        vf_filters.append(f"drawbox=y=ih-{bar_h}:w=iw:h={bar_h}:color=black@0.4:t=fill")
        # Barra de progresso (Amarelo premium com leve transparência para harmonizar)
        vf_filters.append(f"drawbox=y=ih-{bar_h}:w=iw*t/({duration + add_padding*2}):h={bar_h}:color=0xFACC15@0.9:t=fill")

    vf_string = ",".join(vf_filters) if vf_filters else "copy"

    cmd = [
        "ffmpeg",
        "-ss", str(actual_start),
        "-to", str(actual_end),
        "-i", input_path,
        "-vf", vf_string,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(effective_cfg["crf"]),
        "-maxrate", effective_cfg["video_bitrate"],
        "-bufsize", "8M",
        "-c:a", "aac",
        "-b:a", effective_cfg["audio_bitrate"],
        "-af", f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration + add_padding*2 - fade_duration}:d={fade_duration}" if fade_duration > 0 else "anull",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-avoid_negative_ts", "1",
        "-y",
        output_path
    ]

    logger.info(f"Cortando: {seconds_to_hms(start)} → {seconds_to_hms(end)} ({duration:.1f}s) | preset={preset}")
    _run_ffmpeg(cmd, f"cut {start:.1f}s-{end:.1f}s", timeout=300)

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        logger.info(f"Corte gerado: {output_path} ({size / 1024 / 1024:.1f} MB)")
    return output_path


def embed_subtitles_hardcoded(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_name: str = "Arial",
    font_size: int = 18,
    font_color: str = "white",
    outline_color: str = "black",
    outline_width: int = 2,
    position: str = "bottom",   # 'bottom', 'center', 'top'
    bold: bool = True,
) -> str:
    """
    Embuti legendas hardcoded (burn-in) no vídeo usando FFmpeg subtitles filter.

    Args:
        video_path: Vídeo de entrada
        srt_path: Arquivo SRT de legendas
        output_path: Vídeo de saída
        font_name: Nome da fonte
        font_size: Tamanho da fonte
        font_color: Cor do texto
        outline_color: Cor da borda
        outline_width: Largura da borda
        position: Posição vertical das legendas
        bold: Texto em negrito

    Returns:
        Caminho do vídeo com legendas
    """
    # Escapa o caminho do SRT para o filtro do FFmpeg (Windows/Linux)
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    if " " in srt_escaped:
        srt_escaped = f"'{srt_escaped}'"

    # Posição vertical
    pos_map = {
        "bottom": "10",
        "center": "(h-text_h)/2",
        "top": "h-text_h-10",
    }
    margin_v = pos_map.get(position, "10")
    alignment = 2  # alinhamento inferior centralizado no SRT

    # Style para ASS/SSA via FFmpeg
    force_style = (
        f"FontName={font_name},"
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BorderStyle=1,"
        f"Outline={outline_width},"
        f"Shadow=1,"
        f"Bold={1 if bold else 0},"
        f"MarginV=30,"
        f"Alignment={alignment}"
    )

    # Usa subtitles filter para burn-in
    if srt_path.lower().endswith(".ass"):
        # Para ASS, a estilização já está no arquivo
        subtitle_filter = f"subtitles={srt_escaped}"
    else:
        subtitle_filter = f"subtitles={srt_escaped}:force_style='{force_style}'"

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]

    logger.info(f"Embutindo legendas: {srt_path} → {output_path}")
    _run_ffmpeg(cmd, "embed subtitles", timeout=300)

    if os.path.exists(output_path):
        logger.info(f"Vídeo com legendas: {output_path}")
    return output_path


def embed_subtitles_soft(
    video_path: str,
    srt_path: str,
    output_path: str,
    language: str = "por",
) -> str:
    """
    Adiciona legendas como faixa de texto separada (soft subtitles).
    Mais rápido que burn-in, mas requer player compatível.
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", srt_path,
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={language}",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]

    logger.info(f"Adicionando legendas soft: {output_path}")
    _run_ffmpeg(cmd, "soft subtitles", timeout=120)
    return output_path


def process_cut(
    input_video: str,
    output_dir: str,
    cut_index: int,
    start: float,
    end: float,
    srt_path: Optional[str],
    video_info: Optional[dict] = None,
    preset: str = "landscape",
    subtitle_style: str = "hardcoded",  # 'hardcoded', 'soft', 'none'
    cut_name: Optional[str] = None,
    # Opções de Edição Avançada
    visual_filter: str = "none",
    bg_music_path: Optional[str] = None,
    bg_music_volume: float = 0.15,
    fade_duration: float = 0.5,
    progress_bar: bool = False,
    theme: str = "neutral",
    auto_frame: bool = False,
) -> dict:
    """
    Processa um corte completo: corta o vídeo e embuti legendas.

    Args:
        input_video: Vídeo original
        output_dir: Diretório de saída
        cut_index: Número do corte (para naming)
        start: Início em segundos
        end: Fim em segundos
        srt_path: Caminho do SRT (None se sem legendas)
        video_info: Informações do vídeo
        preset: Preset de exportação
        subtitle_style: Estilo de legenda
        cut_name: Nome amigável para o arquivo

    Returns:
        Dict com informações do corte processado
    """
    ensure_dir(output_dir)
    duration = end - start

    # Gera nome de arquivo
    if cut_name:
        safe_name = sanitize_filename(cut_name)
    else:
        safe_name = f"corte_{cut_index:02d}_{int(start)}s_{int(end)}s"

    base_path = os.path.join(output_dir, safe_name)

    result = {
        "cut_index": cut_index,
        "start": start,
        "end": end,
        "duration": duration,
        "files": {}
    }

    try:
        # 1. Corte sem legendas
        raw_path = base_path + "_raw.mp4"
        cut_video_segment(
            input_path=input_video,
            output_path=raw_path,
            start=start,
            end=end,
            video_info=video_info,
            preset=preset,
            visual_filter=visual_filter,
            fade_duration=fade_duration,
            progress_bar=progress_bar,
            auto_frame=auto_frame,
        )
        result["files"]["raw"] = raw_path

        # 1.5. Adiciona Música de Fundo (se configurado)
        if bg_music_path:
            final_music_path = base_path + "_with_music.mp4"
            if add_background_music(raw_path, bg_music_path, final_music_path, volume=bg_music_volume, theme=theme):
                # Substitui o raw pelo vídeo com música para os próximos passos
                if os.path.exists(raw_path): os.remove(raw_path)
                raw_path = final_music_path
                result["files"]["raw"] = raw_path

        # 2. Adiciona legendas
        if srt_path and os.path.exists(srt_path):
            final_path = base_path + ".mp4"

            if subtitle_style in ("hardcoded", "high_impact"):
                embed_subtitles_hardcoded(
                    video_path=raw_path,
                    srt_path=srt_path,
                    output_path=final_path,
                )
            elif subtitle_style == "soft":
                embed_subtitles_soft(
                    video_path=raw_path,
                    srt_path=srt_path,
                    output_path=final_path,
                )
            else:
                # Sem legendas: renomeia o raw como final
                os.rename(raw_path, final_path)

            # Remove arquivo intermediário se gerou final
            if os.path.exists(final_path) and os.path.exists(raw_path):
                if final_path != raw_path:
                    try:
                        os.remove(raw_path)
                    except Exception:
                        pass

            result["files"]["final"] = final_path
        else:
            # Sem SRT: usa o raw como final
            final_path = base_path + ".mp4"
            os.rename(raw_path, final_path)
            result["files"]["final"] = final_path

        result["success"] = True
        logger.info(f"✓ Corte #{cut_index:02d} processado: {final_path}")

    except Exception as e:
        logger.error(f"✗ Erro ao processar corte #{cut_index:02d}: {e}")
        result["success"] = False
        result["error"] = str(e)

    return result


def get_video_thumbnail(
    video_path: str,
    output_path: str,
    timestamp: float = 2.0,
) -> Optional[str]:
    """
    Gera uma thumbnail do vídeo em um timestamp específico.
    """
    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y",
        output_path
    ]

    try:
        _run_ffmpeg(cmd, "thumbnail", timeout=30)
        return output_path
    except Exception as e:
        logger.warning(f"Erro ao gerar thumbnail: {e}")
        return None


def add_background_music(
    video_path: str,
    music_source: str,
    output_path: str,
    volume: float = 0.15,
    theme: str = "neutral"
) -> bool:
    """
    Adiciona música de fundo ao vídeo, mixando com o áudio original.
    
    Args:
        video_path: Caminho do vídeo
        music_source: Caminho para um arquivo MP3 ou diretório de músicas
        output_path: Destino
        volume: Volume da música (0.0 a 1.0)
        theme: Tema sugerido para tentar filtrar músicas por nome
    """
    music_file = music_source
    
    # Se for um diretório, escolhe uma música (tenta bater com o tema)
    if os.path.isdir(music_source):
        files = [f for f in os.listdir(music_source) if f.lower().endswith(('.mp3', '.wav', '.m4a'))]
        if not files:
            logger.warning(f"Nenhuma música encontrada em {music_source}")
            return False
            
        # Tenta encontrar música que contenha o nome do tema
        theme_matches = [f for f in files if theme.lower() in f.lower()]
        music_file = os.path.join(music_source, random.choice(theme_matches if theme_matches else files))

    if not os.path.exists(music_file):
        return False

    logger.info(f"Adicionando trilha sonora: {os.path.basename(music_file)} (vol={volume}) | tema={theme}")

    # Comando complexo de mixagem:
    # 1. Input do vídeo e da música (looping a música)
    # 2. amix para misturar os dois
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-stream_loop", "-1", "-i", music_file,
        "-filter_complex", 
        f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", # vídeo apenas copiado para ser rápido
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-y",
        output_path
    ]

    try:
        _run_ffmpeg(cmd, "add music", timeout=120)
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar música: {e}")
        return False