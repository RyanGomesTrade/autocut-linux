# -*- coding: utf-8 -*-
import utf8_bootstrap
import os
import sys
import json
import time
import argparse
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

# ─── Módulos do sistema ────────────────────────────────────────────────────────
from utils import (
    setup_logging, check_ffmpeg, check_ollama,
    get_video_info, ensure_dir, format_size, seconds_to_hms
)
from transcriber import (
    extract_audio, transcribe,
    split_transcript_into_blocks, save_transcript,
    TranscriptionResult
)
from analyzer import (
    OllamaAnalyzer, rank_and_filter_cuts,
    save_cuts_json, ViralCut
)
from subtitle_generator import generate_srt_for_cut
from cutter import process_cut, detect_silence, adjust_cut_to_avoid_silence, EXPORT_PRESETS
from watermark import apply_watermark_to_result


# ─── Configurações padrão ─────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    # Transcrição
    "whisper_model": "medium",           # tiny, base, small, medium, large-v2, large-v3
    "whisper_backend": "auto",           # auto, faster-whisper, whisper
    "whisper_device": "cpu",             # cpu, cuda
    "language": None,                    # None = detecção automática, "pt", "en", etc.

    # Análise com Ollama
    "ollama_model": "llama3",            # modelo do Ollama instalado
    "ollama_host": "http://localhost:11434",
    "ollama_timeout": 300,               # segundos por requisição
    "block_duration": 360.0,             # 6 minutos por bloco de análise
    "block_overlap": 30.0,               # 30s de sobreposição entre blocos

    # Seleção de cortes
    "top_n": 10,                         # número de cortes finais
    "min_viral_score": 40.0,             # score mínimo para incluir corte
    "min_duration": 20.0,                # duração mínima do corte (s)
    "max_duration": 600.0,               # duração máxima do corte (s)

    # Exportação
    "preset": "landscape",               # landscape, tiktok, reels, shorts, square
    "subtitle_style": "high_impact",     # high_impact, hardcoded, soft, none
    "detect_silence": True,              # ajustar cortes evitando silêncio
    "visual_filter": "none",
    "bg_music": None,
    "bg_music_volume": 0.15,
    "fade_duration": 0.5,
    "progress_bar": False,

    # Diretórios
    "keep_temp": False,                  # manter arquivos temporários
    "log_level": "INFO",

    # Marca d'água
    "watermark_image":    None,          # caminho para PNG/WebP
    "watermark_text":     None,          # texto (ex: @meucanal)
    "watermark_position": "bottom_right",
    "watermark_opacity":  0.8,
    "watermark_scale":    1.0,
    "watermark_font_size": 40,
    "watermark_font_color": "white",
}


def parse_arguments() -> argparse.Namespace:
    """
    Define e processa argumentos da linha de comando.
    """
    parser = argparse.ArgumentParser(
        description="🎬 Viral Cutter - Gerador automático de cortes virais",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python main.py --input podcast.mp4 --output cortes/
  python main.py --input entrevista.mp4 --output clips/ --top-n 5 --preset tiktok
  python main.py --input live.mp4 --output clips/ --model llama3 --language pt
  python main.py --input video.mp4 --output clips/ --whisper-model large-v2 --no-subtitles

Presets de exportação disponíveis:
  landscape  - 1920x1080 (YouTube, padrão)
  tiktok     - 1080x1920 (TikTok vertical)
  reels      - 1080x1920 (Instagram Reels)
  shorts     - 1080x1920 (YouTube Shorts)
  square     - 1080x1080 (Instagram feed)
        """
    )

    # Argumentos obrigatórios
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Caminho do vídeo de entrada (MP4)"
    )
    parser.add_argument(
        "--output", "-o",
        default="output_clips",
        help="Diretório de saída dos cortes (padrão: output_clips/)"
    )

    # Configurações de transcrição
    trans_group = parser.add_argument_group("Transcrição (Whisper)")
    trans_group.add_argument(
        "--whisper-model",
        default=DEFAULT_CONFIG["whisper_model"],
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help=f"Modelo Whisper (padrão: {DEFAULT_CONFIG['whisper_model']})"
    )
    trans_group.add_argument(
        "--whisper-backend",
        default=DEFAULT_CONFIG["whisper_backend"],
        choices=["auto", "faster-whisper", "whisper"],
        help="Backend de transcrição (padrão: auto)"
    )
    trans_group.add_argument(
        "--device",
        default=DEFAULT_CONFIG["whisper_device"],
        choices=["cpu", "cuda"],
        help="Dispositivo de processamento (padrão: cpu)"
    )
    trans_group.add_argument(
        "--language",
        default=DEFAULT_CONFIG["language"],
        help="Código do idioma (ex: pt, en). Padrão: detecção automática"
    )

    # Configurações de análise
    analysis_group = parser.add_argument_group("Análise (Ollama)")
    analysis_group.add_argument(
        "--model",
        default=DEFAULT_CONFIG["ollama_model"],
        help=f"Modelo Ollama (padrão: {DEFAULT_CONFIG['ollama_model']})"
    )
    analysis_group.add_argument(
        "--ollama-host",
        default=DEFAULT_CONFIG["ollama_host"],
        help=f"URL do Ollama (padrão: {DEFAULT_CONFIG['ollama_host']})"
    )
    analysis_group.add_argument(
        "--block-duration",
        type=float,
        default=DEFAULT_CONFIG["block_duration"],
        help=f"Duração dos blocos de análise em segundos (padrão: {DEFAULT_CONFIG['block_duration']})"
    )
    analysis_group.add_argument(
        "--block-overlap",
        type=float,
        default=DEFAULT_CONFIG["block_overlap"],
        help=f"Sobreposição entre blocos em segundos (padrão: {DEFAULT_CONFIG['block_overlap']})"
    )

    # Configurações de seleção
    select_group = parser.add_argument_group("Seleção de cortes")
    select_group.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_CONFIG["top_n"],
        help=f"Número máximo de cortes finais (padrão: {DEFAULT_CONFIG['top_n']})"
    )
    select_group.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_CONFIG["min_viral_score"],
        help=f"Score mínimo para incluir corte (padrão: {DEFAULT_CONFIG['min_viral_score']})"
    )
    select_group.add_argument(
        "--min-duration",
        type=float,
        default=DEFAULT_CONFIG["min_duration"],
        help=f"Duração mínima do corte em segundos (padrão: {DEFAULT_CONFIG['min_duration']})"
    )
    select_group.add_argument(
        "--max-duration",
        type=float,
        default=DEFAULT_CONFIG["max_duration"],
        help=f"Duração máxima do corte em segundos (padrão: {DEFAULT_CONFIG['max_duration']})"
    )

    # Configurações de exportação
    export_group = parser.add_argument_group("Exportação de vídeo")
    export_group.add_argument(
        "--preset",
        default=DEFAULT_CONFIG["preset"],
        choices=list(EXPORT_PRESETS.keys()),
        help=f"Preset de exportação (padrão: {DEFAULT_CONFIG['preset']})"
    )
    export_group.add_argument(
        "--subtitle-style",
        default=DEFAULT_CONFIG["subtitle_style"],
        choices=["high_impact", "hardcoded", "soft", "none"],
        help=f"Estilo de legenda (padrão: {DEFAULT_CONFIG['subtitle_style']})"
    )
    export_group.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Não embuti legendas nos vídeos"
    )
    export_group.add_argument(
        "--no-silence-detect",
        action="store_true",
        help="Não ajusta cortes para evitar silêncios"
    )
    export_group.add_argument(
        "--visual-filter",
        default=DEFAULT_CONFIG["visual_filter"],
        choices=["none", "vibrant", "cinematic", "warm"],
        help=f"Filtro visual (padrão: {DEFAULT_CONFIG['visual_filter']})"
    )
    export_group.add_argument(
        "--bg-music",
        help="Caminho para arquivo ou pasta de músicas de fundo"
    )
    export_group.add_argument(
        "--bg-music-volume",
        type=float,
        default=DEFAULT_CONFIG["bg_music_volume"],
        help=f"Volume da música 0.0-1.0 (padrão: {DEFAULT_CONFIG['bg_music_volume']})"
    )
    export_group.add_argument(
        "--fade-duration",
        type=float,
        default=DEFAULT_CONFIG["fade_duration"],
        help=f"Duração dos fades em segundos (padrão: {DEFAULT_CONFIG['fade_duration']})"
    )
    export_group.add_argument(
        "--progress-bar",
        action="store_true",
        help="Adiciona barra de progresso visual no rodapé"
    )
    export_group.add_argument(
        "--auto-frame",
        action="store_true",
        help="Usa IA para seguir o rosto da pessoa (Auto-Framing)"
    )

    # Configurações gerais
    general_group = parser.add_argument_group("Configurações gerais")
    general_group.add_argument(
        "--keep-temp",
        action="store_true",
        help="Mantém arquivos temporários (áudio extraído, etc.)"
    )
    general_group.add_argument(
        "--log-level",
        default=DEFAULT_CONFIG["log_level"],
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Nível de log (padrão: {DEFAULT_CONFIG['log_level']})"
    )
    general_group.add_argument(
        "--skip-transcription",
        metavar="TRANSCRIPT_JSON",
        help="Pula a transcrição usando arquivo JSON existente"
    )
    general_group.add_argument(
        "--skip-analysis",
        metavar="CUTS_JSON",
        help="Pula a análise usando arquivo JSON de cortes existente"
    )

    # Marca d'água
    wm_group = parser.add_argument_group("Marca d'água")
    wm_group.add_argument(
        "--watermark-image",
        metavar="IMAGE_PATH",
        help="Caminho para PNG/WebP da marca d'água (com transparência)"
    )
    wm_group.add_argument(
        "--watermark-text",
        metavar="TEXT",
        help="Texto da marca d'água (ex: @meucanal)"
    )
    wm_group.add_argument(
        "--watermark-position",
        default="bottom_right",
        choices=["top_left", "top_right", "bottom_left", "bottom_right",
                 "center", "top_center", "bottom_center"],
        help="Posição da marca d'água (padrão: bottom_right)"
    )
    wm_group.add_argument(
        "--watermark-opacity",
        type=float,
        default=0.8,
        help="Opacidade da marca d'água 0.0–1.0 (padrão: 0.8)"
    )
    wm_group.add_argument(
        "--watermark-scale",
        type=float,
        default=1.0,
        help="Escala da imagem de marca d'água (padrão: 1.0)"
    )
    wm_group.add_argument(
        "--watermark-font-size",
        type=int,
        default=40,
        help="Tamanho da fonte do texto da marca d'água (padrão: 40)"
    )
    wm_group.add_argument(
        "--watermark-font-color",
        default="white",
        help="Cor do texto da marca d'água (padrão: white)"
    )

    return parser.parse_args()


def log_banner(logger: logging.Logger):
    """Gera o banner do sistema no log."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║          🎬  VIRAL CUTTER  -  Cortes Automáticos          ║
║     Whisper + Ollama + FFmpeg | 100% Local & Gratuito     ║
╚═══════════════════════════════════════════════════════════╝
"""
    for line in banner.strip().split("\n"):
        logger.info(line)


def preflight_checks(args: argparse.Namespace, logger: logging.Logger) -> bool:
    """
    Verifica pré-requisitos antes de iniciar o processamento.
    """
    all_ok = True

    # Verifica arquivo de entrada
    if not os.path.exists(args.input):
        logger.error(f"Arquivo de entrada não encontrado: {args.input}")
        all_ok = False

    # Verifica FFmpeg
    if not check_ffmpeg():
        logger.error("FFmpeg não encontrado. Instale com: sudo apt install ffmpeg")
        all_ok = False
    else:
        logger.info("✓ FFmpeg disponível")

    # Verifica Ollama (se não está pulando análise)
    if not args.skip_analysis:
        if not check_ollama():
            logger.error(
                f"Ollama não está rodando em {args.ollama_host}. "
                f"Inicie com: ollama serve"
            )
            all_ok = False
        else:
            logger.info(f"✓ Ollama disponível em {args.ollama_host}")

    return all_ok


def save_session_report(
    output_dir: str,
    video_path: str,
    video_info: dict,
    cuts: list[ViralCut],
    processing_results: list[dict],
    elapsed_time: float,
) -> str:
    """
    Salva um relatório JSON completo da sessão de processamento.
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "input_video": video_path,
        "video_info": video_info,
        "total_cuts_found": len(cuts),
        "total_cuts_exported": sum(1 for r in processing_results if r.get("success")),
        "elapsed_seconds": round(elapsed_time, 1),
        "cuts": [c.to_dict() for c in cuts],
        "exported_files": [
            {
                "cut_index": r["cut_index"],
                "start": r["start"],
                "end": r["end"],
                "duration": r["duration"],
                "file": r.get("files", {}).get("final", ""),
                "success": r.get("success", False),
                "error": r.get("error", ""),
            }
            for r in processing_results
        ]
    }

    report_path = os.path.join(output_dir, "session_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_path


def print_summary(cuts: list[ViralCut], results: list[dict], elapsed: float, logger: logging.Logger):
    """Imprime um resumo final do processamento."""
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    logger.info("\n" + "═" * 60)
    logger.info("📊 RESUMO FINAL")
    logger.info("═" * 60)
    logger.info(f"  Cortes selecionados : {len(cuts)}")
    logger.info(f"  Exportados com êxito: {len(successful)}")
    logger.info(f"  Com erro            : {len(failed)}")
    logger.info(f"  Tempo total         : {seconds_to_hms(elapsed)}")
    logger.info("─" * 60)

    if successful:
        logger.info("  Cortes exportados:")
        for r in successful:
            cut = next((c for c in cuts if c.start == r["start"]), None)
            score = f"{cut.final_score:.0f}" if cut else "?"
            logger.info(
                f"  #{r['cut_index']:02d} | {seconds_to_hms(r['start'])}-{seconds_to_hms(r['end'])} "
                f"({r['duration']:.0f}s) | score={score} | "
                f"{Path(r.get('files', {}).get('final', '')).name}"
            )

    if failed:
        logger.info("  Erros:")
        for r in failed:
            logger.info(f"  #{r['cut_index']:02d} | {r.get('error', 'erro desconhecido')}")

    logger.info("═" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(args: argparse.Namespace) -> int:
    """
    Executa o pipeline completo de extração de cortes virais.

    Returns:
        0 se bem-sucedido, 1 se erro
    """
    start_time = time.time()
    logger = logging.getLogger("viral_cutter")

    log_banner(logger)

    # Cria diretórios de saída
    output_dir = ensure_dir(args.output)
    temp_dir = ensure_dir(os.path.join(str(output_dir), ".temp"))
    srt_dir = ensure_dir(os.path.join(str(output_dir), "subtitles"))

    logger.info(f"📁 Saída: {output_dir}")
    logger.info(f"🎬 Entrada: {args.input}")

    # ─── Verificações de pré-requisitos ───────────────────────────────────────
    if not preflight_checks(args, logger):
        return 1

    # ─── Informações do vídeo ─────────────────────────────────────────────────
    logger.info("\n⬛ ETAPA 1/6: Analisando vídeo de entrada...")
    try:
        video_info = get_video_info(args.input)
        logger.info(
            f"  Duração   : {seconds_to_hms(video_info['duration'])} "
            f"({video_info['duration']:.0f}s)"
        )
        logger.info(
            f"  Resolução : {video_info['width']}x{video_info['height']} "
            f"@ {video_info['fps']}fps"
        )
        logger.info(f"  Tamanho   : {format_size(video_info['size_bytes'])}")
        logger.info(f"  Codec     : {video_info['video_codec']}/{video_info['audio_codec']}")
    except Exception as e:
        logger.error(f"Erro ao analisar vídeo: {e}")
        return 1

    # ─── Extração de áudio ────────────────────────────────────────────────────
    transcript: Optional[TranscriptionResult] = None

    if args.skip_transcription:
        logger.info(f"\n⬛ ETAPA 2/6: Carregando transcrição de {args.skip_transcription}...")
        try:
            import pickle
            with open(args.skip_transcription, "rb") as f:
                transcript = pickle.load(f)
            logger.info(f"  {len(transcript.segments)} segmentos carregados")
        except Exception as e:
            logger.error(f"Erro ao carregar transcrição: {e}")
            return 1
    else:
        logger.info("\n⬛ ETAPA 2/6: Extraindo áudio...")
        try:
            import tempfile
            fd, audio_path = tempfile.mkstemp(suffix=".wav", prefix="viral_cutter_audio_")
            os.close(fd)

            extract_audio(args.input, audio_path)
            audio_size = os.path.getsize(audio_path)
            logger.info(f"  Áudio extraído: {format_size(audio_size)}")
        except Exception as e:
            import traceback
            logger.error(f"Erro ao extrair áudio: {e}")
            logger.error(traceback.format_exc())
            return 1

        # ─── Transcrição com Whisper ─────────────────────────────────────────────
        logger.info(f"\n⬛ ETAPA 3/6: Transcrevendo com Whisper ({args.whisper_model})...")
        logger.info("  (Este passo pode levar alguns minutos dependendo do hardware)")

        try:
            transcript = transcribe(
                audio_path=audio_path,
                model_size=args.whisper_model,
                language=args.language,
                device=args.device,
                backend=args.whisper_backend,
            )
            logger.info(
                f"  Idioma: {transcript.language} | "
                f"Segmentos: {len(transcript.segments)} | "
                f"Duração: {seconds_to_hms(transcript.audio_duration)}"
            )

            # Salva transcrição
            transcript_txt = os.path.join(str(output_dir), "transcript.txt")
            save_transcript(transcript, transcript_txt)

            # Salva para reuso
            import pickle
            transcript_pkl = os.path.join(str(output_dir), "transcript.pkl")
            with open(transcript_pkl, "wb") as f:
                pickle.dump(transcript, f)
            logger.info(f"  (Para reusar: --skip-transcription {transcript_pkl})")

        except Exception as e:
            logger.error(f"Erro na transcrição: {e}")
            return 1

        finally:
            # Remove áudio temporário se não for manter
            if not args.keep_temp and os.path.exists(audio_path):
                os.remove(audio_path)

    # ─── Análise com Ollama ───────────────────────────────────────────────────
    all_cuts: list[ViralCut] = []

    if args.skip_analysis:
        logger.info(f"\n⬛ ETAPA 4/6: Carregando cortes de {args.skip_analysis}...")
        try:
            with open(args.skip_analysis, "r", encoding="utf-8") as f:
                cuts_data = json.load(f)
            from analyzer import ViralCut
            all_cuts = [
                ViralCut(
                    start=c["start"], end=c["end"], duration=c["duration"],
                    viral_score=c["viral_score"], hook=c.get("hook", ""),
                    summary=c.get("summary", ""), motivo=c.get("motivo", ""),
                    block_index=c.get("block_index", 0),
                    python_score=c.get("python_score", 0),
                    final_score=c.get("final_score", c["viral_score"]),
                )
                for c in cuts_data
            ]
            logger.info(f"  {len(all_cuts)} cortes carregados")
        except Exception as e:
            logger.error(f"Erro ao carregar cortes: {e}")
            return 1
    else:
        logger.info(f"\n⬛ ETAPA 4/6: Analisando com Ollama ({args.model})...")
        logger.info("  (Este passo pode ser lento dependendo do modelo e hardware)")

        # ── CORREÇÃO: block_duration agora usa o valor configurado ──────────
        # Antes: hardcoded block_duration=60.0, overlap=15.0
        # Agora: lê de args (propagados de DEFAULT_CONFIG ou CLI)
        block_duration = getattr(args, "block_duration", DEFAULT_CONFIG["block_duration"])
        block_overlap = getattr(args, "block_overlap", DEFAULT_CONFIG["block_overlap"])

        # Garante que o bloco seja grande o suficiente para acomodar max_duration
        # O bloco precisa ser pelo menos max_duration + margem para que o LLM
        # consiga gerar cortes na duração desejada.
        min_block = args.max_duration + 60
        if block_duration < min_block:
            logger.warning(
                f"⚠️ block_duration ({block_duration:.0f}s) é menor que "
                f"max_duration + margem ({min_block:.0f}s). "
                f"Ajustando automaticamente para {min_block:.0f}s."
            )
            block_duration = min_block

        blocks = split_transcript_into_blocks(
            transcript,
            block_duration=block_duration,
            overlap=block_overlap,
        )
        logger.info(
            f"  Transcrição dividida em {len(blocks)} blocos para análise "
            f"(bloco={block_duration:.0f}s, sobreposição={block_overlap:.0f}s)"
        )

        # Escolha do motor de análise
        engine = getattr(args, 'analysis_engine', 'ollama')

        try:
            if engine == "heuristic":
                from analyzer import HeuristicAnalyzer
                # ── CORREÇÃO: propaga min_duration / max_duration ───────────
                analyzer = HeuristicAnalyzer(
                    top_n=args.top_n,
                    min_duration=args.min_duration,
                    max_duration=args.max_duration,
                )
                all_cuts = analyzer.analyze(transcript.segments)
            else:
                # ── CORREÇÃO: propaga min_duration / max_duration ───────────
                analyzer = OllamaAnalyzer(
                    model=args.model,
                    host=args.ollama_host,
                    timeout=args.ollama_timeout,
                    min_duration=args.min_duration,
                    max_duration=args.max_duration,
                )
                all_cuts = analyzer.analyze_all_blocks(blocks)
        except Exception as e:
            logger.error(f"Erro na análise: {e}")
            return 1

        if not all_cuts:
            logger.error("Nenhum corte encontrado. Verifique o modelo Ollama e a transcrição.")
            return 1

        # Salva cortes brutos
        raw_cuts_path = os.path.join(str(output_dir), "cuts_raw.json")
        save_cuts_json(all_cuts, raw_cuts_path)

    # ─── Ranqueamento dos cortes ──────────────────────────────────────────────
    logger.info(f"\n⬛ ETAPA 5/6: Ranqueando e selecionando top {args.top_n} cortes...")

    selected_cuts = rank_and_filter_cuts(
        cuts=all_cuts,
        transcript_segments=transcript.segments if transcript else [],
        top_n=args.top_n,
        min_score=args.min_score,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )

    if not selected_cuts:
        logger.warning("Nenhum corte passou pelos filtros. Tente reduzir --min-score.")
        return 1

    # Salva cortes selecionados
    final_cuts_path = os.path.join(str(output_dir), "cuts_selected.json")
    save_cuts_json(selected_cuts, final_cuts_path)
    logger.info(f"  {len(selected_cuts)} cortes selecionados | salvo em: {final_cuts_path}")

    # ─── Detecção de silêncio (opcional) ─────────────────────────────────────
    silences = []
    if not args.no_silence_detect:
        logger.info("  Detectando silêncios para ajuste fino dos cortes...")
        try:
            silences = detect_silence(args.input)
        except Exception as e:
            logger.warning(f"Falha na detecção de silêncio (não crítico): {e}")

    # ─── Geração de vídeos finais ─────────────────────────────────────────────
    logger.info(f"\n⬛ ETAPA 6/6: Gerando {len(selected_cuts)} vídeos finais...")

    subtitle_style = "none"
    if not args.no_subtitles:
        subtitle_style = getattr(args, 'subtitle_style', 'high_impact')
        if getattr(args, 'soft_subtitles', False): subtitle_style = "soft"

    # --- Auto-Detecção de Preset (IA) ---
    selected_preset = args.preset
    if selected_preset == "auto_detect":
        from cutter import auto_select_preset
        logger.info("🤖 Iniciando detecção automática de preset via MediaPipe...")
        selected_preset = auto_select_preset(args.input)
        logger.info(f"🤖 Preset selecionado pela IA: '{selected_preset}'")

    processing_results = []

    for i, cut in enumerate(selected_cuts, 1):
        logger.info(f"\n  ▶ Processando corte {i}/{len(selected_cuts)}: "
                    f"{seconds_to_hms(cut.start)}-{seconds_to_hms(cut.end)} "
                    f"| score={cut.final_score:.0f}")

        # Ajuste de silêncio
        cut_start = cut.start
        cut_end = cut.end
        if silences:
            cut_start, cut_end = adjust_cut_to_avoid_silence(
                cut.start, cut.end, silences
            )

        # Gera legenda SRT
        srt_path = None
        if subtitle_style != "none" and transcript:
            try:
                if subtitle_style == "high_impact":
                    from subtitle_generator import generate_high_impact_subtitles
                    srt_filename = f"cut_{i:02d}_{int(cut_start)}s.ass"
                    srt_path = os.path.join(str(srt_dir), srt_filename)
                    generate_high_impact_subtitles(
                        cut_start=cut_start,
                        cut_end=cut_end,
                        all_segments=transcript.segments,
                        output_path=srt_path,
                        preset=selected_preset,
                    )
                else:
                    srt_filename = f"cut_{i:02d}_{int(cut_start)}s.srt"
                    srt_path = os.path.join(str(srt_dir), srt_filename)
                    generate_srt_for_cut(
                        cut_start=cut_start,
                        cut_end=cut_end,
                        all_segments=transcript.segments,
                        output_path=srt_path,
                        use_word_timestamps=True,
                    )
            except Exception as e:
                logger.warning(f"Erro ao gerar SRT: {e}")
                srt_path = None

        # Nome amigável
        hook_short = cut.hook[:30].strip() if cut.hook else f"corte_{i:02d}"
        cut_name = f"{i:02d}_{hook_short}"

        # Processa o corte
        result = process_cut(
            input_video=args.input,
            output_dir=str(output_dir),
            cut_index=i,
            start=cut_start,
            end=cut_end,
            srt_path=srt_path,
            video_info=video_info,
            preset=selected_preset,
            subtitle_style=subtitle_style,
            cut_name=cut_name,
            visual_filter=getattr(args, 'visual_filter', 'none'),
            bg_music_path=getattr(args, 'bg_music', None),
            bg_music_volume=getattr(args, 'bg_music_volume', 0.15),
            fade_duration=getattr(args, 'fade_duration', 0.5),
            progress_bar=getattr(args, 'progress_bar', False),
            theme=cut.theme,
            auto_frame=getattr(args, 'auto_frame', False),
        )
        processing_results.append(result)

        # ── Marca d'água (opcional) ───────────────────────────────────────────
        wm_image = getattr(args, 'watermark_image', None)
        wm_text  = getattr(args, 'watermark_text', None)
        if wm_image or wm_text:
            watermark_cfg = {
                "image_path":  wm_image,
                "text":        wm_text,
                "position":    getattr(args, 'watermark_position',   'bottom_right'),
                "opacity":     getattr(args, 'watermark_opacity',    0.8),
                "scale":       getattr(args, 'watermark_scale',      1.0),
                "font_size":   getattr(args, 'watermark_font_size',  40),
                "font_color":  getattr(args, 'watermark_font_color', 'white'),
            }
            processing_results[-1] = apply_watermark_to_result(result, watermark_cfg)

    # ─── Relatório final ──────────────────────────────────────────────────────
    elapsed = time.time() - start_time

    report_path = save_session_report(
        output_dir=str(output_dir),
        video_path=args.input,
        video_info=video_info,
        cuts=selected_cuts,
        processing_results=processing_results,
        elapsed_time=elapsed,
    )

    # Remove diretório temp se não for manter
    if not args.keep_temp:
        import shutil
        try:
            shutil.rmtree(str(temp_dir), ignore_errors=True)
        except Exception:
            pass

    print_summary(selected_cuts, processing_results, elapsed, logger)
    logger.info(f"\n📄 Relatório completo: {report_path}")
    logger.info(f"📁 Vídeos gerados em: {output_dir}\n")

    successful = sum(1 for r in processing_results if r.get("success"))
    return 0 if successful > 0 else 1


# ─── Ponto de entrada ─────────────────────────────────────────────────────────

def main():
    args = parse_arguments()

    # Configura logging
    log_file = os.path.join(
        args.output,
        f"viral_cutter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    ensure_dir(args.output)
    logger = setup_logging(log_level=args.log_level, log_file=log_file)

    try:
        exit_code = run_pipeline(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrompido pelo usuário.")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Erro não tratado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()