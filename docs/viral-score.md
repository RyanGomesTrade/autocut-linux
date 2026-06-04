# Algoritmo de Viral Score

## O Racional
O Viral Score não é uma métrica de "qualidade", mas uma métrica de **"probabilidade de atenção"**. Ele combina sinais sociais, temporais e semânticos.

## Componentes do Score

### 1. Momentum Score (30%)
Calcula a força do crescimento do vídeo.
*   **VPH (Views Per Hour):** Velocidade atual.
*   **Relative VPH:** `VPH / Média do Canal`. Essencial para detectar virais em canais pequenos.
*   **VPH Acceleration:** `(VPH_atual - VPH_anterior) / Tempo`. Detecta a explosão antes do pico.

### 2. Clip Density (40%)
Análise semântica da transcrição por segmentos de 30-60s.
*   **Hook Score:** Presença de ganchos verbais.
*   **Controversy Score:** Detecção de temas polarizadores.
*   **Authority Score:** Tom de voz e assertividade.

### 3. Trend Score (20%)
Mapeamento de entidades e eventos atuais (`CURRENT_EVENTS`).
*   **Context Match:** O vídeo fala sobre algo que já é tendência agora?

### 4. Engagement Score (10%)
Sinais diretos da audiência.
*   **Comment Density:** Frequência de comentários por minuto de vídeo.
*   **Timestamp Signals:** Detecção de momentos onde usuários pedem cortes ou comentam horários específicos.

## Exemplo de JSON de Scoring
```json
{
  "video_id": "USbHzIzbXNI",
  "final_viral_score": 0.87,
  "metrics": {
    "relative_vph": 4.2,
    "vph_acceleration": 120.5,
    "clip_density": 0.75,
    "trend_match": "Eleições 2026",
    "comment_count": 450
  }
}
```

## Próximos Passos (Evolução)
*   **ML Integration:** Substituir os pesos fixos (0.4, 0.3, etc) por um modelo de regressão treinado na performance real dos shorts gerados.
*   **Audience Sentiment:** Analisar se o sentimento dos comentários é positivo/curioso (bom para viral) ou tóxico/negativo (risco de ban).
