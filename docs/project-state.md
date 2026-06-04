# Estado Atual do Projeto

## Resumo Técnico
O sistema está em transição de um script de automação simples para um motor de descoberta viral estruturado. A fundação de dados (SQLite) e o pipeline de análise (Fases 1, 2 e 2.1) estão operacionais.

## Status das Fases
*   **Discovery Engine:** 90% (Faltando apenas ajuste fino de thresholds).
*   **Transcription Fallback:** 100% (Implementado com amostragem estratégica).
*   **Scoring Logic:** 80% (Heurísticas implementadas, aguardando validação de dados).
*   **UI/Interface:** 70% (Visualização básica funcionando, integração com novos scores pendente).

## Decisões Críticas Recentes
*   **Uso de Strategic Sampling:** Reduziu o tempo de análise de podcasts de 2h de ~15min para ~2min.
*   **Database-First:** Todas as análises agora passam pelo banco, permitindo cache e observabilidade.
*   **Relative Metrics:** Mudança de foco de números absolutos para performance relativa ao canal.

## Próximos Passos Imediatos
1.  Validar o cálculo de aceleração com dados reais de múltiplos scans.
2.  Refinar o sistema de observabilidade para gerar relatórios de "Por que este vídeo foi escolhido?".
