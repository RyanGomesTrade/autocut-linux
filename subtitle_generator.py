# -*- coding: utf-8 -*-
"""
subtitle_generator.py - Geração de legendas SRT/ASS a partir de transcrição
"""

import re
import logging
from pathlib import Path
from typing import Optional
import math

from utils import seconds_to_srt_time

logger = logging.getLogger("viral_cutter.subtitle_generator")

MAX_CHARS_PER_LINE     = 42
MAX_WORDS_PER_SUBTITLE = 8
MIN_SUBTITLE_DURATION  = 0.8
MAX_SUBTITLE_DURATION  = 5.0

EMOJI_MAP = {
    "dinheiro": "💰", "money": "💰", "cash": "💸", "rico": "🤑", "investir": "📈",
    "atenção": "🚨", "cuidado": "⚠️", "perigo": "🔥", "fogo": "🔥",
    "amor": "❤️", "feliz": "😊", "triste": "😢", "erro": "❌", "certo": "✅",
    "tempo": "⏱️", "agora": "⏳", "segredo": "🤫", "falar": "🗣️",
    "brasil": "🇧🇷", "mundo": "🌎", "tecnologia": "💻", "ia": "🤖",
    "podcast": "🎙️", "sucesso": "🏆", "foco": "🎯", "ideia": "💡",
    "meta": "🎯", "ganhar": "📈", "perder": "📉", "estudar": "📚",
    "jesus": "🙏", "deus": "🙏", "gratidão": "🙏", "fé": "🙏",
    "comida": "🍔", "treino": "💪", "academia": "💪", "saúde": "🍎"
}

HIGHLIGHT_COLORS = {
    "yellow": "&H00FFFF&",
    "green":  "&H00FF00&",
    "cyan":   "&HFFFF00&",
    "red":    "&H0000FF&",
}


def get_emoji_for_word(word: str) -> str:
    clean = re.sub(r'[^\w]', '', word.lower())
    return EMOJI_MAP.get(clean, "")


def clean_text(text: str) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()


def split_text_into_lines(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    words = text.split()
    if len(text) <= max_chars or len(words) <= 2:
        return text
    mid = len(words) // 2
    line1 = " ".join(words[:mid])
    line2 = " ".join(words[mid:])
    while len(line1) > max_chars and mid > 1:
        mid -= 1
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
    return f"{line1}\n{line2}"


# ─── SRT generators ───────────────────────────────────────────────────────────

def generate_srt_from_words(
    words: list,
    cut_start: float,
    cut_end: float,
    max_words_per_block: int = MAX_WORDS_PER_SUBTITLE,
) -> str:
    relevant_words = [
        w for w in words
        if w.get("start", 0) >= cut_start - 0.1
        and w.get("end", 0) <= cut_end + 0.5
    ]
    if not relevant_words:
        return ""

    srt_entries = []
    entry_index = 1
    i = 0

    while i < len(relevant_words):
        block_words = []
        block_start = relevant_words[i].get("start", cut_start)

        while i < len(relevant_words) and len(block_words) < max_words_per_block:
            word = relevant_words[i].get("word", "")
            if isinstance(word, bytes):
                word = word.decode("utf-8", errors="replace")
            block_words.append(word.strip())
            block_end = relevant_words[i].get("end", block_start + 1)
            i += 1

        if not block_words:
            break

        rel_start = max(0.0, block_start - cut_start)
        rel_end   = min(cut_end - cut_start, block_end - cut_start)
        rel_end   = max(rel_start + MIN_SUBTITLE_DURATION, rel_end)
        rel_end   = min(rel_start + MAX_SUBTITLE_DURATION, rel_end)

        text = clean_text(" ".join(block_words))
        if not text:
            continue

        srt_entries.append(
            f"{entry_index}\n"
            f"{seconds_to_srt_time(rel_start)} --> {seconds_to_srt_time(rel_end)}\n"
            f"{split_text_into_lines(text)}\n"
        )
        entry_index += 1

    return "\n".join(srt_entries)


def generate_srt_from_segments(
    segments: list,
    cut_start: float,
    cut_end: float,
    max_chars_per_subtitle: int = MAX_CHARS_PER_LINE * 2,
) -> str:
    relevant_segs = [s for s in segments if s.start < cut_end and s.end > cut_start]
    if not relevant_segs:
        return ""

    srt_entries = []
    entry_index = 1

    for seg in relevant_segs:
        text = clean_text(seg.text)
        if not text:
            continue

        rel_start = max(0.0, seg.start - cut_start)
        rel_end   = min(cut_end - cut_start, seg.end - cut_start)
        if rel_end <= rel_start:
            rel_end = rel_start + 1.5

        words = text.split()
        if len(words) > MAX_WORDS_PER_SUBTITLE * 2:
            duration        = rel_end - rel_start
            words_per_block = MAX_WORDS_PER_SUBTITLE
            num_blocks      = max(1, (len(words) + words_per_block - 1) // words_per_block)
            time_per_block  = duration / num_blocks

            for j in range(num_blocks):
                block_words = words[j * words_per_block:(j + 1) * words_per_block]
                if not block_words:
                    continue
                b_start = rel_start + j * time_per_block
                b_end   = rel_start + (j + 1) * time_per_block
                srt_entries.append(
                    f"{entry_index}\n"
                    f"{seconds_to_srt_time(b_start)} --> {seconds_to_srt_time(b_end)}\n"
                    f"{split_text_into_lines(' '.join(block_words))}\n"
                )
                entry_index += 1
        else:
            srt_entries.append(
                f"{entry_index}\n"
                f"{seconds_to_srt_time(rel_start)} --> {seconds_to_srt_time(rel_end)}\n"
                f"{split_text_into_lines(text)}\n"
            )
            entry_index += 1

    return "\n".join(srt_entries)


def generate_srt_for_cut(
    cut_start: float,
    cut_end: float,
    all_segments: list,
    output_path: str,
    use_word_timestamps: bool = True,
) -> str:
    output_path = str(output_path)
    srt_content = ""

    if use_word_timestamps:
        all_words = []
        for seg in all_segments:
            if seg.start < cut_end and seg.end > cut_start:
                for w in getattr(seg, 'words', []):
                    all_words.append(w)
        if all_words:
            srt_content = generate_srt_from_words(all_words, cut_start, cut_end)

    if not srt_content:
        srt_content = generate_srt_from_segments(all_segments, cut_start, cut_end)

    if not srt_content:
        logger.warning(f"Nenhuma legenda gerada para {cut_start:.1f}s-{cut_end:.1f}s")
        srt_content = "1\n00:00:00,000 --> 00:00:03,000\n[sem transcricao]\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"SRT salvo: {output_path}")
    return output_path


def seconds_to_ass_time(seconds: float) -> str:
    hours   = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs    = int(seconds % 60)
    centis  = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


# ─── ASS VERTICAL (TikTok / Shorts / Reels) ──────────────────────────────────

def _generate_ass_vertical(
    words: list,
    cut_start: float,
    cut_end: float,
    highlight_color: str = "&H00FFFF&",
    font_size: int = 26,
) -> str:
    """
    Estilo word-by-word para vídeos verticais 1080×1920.
    3 palavras por bloco, destaque animado na palavra em foco.
    """
    relevant = [
        w for w in words
        if w.get("start", 0) >= cut_start - 0.2
        and w.get("end", 0) <= cut_end + 0.5
    ]
    if not relevant:
        return ""

    header = f"""\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,30,30,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    i = 0
    while i < len(relevant):
        chunk = relevant[i:i + 3]
        if not chunk:
            break

        # Tempo do bloco inteiro
        block_start = max(0.0, chunk[0]["start"] - cut_start)
        block_end   = min(cut_end - cut_start, chunk[-1]["end"] - cut_start)
        block_end   = max(block_start + MIN_SUBTITLE_DURATION, block_end)

        for idx, fw in enumerate(chunk):
            # Cada frame de highlight dura até o início da próxima palavra
            ws = max(block_start, max(0.0, fw["start"] - cut_start))
            if idx + 1 < len(chunk):
                we = max(0.0, chunk[idx + 1]["start"] - cut_start)
            else:
                we = block_end
            we = min(cut_end - cut_start, we)
            if we - ws < 0.12:
                we = ws + 0.12

            parts = []
            for j, w in enumerate(chunk):
                raw = w.get("word", "").strip().upper()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                emoji = get_emoji_for_word(raw)
                txt   = f"{raw} {emoji}".strip() if emoji else raw

                if j == idx:
                    parts.append(
                        f"{{\\c{highlight_color}\\b1\\fscx115\\fscy115"
                        f"\\t(0,80,\\fscx125\\fscy125)}}{txt}{{\\r}}"
                    )
                else:
                    parts.append(txt)

            lines.append(
                f"Dialogue: 0,{seconds_to_ass_time(ws)},{seconds_to_ass_time(we)},"
                f"Default,,0,0,0,,{' '.join(parts)}"
            )
        i += 3

    return header + "\n".join(lines)


# ─── ASS LANDSCAPE (1920×1080) ────────────────────────────────────────────────

def _generate_ass_landscape(
    words: list,
    cut_start: float,
    cut_end: float,
    highlight_color: str = "&H00FFFF&",  # amarelo vibrante (BGR no ASS)
    font_size: int = 56,
    words_per_block: int = 6,
) -> str:
    """
    Legendas profissionais para landscape 1920×1080.

    Design:
    - Arial Black 56pt — legível em widescreen sem ocupar demais
    - 6 palavras por bloco — ritmo confortável para 16:9
    - Palavra em foco: amarelo + bold + scale 105→112 em 80ms
    - Resto do bloco: branco puro (bold herdado do style)
    - Outline preto 3px + shadow duplo para profundidade
    - MarginV=70 — posição segura acima da barra de controles
    - Fade-in 120ms no primeiro frame de cada bloco
    - PlayResX/Y corretos para 1920×1080
    """
    relevant = [
        w for w in words
        if w.get("start", 0) >= cut_start - 0.2
        and w.get("end", 0) <= cut_end + 0.5
    ]
    if not relevant:
        return ""

    header = f"""\
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1.2,0,1,3,2,2,80,80,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    i = 0

    while i < len(relevant):
        chunk = relevant[i:i + words_per_block]
        if not chunk:
            break

        # ── Tempo do BLOCO INTEIRO ────────────────────────────────────────
        # O bloco fica na tela do início da 1ª palavra até o fim da última.
        # Cada Dialogue cobre esse intervalo completo — só o highlight muda.
        block_start = max(0.0, chunk[0]["start"] - cut_start)
        block_end   = min(cut_end - cut_start, chunk[-1]["end"] - cut_start)
        block_end   = max(block_start + MIN_SUBTITLE_DURATION, block_end)

        # ── Um Dialogue por palavra em foco dentro do bloco ───────────────
        # Start/End de cada Dialogue = tempo em que AQUELA palavra é falada,
        # mas o texto exibido é sempre o bloco inteiro (só a cor muda).
        for idx, fw in enumerate(chunk):
            # Tempo de exibição deste frame de highlight
            ws = max(block_start, max(0.0, fw["start"] - cut_start))
            # Fim: até o início da próxima palavra (ou fim do bloco)
            if idx + 1 < len(chunk):
                we = max(0.0, chunk[idx + 1]["start"] - cut_start)
            else:
                we = block_end
            we = min(cut_end - cut_start, we)
            # Garante duração mínima visível
            if we - ws < 0.12:
                we = ws + 0.12

            parts = []
            for j, w in enumerate(chunk):
                raw = w.get("word", "").strip().upper()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                emoji = get_emoji_for_word(raw)
                txt   = f"{raw} {emoji}".strip() if emoji else raw

                if j == idx:
                    # Palavra em foco: amarelo + scale animado sutil
                    parts.append(
                        f"{{\\c{highlight_color}\\b1"
                        f"\\fscx108\\fscy108"
                        f"\\t(0,80,\\fscx115\\fscy115)}}{txt}{{\\r}}"
                    )
                else:
                    # Palavras normais: branco, bold herdado do style
                    parts.append(txt)

            # Fade-in 120ms apenas no primeiro frame de cada bloco
            fade = "{\\fad(120,0)}" if idx == 0 else ""

            lines.append(
                f"Dialogue: 0,{seconds_to_ass_time(ws)},{seconds_to_ass_time(we)},"
                f"Default,,0,0,0,,{fade}{' '.join(parts)}"
            )

        i += words_per_block

    return header + "\n".join(lines)


# ─── Dispatcher principal ─────────────────────────────────────────────────────

def generate_ass_from_words(
    words: list,
    cut_start: float,
    cut_end: float,
    highlight_color: str = "&H00FFFF&",
    font_size: Optional[int] = None,
    preset: str = "shorts",
) -> str:
    """
    Escolhe o gerador ASS correto com base no preset.
    - landscape            → _generate_ass_landscape (1920×1080, 56pt, 6 palavras)
    - tiktok/reels/shorts  → _generate_ass_vertical  (1080×1920, 26pt, 3 palavras)
    """
    if preset == "landscape":
        fs = font_size or 56
        return _generate_ass_landscape(words, cut_start, cut_end, highlight_color, fs)
    else:
        fs = font_size or 26
        return _generate_ass_vertical(words, cut_start, cut_end, highlight_color, fs)


def generate_high_impact_subtitles(
    cut_start: float,
    cut_end: float,
    all_segments: list,
    output_path: str,
    preset: str = "shorts",
) -> str:
    """
    Gera legendas ASS de alto impacto.
    Recebe o preset para escolher o layout correto (landscape vs vertical).
    """
    output_path = str(output_path)

    all_words = []
    for seg in all_segments:
        if seg.start < cut_end and seg.end > cut_start:
            for w in getattr(seg, 'words', []):
                all_words.append(w)

    if not all_words:
        srt_fallback = output_path.replace(".ass", ".srt")
        return generate_srt_for_cut(cut_start, cut_end, all_segments, srt_fallback)

    ass_content = generate_ass_from_words(all_words, cut_start, cut_end, preset=preset)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    logger.info(f"Legendas [{preset}] salvas: {output_path}")
    return output_path


# ─── Utilidades extras ────────────────────────────────────────────────────────

def generate_ass_style_srt(
    srt_content: str,
    highlight_color: str = "&H0000FFFF",
) -> str:
    if isinstance(srt_content, bytes):
        srt_content = srt_content.decode("utf-8", errors="replace")

    lines        = srt_content.split("\n")
    styled_lines = []
    is_text_line = False
    entry_line_count = 0

    for line in lines:
        if re.match(r'^\d+$', line.strip()):
            styled_lines.append(line)
            entry_line_count = 0
            is_text_line     = False
        elif '-->' in line:
            styled_lines.append(line)
            is_text_line     = True
            entry_line_count = 0
        elif is_text_line and line.strip():
            entry_line_count += 1
            styled_lines.append(f"<b>{line}</b>" if entry_line_count == 1 else line)
        else:
            styled_lines.append(line)
            if not line.strip():
                is_text_line = False

    return "\n".join(styled_lines)


def validate_srt(srt_path: str) -> tuple:
    srt_path = str(srt_path)
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return False, "Arquivo SRT vazio"
        if "-->" not in content:
            return False, "Nenhum timestamp encontrado no SRT"
        return True, ""
    except Exception as e:
        return False, str(e)