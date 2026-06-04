# Whisper Fallback: Estratégia Híbrida

## O Problema
Muitos criadores desativam legendas automáticas ou o YouTube falha em gerá-las para vídeos muito longos. Isso quebrava o pipeline de análise semântica.

## A Solução: Strategic Audio Sampling
Em vez de baixar o vídeo completo (lento/pesado) ou transcrever tudo (caro em CPU), implementamos uma extração cirúrgica:

### O Pipeline de Fallback
1.  **Detecção de Falha:** `YouTubeTranscriptApi` retorna erro.
2.  **Validação de Valor:** Só prossegue se o vídeo for "quente" (VPH/Relative VPH altos).
3.  **Extração Cirúrgica:** `yt-dlp` + `ffmpeg` baixam apenas pequenos blocos de áudio (ex: 5 blocos de 60s em pontos estratégicos).
4.  **Inferência Local:** `faster-whisper` (modelo `base`) transcreve esses blocos.
5.  **Reconstrução:** Os blocos são tratados como uma amostra estatística do vídeo todo.

## Custo vs Precisão
*   **Modelo Whisper:** `base` (Velocidade > Precisão). Para descoberta, não precisamos de perfeição gramatical, apenas detecção de palavras-chave e ganchos.
*   **Economia de Banda:** ~95% de redução comparado ao download do vídeo completo.
*   **Economia de Tempo:** Processamento de um podcast de 3h em menos de 2 minutos.
