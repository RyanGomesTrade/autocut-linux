# -*- coding: utf-8 -*-
import logging
import random
import time
from typing import List, Dict
import database

logger = logging.getLogger("attention_os.title_engine")

class AttentionTitleEngine:
    """
    Attention Title Engine (ATE) v1.0
    Gera títulos contextuais baseados em gatilhos psicológicos e metadados.
    """

    STRATEGIES = {
        "HOOK_REVEAL": ["O segredo de {topic} finalmente apareceu", "Ele não esperava que {subject} fosse assim", "A verdade sobre {topic}"],
        "HOOK_CONFLICT": ["O clima pesou quando falaram de {topic}", "A discussão sobre {topic} fugiu do controle", "O confronto que ninguém previu"],
        "HOOK_WARNING": ["Pare de fazer isso com seu {topic}", "O erro fatal que destrói {topic}", "Aviso urgente: não ignore isso"],
        "HOOK_DISCOVERY": ["O que ele descobriu sobre {topic} muda tudo", "A nova forma de ver {topic}", "Encontramos o código secreto de {topic}"],
        "HOOK_ESCALATION": ["Isso escalou rápido demais", "O momento em que {topic} explodiu", "Ninguém conseguiu parar {subject}"],
        "HOOK_AUTHORITY": ["A lição de mestre sobre {topic}", "Como os grandes dominam {topic}", "A estratégia de elite de {subject}"],
        "HOOK_COLLAPSE": ["O dia que {topic} parou", "O fim de uma era para {topic}", "Quando {subject} perdeu tudo"],
        "HOOK_SECRET": ["O que não te contam sobre {topic}", "A técnica oculta de {subject}", "Os bastidores proibidos"],
        "HOOK_INSANITY": ["Isso foi pura loucura", "O plano mais insano de {subject}", "Inacreditável o que aconteceu aqui"],
        "HOOK_HUMILIATION": ["Ele foi colocado no seu lugar", "A resposta que calou o estúdio", "O xeque-mate de {subject}"]
    }

    def _detect_dominant_strategy(self, clip_data: Dict) -> str:
        """Escolhe a estratégia baseada nos sinais virais e categoria."""
        score = clip_data.get("viral_score", 0.5)
        energy = clip_data.get("speaker_energy", 0.5)
        category = str(clip_data.get("category", "general")).lower()

        if energy > 0.8: return "HOOK_INSANITY"
        if "debate" in category or "politica" in category: return "HOOK_CONFLICT"
        if "finance" in category: return "HOOK_WARNING"
        if score > 0.85: return "HOOK_REVEAL"
        
        return random.choice(list(self.STRATEGIES.keys()))

    def _extract_entities(self, transcript: str) -> Dict[str, str]:
        """Simula extração de entidades do texto para preencher templates."""
        words = transcript.split()
        topic = words[0] if len(words) > 0 else "isso"
        return {"topic": topic, "subject": "ele"}

    def generate_titles(self, clip_data: Dict) -> Dict:
        """Gera e rankeia 15 candidatos a título."""
        start_time = time.time()
        transcript = clip_data.get("transcript", "")
        strategy = self._detect_dominant_strategy(clip_data)
        entities = self._extract_entities(transcript)
        
        candidates = []
        templates = self.STRATEGIES[strategy]
        
        for _ in range(15):
            tpl = random.choice(templates)
            text = tpl.format(topic=entities["topic"], subject=entities["subject"])
            
            # Heurística de Ranking V1
            base_score = clip_data.get("viral_score", 0.5)
            curiosity_gap = 0.2 if len(text) < 45 else 0.1
            
            final_score = round(min(base_score + curiosity_gap + random.uniform(-0.05, 0.05), 0.99), 2)
            
            candidates.append({
                "text": text.lower(),
                "score": final_score,
                "strategy": strategy
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"ATE: {len(candidates)} títulos gerados em {time.time() - start_time:.2f}s")
        return {
            "best_title": candidates[0]["text"],
            "strategy_detected": strategy,
            "titles": candidates
        }

    def generate_titles_for_job(self, job_id: int, clip_data: Dict = None):
        """Orquestra a geração, persistência e retorno para o worker/SSE."""
        try:
            if not clip_data:
                job = database.get_job_by_id(job_id)
                if not job: return
                clip_data = {
                    "transcript": "Corte gerado do vídeo " + str(job.get('video_id', job_id)),
                    "viral_score": job.get("priority_score", 0.5),
                    "category": "general"
                }

            result = self.generate_titles(clip_data)
            database.save_generated_titles(job_id, result["titles"])
            return result
        except Exception as e:
            logger.error(f"Falha no Title Engine para Job {job_id}: {e}")
            fallback = [{"text": f"Clip #{job_id}", "score": 0.1, "strategy": "FALLBACK"}]
            database.save_generated_titles(job_id, fallback)
            return {"best_title": fallback[0]["text"], "titles": fallback}