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

# ─── Configuração por região ──────────────────────────────────────────────────

REGIONS = {
    "BR": {
        "label":    "🇧🇷  Brasil (Português)",
        "region":   "BR",
        "language": "pt",
    },
    "US": {
        "label":    "🇺🇸  United States (English)",
        "region":   "US",
        "language": "en",
    },
}

class YouTubeSearcher:
    """
    Handles authentication and searching for videos on YouTube via Data API v3.
    """
    
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.readonly',
        'https://www.googleapis.com/auth/youtube.upload'
    ]
    
    # Categorias com queries em PT e EN
    CATEGORIES = {
        "1":  {
            "name": "Finance",
            "query_pt": "investimentos bolsa de valores finanças pessoais",
            "query_en": "investing stock market personal finance wealth",
            "pay": "Very high", "viral": "Medium",
        },
        "2":  {
            "name": "AI / Tech",
            "query_pt": "inteligência artificial tecnologia novidades chatgpt",
            "query_en": "artificial intelligence technology chatgpt future tech",
            "pay": "Very high", "viral": "High",
        },
        "3":  {
            "name": "Business",
            "query_pt": "empreendedorismo negócios startups marketing digital",
            "query_en": "entrepreneurship business startups side hustle",
            "pay": "High", "viral": "Medium",
        },
        "4":  {
            "name": "Fitness",
            "query_pt": "fitness treino musculação dieta saúde",
            "query_en": "fitness workout gym diet weight loss health",
            "pay": "Medium/High", "viral": "High",
        },
        "5":  {
            "name": "Politics",
            "query_pt": "política notícias brasil debate",
            "query_en": "politics news debate usa congress",
            "pay": "Medium", "viral": "High",
        },
        "6":  {
            "name": "Gaming",
            "query_pt": "games gameplay novidades jogos ps5 xbox",
            "query_en": "gaming gameplay ps5 xbox pc games review",
            "pay": "Low", "viral": "Very high",
        },
        "7":  {
            "name": "Facts / Curiosities",
            "query_pt": "curiosidades fatos desconhecidos documentário",
            "query_en": "mind blowing facts did you know documentary",
            "pay": "Low", "viral": "Very high",
        },
        "8":  {
            "name": "Humor",
            "query_pt": "humor comédia engraçado memes",
            "query_en": "comedy funny memes fails compilation",
            "pay": "Low", "viral": "Extremely high",
        },
        "9":  {
            "name": "Luxury / Lifestyle",
            "query_pt": "luxo mansões carros esportivos lifestyle rico",
            "query_en": "luxury mansion supercar rich lifestyle billionaire",
            "pay": "High", "viral": "Medium",
        },
        "10": {
            "name": "Motivation",
            "query_pt": "motivacional superação frases motivação desenvolvimento pessoal",
            "query_en": "motivation mindset success self improvement hustle",
            "pay": "Medium", "viral": "High",
        },
        "11": {
            "name": "True Crime",
            "query_pt": "crime verdadeiro casos policiais investigação",
            "query_en": "true crime murder mystery investigation documentary",
            "pay": "Medium/High", "viral": "Very high",
        },
        "12": {
            "name": "Real Estate",
            "query_pt": "imóveis investimento apartamento mercado imobiliário",
            "query_en": "real estate investing house flipping airbnb passive income",
            "pay": "Very high", "viral": "Medium",
        },
    }

    def __init__(
        self,
        client_secrets_file: str = "client_secrets.json",
        token_file: str = "token.pickle",
        region: str = "BR",
    ):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.region = region.upper() if region.upper() in REGIONS else "BR"
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
        logger.info(f"Autenticação com YouTube concluída. Região: {self.region}")

    def search_trending_videos(self, category_key: str, max_results: int = 5) -> List[Dict]:
        """
        Searches for high-performance videos based on a category and the
        configured region/language.
        """
        category = self.CATEGORIES.get(category_key)
        if not category:
            logger.error(f"Categoria {category_key} inválida.")
            return []

        region_cfg = REGIONS[self.region]
        lang_key   = "query_en" if self.region == "US" else "query_pt"
        query      = category[lang_key]

        logger.info(
            f"Buscando {max_results} vídeos de '{category['name']}' | "
            f"região={region_cfg['region']} idioma={region_cfg['language']}"
        )

        from datetime import datetime, timedelta
        # Busca vídeos dos últimos 30 dias para garantir que são "frescos"
        published_after = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"

        request = self.youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            order="relevance", # Mudado de viewCount para relevance para mais variedade
            maxResults=max_results,
            regionCode=region_cfg["region"],
            relevanceLanguage=region_cfg["language"],
            videoDuration="medium", 
            publishedAfter=published_after # FILTRO DE DATA
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
            title    = item['snippet']['title']
            channel  = item['snippet']['channelTitle']
            url      = f"https://www.youtube.com/watch?v={video_id}"
            videos.append({"title": title, "channel": channel, "url": url})
        
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
                channel = v.get("channel", "")
                comment = f"{v['title']} | {channel}" if channel else v['title']
                f.write(f"{v['url']} # {comment}\n")
        logger.info(f"Lista salva em {filename} ({len(new_videos)} novos vídeos)")
        return len(new_videos)
    except Exception as e:
        logger.error(f"Erro ao salvar lista: {e}")
        return 0


def main():
    print("\n=== Auto List YouTube - Viral Cutter ===")

    # Seleção de região
    print("\nSelecione o canal de destino:")
    for key, val in REGIONS.items():
        print(f"  [{key}] {val['label']}")
    region_choice = input("\nRegião (BR/US): ").strip().upper()
    if region_choice not in REGIONS:
        region_choice = "BR"

    searcher = YouTubeSearcher(region=region_choice)
    
    print(f"\nNicho | Região: {REGIONS[region_choice]['label']}")
    print(f"{'ID':<3} | {'Nicho':<22} | {'Pagamento':<15} | {'Viralização':<15}")
    print("-" * 62)
    for key, val in YouTubeSearcher.CATEGORIES.items():
        print(f"{key:<3} | {val['name']:<22} | {val['pay']:<15} | {val['viral']:<15}")
    
    choice = input("\nEscolha uma opção (1-12): ").strip()
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
        print(f"{i}. [{v.get('channel','')}] {v['title']}")
        print(f"   {v['url']}")

    confirm = input("\nDeseja salvar estes vídeos no arquivo list.txt? (s/n): ").strip().lower()
    if confirm == 's':
        save_to_list(videos)
    else:
        print("Operação cancelada.")

if __name__ == "__main__":
    main()
