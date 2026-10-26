import unittest
from src.agent.cleaner import sanitize_assistant_reply


class TestThinkingCleaner(unittest.TestCase):
    def test_eai_menor_thinking_process(self):
        raw = """Thinking Process:

1. **Analyze the Request:**
   * User: "eai menor" (Portuguese for "hey [Name]").
   * My Role: Menor v2 (Isaac's AI assistant).
   * Directives: Short, natural, friendly, pt-BR (use slang like mano, suave, blz).
   * User Profile: Isaac Werneck (Founder/Lead Dev)"""
        result = sanitize_assistant_reply(raw, "eai menor")
        self.assertNotIn("Thinking Process", result)
        self.assertIn("Isaac", result)

    def test_tudo_bem_thinking_process(self):
        raw = """Thinking Process:

1. **Analyze the Request:**
   * Input: "tudo bem?" (Portuguese for "everything okay?").
   * Role: Menor v2 (Isaac's AI assistant).
   * Directives:
     * Short, natural, friendly response in pt-BR.
     * Use light slang (mano, suave, blz).
     * If greeting ("e ai", "oi", "fala"), respond in 1 welcoming sentence without tech topics.
     * This"""
        result = sanitize_assistant_reply(raw, "tudo bem?")
        self.assertNotIn("Thinking Process", result)
        self.assertEqual(result, "Tudo suave por aqui, mano! E com você, como estão as coisas?")

    def test_consegue_fazer_um_site_english_scratchpad(self):
        raw = (
            "Okay, let's tackle this user request. They're asking if I can make a website for them. "
            "First, I need to remember my role as Menor v2, the assistant for Isaac.\n\n"
            "Wait, the user might not know that I can actually build websites. My capabilities include "
            "generating HTML/CSS/JS.\n\n"
            "Wait, the third guideline says: 'Se o Isaac não pedir código, apenas converse amigavelmente.'"
        )
        result = sanitize_assistant_reply(raw, "consegue fazer um site pra mim?")
        self.assertNotIn("Okay, let's", result)
        self.assertNotIn("user request", result)
        self.assertIn("Consigo sim", result)
        self.assertIn("site", result)

    def test_thinking_with_real_answer(self):
        raw = """Thinking Process:
* user wants hello

Response:
Fala meu parceiro, tudo na paz?"""
        result = sanitize_assistant_reply(raw, "fala")
        self.assertEqual(result, "Fala meu parceiro, tudo na paz?")

    def test_think_tags_stripping(self):
        raw = "<think>Analyzing user message... User says hello.</think>E aí mano, beleza pura?"
        result = sanitize_assistant_reply(raw, "oi")
        self.assertEqual(result, "E aí mano, beleza pura?")

    def test_unclosed_think_tag(self):
        raw = "<think>Thinking about what to say without closing tag..."
        result = sanitize_assistant_reply(raw, "eai")
        self.assertNotIn("<think>", result)
        self.assertIn("Isaac", result)

    def test_app_request_scratchpad(self):
        raw = "Okay, let's tackle this request to build an application for Isaac..."
        result = sanitize_assistant_reply(raw, "faz um aplicativo pra mim")
        self.assertNotIn("Okay, let's", result)
        self.assertIn("Consigo sim", result)

    def test_clean_text_unchanged(self):
        raw = "Com certeza! Vamos refatorar o backend agora."
        result = sanitize_assistant_reply(raw, "vamos codar")
        self.assertEqual(result, "Com certeza! Vamos refatorar o backend agora.")

    def test_empty_reply_fallback(self):
        result = sanitize_assistant_reply("", "salve")
        self.assertIn("Isaac", result)

    def test_strip_simulated_bash_tool_commands(self):
        raw = (
            "Olá Isaac! Vou checar o que a gente fez com o site de áudio.\n\n"
            "```bash\n"
            "terminal_run ls -la ~/estudos/ 2>/dev/null || terminal_run ls -la ~/ancora_de_estudos/ 2>/dev/null\n"
            "```"
        )
        result = sanitize_assistant_reply(raw, "mostra o site de audio")
        self.assertNotIn("terminal_run", result)
        self.assertNotIn("ancora_de_estudos", result)
        self.assertIn("site de áudio", result)

    def test_looking_at_study_anchors_scratchpad(self):
        raw = """Looking at the current STUDY_ANCHORS in core memory:
1. Inteligência Artificial e Agentes (RAG, Agentes Autônomos, Embeddings, MoE, Fine-tuning)
2. Engenharia de Software e Backend (Python assíncrono, FastAPI, Concorrência, SQLite, Arquitetura)
3. Frontend e JavaScript (EventLoop, WebSockets, Web Workers, Web Audio API, DOM Performance)
4. Design e UI/UX (Design Systems, Micro-interações, Teoria das Cores, Acessibilidade)

Given their work profile (websites, 2D games, music apps, systems), I should suggest topics that complement these existing anchors and align with what would be valuable for a developer building diverse software products.

I need to respond directly in Portuguese, as per the rules - no tool simulation, just direct response. Since they're asking about study topics, this is a consultation question, not a request to create files or execute tools. I should provide thoughtful recommendations based on their profile and existing anchors."""
        result = sanitize_assistant_reply(
            raw,
            "eu sou um desenvolvedor de software. me sugira topicos interessantes para colocar na ancora de estudos"
        )
        self.assertNotIn("Looking at the current", result)
        self.assertNotIn("Given their work profile", result)
        self.assertNotIn("I need to respond directly", result)
        self.assertIn("Jogos 2D", result)
        self.assertIn("Áudio", result)

    def test_okay_user_wants_portuguese_scratchpad(self):
        raw = (
            "Okay, the user wants me to write in Portuguese. Let me check the previous conversation history. "
            "The user is asking for study topics that would be interesting given they're a software developer who builds websites.\n\n"
            "Com certeza, Isaac! Aqui estão os tópicos ideais para o seu fluxo de desenvolvimento."
        )
        result = sanitize_assistant_reply(raw, "escreve em portugues")
        self.assertNotIn("Okay, the user wants me to write in Portuguese", result)
        self.assertIn("Com certeza, Isaac!", result)

    def test_portuguese_scratchpad_filtering(self):
        raw = (
            "O usuário está perguntando sobre a configuração de máquinas e hardware. "
            "Isso é uma pergunta direta que pode ser respondida com base nas informações do perfil do usuário "
            "(USER_PROFILE) na Core Memory, que já contém os detalhes do hardware do Isaac."
        )
        result = sanitize_assistant_reply(raw, "qual é a nossa configuração de máquinas e hardware?")
        self.assertNotIn("O usuário está perguntando", result)
        self.assertNotIn("Isso é uma pergunta direta", result)
        self.assertIn("GTX 1650", result)
        self.assertIn("Servidor Ubuntu", result)


if __name__ == "__main__":
    unittest.main()
