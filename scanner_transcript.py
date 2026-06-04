import logging
from youtube_transcript_api import YouTubeTranscriptApi
import json
from transcription_fallback import get_whisper_transcript

logger = logging.getLogger("scanner_transcript")

# Dicionários de Heurísticas (Fase 1)
HEURISTICS = {
    "controversy": ["mentira", "humilhação", "absurdo", "lixo", "crítica", "pior", "horrível", "roubo", "falso", "exposto"],
    "expectation_break": ["o problema é que", "ninguém percebe", "o segredo é", "na verdade", "mas o que acontece", "o que ninguém fala", "o erro"],
    "absolute": ["todo mundo", "nunca", "sempre", "ninguém", "impossível", "certeza", "exatamente", "jamais"],
    "emotion": ["chorei", "dor", "triste", "feliz", "amo", "odeio", "medo", "desespero", "loucura", "sofrimento"],
    "authority": ["milhão", "bilhão", "físico", "médico", "pesquisa", "ciência", "especialista", "provado", "científico"]
}

def get_transcript_data(video_id, languages=['pt', 'en']):
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=languages)
        return transcript
    except Exception as e:
        logger.error(f"Erro ao buscar transcrição para {video_id}: {e}")
        return None

def normalize_score(count, max_expected=5):
    """ Normaliza o score de 0.0 a 1.0 """
    return min(count / max_expected, 1.0)

def analyze_segment(text):
    text_lower = text.lower()
    
    # Contagens
    counts = {
        "controversy": sum(1 for w in HEURISTICS["controversy"] if w in text_lower),
        "expectation_break": sum(1 for w in HEURISTICS["expectation_break"] if w in text_lower),
        "absolute": sum(1 for w in HEURISTICS["absolute"] if w in text_lower),
        "emotion": sum(1 for w in HEURISTICS["emotion"] if w in text_lower),
        "authority": sum(1 for w in HEURISTICS["authority"] if w in text_lower),
    }
    
    # Calcular scores normalizados (0.0 a 1.0)
    hook_score = normalize_score(counts["expectation_break"] + counts["absolute"], max_expected=3)
    controversy_score = normalize_score(counts["controversy"], max_expected=2)
    emotion_score = normalize_score(counts["emotion"], max_expected=2)
    authority_score = normalize_score(counts["authority"], max_expected=2)
    
    # Total Score (Normalizado entre 0.0 e 1.0 baseado em pesos)
    total_score = (hook_score * 0.4) + (controversy_score * 0.3) + (emotion_score * 0.2) + (authority_score * 0.1)
    
    return {
        "hook_score": round(hook_score, 2),
        "controversy_score": round(controversy_score, 2),
        "emotion_score": round(emotion_score, 2),
        "authority_score": round(authority_score, 2),
        "total_score": round(total_score, 2),
        "features": counts
    }

def process_video_transcript(video_id, block_duration=30.0, use_fallback=True, intervals=None):
    transcript = get_transcript_data(video_id)
    audio_hash = None
    
    # Se falhou o método oficial, tenta o fallback com Whisper
    if not transcript and use_fallback:
        logger.info(f"Iniciando fallback via Whisper para {video_id}...")
        transcript, audio_hash = get_whisper_transcript(video_id, intervals=intervals)

    if not transcript:
        return [], None
        
    segments = []
    current_block = []
    current_start = 0.0
    
    for item in transcript:
        start = item.start
        duration = item.duration
        text = item.text
        
        if not current_block:
            current_start = start
            
        current_block.append(text)
        
        # Se ultrapassou o tamanho do bloco (ex: 30s)
        if (start + duration) - current_start >= block_duration:
            block_text = " ".join(current_block)
            analysis = analyze_segment(block_text)
            
            segments.append({
                "start_time": round(current_start, 2),
                "end_time": round(start + duration, 2),
                "hook_score": analysis["hook_score"],
                "controversy_score": analysis["controversy_score"],
                "emotion_score": analysis["emotion_score"],
                "authority_score": analysis["authority_score"],
                "total_score": analysis["total_score"],
                "features": analysis["features"]
            })
            
            # Reset
            current_block = []
            
    # Processar o restante
    if current_block:
        block_text = " ".join(current_block)
        analysis = analyze_segment(block_text)
        last_item = transcript[-1]
        segments.append({
            "start_time": round(current_start, 2),
            "end_time": round(last_item.start + last_item.duration, 2),
            "hook_score": analysis["hook_score"],
            "controversy_score": analysis["controversy_score"],
            "emotion_score": analysis["emotion_score"],
            "authority_score": analysis["authority_score"],
            "total_score": analysis["total_score"],
            "features": analysis["features"]
        })
        
    return segments, audio_hash

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testando scanner de transcrição...")
    # Necessário um video_id real em PT com legendas ativadas para testar
    res = process_video_transcript("aqz-KE-bpKQ", 30) # Exemplo fictício/genérico
    if res:
        print(f"Gerados {len(res)} segmentos. Exemplo do primeiro:")
        print(json.dumps(res[0], indent=2, ensure_ascii=False))
