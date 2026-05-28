# Ciclo de Aprendizado (Learning Loop)

## O Nascimento do Modelo Supervisionado
O objetivo final é que o sistema aprenda com seus próprios acertos e erros.

## O Fluxo do Loop
1.  **Predição:** Sistema gera `Viral Score` e recomenda cortes.
2.  **Ação:** Usuário posta os cortes nas redes (TikTok/YouTube/Instagram).
3.  **Coleta:** Após 24h/7d, o sistema lê os dados reais de performance.
4.  **Correlação:** O sistema compara o `Predicted Score` com o `Actual Performance`.
5.  **Ajuste:** Calibragem automática dos pesos das heurísticas.

## Tabela: `generated_clips` (Estatísticas Reais)
Esta tabela no SQLite é a base para o treinamento de ML futuro.
*   `clip_id`, `source_video_id`, `predicted_score`.
*   `views_24h`, `retention_rate`, `shares_count`.
*   `performance_delta`: Diferença entre o previsto e o real.

## Metas de Evolução
*   **Mês 1:** Coleta de dados e análise manual de correlação.
*   **Mês 3:** Ajuste dinâmico de pesos baseado em nichos específicos.
*   **Mês 6:** Primeira rede neural treinada no dataset proprietário de clips.
