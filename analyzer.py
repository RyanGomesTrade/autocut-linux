# -*- coding: utf-8 -*-
"""
analyzer.py - Integração com Ollama para análise inteligente de cortes virais

CORREÇÕES APLICADAS (limites de duração):
  1. VIRAL_ANALYSIS_SYSTEM_PROMPT substituído por build_system_prompt(min, max)
     → O LLM agora recebe o intervalo correto de duração em vez de "20 a 60 segundos" fixo.
  2. OllamaAnalyzer.__init__: novos parâmetros min_duration / max_duration.
  3. OllamaAnalyzer._parse_cuts: filtro "duration > 90" substituído por limites dinâmicos.
  4. HeuristicAnalyzer.__init__: novos parâmetros min_duration / max_duration.
  5. HeuristicAnalyzer.analyze: window_size e step agora derivam dos parâmetros da instância.
  6. calculate_python_score: penalidade de duração agora usa min_duration / max_duration externos.
  7. rank_and_filter_cuts: sem alteração de assinatura (já lia do config), mas documentado.
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
# BUILDER DO PROMPT DO SISTEMA  (substitui a constante VIRAL_ANALYSIS_SYSTEM_PROMPT)
# ─────────────────────────────────────────────────────────────────────────────

def build_system_prompt(min_duration: float, max_duration: float) -> str:
    """
    Constrói o prompt de sistema do analisador viral com os limites de duração
    corretos para este pipeline, em vez de usar valores fixos de "20 a 60 segundos".

    Args:
        min_duration: Duração mínima em segundos (ex: 20.0)
        max_duration: Duração máxima em segundos (ex: 300.0)

    Returns:
        String de prompt pronta para envio ao modelo.
    """
    return f"""Você é um editor de vídeos curtos especializado em retenção e viralização.
Sua tarefa é encontrar trechos de {min_duration:.0f} a {max_duration:.0f} segundos com altíssimo potencial de retenção.

REGRAS CRÍTICAS DE RETENÇÃO:
1. O GANCHO (HOOK) É TUDO: Os primeiros 3 segundos do corte DEVEM conter uma frase de impacto, uma pergunta instigante ou uma afirmação polêmica.
2. Identifique momentos emocionantes, polêmicos ou informativos.
3. STORYTELLING: Priorize trechos com início (gancho), meio e fim.
4. A duração dos cortes DEVE estar entre {min_duration:.0f}s e {max_duration:.0f}s — nunca fora desse intervalo.

Formato JSON estrito:
[
  {{
    "start": 0.0,
    "end": 0.0,
    "duration": 0.0,
    "viral_score": 0,
    "hook": "gancho de impacto dos primeiros 3s",
    "summary": "resumo",
    "motivo": "por que isso vai viralizar",
    "theme": "tema sugerido (ex: motivational, dramatic, funny, fast-paced)"
  }}
]
- RESPONDA APENAS O JSON, SEM MARKDOWN OU COMENTÁRIOS."""


# Mantém a constante legada apontando para o builder com valores padrão,
# para compatibilidade com qualquer importação direta existente.
VIRAL_ANALYSIS_SYSTEM_PROMPT = build_system_prompt(20.0, 300.0)


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

    CORREÇÃO: min_duration e max_duration agora são parâmetros do construtor e
    propagados para o prompt do sistema e para o filtro interno de duração.
    """

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        min_duration: float = 20.0,    # NOVO: duração mínima configurável
        max_duration: float = 300.0,   # NOVO: duração máxima configurável (era implicitamente 60s via prompt)
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.min_duration = min_duration
        self.max_duration = max_duration
        self._api_url = f"{self.host}/api/generate"

        # Prompt construído uma vez com os limites corretos
        self._system_prompt = build_system_prompt(min_duration, max_duration)

        logger.info(
            f"OllamaAnalyzer inicializado | modelo={model} | "
            f"duração={min_duration:.0f}s–{max_duration:.0f}s"
        )

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
        # CORREÇÃO: usa self._system_prompt (construído com min/max_duration reais)
        # em vez da constante VIRAL_ANALYSIS_SYSTEM_PROMPT com "20 a 60 segundos" fixo.
        prompt = f"""{self._system_prompt}

----------------------------------------
TRANSCRIÇÃO PARA ANÁLISE (bloco {block_index + 1}):
Intervalo total do bloco: {block_start:.1f}s até {block_end:.1f}s

{block_text}

----------------------------------------
Analise o trecho acima e retorne APENAS o JSON com os cortes virais identificados.
Lembre-se: cada corte deve ter entre {self.min_duration:.0f}s e {self.max_duration:.0f}s."""

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

        CORREÇÃO: O filtro de duração era "duration < 15 or duration > 90" com valores
        completamente fixos. Agora usa self.min_duration e self.max_duration com uma
        margem de tolerância de 10% para absorver pequenas imprecisões do LLM.
        """
        cuts = []
        seen_ranges: list[tuple[float, float]] = []

        # Limites dinâmicos: margem de 10% para tolerar imprecisões do LLM
        # sem descartar cortes válidos próximos do limite configurado.
        hard_min = self.min_duration * 0.80   # ex: min=20s → aceita a partir de 16s
        hard_max = self.max_duration * 1.10   # ex: max=300s → aceita até 330s

        logger.debug(
            f"_parse_cuts: limites dinâmicos = [{hard_min:.1f}s, {hard_max:.1f}s] "
            f"(config: {self.min_duration:.0f}s–{self.max_duration:.0f}s ±10%)"
        )

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

                # CORREÇÃO: validação de duração agora usa limites dinâmicos,
                # não mais os valores fixos 15 e 90.
                if duration < hard_min or duration > hard_max:
                    logger.warning(
                        f"Corte com duração fora dos limites ignorado: {duration:.1f}s "
                        f"(limites aceitos: {hard_min:.1f}s–{hard_max:.1f}s)"
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
    Motor de análise avançado baseado em padrões linguísticos e heurísticas de retenção.
    Ideal para processamento ultra-rápido ou quando não há acesso ao Ollama.

    CORREÇÃO: window_size e step eram valores fixos (45s e 25s). Agora derivam de
    min_duration e max_duration passados no construtor, permitindo cortes longos.
    """

    def __init__(
        self,
        top_n: int = 10,
        min_duration: float = 20.0,    # NOVO: duração mínima configurável
        max_duration: float = 300.0,   # NOVO: duração máxima configurável (era 45s fixo)
    ):
        self.top_n = top_n
        self.min_duration = min_duration
        self.max_duration = max_duration

        logger.info(
            f"HeuristicAnalyzer inicializado | "
            f"duração={min_duration:.0f}s–{max_duration:.0f}s"
        )

        # Categorias de palavras-chave para scoring diferenciado
        self.keywords = {
            "polêmica": ["absurdo", "mentira", "errado", "ridículo", "pare", "chega", "odeio", "vergonha", "farsa"],
            "curiosidade": ["segredo", "revelado", "escondido", "finalmente", "descobri", "sabia", "olha", "veja", "escuta"],
            "sucesso_dinheiro": ["rico", "milhão", "ganhar", "lucro", "sucesso", "estratégia", "vencer", "bilhão", "investir"],
            "impacto": ["incrível", "choque", "surpresa", "loucura", "mudou", "transformou", "impossível", "nunca", "sempre"],
            "urgência": ["agora", "hoje", "rápido", "urgente", "pare", "atenção", "importante", "cuidado"]
        }

        # Gatilhos de início de frase (Hooks heurísticos)
        self.hook_triggers = [
            "você sabia", "o grande erro", "muita gente", "o segredo para", "pare de",
            "eu vou te contar", "a verdade sobre", "nunca faça", "sempre que"
        ]

    def analyze(self, transcript_segments: list) -> list[ViralCut]:
        """
        Gera cortes baseados em padrões de retenção sem usar IA.

        CORREÇÃO: window_size era 45.0 fixo. Agora usa self.max_duration.
        O step é calculado dinamicamente: no mínimo self.min_duration,
        no máximo 50% da janela, para garantir overlap razoável sem saltos grandes.
        """
        logger.info(
            f"Iniciando análise heurística | "
            f"janela={self.max_duration:.0f}s | "
            f"min={self.min_duration:.0f}s"
        )
        cuts = []

        if not transcript_segments:
            return []

        total_duration = transcript_segments[-1].end

        # CORREÇÃO PRINCIPAL:
        # Antes: window_size = 45.0 (fixo) / step = 25.0 (fixo)
        # Agora: window_size = max_duration configurado pelo usuário
        #        step = max(min_duration, window_size * 0.4) para overlap de 60%
        #        Isso garante que segmentos longos sejam gerados E que haja
        #        sobreposição suficiente para não perder momentos no início/fim.
        window_size = self.max_duration
        step = max(self.min_duration, window_size * 0.4)

        logger.debug(f"Heurística: window_size={window_size:.1f}s, step={step:.1f}s")

        for start_t in self._frange(0, total_duration, step):
            end_t = start_t + window_size

            # 1. Filtra segmentos na janela
            segs = [s for s in transcript_segments if s.start >= start_t and s.end <= end_t]
            if not segs:
                continue

            text = " ".join(s.text.lower() for s in segs)
            words = text.split()

            # Mínimo de palavras proporcional à duração esperada
            # (~2 palavras/segundo é ritmo normal de fala)
            min_words = max(25, int(self.min_duration * 1.5))
            if len(words) < min_words:
                continue

            # 2. Scoring por Palavras-Chave (Power Words)
            score = 35.0  # Base inicial
            for category, kws in self.keywords.items():
                hits = sum(1 for kw in kws if kw in text)
                score += min(hits * 6, 30)  # Máximo 30 pontos por categoria

            # 3. Análise de Pontuação (Entusiasmo/Interação)
            energy_hits = text.count("?") + text.count("!")
            score += min(energy_hits * 5, 20)

            # 4. Detecção de Hooks (Gatilhos de Início)
            first_text = segs[0].text.lower()
            if any(trigger in first_text for trigger in self.hook_triggers):
                score += 25
                logger.debug(f"Hook heurístico detectado em {start_t:.1f}s")

            # 5. Speech Rate (Velocidade de Fala)
            # Ideal para retenção: entre 130 e 160 palavras por minuto (2.1 a 2.6 palavras/s)
            actual_duration = segs[-1].end - segs[0].start
            wps = len(words) / actual_duration if actual_duration > 0 else 0
            if 2.0 <= wps <= 3.0:
                score += 10  # Ritmo bom
            elif wps > 4.0:
                score -= 10  # Rápido demais (ruído?)

            # 6. Bonus para cortes na faixa "ideal" de duração
            # (para cortes longos, faixas maiores também ganham bonus)
            if self.min_duration <= actual_duration <= self.max_duration:
                score += 5

            # 7. Gerador de Título/Hook Heurístico
            hook_candidate = segs[0].text.strip()
            if len(hook_candidate.split()) > 10:
                hook_candidate = " ".join(hook_candidate.split()[:10]) + "..."

            cuts.append(ViralCut(
                start=float(segs[0].start),
                end=float(segs[-1].end),
                duration=float(segs[-1].end - segs[0].start),
                viral_score=clamp(score, 0, 100),
                hook=hook_candidate,
                summary=text[:100] + "...",
                motivo=f"Padrão heurístico (WPS: {wps:.1f}, Energy: {energy_hits})"
            ))

        logger.info(f"Análise heurística gerou {len(cuts)} candidatos potenciais.")
        return cuts

    @staticmethod
    def _frange(start: float, stop: float, step: float):
        """range() com suporte a float."""
        current = start
        while current < stop:
            yield current
            current += step


def calculate_python_score(
    cut: ViralCut,
    transcript_segments: list,
    min_duration: float = 20.0,
    max_duration: float = 300.0,
) -> float:
    """
    Calcula uma pontuação adicional em Python baseada em heurísticas objetivas.
    Complementa o viral_score do LLM.

    CORREÇÃO: A penalidade de duração antes era hardcoded para 20–65s.
    Agora recebe min_duration e max_duration como parâmetros para refletir
    a configuração real do pipeline.

    Args:
        cut: O corte viral a avaliar
        transcript_segments: Segmentos da transcrição no intervalo do corte
        min_duration: Duração mínima configurada (default: 20.0)
        max_duration: Duração máxima configurada (default: 300.0)

    Returns:
        Pontuação Python de 0 a 100
    """
    score = 50.0  # base

    duration = cut.duration

    # 1. Duração ideal
    # O "sweet spot" é a faixa central entre min e max configurados.
    # Faixa ótima: 30–45% da duração máxima (ex: max=300 → ótimo=90–135s)
    # Faixa boa:   20–65% da duração máxima
    # Faixa ok:    min até max (dentro do range aceito)
    sweet_low = max_duration * 0.30
    sweet_high = max_duration * 0.45
    good_low = max_duration * 0.20
    good_high = max_duration * 0.65

    if sweet_low <= duration <= sweet_high:
        score += 15
    elif good_low <= duration <= good_high:
        score += 8
    elif min_duration <= duration <= max_duration:
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

    # 5. CORREÇÃO: Penalidade para cortes fora dos limites configurados
    # Antes: "if duration < 20 or duration > 65" (completamente fixo)
    # Agora: usa os parâmetros reais do pipeline
    if duration < min_duration or duration > max_duration:
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
    max_duration: float = 300.0,   # PADRÃO ATUALIZADO: era 65.0
) -> list[ViralCut]:
    """
    Ranqueia e filtra os melhores cortes virais.

    Nota: Esta função já recebia min_duration e max_duration do config externo.
    O padrão do parâmetro max_duration foi atualizado de 65.0 para 300.0 para
    refletir o novo comportamento padrão. O valor real sempre vem de args.max_duration.

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
    logger.info(
        f"Ranqueando {len(cuts)} cortes | "
        f"duração={min_duration:.0f}s–{max_duration:.0f}s | "
        f"score_mín={min_score}"
    )

    # Calcula python_score e final_score para cada corte
    # CORREÇÃO: passa min_duration e max_duration para calculate_python_score
    for cut in cuts:
        cut.python_score = calculate_python_score(
            cut, transcript_segments,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        # Score final: 70% LLM + 30% Python
        cut.final_score = (cut.viral_score * 0.70) + (cut.python_score * 0.30)

    # Filtra por score mínimo e duração
    filtered = [
        c for c in cuts
        if c.final_score >= min_score
        and min_duration <= c.duration <= max_duration
    ]
    logger.info(
        f"{len(filtered)} cortes após filtros "
        f"(score >= {min_score}, duração {min_duration:.0f}s–{max_duration:.0f}s)"
    )

    # Fallback inteligente se nenhum corte passar pelos filtros estritos
    if not filtered and cuts:
        fallback_min_score = min(30.0, min_score)
        logger.warning(
            f"⚠️ Nenhum corte passou pelos filtros. "
            f"Aplicando fallback (score >= {fallback_min_score}, "
            f"duração {min_duration:.0f}s–{max_duration:.0f}s)..."
        )
        filtered = [
            c for c in cuts
            if c.final_score >= fallback_min_score
            and min_duration <= c.duration <= max_duration
        ]
        logger.info(f"{len(filtered)} cortes obtidos via fallback.")

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