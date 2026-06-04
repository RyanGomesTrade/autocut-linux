# Integridade de Sinais (Signal Integrity)

## Anti-Gaming Protection
Sistemas de atenção são alvos fáceis para manipulação. Precisamos proteger o `Viral Score` de dados artificiais.

## Defesas Implementadas / Planejadas

### 1. Detecção de Anomalias de Comentários
*   **Sinal:** Milhares de comentários em poucos segundos com frases repetitivas.
*   **Defesa:** `Comment Diversity Score`. Se o vocabulário for muito pobre, o peso do engajamento cai.

### 2. Verificação de Burst de Views
*   **Sinal:** `VPH` explode sem correspondência em `Comment Velocity`.
*   **Defesa:** `Social Consistency Check`. Views sem comentários ou likes proporcionais são sinalizadas como suspeitas (bots).

### 3. Confidence Score (O Filtro de Incerteza)
Calculamos quão "seguro" o sistema está sobre aquele score.
*   **Fatores de Redução:** 
    *   Transcrição parcial (fallback).
    *   Baixa quantidade de comentários históricos no canal.
    *   API do YouTube retornando dados inconsistentes.

## Regra de Ouro
**Score alto com Confiança baixa = Investigação Manual.**
**Score médio com Confiança alta = Aposta Segura.**
