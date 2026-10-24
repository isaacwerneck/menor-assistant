import unittest
from src.agent.cleaner import sanitize_assistant_reply

class TestThinkingCleaner(unittest.TestCase):
    def test_eai_menor_thinking_process(self):
        raw = """Thinking Process:

1. **Analyze the Request:**
   * User: "eai menor" (Portuguese for "hey [Name]").
   * My Role: Menor v2 (Isaac's AI assistant).
   * Directives: Short, natural, friendly, pt-BR (use slang like mano, suave, blz), respond to greetings in 1 sentence without technical topics. No internal thought blocks/tags.
   * User Profile: Isaac Werneck (Founder/Lead Dev), specific hardware stack mentioned previously but not"""
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
        raw = """Okay, let's tackle this user request. They're asking if I can make a website for them. First, I need to remember my role as Menor v2, the assistant for Isaac. The guidelines say to keep responses short, natural, friendly in Portuguese with some slang like "mano", "suave", etc. Also, if they don't ask for code or tools, just chat amiably. But here, they are asking about making a website, which is a technical request.

Wait, the user might not know that I can actually build websites. My capabilities include generating HTML/CSS/JS, but maybe they need more guidance. However, according to the guidelines, if Isaac doesn't ask for code or tools, just chat. But in this case, the user is asking directly about making a site. So I should check if they want me to write code. Since they didn't specify, maybe I should offer help but keep it friendly.

Wait, the third guideline says: "Se o Isaac não pedir código ou ferramentas, apenas converse com ele amigavelmente." But here, the user is asking if I can make a site. So I need to respond in a way that's helpful without being too technical"""
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

if __name__ == "__main__":
    unittest.main()
