# -*- coding: utf-8 -*-
"""
watermark.py - Adição de marca d'água aos cortes finais do Viral Cutter

Integração: chamado em main.py logo após process_cut(), antes de salvar
o resultado final em processing_results.

Suporta:
  - Imagem PNG/SVG (com transparência) em qualquer canto ou posição custom
  - Texto simples com fonte, tamanho, cor e opacidade configuráveis
  - Combinação de imagem + texto
  - Respeita todos os presets de resolução (portrait/landscape/square)
  - Segue os padrões do projeto: _run_ffmpeg, _utf8_env, logging, str() em paths

Uso standalone (CLI):
  python watermark.py --input corte.mp4 --output corte_wm.mp4 \
      --image logo.png --position bottom_right --opacity 0.7

  python watermark.py --input corte.mp4 --output corte_wm.mp4 \
      --text "@meucanal" --text-size 48 --text-color white \
      --position top_right

Integração em main.py (adicionar após process_cut):
  from watermark import apply_watermark_to_result

  result = process_cut(...)
  result = apply_watermark_to_result(result, watermark_config)
"""

import os
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Optional

from utils import ensure_dir, _utf8_env

logger = logging.getLogger("viral_cutter.watermark")


# ─── Posições predefinidas ────────────────────────────────────────────────────
#
# Cada valor é uma expressão FFmpeg para (x, y) do overlay.
# As variáveis main_w / main_h = dimensões do vídeo base.
#           overlay_w / overlay_h = dimensões da marca d'água.
# MARGIN = margem em pixels em relação às bordas.
#
MARGIN = 30  # px

POSITIONS = {
    "top_left":      (f"{MARGIN}",                       f"{MARGIN}"),
    "top_right":     (f"main_w-overlay_w-{MARGIN}",      f"{MARGIN}"),
    "bottom_left":   (f"{MARGIN}",                       f"main_h-overlay_h-{MARGIN}"),
    "bottom_right":  (f"main_w-overlay_w-{MARGIN}",      f"main_h-overlay_h-{MARGIN}"),
    "center":        (f"(main_w-overlay_w)/2",           f"(main_h-overlay_h)/2"),
    "top_center":    (f"(main_w-overlay_w)/2",           f"{MARGIN}"),
    "bottom_center": (f"(main_w-overlay_w)/2",           f"main_h-overlay_h-{MARGIN}"),
}

# ─── Posições para TEXTO (usando variáveis drawtext) ──────────────────────────
# O filtro drawtext usa variáveis diferentes (W, H, tw, th) em vez de main_w, overlay_w.
TEXT_POSITIONS = {
    "top_left":      (f"{MARGIN}",                f"{MARGIN}"),
    "top_right":     (f"W-tw-{MARGIN}",           f"{MARGIN}"),
    "bottom_left":   (f"{MARGIN}",                f"H-th-{MARGIN}"),
    "bottom_right":  (f"W-tw-{MARGIN}",           f"H-th-{MARGIN}"),
    "center":        (f"(W-tw)/2",                f"(H-th)/2"),
    "top_center":    (f"(W-tw)/2",                f"{MARGIN}"),
    "bottom_center": (f"(W-tw)/2",                f"H-th-{MARGIN}"),
}


# ─── Helpers internos ────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list, description: str = "", timeout: int = 300) -> None:
    """Executa FFmpeg com tratamento de erro padronizado (espelho do cutter.py)."""
    logger.debug(f"FFmpeg [{description}]: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=_utf8_env(),
    )
    if result.returncode != 0:
        logger.error(f"FFmpeg falhou ({description}):\n{result.stderr[-2000:]}")
        raise RuntimeError(
            f"FFmpeg retornou código {result.returncode}: {result.stderr[-500:]}"
        )


def _get_image_size(image_path: str) -> tuple:
    """
    Retorna (largura, altura) em pixels de uma imagem usando ffprobe.
    Usado para calcular coordenadas fixas do drawtext no modo combinado,
    pois drawtext não tem acesso às variáveis overlay_w / overlay_h.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(image_path),
        ],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=15, env=_utf8_env(),
    )
    try:
        import json as _json
        data = _json.loads(result.stdout)
        for s in data.get("streams", []):
            if s.get("width") and s.get("height"):
                return int(s["width"]), int(s["height"])
    except Exception:
        pass
    # Fallback conservador se ffprobe falhar
    return 200, 200


def _resolve_position(position: str, custom_x: Optional[str], custom_y: Optional[str], is_text: bool = False):
    """Retorna (x_expr, y_expr) para o overlay ou drawtext."""
    if position == "custom":
        if custom_x is None or custom_y is None:
            raise ValueError("position='custom' requer custom_x e custom_y.")
        return str(custom_x), str(custom_y)
    
    source = TEXT_POSITIONS if is_text else POSITIONS
    if position not in source:
        raise ValueError(
            f"Posição inválida: '{position}'. "
            f"Escolha entre: {list(source.keys())} ou 'custom'."
        )
    return source[position]


# ─── Funções principais ───────────────────────────────────────────────────────

def add_image_watermark(
    video_path: str,
    output_path: str,
    image_path: str,
    position: str = "bottom_right",
    opacity: float = 0.8,
    scale: float = 1.0,
    custom_x: Optional[str] = None,
    custom_y: Optional[str] = None,
) -> str:
    """
    Adiciona uma imagem (logo/marca d'água) sobre o vídeo via FFmpeg.

    Args:
        video_path:  Vídeo de entrada.
        output_path: Vídeo de saída com marca d'água.
        image_path:  Caminho para PNG/WebP com canal alpha (transparência).
        position:    Posição predefinida (ver POSITIONS) ou 'custom'.
        opacity:     Opacidade da marca d'água (0.0 = invisível, 1.0 = sólida).
        scale:       Fator de escala da imagem (1.0 = tamanho original).
        custom_x:    Expressão FFmpeg para X (apenas quando position='custom').
        custom_y:    Expressão FFmpeg para Y (apenas quando position='custom').

    Returns:
        Caminho do vídeo de saída.
    """
    video_path  = str(video_path)
    output_path = str(output_path)
    image_path  = str(image_path)

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Imagem de marca d'água não encontrada: {image_path}")

    x_expr, y_expr = _resolve_position(position, custom_x, custom_y)
    opacity = max(0.0, min(1.0, opacity))

    # Filtro:
    #   1. [wm] escala e aplica alpha (opacidade)
    #   2. overlay posiciona sobre o vídeo principal
    # Melhoria na escala: usa scale do ffmpeg garantindo que a proporção seja mantida
    # iw*scale:-1 faz com que a altura seja calculada proporcionalmente
    wm_chain      = f"[1:v]scale=iw*{scale}:-1,format=rgba,colorchannelmixer=aa={opacity:.3f}[wm]"
    overlay_chain = f"[0:v][wm]overlay={x_expr}:{y_expr}[out]"
    filter_complex = f"{wm_chain};{overlay_chain}"

    cmd = [
        "ffmpeg",
        "-i",  video_path,
        "-i",  image_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",          # copia áudio se existir
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]

    logger.info(
        f"Adicionando marca d'água (imagem) | posição={position} "
        f"opacidade={opacity:.0%} → {os.path.basename(output_path)}"
    )
    _run_ffmpeg(cmd, "image watermark", timeout=300)

    if not os.path.exists(output_path):
        raise RuntimeError(f"Arquivo de saída não gerado: {output_path}")

    logger.info(f"✓ Marca d'água (imagem) aplicada: {output_path}")
    return output_path


def add_text_watermark(
    video_path: str,
    output_path: str,
    text: str,
    position: str = "bottom_right",
    font_size: int = 40,
    font_color: str = "white",
    font_file: Optional[str] = None,
    opacity: float = 0.85,
    box_background: bool = True,
    box_color: str = "black@0.35",
    custom_x: Optional[str] = None,
    custom_y: Optional[str] = None,
) -> str:
    """
    Adiciona texto como marca d'água via FFmpeg drawtext.

    Args:
        video_path:      Vídeo de entrada.
        output_path:     Vídeo de saída.
        text:            Texto a exibir (ex: '@meucanal').
        position:        Posição predefinida ou 'custom'.
        font_size:       Tamanho da fonte em pixels.
        font_color:      Cor do texto (nome ou hex, ex: 'white', '#FFFFFFFF').
        font_file:       Caminho para arquivo .ttf/.otf (opcional; usa fonte padrão do FFmpeg).
        opacity:         Opacidade do texto (0.0–1.0).
        box_background:  Se True, adiciona fundo semi-transparente atrás do texto.
        box_color:       Cor e opacidade do fundo (sintaxe FFmpeg: 'black@0.35').
        custom_x:        Expressão FFmpeg para X (quando position='custom').
        custom_y:        Expressão FFmpeg para Y (quando position='custom').

    Returns:
        Caminho do vídeo de saída.
    """
    video_path  = str(video_path)
    output_path = str(output_path)

    x_expr, y_expr = _resolve_position(position, custom_x, custom_y, is_text=True)
    opacity = max(0.0, min(1.0, opacity))

    # Monta parâmetros do drawtext
    # Escapa aspas simples no texto para o filtro do FFmpeg
    safe_text = text.replace("'", "\\'").replace(":", "\\:")

    drawtext_params = [
        f"text='{safe_text}'",
        f"fontsize={font_size}",
        f"fontcolor={font_color}@{opacity:.3f}",
        f"x={x_expr}",
        f"y={y_expr}",
    ]

    if font_file and os.path.exists(str(font_file)):
        escaped_font = str(font_file).replace(":", "\\:").replace("'", "\\'")
        drawtext_params.insert(0, f"fontfile='{escaped_font}'")

    if box_background:
        drawtext_params += [
            "box=1",
            f"boxcolor={box_color}",
            "boxborderw=10",
        ]

    drawtext_filter = f"drawtext={':'.join(drawtext_params)}"

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", drawtext_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]

    logger.info(
        f"Adicionando marca d'água (texto) | texto='{text}' "
        f"posição={position} → {os.path.basename(output_path)}"
    )
    _run_ffmpeg(cmd, "text watermark", timeout=300)

    if not os.path.exists(output_path):
        raise RuntimeError(f"Arquivo de saída não gerado: {output_path}")

    logger.info(f"✓ Marca d'água (texto) aplicada: {output_path}")
    return output_path


def add_watermark(
    video_path: str,
    output_path: str,
    image_path: Optional[str] = None,
    text: Optional[str] = None,
    position: str = "bottom_right",
    opacity: float = 0.8,
    scale: float = 1.0,
    font_size: int = 40,
    font_color: str = "white",
    font_file: Optional[str] = None,
    box_background: bool = True,
    box_color: str = "black@0.35",
    custom_x: Optional[str] = None,
    custom_y: Optional[str] = None,
) -> str:
    """
    Aplica marca d'água ao vídeo — imagem, texto ou ambos em sequência.

    Se image_path E text forem fornecidos, a imagem é aplicada primeiro
    e o texto por cima, no mesmo passo de renderização para evitar
    dupla recodificação.

    Args:
        video_path:    Vídeo de entrada.
        output_path:   Vídeo de saída.
        image_path:    Caminho para PNG da logo (opcional).
        text:          Texto da marca d'água (opcional).
        position:      Posição (ex: 'bottom_right', 'top_left').
        opacity:       Opacidade geral (imagem e texto).
        scale:         Escala da imagem (1.0 = original).
        font_size:     Tamanho da fonte para o texto.
        font_color:    Cor do texto.
        font_file:     Caminho para .ttf/.otf (opcional).
        box_background: Fundo semi-transparente atrás do texto.
        box_color:     Cor/opacidade do fundo do texto.
        custom_x/y:    Posição customizada (expressões FFmpeg).

    Returns:
        Caminho do vídeo de saída.
    """
    if not image_path and not text:
        raise ValueError("Forneça ao menos image_path ou text para a marca d'água.")

    video_path  = str(video_path)
    output_path = str(output_path)

    # ── Caso 1: apenas texto ──────────────────────────────────────────────────
    if not image_path:
        return add_text_watermark(
            video_path=video_path,
            output_path=output_path,
            text=text,
            position=position,
            font_size=font_size,
            font_color=font_color,
            font_file=font_file,
            opacity=opacity,
            box_background=box_background,
            box_color=box_color,
            custom_x=custom_x,
            custom_y=custom_y,
        )

    # ── Caso 2: apenas imagem ─────────────────────────────────────────────────
    if not text:
        return add_image_watermark(
            video_path=video_path,
            output_path=output_path,
            image_path=image_path,
            position=position,
            opacity=opacity,
            scale=scale,
            custom_x=custom_x,
            custom_y=custom_y,
        )

    # ── Caso 3: imagem + texto (filtro combinado, 1 pass) ────────────────────
    image_path = str(image_path)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Imagem não encontrada: {image_path}")

    opacity = max(0.0, min(1.0, opacity))

    # Lê dimensões reais da imagem em pixels.
    img_w_px, img_h_px = _get_image_size(image_path)
    img_w_scaled = int(img_w_px * scale)
    img_h_scaled = int(img_h_px * scale)

    x_expr, y_expr = _resolve_position(position, custom_x, custom_y)
    text_x_expr, text_y_expr_raw = _resolve_position(position, custom_x, custom_y, is_text=True)

    # Substitui overlay_w e overlay_h pelos valores reais nas expressões de posição da imagem,
    # para calcular onde o texto deve ficar em relação à imagem.
    # O texto fica colado abaixo da imagem (8px de padding)
    text_y_expr = f"{text_y_expr_raw}+{img_h_scaled}+8"

    # Filtro de imagem
    wm_chain      = f"[1:v]scale={img_w_scaled}:-1,format=rgba,colorchannelmixer=aa={opacity:.3f}[wm]"
    overlay_chain = f"[0:v][wm]overlay={x_expr}:{y_expr}[vwm]"

    safe_text = text.replace("'", "\\'").replace(":", "\\:")
    drawtext_parts = [
        f"text='{safe_text}'",
        f"fontsize={font_size}",
        f"fontcolor={font_color}@{opacity:.3f}",
        f"x={text_x_expr}",
        f"y={text_y_expr}",
    ]
    if font_file and os.path.exists(str(font_file)):
        escaped_font = str(font_file).replace(":", "\\:").replace("'", "\\'")
        drawtext_parts.insert(0, f"fontfile='{escaped_font}'")
    if box_background:
        drawtext_parts += ["box=1", f"boxcolor={box_color}", "boxborderw=8"]

    drawtext_filter = f"drawtext={':'.join(drawtext_parts)}"
    text_chain      = f"[vwm]{drawtext_filter}[out]"

    filter_complex = f"{wm_chain};{overlay_chain};{text_chain}"

    cmd = [
        "ffmpeg",
        "-i",  video_path,
        "-i",  image_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]

    logger.info(
        f"Adicionando marca d'água (imagem + texto) | posição={position} "
        f"opacidade={opacity:.0%} → {os.path.basename(output_path)}"
    )
    _run_ffmpeg(cmd, "combined watermark", timeout=300)

    if not os.path.exists(output_path):
        raise RuntimeError(f"Arquivo de saída não gerado: {output_path}")

    logger.info(f"✓ Marca d'água combinada aplicada: {output_path}")
    return output_path


# ─── Integração com o pipeline (main.py) ─────────────────────────────────────

def apply_watermark_to_result(result: dict, watermark_config: dict) -> dict:
    """
    Aplica marca d'água ao arquivo final de um resultado de process_cut().

    Chamada em main.py após process_cut(), substituindo o arquivo final
    in-place para não quebrar o fluxo de relatório/upload.

    Args:
        result:           Dict retornado por process_cut().
        watermark_config: Dict com as opções da marca d'água:
            {
                "image_path":     "logo.png",        # opcional
                "text":           "@meucanal",        # opcional
                "position":       "bottom_right",     # padrão
                "opacity":        0.8,                # padrão
                "scale":          1.0,                # padrão (só imagem)
                "font_size":      40,                 # padrão (só texto)
                "font_color":     "white",            # padrão (só texto)
                "font_file":      None,               # caminho .ttf opcional
                "box_background": True,               # padrão (só texto)
                "box_color":      "black@0.35",       # padrão (só texto)
                "custom_x":       None,               # posição custom
                "custom_y":       None,
            }

    Returns:
        result dict atualizado com o arquivo final substituído.

    Exemplo de integração em main.py (Etapa 6/6, dentro do loop de cortes):

        result = process_cut(...)

        watermark_cfg = {
            "image_path": getattr(args, "watermark_image", None),
            "text":       getattr(args, "watermark_text", None),
            "position":   getattr(args, "watermark_position", "bottom_right"),
            "opacity":    getattr(args, "watermark_opacity", 0.8),
        }
        if watermark_cfg["image_path"] or watermark_cfg["text"]:
            result = apply_watermark_to_result(result, watermark_cfg)

        processing_results.append(result)
    """
    if not result.get("success"):
        logger.warning(
            f"Corte #{result.get('cut_index', '?')} falhou; "
            "pulando marca d'água."
        )
        return result

    final_path = result.get("files", {}).get("final")
    if not final_path or not os.path.exists(str(final_path)):
        logger.warning(
            f"Arquivo final não encontrado para corte "
            f"#{result.get('cut_index', '?')}; pulando marca d'água."
        )
        return result

    final_path = str(final_path)
    base, ext   = os.path.splitext(final_path)
    wm_path     = base + "_wm" + ext

    try:
        add_watermark(
            video_path=final_path,
            output_path=wm_path,
            image_path=watermark_config.get("image_path"),
            text=watermark_config.get("text"),
            position=watermark_config.get("position", "bottom_right"),
            opacity=watermark_config.get("opacity", 0.8),
            scale=watermark_config.get("scale", 1.0),
            font_size=watermark_config.get("font_size", 40),
            font_color=watermark_config.get("font_color", "white"),
            font_file=watermark_config.get("font_file"),
            box_background=watermark_config.get("box_background", True),
            box_color=watermark_config.get("box_color", "black@0.35"),
            custom_x=watermark_config.get("custom_x"),
            custom_y=watermark_config.get("custom_y"),
        )

        # Substitui o arquivo final pelo com marca d'água (in-place)
        try:
            os.remove(final_path)
        except Exception:
            pass
        os.rename(wm_path, final_path)

        logger.info(
            f"✓ Marca d'água aplicada ao corte "
            f"#{result.get('cut_index', '?')}: {final_path}"
        )

    except Exception as e:
        logger.error(
            f"✗ Erro ao aplicar marca d'água no corte "
            f"#{result.get('cut_index', '?')}: {e}"
        )
        result["watermark_error"] = str(e)

    return result


# ─── CLI standalone ───────────────────────────────────────────────────────────

def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="watermark.py - Adiciona marca d'água a vídeos do Viral Cutter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Apenas imagem
  python watermark.py -i corte.mp4 -o corte_wm.mp4 --image logo.png

  # Apenas texto
  python watermark.py -i corte.mp4 -o corte_wm.mp4 --text "@meucanal"

  # Imagem + texto, canto inferior direito
  python watermark.py -i corte.mp4 -o corte_wm.mp4 \\
      --image logo.png --text "@meucanal" --position bottom_right

  # Posição customizada (expressões FFmpeg)
  python watermark.py -i corte.mp4 -o corte_wm.mp4 \\
      --image logo.png --position custom --custom-x "50" --custom-y "50"

  # Processar pasta inteira
  python watermark.py --batch-dir ./output_clips --image logo.png --text "@canal"
        """,
    )

    parser.add_argument("--input",  "-i", help="Vídeo de entrada")
    parser.add_argument("--output", "-o", help="Vídeo de saída")

    parser.add_argument("--image",    help="Caminho para imagem PNG da marca d'água")
    parser.add_argument("--text",     help="Texto da marca d'água (ex: @meucanal)")

    parser.add_argument(
        "--position", "-p",
        default="bottom_right",
        choices=list(POSITIONS.keys()) + ["custom"],
        help="Posição da marca d'água (padrão: bottom_right)",
    )
    parser.add_argument("--opacity",    type=float, default=0.8,  help="Opacidade 0.0–1.0 (padrão: 0.8)")
    parser.add_argument("--scale",      type=float, default=1.0,  help="Escala da imagem (padrão: 1.0)")
    parser.add_argument("--text-size",  type=int,   default=40,   help="Tamanho da fonte (padrão: 40)")
    parser.add_argument("--text-color", default="white",          help="Cor do texto (padrão: white)")
    parser.add_argument("--font-file",  help="Caminho para .ttf/.otf personalizado")
    parser.add_argument("--no-box",     action="store_true",       help="Remove o fundo do texto")
    parser.add_argument("--custom-x",   help="Posição X custom (expressão FFmpeg)")
    parser.add_argument("--custom-y",   help="Posição Y custom (expressão FFmpeg)")

    parser.add_argument(
        "--batch-dir",
        help="Processa todos os .mp4 de uma pasta (ignora --input/--output)",
    )

    return parser


def main():
    from utils import setup_logging
    setup_logging("INFO")

    parser = _build_cli_parser()
    args = parser.parse_args()

    common = dict(
        image_path=args.image,
        text=args.text,
        position=args.position,
        opacity=args.opacity,
        scale=args.scale,
        font_size=args.text_size,
        font_color=args.text_color,
        font_file=args.font_file,
        box_background=not args.no_box,
        custom_x=args.custom_x,
        custom_y=args.custom_y,
    )

    # ── Modo batch ────────────────────────────────────────────────────────────
    if args.batch_dir:
        batch_dir = Path(str(args.batch_dir))
        if not batch_dir.is_dir():
            logger.error(f"Diretório não encontrado: {batch_dir}")
            return 1

        videos = [
            p for p in batch_dir.glob("*.mp4")
            if not p.stem.endswith("_wm")  # evita reprocessar saídas
        ]
        if not videos:
            logger.warning(f"Nenhum .mp4 encontrado em: {batch_dir}")
            return 1

        logger.info(f"Processando {len(videos)} vídeo(s) em: {batch_dir}")
        ok = 0
        for video in sorted(videos):
            out = video.parent / (video.stem + "_wm.mp4")
            try:
                add_watermark(video_path=str(video), output_path=str(out), **common)
                ok += 1
            except Exception as e:
                logger.error(f"Erro em {video.name}: {e}")

        logger.info(f"Concluído: {ok}/{len(videos)} vídeo(s) com marca d'água.")
        return 0 if ok > 0 else 1

    # ── Modo single ───────────────────────────────────────────────────────────
    if not args.input or not args.output:
        parser.error("--input e --output são obrigatórios (ou use --batch-dir).")

    try:
        add_watermark(
            video_path=args.input,
            output_path=args.output,
            **common,
        )
        return 0
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())