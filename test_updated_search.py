
import os
import json
from auto_list import YouTubeSearcher

def test():
    try:
        print("Iniciando YouTubeSearcher com perfil padrão (0)...")
        searcher = YouTubeSearcher(region="BR")
        print(f"Arquivos usados: {searcher.client_secrets_file}, {searcher.token_file}")
        
        # Testar busca rápida
        videos = searcher.search_trending_videos("1", max_results=1)
        print(f"Sucesso! Encontrados {len(videos)} vídeos.")
        for v in videos:
            print(f"- {v['title']} ({v['url']})")
            
    except Exception as e:
        print(f"Erro no teste: {e}")

if __name__ == "__main__":
    test()
