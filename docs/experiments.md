# Registro de Experimentos e Hipóteses

## Hipóteses Atuais

### H1: O VPH Relativo é mais importante que o VPH Absoluto
*   **Racional:** Um vídeo com 1.000 VPH em um canal de 10 inscritos é um sinal viral muito mais forte que 100.000 VPH em um canal de 10 milhões.
*   **Status:** Validando via métrica `relative_vph`.

### H2: A aceleração detecta o viral antes do pico
*   **Racional:** Se o VPH dobrou nos últimos 30 minutos, o vídeo ainda vai crescer muito. É a hora ideal para postar o corte.
*   **Status:** Implementado via `vph_acceleration`.

### H3: Strategic Audio Sampling é suficiente para Scoring
*   **Racional:** Não precisamos transcrever o vídeo todo. Se os primeiros 5 minutos e amostras do meio/fim tiverem alta densidade de ganchos, o vídeo todo é bom.
*   **Status:** Implementado em `transcription_fallback.py`.

## Experimentos Planejados
1.  **Testar Threshold de VPH:** Qual o número mágico? 500? 1000? 2000?
2.  **Análise de Comentários vs Retenção:** Comentários positivos correlacionam com maior tempo de tela nos Shorts?
3.  **Comparação Whisper Model:** O modelo `base` perde muitos ganchos importantes comparado ao `medium`?
