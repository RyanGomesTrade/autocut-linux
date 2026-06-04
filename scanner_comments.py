import re
import logging
from datetime import datetime, timezone
from auto_list import YouTubeSearcher

logger = logging.getLogger("scanner_comments")

TIMESTAMP_PATTERN = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\b')

def parse_iso8601(date_str):
    """ Parse YouTube iso 8601 string safely """
    date_str = date_str.replace("Z", "+00:00")
    return datetime.fromisoformat(date_str)

def get_video_comments(youtube, video_id, max_results=100):
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_results,
            order="relevance"
        )
        response = request.execute()
        return response.get("items", [])
    except Exception as e:
        logger.error(f"Erro ao buscar comentários para {video_id}: {e}")
        return []

def scan_comments(youtube, video_id):
    comments_data = get_video_comments(youtube, video_id)
    
    timestamp_mentions = {}
    now = datetime.now(timezone.utc)
    
    for item in comments_data:
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        text = snippet["textOriginal"]
        likes = snippet["likeCount"]
        published_at = parse_iso8601(snippet["publishedAt"])
        
        # Encontrar timestamps
        timestamps = TIMESTAMP_PATTERN.findall(text)
        
        # Calcular velocity score simplificado (Likes por hora desde a publicação)
        hours_since_pub = (now - published_at).total_seconds() / 3600.0
        if hours_since_pub < 1.0:
            hours_since_pub = 1.0 # evitar divisão por zero
            
        velocity_score = likes / hours_since_pub
        
        # Adicionar repetições de palavras virais
        text_lower = text.lower()
        has_reaction = any(w in text_lower for w in ["kkk", "absurdo", "essa parte", "genial"])
        
        # Boost de velocity se tiver reação
        if has_reaction:
            velocity_score *= 1.5
            
        for ts in timestamps:
            if ts not in timestamp_mentions:
                timestamp_mentions[ts] = {
                    "count": 0,
                    "total_likes": 0,
                    "max_velocity": 0.0
                }
            timestamp_mentions[ts]["count"] += 1
            timestamp_mentions[ts]["total_likes"] += likes
            if velocity_score > timestamp_mentions[ts]["max_velocity"]:
                timestamp_mentions[ts]["max_velocity"] = velocity_score
                
    # Transformar e ordenar
    signals = []
    for ts, data in timestamp_mentions.items():
        signals.append({
            "timestamp_str": ts,
            "likes": data["total_likes"],
            "velocity_score": round(data["max_velocity"], 2),
            "repeated_mentions": data["count"]
        })
        
    # Ordenar por mentions e likes
    signals = sorted(signals, key=lambda x: (x["repeated_mentions"], x["likes"]), reverse=True)
    return signals

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    searcher = YouTubeSearcher()
    # Teste rápido
    res = scan_comments(searcher.youtube, "dQw4w9WgXcQ")
    print(res)
