# Requisitos de Hardware & Escolha de Modelo

> **Medição real de 20/10/2026:** [inventário e benchmark CPU/GPU](handoff/02_HARDWARE_E_LATENCIA.md).
> i7-1185G7 (8 threads), 31,06 GiB RAM, 23,87 GiB disponíveis, Iris Xe
> reconhecida, Ollama 0.40.6, `qwen2.5-coder:7b` com 0 GiB de VRAM
> reportada/100% CPU. Três probes concluídos: **10,24 tokens/s** de mediana,
> **4,791 s** por resposta curta. `vulkaninfo` não estava instalado na
> medição; aceleração GPU **não validada**. As estimativas de RAM/velocidade
> de modelos abaixo não são benchmarks deste equipamento.

## Hardware Confirmado
- **Processador**: Intel Core i7-1185G7 (4 núcleos / 8 threads com suporte a instruções AVX-512).
- **Memória RAM**: 32 GB DDR4.
- **Gráficos**: Intel Iris Xe (integrada).

## Modelos Hugging Face Recomendados (Inferência em CPU com AVX-512)

Os candidatos abaixo são referências de planejamento, não benchmarks deste notebook.
Caber na RAM não comprova velocidade, qualidade ou capacidade de usar ferramentas.
Na avaliação remota de 19/10/2026, o servidor reportou somente
`qwen2.5-coder:7b`; pedidos curtos também apresentaram espera perceptível.
Antes de trocar o modelo, comparar inferência direta e planejador em `/lab/view`
com os mesmos casos, versão e carga. Não aumentar parâmetros como tentativa
presumida de resolver latência. Valores de RAM abaixo são estimativas antigas:

| Modelo | Parâmetros | Quantização | Uso de RAM | Foco |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 Coder** | 7B | GGUF Q4_K_M | ~5.5 GB | Excelente para código e ferramentas |
| **Qwen 2.5 Coder** | 14B | GGUF Q4_K_M | ~9.5 GB | Raciocínio profundo, auto-melhoria e código |
| **Llama 3.1** | 8B | GGUF Q4_K_M | ~6.0 GB | Conversação e planejamento geral |
| **Phi-4** | 14B | GGUF Q4_K_M | ~9.8 GB | Lógica e matemática |

> A memória disponível depende de quantização, janela de contexto, caches e serviços
> concorrentes. A execução simultânea de 14B, Whisper e TTS e a folga de 15 GB
> não foram medidas; não são requisitos validados ou promessa de desempenho.
