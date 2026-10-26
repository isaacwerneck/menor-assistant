import struct
import unittest

from src.audio.neural_audio import NeuralAudioEngine


class TestNeuralAudioV2(unittest.TestCase):
    def setUp(self):
        self.audio_engine = NeuralAudioEngine()

    def test_detect_speech_activity_silence_vs_sound(self):
        # 1. Silêncio puro (zeros)
        silence = bytes(640)
        self.assertFalse(self.audio_engine.detect_speech_activity(silence))

        # 2. Sinal com energia simulada
        signal = b"".join(struct.pack("<h", 8000 if i % 2 == 0 else -8000) for i in range(320))
        self.assertTrue(self.audio_engine.detect_speech_activity(signal))

    def test_detect_wake_word_in_text(self):
        self.assertTrue(self.audio_engine.detect_wake_word("E aí menor, como você tá?"))
        self.assertTrue(self.audio_engine.detect_wake_word("menor cria um site"))
        self.assertTrue(self.audio_engine.detect_wake_word("Menor, bom dia!"))
        self.assertFalse(self.audio_engine.detect_wake_word("hoje a temperatura está amena"))

    def test_synthesize_to_buffer_ram(self):
        # Sintetiza diretamente em buffer PCM em RAM sem tocar no disco
        pcm_bytes = self.audio_engine.synthesize_to_buffer("Bom dia Isaac, pronto para programar?")
        self.assertTrue(len(pcm_bytes) > 0)
        self.assertEqual(len(pcm_bytes) % 2, 0)  # Alinhamento 16-bit


if __name__ == "__main__":
    unittest.main()
