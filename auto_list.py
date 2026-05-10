# -*- coding: utf-8 -*-
# auto_list.py

import os
import pickle
import logging
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import List, Dict

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("auto_list")

class YouTubeSearcher:
    """
    Handles authentication and searching for videos on YouTube via Data API v3.
    """
    
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.readonly',
        'https://www.googleapis.com/auth/youtube.upload'
    ]
    
    # Nichos atualizados com base na remuneração e viralização
    CATEGORIES = {
        "1": {"name": "Finanças", "query": "investimentos bolsa de valores finanças pessoais", "pay": "Muito alto", "viral": "Médio"},
        "2": {"name": "IA / Tecnologia", "query": "inteligência artificial tecnologia novidades chatgpt", "pay": "Muito alto", "viral": "Alto"},
        "3": {"name": "Negócios", "query": "empreendedorismo negócios startups marketing digital", "pay": "Alto", "viral": "Médio"},
        "4": {"name": "Fitness", "query": "fitness treino musculação dieta saúde", "pay": "Médio/alto", "viral": "Alto"},
        "5": {"name": "Política", "query": "política notícias brasil debate", "pay": "Médio", "viral": "Alto"},
        "6": {"name": "Games", "query": "games gameplay novidades jogos ps5 xbox", "pay": "Baixo", "viral": "Muito alto"},
        "7": {"name": "Curiosidades", "query": "curiosidades fatos desconhecidos documentário", "pay": "Baixo", "viral": "Muito alto"},
        "8": {"name": "Humor", "query": "humor comédia engraçado memes", "pay": "Baixo", "viral": "Extremamente alto"},
        "9": {"name": "Luxo", "query": "luxo mansões carros esportivos lifestyle rico", "pay": "Alto", "viral": "Médio"},
        "10": {"name": "Motivacional", "query": "motivacional superação frases motivação desenvolvimento pessoal", "pay": "Médio", "viral": "Alto"},
    }

    def __init__(self, client_secrets_file: str = "client_secrets.json", token_file: str = "token.pickle"):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.youtube = None
        self.authenticate()

    def authenticate(self):
        """
        Authenticates using OAuth2, reusing existing token if valid.
        """
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets_file):
                    print(f"\n[ERRO] Arquivo '{self.client_secrets_file}' não encontrado.")
                    print("Por favor, coloque o arquivo de segredos do Google Cloud no diretório atual.")
                    sys.exit(1)
                
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info("Autenticação com YouTube concluída.")

    def search_trending_videos(self, category_key: str, max_results: int = 5) -> List[Dict]:
        """
        Searches for high-performance videos based on a category.
        """
        category = self.CATEGORIES.get(category_key)
        if not category:
            logger.error(f"Categoria {category_key} inválida.")
            return []

        logger.info(f"Buscando {max_results} vídeos de '{category['name']}'...")

        request = self.youtube.search().list(
            q=category['query'],
            part="snippet",
            type="video",
            order="viewCount",
            maxResults=max_results,
            regionCode="BR",
            relevanceLanguage="pt"
        )
        
        try:
            response = request.execute()
        except Exception as e:
            if "insufficient authentication scopes" in str(e).lower() or "insufficientpermissions" in str(e).lower():
                print("\n[ERRO] Permissões insuficientes.")
                print("SOLUÇÃO: Apague o arquivo 'token.pickle' e execute o script novamente para autorizar.")
                return []
            else:
                logger.error(f"Erro na busca: {e}")
                return []

        videos = []
        for item in response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            url = f"https://www.youtube.com/watch?v={video_id}"
            videos.append({"title": title, "url": url})
        
        return videos

def get_existing_urls(filename: str) -> set:
    """
    Lê o arquivo de lista e retorna um conjunto com as URLs já existentes.
    """
    if not os.path.exists(filename):
        return set()
    urls = set()
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    url = line.split('#')[0].strip()
                    if url:
                        urls.add(url)
    except Exception as e:
        logger.error(f"Erro ao ler URLs existentes: {e}")
    return urls

def save_to_list(videos: List[Dict], filename: str = "list.txt") -> int:
    """
    Adiciona novas URLs ao list.txt, pulando duplicadas.
    Retorna o número de vídeos realmente adicionados.
    """
    existing_urls = get_existing_urls(filename)
    new_videos = [v for v in videos if v['url'] not in existing_urls]
    
    if not new_videos:
        logger.info("Todos os vídeos selecionados já estão na lista.")
        return 0
        
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"\n# --- Novas adições: {len(new_videos)} vídeos ---\n")
            for v in new_videos:
                f.write(f"{v['url']} # {v['title']}\n")
        logger.info(f"Lista salva em {filename} ({len(new_videos)} novos vídeos)")
        return len(new_videos)
    except Exception as e:
        logger.error(f"Erro ao salvar lista: {e}")
        return 0

def main():
    print("\n=== Auto List YouTube - Viral Cutter ===")
    
    searcher = YouTubeSearcher()
    
    print("\nSelecione o nicho:")
    print(f"{'ID':<3} | {'Nicho':<20} | {'Pagamento':<15} | {'Viralização':<15}")
    print("-" * 60)
    for key, val in YouTubeSearcher.CATEGORIES.items():
        print(f"{key:<3} | {val['name']:<20} | {val['pay']:<15} | {val['viral']:<15}")
    
    choice = input("\nEscolha uma opção (1-10): ").strip()
    if choice not in YouTubeSearcher.CATEGORIES:
        print("Opção inválida.")
        return

    try:
        count = int(input("Quantos vídeos deseja salvar? ").strip())
        if count <= 0:
            print("Número deve ser maior que zero.")
            return
    except ValueError:
        print("Por favor, insira um número válido.")
        return

    videos = searcher.search_trending_videos(choice, max_results=count)
    
    if not videos:
        print("Nenhum vídeo encontrado.")
        return

    print(f"\nEncontrados {len(videos)} vídeos:")
    for i, v in enumerate(videos, 1):
        print(f"{i}. {v['title']} ({v['url']})")

    confirm = input("\nDeseja salvar estes vídeos no arquivo list.txt? (s/n): ").strip().lower()
    if confirm == 's':
        save_to_list(videos)
    else:
        print("Operação cancelada.")

if __name__ == "__main__":
    main()
