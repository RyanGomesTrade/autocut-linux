# Análise de Falhas (Failure Analysis)

## O Perigo do Overfitting Psicológico
Acreditar que o sistema entende a mente humana perfeitamente é o maior risco técnico. Este documento registra onde o modelo falha para recalibrar as expectativas.

## Tipos de Falha

### 1. O Falso Positivo (Score Alto -> Flop)
O sistema detecta um "momento perfeito", mas o vídeo não performa.
*   **Causas Prováveis:** 
    *   Thumbnail/Título fracos no post final.
    *   Saturação do assunto (assunto "batido").
    *   Shadowban ou restrições de plataforma.
    *   Contexto cultural mudou entre a análise e a postagem.

### 2. O Falso Negativo (Score Baixo -> Viral)
Um vídeo ignorado pelo sistema explode organicamente.
*   **Causas Prováveis:**
    *   Viralização por "estética" ou "vibe" (difícil de medir via texto).
    *   Compartilhamento por uma autoridade externa (efeito rede).
    *   Humor sutil ou ironia que a IA não captou.

### 3. Falha de Sinal (Data Corruption)
*   **Gaming:** Comentários de bots inflando o `Engagement Score`.
*   **Spam:** Repetição de palavras-chave para enganar o `Trend Score`.

## Registro de Incidentes (Logs)
*(Espaço para registrar IDs de vídeos e motivos das falhas observadas durante o uso real)*
| Video ID | Predicted Score | Real Performance | Root Cause Analysis |
| :--- | :--- | :--- | :--- |
| | | | |
