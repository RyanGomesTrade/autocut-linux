# -*- coding: utf-8 -*-
# auto_list.py

import os
import pickle
import logging
import sys
import json
import random
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("auto_list")

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

def parse_yt_duration(duration_str: str) -> int:
    import re
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration_str)
    if not match:
        return 0
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)

class YouTubeSearcher:
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.readonly',
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube.force-ssl'
    ]

    CATEGORIES = {
        "1": {
            "name": "Finance",
            "queries_pt": [
                "investimentos bolsa de valores finanças pessoais",
                "como investir dinheiro renda fixa tesouro direto",
                "educação financeira independência financeira carteira",
                "ações fundos imobiliários dividendos passivos",
                "criptomoedas bitcoin ethereum carteira digital",
            ],
            "queries_en": [
                "investing stock market personal finance wealth",
                "how to invest money index funds retirement",
                "passive income dividend stocks financial freedom",
                "crypto bitcoin ethereum portfolio strategy",
                "real estate investing cash flow rental income",
            ],
            "pay": "Very high", "viral": "Medium",
        },
        "2": {
            "name": "AI / Tech",
            "queries_pt": [
                "inteligência artificial tecnologia novidades chatgpt",
                "IA generativa ferramentas automação produtividade",
                "machine learning deep learning tutorial",
                "agentes IA futuro trabalho tecnologia disruptiva",
                "open source modelos linguagem llm local",
            ],
            "queries_en": [
                "artificial intelligence technology chatgpt future tech",
                "AI tools automation productivity workflow",
                "machine learning tutorial neural networks",
                "open source LLM local AI models self hosted",
                "AI agents autonomous systems agentic workflow",
            ],
            "pay": "Very high", "viral": "High",
        },
        "3": {
            "name": "Business",
            "queries_pt": [
                "empreendedorismo negócios startups marketing digital",
                "como montar negócio do zero lucrativo",
                "gestão empresarial liderança equipes resultados",
                "vendas persuasão copywriting cliente",
                "franquia pequeno negócio lucro rápido",
            ],
            "queries_en": [
                "entrepreneurship business startups side hustle",
                "how to start a business from scratch profitable",
                "sales marketing funnel conversion growth",
                "leadership management team building culture",
                "solopreneur freelance online business passive",
            ],
            "pay": "High", "viral": "Medium",
        },
        "4": {
            "name": "Fitness",
            "queries_pt": [
                "fitness treino musculação dieta saúde",
                "como perder gordura ganhar músculo rápido",
                "treino em casa sem equipamento funcional",
                "alimentação saudável proteína cutting bulking",
                "corrida resistência cardio treino aeróbico",
            ],
            "queries_en": [
                "fitness workout gym diet weight loss health",
                "how to lose fat build muscle fast",
                "home workout no equipment bodyweight",
                "nutrition meal prep protein cutting bulking",
                "running marathon cardio endurance training",
            ],
            "pay": "Medium/High", "viral": "High",
        },
        "5": {
            "name": "Politics",
            "queries_pt": [
                "política notícias brasil debate",
                "eleições governo congresso decisões",
                "economia política impostos reforma",
                "geopolítica relações internacionais guerra",
                "opinião análise Brasil mundo atualidade",
            ],
            "queries_en": [
                "politics news debate usa congress",
                "elections government policy decisions analysis",
                "geopolitics international relations war conflict",
                "economy inflation federal reserve fiscal policy",
                "political commentary opinion analysis current events",
            ],
            "pay": "Medium", "viral": "High",
        },
        "6": {
            "name": "Gaming",
            "queries_pt": [
                "games gameplay novidades jogos ps5 xbox",
                "review análise jogo lançamento",
                "gameplay zerado walkthrough campanha",
                "torneio esports campeonato brasileiro",
                "indie game oculto jogo desconhecido",
            ],
            "queries_en": [
                "gaming gameplay ps5 xbox pc games review",
                "new game release review analysis",
                "speedrun challenge world record gaming",
                "esports tournament championship highlights",
                "hidden gem indie game underrated",
            ],
            "pay": "Low", "viral": "Very high",
        },
        "7": {
            "name": "Facts / Curiosities",
            "queries_pt": [
                "curiosidades fatos desconhecidos documentário",
                "história mistério segredo revelado",
                "ciência experimento incrível explicado",
                "fatos bizarros mundo inacreditável real",
                "documentário natureza animais selvagens",
            ],
            "queries_en": [
                "mind blowing facts did you know documentary",
                "history mystery secret revealed",
                "science experiment incredible explained",
                "bizarre facts world unbelievable true",
                "nature wildlife documentary animals",
            ],
            "pay": "Low", "viral": "Very high",
        },
        "8": {
            "name": "Humor",
            "queries_pt": [
                "humor comédia engraçado memes",
                "stand up comedy brasileiro ao vivo",
                "paródia sátira situação cotidiana",
                "compilação situações engraçadas reais",
                "piada inteligente intelectual absurdo",
            ],
            "queries_en": [
                "comedy funny memes fails compilation",
                "stand up comedy live special",
                "parody satire sketch comedy",
                "funny moments compilation real life",
                "dark humor intelligent absurd comedy",
            ],
            "pay": "Low", "viral": "Extremely high",
        },
        "9": {
            "name": "Luxury / Lifestyle",
            "queries_pt": [
                "luxo mansões carros esportivos lifestyle rico",
                "viagem destino exclusivo hotel cinco estrelas",
                "rotina milionário bilionário dia a dia",
                "supercar hypercars test drive avaliação",
                "lifestyle minimalismo design luxo discreto",
            ],
            "queries_en": [
                "luxury mansion supercar rich lifestyle billionaire",
                "travel exclusive destination five star hotel",
                "millionaire billionaire daily routine life",
                "supercar hypercar test drive review",
                "luxury minimalism design quiet wealth",
            ],
            "pay": "High", "viral": "Medium",
        },
        "10": {
            "name": "Motivation",
            "queries_pt": [
                "motivacional superação frases motivação desenvolvimento pessoal",
                "mentalidade vencedora mindset produtividade hábitos",
                "história superação trauma resiliência sucesso",
                "disciplina foco consistência resultados",
                "autoconhecimento psicologia comportamento mudança",
            ],
            "queries_en": [
                "motivation mindset success self improvement hustle",
                "discipline focus consistency results habits",
                "overcoming trauma resilience success story",
                "psychology behavior change self mastery",
                "stoicism philosophy life lessons wisdom",
            ],
            "pay": "Medium", "viral": "High",
        },
        "11": {
            "name": "True Crime",
            "queries_pt": [
                "crime verdadeiro casos policiais investigação",
                "serial killer caso não resolvido mistério",
                "fraude golpe estelionato exposição",
                "documentário crime organizado máfia",
                "julgamento tribunal caso famoso brasil",
            ],
            "queries_en": [
                "true crime murder mystery investigation documentary",
                "serial killer cold case unsolved mystery",
                "fraud scam exposed investigation",
                "organized crime mafia documentary",
                "trial court case famous crime",
            ],
            "pay": "Medium/High", "viral": "Very high",
        },
        "12": {
            "name": "Real Estate",
            "queries_pt": [
                "imóveis investimento apartamento mercado imobiliário",
                "como comprar primeiro imóvel financiamento",
                "airbnb aluguel por temporada renda passiva",
                "reforma imóvel valorização obra lucro",
                "fundos imobiliários FII dividendos passivos",
            ],
            "queries_en": [
                "real estate investing house flipping airbnb passive income",
                "how to buy first home mortgage tips",
                "rental property cash flow landlord",
                "house hacking BRRRR method real estate",
                "commercial real estate multifamily syndication",
            ],
            "pay": "Very high", "viral": "Medium",
        },
        "13": {
            "name": "Podcast",
            # Nota: a API do YouTube IGNORA operadores negativos (-palavra).
            # O filtro real é feito localmente após receber os resultados.
            "queries_pt": [
                "podcast episódio completo",
                "podcast entrevista completa",
                "podcast completo",
                "podcast ao vivo completo",
                "entrevista completa podcast",
                "bate papo completo podcast",
            ],
            "queries_en": [
                "podcast full episode",
                "podcast interview full",
                "long form podcast episode",
                "podcast conversation full length",
                "podcast new episode this week",
            ],
            "pay": "High", "viral": "High",
            "video_duration": "long",
            "video_category_id": "22",
            "min_views": 20000,
            "min_duration": 1800,  # 30 minutos mínimo
            "reject_title_keywords": [
                "highlights", "melhores momentos", "cortes", "compilação",
                "compilation", "best moments", "clips", "clip do",
                "news", "notícias", "breaking", "shorts", "reel",
                "trailer", "teaser", "preview", "recap", "corte",
                "clipes", "clip", "trecho", "trechos", "react",
                "reagindo", "compilado", "edit", "edits", "partes",
                "parte", "pílula", "pílulas", "cenas", "cena",
                "melhor momento",
            ],
            "require_podcast_signal": True,
            "podcast_signal_keywords": [
                "podcast", "ep.", "ep ", "episode", "episódio",
                "entrevista", "interview", "conversa", "bate-papo",
                "talk", "show", "s01", "s02", "s03",
            ],
        },
    }

    # Ordens de busca disponíveis — rotacionadas aleatoriamente
    _SEARCH_ORDERS = ["relevance", "viewCount", "date", "rating"]

    # Janelas de tempo (em dias) — variadas para explorar conteúdo diferente
    _TIME_WINDOWS = [7, 14, 30, 60, 90]

    def __init__(
        self,
        client_secrets_file: str = None,
        token_file: str = None,
        region: str = "BR",
        profile_index: int = None
    ):
        if (client_secrets_file is None or token_file is None):
            profiles_file = "youtube_profiles.json"
            if os.path.exists(profiles_file):
                try:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                        idx = profile_index if profile_index is not None else 0
                        if 0 <= idx < len(profiles):
                            p = profiles[idx]
                            client_secrets_file = client_secrets_file or p.get("client_secrets")
                            token_file = token_file or p.get("token")
                            logger.info(f"Usando perfil do YouTube: {p.get('name')}")
                except Exception as e:
                    logger.error(f"Erro ao carregar perfis para busca: {e}")

        self.client_secrets_file = client_secrets_file or "client_secrets.json"
        self.token_file = token_file or "token.pickle"
        self.region = region.upper() if region.upper() in REGIONS else "BR"
        self.youtube = None
        self.authenticate()

    @classmethod
    def get_all_categories(cls):
        return cls.CATEGORIES

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise Exception("Token inexistente ou inválido.")
            except Exception as e:
                logger.warning(f"Não foi possível renovar o token: {e}")
                if not os.path.exists(self.client_secrets_file):
                    raise FileNotFoundError(
                        f"Arquivo '{self.client_secrets_file}' não encontrado e o token atual expirou ou é inválido. "
                        "Por favor, coloque o arquivo client_secrets.json do Google Cloud no diretório para reautenticar."
                    )
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as flow_err:
                    raise Exception(f"Erro ao iniciar fluxo de autenticação: {flow_err}")

            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info(f"Autenticação com YouTube concluída. Região: {self.region}")

    def _pick_query(self, category: dict, lang_key: str) -> str:
        """
        Escolhe aleatoriamente uma das queries disponíveis para o nicho/idioma.
        Usa queries_pt/queries_en (lista) se existir, senão cai no campo único legado.
        """
        list_key = f"queries_{lang_key.split('_')[1]}"   # queries_pt / queries_en
        queries  = category.get(list_key) or []
        if queries:
            return random.choice(queries)
        # fallback para campo único (retrocompatibilidade)
        return category.get(lang_key, "")

    def search_trending_videos(self, category_key: str, max_results: int = 5) -> List[Dict]:
        category = self.CATEGORIES.get(category_key)
        if not category:
            logger.error(f"Categoria {category_key} inválida.")
            return []

        region_cfg = REGIONS[self.region]
        lang_key   = "query_en" if self.region == "US" else "query_pt"

        # ── Variação aleatória dos parâmetros de busca ────────────────────────
        query          = self._pick_query(category, lang_key)
        search_order   = random.choice(self._SEARCH_ORDERS)
        time_window    = random.choice(self._TIME_WINDOWS)
        video_duration = category.get("video_duration", "medium")
        min_views      = category.get("min_views", 0)

        from datetime import datetime, timedelta
        published_after = (datetime.utcnow() - timedelta(days=time_window)).isoformat() + "Z"

        logger.info(
            f"Buscando {max_results} vídeos de '{category['name']}' | "
            f"região={region_cfg['region']} | ordem={search_order} | "
            f"janela={time_window}d | query='{query[:60]}...'"
        )

        # Busca com margem extra para compensar filtragem por views
        fetch_n = min(max_results * 5, 50)

        # Monta parâmetros da busca — videoCategoryId é opcional por nicho
        search_params = dict(
            q=query,
            part="snippet",
            type="video",
            order=search_order,
            maxResults=fetch_n,
            regionCode=region_cfg["region"],
            relevanceLanguage=region_cfg["language"],
            videoDuration=video_duration,
            publishedAfter=published_after,
        )
        cat_id = category.get("video_category_id")
        if cat_id:
            search_params["videoCategoryId"] = cat_id

        try:
            search_response = self.youtube.search().list(**search_params).execute()
        except Exception as e:
            if "insufficient authentication scopes" in str(e).lower() or "insufficientpermissions" in str(e).lower():
                raise Exception(
                    f"O token '{self.token_file}' não tem permissão para busca. "
                    "Por favor, apague este arquivo e tente novamente."
                )
            logger.error(f"Erro na busca: {e}")
            return []

        items = search_response.get("items", [])
        if not items:
            return []

        # ── Busca estatísticas (views e duration) em batch ────────────────────
        video_ids = [item["id"]["videoId"] for item in items]
        stats_map: Dict[str, dict] = {}
        try:
            stats_response = self.youtube.videos().list(
                part="statistics,contentDetails",
                id=",".join(video_ids)
            ).execute()

            for item in stats_response.get("items", []):
                vid   = item["id"]
                views = int(item["statistics"].get("viewCount", 0))
                duration_str = item["contentDetails"].get("duration", "PT0S")
                duration_sec = parse_yt_duration(duration_str)
                stats_map[vid] = {"views": views, "duration": duration_sec}
        except Exception as e:
            logger.warning(f"Falha ao buscar estatísticas: {e}")

        # ── Filtros locais de qualidade (aplicados APÓS receber da API) ────────
        reject_kws   = [k.lower() for k in category.get("reject_title_keywords", [])]
        signal_kws   = [k.lower() for k in category.get("podcast_signal_keywords", [])]
        req_signal   = category.get("require_podcast_signal", False)
        min_duration = category.get("min_duration", 0)

        candidates = []
        rejected_views = rejected_duration = rejected_kw = rejected_signal = 0

        for item in items:
            vid     = item["id"]["videoId"]
            stats   = stats_map.get(vid, {})
            views   = stats.get("views", 0)
            duration = stats.get("duration", 0)
            title   = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            title_lower   = title.lower()
            channel_lower = channel.lower()
            combined      = f"{title_lower} {channel_lower}"

            # 1. Filtro de views mínimas
            if min_views and views < min_views:
                rejected_views += 1
                logger.debug(f"Rejeitado (views={views:,}): {title[:50]}")
                continue

            # 2. Filtro de duração mínima (se configurado)
            if min_duration and duration < min_duration:
                rejected_duration += 1
                logger.debug(f"Rejeitado (duração={duration}s < {min_duration}s): {title[:50]}")
                continue

            # 3. Filtro de rejeição por keywords no título ou canal (evitar canais de cortes)
            if reject_kws and (any(kw in title_lower for kw in reject_kws) or any(kw in channel_lower for kw in reject_kws)):
                rejected_kw += 1
                logger.debug(f"Rejeitado (keyword lixo no título/canal): {title[:50]} | Canal: {channel}")
                continue

            # 4. Filtro de sinal de podcast — título OU canal deve ter ao menos
            #    uma palavra-chave que indique que é um podcast de verdade
            if req_signal and signal_kws:
                has_signal = any(kw in combined for kw in signal_kws)
                if not has_signal:
                    rejected_signal += 1
                    logger.debug(f"Rejeitado (sem sinal podcast): {title[:50]}")
                    continue

            candidates.append({
                "title":   title,
                "channel": channel,
                "url":     f"https://www.youtube.com/watch?v={vid}",
                "views":   views,
                "duration": duration,
            })

        logger.info(
            f"Filtros locais: {len(candidates)} aprovados | "
            f"{rejected_views} views | {rejected_duration} duração | {rejected_kw} lixo | {rejected_signal} sem sinal"
        )

        # Embaralha para que chamadas consecutivas ao mesmo nicho entreguem
        # resultados em ordem diferente mesmo quando a API retorna o mesmo pool
        random.shuffle(candidates)

        result = candidates[:max_results]
        logger.info(
            f"Retornando {len(result)}/{len(candidates)} vídeos "
            f"(descartados por filtros: {len(items) - len(candidates)})"
        )
        return result


def get_existing_urls(filename: str) -> set:
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
    existing_urls = get_existing_urls(filename)
    new_videos    = [v for v in videos if v['url'] not in existing_urls]

    if not new_videos:
        logger.info("Todos os vídeos selecionados já estão na lista.")
        return 0

    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"\n# --- Novas adições: {len(new_videos)} vídeos ---\n")
            for v in new_videos:
                channel = v.get("channel", "")
                views   = f" | {v['views']:,} views" if v.get("views") else ""
                comment = f"{v['title']} | {channel}{views}" if channel else v['title']
                f.write(f"{v['url']} # {comment}\n")
        logger.info(f"Lista salva em {filename} ({len(new_videos)} novos vídeos)")
        return len(new_videos)
    except Exception as e:
        logger.error(f"Erro ao salvar lista: {e}")
        return 0


def main():
    print("\n=== Auto List YouTube - Viral Cutter ===")

    print("\n[1] Busca Simples por Nicho (Antiga)")
    print("[2] Motor de Descoberta Viral (Funil de IA + SQLite)")
    modo = input("\nEscolha o modo: ").strip()

    if modo == "2":
        try:
            import discovery_engine
            searcher = YouTubeSearcher(region="BR")
            discovery_engine.run_discovery(searcher.youtube)
            print("\n✅ Busca Viral concluída. Resultados salvos em viral_engine.db")
        except Exception as e:
            logger.error(f"Erro ao rodar Motor Viral: {e}")
        return

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

    choice = input("\nEscolha uma opção (1-13): ").strip()
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
        views_str = f" | {v.get('views', 0):,} views" if v.get('views') else ""
        print(f"{i}. [{v.get('channel','')}] {v['title']}{views_str}")
        print(f"   {v['url']}")

    confirm = input("\nDeseja salvar estes vídeos no arquivo list.txt? (s/n): ").strip().lower()
    if confirm == 's':
        save_to_list(videos)
    else:
        print("Operação cancelada.")

if __name__ == "__main__":
    main()