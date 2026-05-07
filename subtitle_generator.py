"""
subtitle_generator.py - Geração de legendas SRT sincronizadas com os cortes
"""

import re
import logging
from pathlib import Path
from typing import Optional

from utils import seconds_to_srt_time
import math

logger = logging.getLogger("viral_cutter.subtitle_generator")

# Número máximo de caracteres por linha de legenda
MAX_CHARS_PER_LINE = 42
# Número máximo de palavras por bloco de legenda
MAX_WORDS_PER_SUBTITLE = 8
# Duração mínima de um bloco de legenda (segundos)
MIN_SUBTITLE_DURATION = 0.8
# Duração máxima de um bloco de legenda (segundos)
MAX_SUBTITLE_DURATION = 5.0


def clean_text(text: str) -> str:
    """Remove espaços extras, artefatos de transcrição e normaliza o texto."""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)   # Remove marcadores como [música]
    text = text.strip()
    return text


def split_text_into_lines(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    """
    Quebra texto em duas linhas se necessário para caber na tela.
    """
    words = text.split()
    if len(text) <= max_chars or len(words) <= 2:
        return text

    # Tenta quebrar na metade das palavras
    mid = len(words) // 2
    line1 = " ".join(words[:mid])
    line2 = " ".join(words[mid:])

    # Ajusta ponto de quebra para equilibrar comprimento
    while len(line1) > max_chars and mid > 1:
        mid -= 1
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

    return f"{line1}\n{line2}"


def generate_srt_from_words(
    words: list[dict],
    cut_start: float,
    cut_end: float,
    max_words_per_block: int = MAX_WORDS_PER_SUBTITLE,
) -> str:
    """
    Gera conteúdo SRT a partir de timestamps por palavra (nível de palavra).
    Produz legendas sincronizadas com precisão máxima.

    Args:
        words: Lista de dicts com 'word', 'start', 'end'
        cut_start: Início do corte em segundos (para relativizar timestamps)
        cut_end: Fim do corte em segundos
        max_words_per_block: Palavras máximas por bloco de legenda

    Returns:
        String no formato SRT
    """
    # Filtra palavras no intervalo do corte
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

        # Agrupa palavras em blocos de max_words_per_block
        while i < len(relevant_words) and len(block_words) < max_words_per_block:
            block_words.append(relevant_words[i].get("word", "").strip())
            block_end = relevant_words[i].get("end", block_start + 1)
            i += 1

        if not block_words:
            break

        # Normaliza timestamps relativos ao início do corte
        rel_start = max(0.0, block_start - cut_start)
        rel_end = min(cut_end - cut_start, block_end - cut_start)
        rel_end = max(rel_start + MIN_SUBTITLE_DURATION, rel_end)
        rel_end = min(rel_start + MAX_SUBTITLE_DURATION, rel_end)

        text = clean_text(" ".join(block_words))
        if not text:
            continue

        # Formata texto em linhas
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
    """
    Gera SRT a partir de segmentos de transcrição (fallback quando não há palavras).

    Args:
        segments: Lista de TranscriptSegment
        cut_start: Início do corte
        cut_end: Fim do corte
        max_chars_per_subtitle: Limite de caracteres por legenda

    Returns:
        String no formato SRT
    """
    # Filtra segmentos no intervalo
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

        # Relativiza o tempo
        rel_start = max(0.0, seg.start - cut_start)
        rel_end = min(cut_end - cut_start, seg.end - cut_start)

        if rel_end <= rel_start:
            rel_end = rel_start + 1.5

        # Se o segmento é muito longo, divide em sub-blocos
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

    Args:
        cut_start: Início do corte em segundos
        cut_end: Fim do corte em segundos
        all_segments: Todos os segmentos da transcrição
        output_path: Caminho para salvar o arquivo .srt
        use_word_timestamps: Se True, tenta usar timestamps por palavra

    Returns:
        Caminho do arquivo SRT salvo
    """
    srt_content = ""

    if use_word_timestamps:
        # Coleta todas as palavras dos segmentos no intervalo
        all_words = []
        for seg in all_segments:
            if seg.start < cut_end and seg.end > cut_start:
                for w in getattr(seg, 'words', []):
                    all_words.append(w)

        if all_words:
            srt_content = generate_srt_from_words(all_words, cut_start, cut_end)

    # Fallback: usa segmentos se não há palavras
    if not srt_content:
        srt_content = generate_srt_from_segments(all_segments, cut_start, cut_end)

    if not srt_content:
        logger.warning(f"Nenhuma legenda gerada para o intervalo {cut_start:.1f}s-{cut_end:.1f}s")
        srt_content = f"1\n00:00:00,000 --> 00:00:03,000\n[sem transcrição]\n"

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
    words: list[dict],
    cut_start: float,
    cut_end: float,
    highlight_color: str = "&H00FFFF&", # Amarelo (formato BGR em ASS: BBGGRR)
    font_size: int = 24,
) -> str:
    """
    Gera conteúdo ASS com destaque dinâmico na palavra falada.
    Estilo "Viral Shorts" clássico.
    """
    relevant_words = [
        w for w in words
        if w.get("start", 0) >= cut_start - 0.2
        and w.get("end", 0) <= cut_end + 0.5
    ]

    if not relevant_words:
        return ""

    # Header do ASS - Estilo Premium Viral
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,4,2,20,20,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    i = 0
    words_per_event = 3 # Poucas palavras para impacto (máx 3 para visibilidade em tela de celular)

    while i < len(relevant_words):
        chunk = relevant_words[i:i+words_per_event]
        if not chunk: break
        
        event_start = max(0.0, chunk[0]["start"] - cut_start)
        event_end = min(cut_end - cut_start, chunk[-1]["end"] - cut_start)
        
        # Para cada palavra no chunk, criamos um micro-evento para aplicar o destaque
        for idx, focus_word in enumerate(chunk):
            w_start = max(0.0, focus_word["start"] - cut_start)
            w_end = min(cut_end - cut_start, focus_word["end"] - cut_start)
            
            # Garante duração mínima para legibilidade da animação
            if w_end - w_start < 0.1: w_end = w_start + 0.1
            
            # Constrói o texto com a palavra atual destacada
            line_parts = []
            for j, w in enumerate(chunk):
                word_text = w["word"].strip().upper()
                if j == idx:
                    # Animação suave: Escala a 130% rapidamente e cor em destaque
                    # \t(t1,t2, \tags) cria uma animação fluida.
                    # Pulo inicial usando fscx/fscy
                    line_parts.append(f"{{\\c{highlight_color}\\fscx120\\fscy120\\t(0,100,\\fscx125\\fscy125)}}{word_text}{{\\r}}")
                else:
                    line_parts.append(word_text)
            
            full_line = " ".join(line_parts)
            events.append(f"Dialogue: 0,{seconds_to_ass_time(w_start)},{seconds_to_ass_time(w_end)},Default,,0,0,0,,{full_line}")
        
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
    """
    all_words = []
    for seg in all_segments:
        if seg.start < cut_end and seg.end > cut_start:
            for w in getattr(seg, 'words', []):
                all_words.append(w)
                
    if not all_words:
        # Fallback para SRT se não houver palavras
        return generate_srt_for_cut(cut_start, cut_end, all_segments, output_path.replace(".ass", ".srt"))

    ass_content = generate_ass_from_words(all_words, cut_start, cut_end)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
        
    logger.info(f"Legendas de alto impacto salvas: {output_path}")
    return output_path


def generate_ass_style_srt(
    srt_content: str,
    highlight_color: str = "&H0000FFFF",  # Amarelo em ASS
) -> str:
    """
    Converte SRT básico para SRT com marcações de estilo simples.
    (Nem todos players suportam, mas aumenta impacto visual)

    Args:
        srt_content: Conteúdo SRT padrão
        highlight_color: Cor em formato ASS/SSA

    Returns:
        SRT com marcações de cor nas primeiras palavras (hook)
    """
    # Padrão simples: primeira linha de cada entrada fica em negrito
    lines = srt_content.split("\n")
    styled_lines = []
    is_text_line = False
    entry_line_count = 0

    for line in lines:
        if re.match(r'^\d+$', line.strip()):
            # Número de entrada
            styled_lines.append(line)
            entry_line_count = 0
            is_text_line = False
        elif '-->' in line:
            # Timestamp
            styled_lines.append(line)
            is_text_line = True
            entry_line_count = 0
        elif is_text_line and line.strip():
            entry_line_count += 1
            if entry_line_count == 1:
                # Primeira linha de texto: negrito
                styled_lines.append(f"<b>{line}</b>")
            else:
                styled_lines.append(line)
        else:
            styled_lines.append(line)
            if not line.strip():
                is_text_line = False

    return "\n".join(styled_lines)


def validate_srt(srt_path: str) -> tuple[bool, str]:
    """
    Valida a estrutura básica de um arquivo SRT.

    Returns:
        (válido, mensagem de erro ou '')
    """
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return False, "Arquivo SRT vazio"

        # Verifica se tem ao menos um timestamp
        if "-->" not in content:
            return False, "Nenhum timestamp encontrado no SRT"

        return True, ""
    except Exception as e:
        return False, str(e)