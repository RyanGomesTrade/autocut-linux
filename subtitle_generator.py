# -*- coding: utf-8 -*-
"""
subtitle_generator.py - Geração de legendas SRT/ASS a partir de transcrição

PATCH UTF-8:
  - Todos os open() para escrita de .srt e .ass agora têm encoding="utf-8" explícito.
    O código original não especificava encoding, causando escrita em codec do locale
    (pode ser ASCII em sistemas sem UTF-8 configurado).
  - clean_text: guard defensivo para garantir que input seja str.
  - generate_srt_for_cut / generate_high_impact_subtitles: str() em output_path.
  - validate_srt: encoding="utf-8" explícito no open().
"""

import re
import logging
from pathlib import Path
from typing import Optional
import math

from utils import seconds_to_srt_time

logger = logging.getLogger("viral_cutter.subtitle_generator")

MAX_CHARS_PER_LINE = 42
MAX_WORDS_PER_SUBTITLE = 8
MIN_SUBTITLE_DURATION = 0.8
MAX_SUBTITLE_DURATION = 5.0

# ─── Configurações Dinâmicas (Estilo Viral) ──────────────────────────────────

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
    "green": "&H00FF00&",
    "cyan": "&HFFFF00&",
    "red": "&H0000FF&",
}

def get_emoji_for_word(word: str) -> str:
    """Retorna um emoji se a palavra (limpa) estiver no mapa."""
    clean = re.sub(r'[^\w]', '', word.lower())
    return EMOJI_MAP.get(clean, "")


def clean_text(text: str) -> str:
    """
    Remove espaços extras, artefatos de transcrição e normaliza o texto.

    CORREÇÃO UTF-8:
      - Guard defensivo: se text chegar como bytes (improvável mas possível
        em integrações incorretas), decodifica para UTF-8.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = text.strip()
    return text


def split_text_into_lines(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    """Quebra texto em duas linhas se necessário para caber na tela."""
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


def generate_srt_from_words(
    words: list,
    cut_start: float,
    cut_end: float,
    max_words_per_block: int = MAX_WORDS_PER_SUBTITLE,
) -> str:
    """
    Gera conteúdo SRT a partir de timestamps por palavra.
    """
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
            # Guard defensivo
            if isinstance(word, bytes):
                word = word.decode("utf-8", errors="replace")
            block_words.append(word.strip())
            block_end = relevant_words[i].get("end", block_start + 1)
            i += 1

        if not block_words:
            break

        rel_start = max(0.0, block_start - cut_start)
        rel_end = min(cut_end - cut_start, block_end - cut_start)
        rel_end = max(rel_start + MIN_SUBTITLE_DURATION, rel_end)
        rel_end = min(rel_start + MAX_SUBTITLE_DURATION, rel_end)

        text = clean_text(" ".join(block_words))
        if not text:
            continue

        formatted_text = split_text_into_lines(text)

        srt_entries.append(
            f"{entry_index}\n"
            f"{seconds_to_srt_time(rel_start)} --> {seconds_to_srt_time(rel_end)}\n"
            f"{formatted_text}\n"
        )
        entry_index += 1

    return "\n".join(srt_entries)


def generate_srt_from_segments(
    segments: list,
    cut_start: float,
    cut_end: float,
    max_chars_per_subtitle: int = MAX_CHARS_PER_LINE * 2,
) -> str:
    """Gera SRT a partir de segmentos de transcrição (fallback)."""
    relevant_segs = [
        s for s in segments
        if s.start < cut_end and s.end > cut_start
    ]

    if not relevant_segs:
        return ""

    srt_entries = []
    entry_index = 1

    for seg in relevant_segs:
        text = clean_text(seg.text)
        if not text:
            continue

        rel_start = max(0.0, seg.start - cut_start)
        rel_end = min(cut_end - cut_start, seg.end - cut_start)

        if rel_end <= rel_start:
            rel_end = rel_start + 1.5

        words = text.split()
        if len(words) > MAX_WORDS_PER_SUBTITLE * 2:
            duration = rel_end - rel_start
            words_per_block = MAX_WORDS_PER_SUBTITLE
            num_blocks = max(1, (len(words) + words_per_block - 1) // words_per_block)
            time_per_block = duration / num_blocks

            for j in range(num_blocks):
                block_words = words[j * words_per_block:(j + 1) * words_per_block]
                if not block_words:
                    continue
                b_start = rel_start + j * time_per_block
                b_end = rel_start + (j + 1) * time_per_block
                block_text = split_text_into_lines(" ".join(block_words))
                srt_entries.append(
                    f"{entry_index}\n"
                    f"{seconds_to_srt_time(b_start)} --> {seconds_to_srt_time(b_end)}\n"
                    f"{block_text}\n"
                )
                entry_index += 1
        else:
            formatted_text = split_text_into_lines(text)
            srt_entries.append(
                f"{entry_index}\n"
                f"{seconds_to_srt_time(rel_start)} --> {seconds_to_srt_time(rel_end)}\n"
                f"{formatted_text}\n"
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
    """
    Gera e salva o arquivo SRT para um corte específico.

    CORREÇÃO UTF-8:
      - open(output_path, "w", encoding="utf-8") — sem encoding explícito,
        Python usaria o codec do locale, que pode ser ASCII/latin-1,
        causando UnicodeEncodeError ao escrever texto com acentos.
    """
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
        logger.warning(
            f"Nenhuma legenda gerada para {cut_start:.1f}s-{cut_end:.1f}s"
        )
        srt_content = "1\n00:00:00,000 --> 00:00:03,000\n[sem transcricao]\n"

    # FIX: encoding="utf-8" obrigatório
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"SRT salvo: {output_path}")
    return output_path


def seconds_to_ass_time(seconds: float) -> str:
    """Converte segundos para formato ASS: H:MM:SS.cc"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def generate_ass_from_words(
    words: list,
    cut_start: float,
    cut_end: float,
    highlight_color: str = "&H00FFFF&", # Amarelo vibrante por padrão
    font_size: int = 26, # Aumentado para mais impacto
) -> str:
    """Gera conteúdo ASS com destaque dinâmico (estilo viral/Hormozi)."""
    relevant_words = [
        w for w in words
        if w.get("start", 0) >= cut_start - 0.2
        and w.get("end", 0) <= cut_end + 0.5
    ]

    if not relevant_words:
        return ""

    # Header com estilo mais agressivo (Shadow e Outline fortes)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,5,2,20,20,450,1
"""
    # MarginV=450 posiciona as legendas um pouco acima da barra inferior de apps como TikTok/Reels

    events = []
    i = 0
    # Agrupamos menos palavras por evento para manter o dinamismo alto
    words_per_event = 3

    while i < len(relevant_words):
        chunk = relevant_words[i:i + words_per_event]
        if not chunk:
            break

        # Início e fim do bloco total das 3 palavras
        event_start = max(0.0, chunk[0]["start"] - cut_start)
        event_end = min(cut_end - cut_start, chunk[-1]["end"] - cut_start)

        for idx, focus_word in enumerate(chunk):
            w_start = max(0.0, focus_word["start"] - cut_start)
            w_end = min(cut_end - cut_start, focus_word["end"] - cut_start)

            # Garante duração mínima para o frame não piscar
            if w_end - w_start < 0.08:
                w_end = w_start + 0.08

            line_parts = []
            for j, w in enumerate(chunk):
                word_text = w.get("word", "").strip().upper()
                if isinstance(word_text, bytes):
                    word_text = word_text.decode("utf-8", errors="replace")
                
                emoji = get_emoji_for_word(word_text)
                display_text = f"{word_text} {emoji}".strip() if emoji else word_text

                if j == idx:
                    # Aplica cor de destaque, negrito e efeito de escala (Pop-up)
                    line_parts.append(
                        f"{{\\c{highlight_color}\\fscx115\\fscy115"
                        f"\\t(0,80,\\fscx125\\fscy125)}}"
                        f"\\b1 {display_text} \\b0"
                        f"{{\\r}}"
                    )
                else:
                    # Outras palavras ficam brancas e normais
                    line_parts.append(word_text)

            full_line = " ".join(line_parts)
            events.append(
                f"Dialogue: 0,"
                f"{seconds_to_ass_time(w_start)},"
                f"{seconds_to_ass_time(w_end)},"
                f"Default,,0,0,0,,{full_line}"
            )

        i += words_per_event

    return header + "\n".join(events)


def generate_high_impact_subtitles(
    cut_start: float,
    cut_end: float,
    all_segments: list,
    output_path: str,
) -> str:
    """
    Gera legendas ASS de alto impacto.

    CORREÇÃO UTF-8:
      - open(output_path, "w", encoding="utf-8") obrigatório para .ass com
        acentos no texto.
    """
    output_path = str(output_path)

    all_words = []
    for seg in all_segments:
        if seg.start < cut_end and seg.end > cut_start:
            for w in getattr(seg, 'words', []):
                all_words.append(w)

    if not all_words:
        srt_fallback = output_path.replace(".ass", ".srt")
        return generate_srt_for_cut(
            cut_start, cut_end, all_segments, srt_fallback
        )

    ass_content = generate_ass_from_words(all_words, cut_start, cut_end)

    # FIX: encoding="utf-8" obrigatório
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    logger.info(f"Legendas de alto impacto salvas: {output_path}")
    return output_path


def generate_ass_style_srt(
    srt_content: str,
    highlight_color: str = "&H0000FFFF",
) -> str:
    """Converte SRT básico para SRT com marcações de estilo simples."""
    if isinstance(srt_content, bytes):
        srt_content = srt_content.decode("utf-8", errors="replace")

    lines = srt_content.split("\n")
    styled_lines = []
    is_text_line = False
    entry_line_count = 0

    for line in lines:
        if re.match(r'^\d+$', line.strip()):
            styled_lines.append(line)
            entry_line_count = 0
            is_text_line = False
        elif '-->' in line:
            styled_lines.append(line)
            is_text_line = True
            entry_line_count = 0
        elif is_text_line and line.strip():
            entry_line_count += 1
            if entry_line_count == 1:
                styled_lines.append(f"<b>{line}</b>")
            else:
                styled_lines.append(line)
        else:
            styled_lines.append(line)
            if not line.strip():
                is_text_line = False

    return "\n".join(styled_lines)


def validate_srt(srt_path: str) -> tuple:
    """
    Valida a estrutura básica de um arquivo SRT.

    CORREÇÃO UTF-8:
      - encoding="utf-8" obrigatório no open() para leitura do arquivo SRT.
        Sem isso, Python usaria o codec do locale para ler o arquivo, causando
        UnicodeDecodeError se o arquivo contiver acentos.
    """
    srt_path = str(srt_path)
    try:
        # FIX: encoding="utf-8" explícito
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return False, "Arquivo SRT vazio"

        if "-->" not in content:
            return False, "Nenhum timestamp encontrado no SRT"

        return True, ""
    except Exception as e:
        return False, str(e)