# Discovery Engine: O Coração do Sistema

## Objetivo
O `Discovery Engine` é o orquestrador que decide quais conteúdos merecem a atenção do pipeline. Ele é a implementação prática da visão estratégica de "previsão de atenção".

## Funcionamento Interno

### 1. Triagem (The Radar)
Monitora continuamente nichos e canais. Não é uma busca passiva; é uma varredura ativa por anomalias estatísticas de crescimento.

### 2. Funil de Decisão
1.  **Fase 1 (Metadados):** Filtra por VPH e Recência.
2.  **Fase 2 (Sinais):** Filtra por engajamento e Relative VPH.
3.  **Fase 3 (Conteúdo):** Filtra por densidade de transcrição.

## Lógica de Priorização
Vídeos com `vph_acceleration` positiva e `relative_vph > 3.0` ganham prioridade máxima na fila de processamento, passando na frente de vídeos com VPH absoluto maior, mas estagnados.

## Configurações Estratégicas
*   **Cooldown:** Tempo de espera entre scans do mesmo vídeo (evita gastos de API).
*   **Viral Threshold:** Valor mínimo de score para o vídeo ser considerado "Candidato a Corte".
