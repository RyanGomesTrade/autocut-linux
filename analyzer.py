# -*- coding: utf-8 -*-
"""
analyzer.py - Integração com Ollama para análise inteligente de cortes virais
"""

import json
import time
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

from utils import parse_ollama_json_response, clamp

logger = logging.getLogger("viral_cutter.analyzer")

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT PRINCIPAL DO SISTEMA
# ─────────────────────────────────────────────────────────────────────────────

VIRAL_ANALYSIS_SYSTEM_PROMPT = """Você é um editor de vídeos curtos.
Sua tarefa é encontrar trechos de 20 a 60 segundos com alto potencial viral.
Receba a transcrição com [start - end] e retorne APENAS um JSON.

REGRAS:
- Identifique momentos emocionantes, polêmicos ou informativos.
- Formato JSON estrito:
[
  {
    "start": 0.0,
    "end": 0.0,
    "duration": 0.0,
    "viral_score": 0,
    "hook": "gancho",
    "summary": "resumo",
    "motivo": "motivo",
    "theme": "tema sugerido (ex: motivational, dramatic, funny, fast-paced)"
  }
]
- RESPONDA APENAS O JSON, SEM MARKDOWN."""


@dataclass
class ViralCut:
    """Representa um corte viral identificado pela IA."""
    start: float
    end: float
    duration: float
    viral_score: float
    hook: str
    summary: str
    motivo: str
    theme: str = "neutral"
    block_index: int = 0           # qual bloco originou este corte
    python_score: float = 0.0      # pontuação extra calculada em Python
    final_score: float = 0.0       # score combinado final

    def __post_init__(self):
        # Valida e corrige campos
        self.start = max(0.0, float(self.start))
        self.end = max(self.start + 1.0, float(self.end))
        self.duration = self.end - self.start
        self.viral_score = clamp(float(self.viral_score), 0.0, 100.0)

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.duration, 2),
            "viral_score": round(self.viral_score, 1),
            "python_score": round(self.python_score, 1),
            "final_score": round(self.final_score, 1),
            "hook": self.hook,
            "summary": self.summary,
            "motivo": self.motivo,
            "theme": self.theme,
            "block_index": self.block_index,
        }


class OllamaAnalyzer:
    """
    Cliente para análise de cortes virais via Ollama.
    """

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._api_url = f"{self.host}/api/generate"

    def _make_request(self, prompt: str) -> str:
        """
        Faz uma requisição HTTP para a API do Ollama com streaming para feedback.

        Returns:
            Texto completo da resposta do modelo
        """
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 4096,
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            self._api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        full_response = ""
        start_time = time.time()
        chunks_received = 0
        
        try:
            logger.info("  > Enviando dados ao Ollama e aguardando resposta...")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        text_part = chunk.get("response", "")
                        full_response += text_part
                        chunks_received += 1
                        
                        # Feedback visual frequente (a cada 20 pedaços de texto)
                        if chunks_received % 20 == 0:
                            logger.info(f"  ... Analisando ({len(full_response)} caracteres recebidos)")
                            
                        if chunk.get("done"):
                            break
            
            duration = time.time() - start_time
            logger.info(f"  > Resposta completa recebida em {duration:.1f}s")
            return full_response
            
        except Exception as e:
            logger.error(f"Erro na requisição streaming: {e}")
            raise

    def analyze_block(
        self,
        block_text: str,
        block_start: float,
        block_end: float,
        block_index: int
    ) -> list[ViralCut]:
        """
        Analisa um bloco de transcrição e retorna cortes virais identificados.

        Args:
            block_text: Texto do bloco com timestamps
            block_start: Início do bloco em segundos
            block_end: Fim do bloco em segundos
            block_index: Índice do bloco (para rastreabilidade)

        Returns:
            Lista de ViralCut identificados no bloco
        """
        prompt = f"""{VIRAL_ANALYSIS_SYSTEM_PROMPT}

----------------------------------------
TRANSCRIÇÃO PARA ANÁLISE (bloco {block_index + 1}):
Intervalo total do bloco: {block_start:.1f}s até {block_end:.1f}s

{block_text}

----------------------------------------
Analise o trecho acima e retorne APENAS o JSON com os cortes virais identificados."""

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"Analisando bloco {block_index + 1} "
                    f"({block_start:.0f}s-{block_end:.0f}s) | "
                    f"tentativa {attempt}/{self.max_retries}"
                )
                raw_response = self._make_request(prompt)
                logger.debug(f"Resposta bruta (início): {raw_response[:200]}")

                cuts_data = parse_ollama_json_response(raw_response)
                cuts = self._parse_cuts(cuts_data, block_start, block_end, block_index)

                logger.info(
                    f"Bloco {block_index + 1}: {len(cuts)} cortes encontrados"
                )
                return cuts

            except urllib.error.URLError as e:
                last_error = e
                logger.warning(f"Erro de conexão com Ollama: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

            except ValueError as e:
                last_error = e
                logger.warning(f"Erro ao parsear JSON do bloco {block_index + 1}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * 0.5)

            except Exception as e:
                last_error = e
                logger.error(f"Erro inesperado ao analisar bloco {block_index + 1}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        logger.error(
            f"Falha ao analisar bloco {block_index + 1} após "
            f"{self.max_retries} tentativas. Último erro: {last_error}"
        )
        return []

    def _parse_cuts(
        self,
        cuts_data: list[dict],
        block_start: float,
        block_end: float,
        block_index: int
    ) -> list[ViralCut]:
        """
        Converte a resposta do modelo em objetos ViralCut validados.
        """
        cuts = []
        seen_ranges: list[tuple[float, float]] = []

        for item in cuts_data:
            try:
                start = float(item.get("start", 0))
                end = float(item.get("end", 0))
                duration = end - start

                # Valida limites do bloco
                if start < block_start - 5 or end > block_end + 5:
                    logger.warning(
                        f"Corte fora do bloco ignorado: {start:.1f}s-{end:.1f}s "
                        f"(bloco: {block_start:.1f}s-{block_end:.1f}s)"
                    )
                    continue

                # Valida duração
                if duration < 15 or duration > 90:
                    logger.warning(
                        f"Corte com duração inválida ignorado: {duration:.1f}s"
                    )
                    continue

                # Verifica sobreposição excessiva com cortes já aceitos
                overlap_ok = True
                for r_start, r_end in seen_ranges:
                    overlap = min(end, r_end) - max(start, r_start)
                    overlap_ratio = overlap / duration if duration > 0 else 0
                    if overlap_ratio > 0.5:
                        logger.debug(
                            f"Corte duplicado/sobreposto ignorado: "
                            f"{start:.1f}s-{end:.1f}s"
                        )
                        overlap_ok = False
                        break

                if not overlap_ok:
                    continue

                cut = ViralCut(
                    start=start,
                    end=end,
                    duration=duration,
                    viral_score=float(item.get("viral_score", 50)),
                    hook=str(item.get("hook", ""))[:200],
                    summary=str(item.get("summary", ""))[:500],
                    motivo=str(item.get("motivo", ""))[:500],
                    theme=str(item.get("theme", "neutral"))[:50],
                    block_index=block_index,
                )

                cuts.append(cut)
                seen_ranges.append((start, end))

            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Corte inválido ignorado: {e} | item: {item}")
                continue

        return cuts

    def analyze_all_blocks(self, blocks: list[dict]) -> list[ViralCut]:
        """
        Analisa todos os blocos de transcrição e consolida os cortes.

        Args:
            blocks: Lista de blocos com 'start', 'end', 'text'

        Returns:
            Lista consolidada de todos os ViralCut encontrados
        """
        all_cuts: list[ViralCut] = []
        total = len(blocks)

        for i, block in enumerate(blocks):
            logger.info(f"─── Processando bloco {i + 1}/{total} ───")

            cuts = self.analyze_block(
                block_text=block["text"],
                block_start=block["start"],
                block_end=block["end"],
                block_index=i,
            )
            all_cuts.extend(cuts)

            # Pequena pausa entre requisições para não sobrecarregar o Ollama
            if i < total - 1:
                time.sleep(1.0)

        logger.info(f"Total de cortes encontrados: {len(all_cuts)}")
        return all_cuts


class HeuristicAnalyzer:
    """
    Motor de análise simplificado que não usa IA. 
    Baseia-se em palavras-chave e densidade de fala.
    """
    def __init__(self, top_n: int = 10):
        self.top_n = top_n
        self.viral_keywords = [
            "incrível", "segredo", "olha só", "revelação", "absurdo", "mentira",
            "verdade", "sempre", "nunca", "choque", "surpresa", "importante",
            "atenção", "descobri", "erro", "ganhei", "perdi", "mudou", "vencer",
            "dica", "estratégia", "sucesso", "falhou", "loucura"
        ]

    def analyze(self, transcript_segments: list) -> list[ViralCut]:
        """
        Gera cortes baseados em heurísticas simples.
        """
        logger.info("Iniciando análise heurística (sem IA)...")
        cuts = []
        
        # Agrupa segmentos em blocos de ~45 segundos
        current_start = 0.0
        if not transcript_segments:
            return []
            
        total_duration = transcript_segments[-1].end
        step = 40.0 # segundos
        
        for start in range(0, int(total_duration), int(step)):
            end = start + 50.0 # um pouco de overlap
            
            # Filtra segmentos nesse intervalo
            segs = [s for s in transcript_segments if s.start >= start and s.end <= end]
            if not segs:
                continue
                
            text = " ".join(s.text.lower() for s in segs)
            
            # Calcula score básico
            score = 40.0
            hits = sum(2 for kw in self.viral_keywords if kw in text)
            score += min(hits * 5, 40)
            
            # Penaliza se tiver pouco texto (silêncio)
            if len(text.split()) < 20:
                score -= 20
                
            cuts.append(ViralCut(
                start=float(start),
                end=float(end),
                duration=float(end - start),
                viral_score=score,
                hook="Trecho selecionado via análise heurística",
                summary=text[:100] + "...",
                motivo="Detectado via densidade de palavras e palavras-chave."
            ))
            
        logger.info(f"Análise heurística gerou {len(cuts)} candidatos.")
        return cuts


def calculate_python_score(cut: ViralCut, transcript_segments: list) -> float:
    """
    Calcula uma pontuação adicional em Python baseada em heurísticas objetivas.
    Complementa o viral_score do LLM.

    Args:
        cut: O corte viral a avaliar
        transcript_segments: Segmentos da transcrição no intervalo do corte

    Returns:
        Pontuação Python de 0 a 100
    """
    score = 50.0  # base

    # 1. Duração ideal (30-45s = ótimo para redes sociais)
    duration = cut.duration
    if 30 <= duration <= 45:
        score += 15
    elif 25 <= duration <= 55:
        score += 8
    elif 20 <= duration <= 60:
        score += 3

    # 2. Análise do texto transcrito no intervalo
    text = " ".join(
        s.text for s in transcript_segments
        if s.start >= cut.start and s.end <= cut.end + 1
    ).lower()

    # Palavras de alto impacto emocional
    high_impact_words = [
        "nunca", "sempre", "impossível", "inacreditável", "surpreendente",
        "segredo", "verdade", "mentira", "revelação", "descobri",
        "mudou", "transformou", "chocante", "absurdo", "ridículo",
        "never", "always", "impossible", "unbelievable", "secret",
        "truth", "lie", "revealed", "discovered", "shocking",
        "errado", "errei", "fracassei", "perdi", "ganhei",
        "mil", "milhão", "bilhão", "1000", "10000",
    ]
    word_hits = sum(1 for w in high_impact_words if w in text)
    score += min(word_hits * 4, 20)

    # 3. Presença de números (dados/estatísticas aumentam credibilidade)
    import re
    numbers = re.findall(r'\b\d+[.,]?\d*\b', text)
    if numbers:
        score += min(len(numbers) * 2, 8)

    # 4. Palavras de pergunta (engajamento)
    question_words = ["por que", "como", "quando", "o que", "quanto", "why", "how", "what", "when"]
    if any(w in text for w in question_words):
        score += 5

    # 5. Penalidade para cortes muito curtos ou muito longos
    if duration < 20 or duration > 65:
        score -= 15

    # 6. Hook forte (campo hook preenchido e substancial)
    if len(cut.hook) > 20:
        score += 5

    return clamp(score, 0.0, 100.0)


def rank_and_filter_cuts(
    cuts: list[ViralCut],
    transcript_segments: list,
    top_n: int = 10,
    min_score: float = 40.0,
    min_duration: float = 20.0,
    max_duration: float = 65.0,
) -> list[ViralCut]:
    """
    Ranqueia e filtra os melhores cortes virais.

    Args:
        cuts: Lista de todos os cortes encontrados
        transcript_segments: Segmentos da transcrição (para cálculo Python)
        top_n: Número máximo de cortes a retornar
        min_score: Score mínimo para incluir um corte
        min_duration: Duração mínima em segundos
        max_duration: Duração máxima em segundos

    Returns:
        Lista ranqueada dos melhores cortes
    """
    logger.info(f"Ranqueando {len(cuts)} cortes...")

    # Calcula python_score e final_score para cada corte
    for cut in cuts:
        cut.python_score = calculate_python_score(cut, transcript_segments)
        # Score final: 70% LLM + 30% Python
        cut.final_score = (cut.viral_score * 0.70) + (cut.python_score * 0.30)

    # Filtra por score mínimo e duração
    filtered = [
        c for c in cuts
        if c.final_score >= min_score
        and min_duration <= c.duration <= max_duration
    ]
    logger.info(f"{len(filtered)} cortes após filtros (score >= {min_score}, duração {min_duration}-{max_duration}s)")

    # Ordena por final_score descendente
    filtered.sort(key=lambda c: c.final_score, reverse=True)

    # Remove sobreposições excessivas (guarda o de maior score)
    deduplicated: list[ViralCut] = []
    for cut in filtered:
        overlap_found = False
        for accepted in deduplicated:
            overlap = min(cut.end, accepted.end) - max(cut.start, accepted.start)
            min_dur = min(cut.duration, accepted.duration)
            if overlap > 0 and (overlap / min_dur) > 0.4:
                overlap_found = True
                break
        if not overlap_found:
            deduplicated.append(cut)

    logger.info(f"{len(deduplicated)} cortes após remoção de sobreposições")

    # Retorna top N
    result = deduplicated[:top_n]

    # Re-ordena por tempo de aparição para facilitar visualização
    result.sort(key=lambda c: c.start)

    logger.info(f"Top {len(result)} cortes selecionados:")
    for i, c in enumerate(result, 1):
        logger.info(
            f"  #{i:02d} | {c.start:.1f}s-{c.end:.1f}s "
            f"({c.duration:.0f}s) | score={c.final_score:.1f} "
            f"| {c.hook[:50]}"
        )

    return result


def save_cuts_json(cuts: list[ViralCut], output_path: str) -> None:
    """Salva a lista de cortes em arquivo JSON."""
    data = [c.to_dict() for c in cuts]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Cortes salvos em: {output_path}")