# Requisitos de Hardware & Escolha de Modelo

## Hardware Confirmado
- **Processador**: Intel Core i7-1185G7 (4 núcleos / 8 threads com suporte a instruções AVX-512).
- **Memória RAM**: 32 GB DDR4.
- **Gráficos**: Intel Iris Xe (integrada).

## Modelos Hugging Face Recomendados (Inferência em CPU com AVX-512)

Com 32 GB de RAM e AVX-512, é possível rodar modelos de até 14B com ótima velocidade em CPU:

| Modelo | Parâmetros | Quantização | Uso de RAM | Foco |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 Coder** | 7B | GGUF Q4_K_M | ~5.5 GB | Excelente para código e ferramentas |
| **Qwen 2.5 Coder** | 14B | GGUF Q4_K_M | ~9.5 GB | Raciocínio profundo, auto-melhoria e código |
| **Llama 3.1** | 8B | GGUF Q4_K_M | ~6.0 GB | Conversação e planejamento geral |
| **Phi-4** | 14B | GGUF Q4_K_M | ~9.8 GB | Lógica e matemática |

> **Vantagem dos 32 GB**: Permite rodar o modelo de 14B, o Whisper (áudio) e o TTS simultaneamente, restando mais de 15 GB de folga.
