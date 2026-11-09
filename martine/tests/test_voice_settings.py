import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from martine.voice.config import ConfigError, VoiceConfigPaths, load_voice_config
from martine.voice.stt import FasterWhisperTranscriber


class VoiceSettingsTests(unittest.TestCase):
    def config(self, extra='', core='language=en\n'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'voice').write_text(extra)
            (root / 'core').write_text(core)
            (root / 'murmur').write_text('serverpassword=test-only\n')
            return load_voice_config(VoiceConfigPaths(root / 'voice', root / 'core', root / 'murmur', root / 'state'))

    def test_language_overrides_ui_language(self):
        cfg = self.config('voice_language=de-DE\nvoice_mode=accurate\n')
        self.assertEqual((cfg.language, cfg.model, cfg.voice_mode), ('de', 'large-v3', 'accurate'))

    def test_old_configuration_preserves_model_and_language(self):
        cfg = self.config('model=large-v3\n')
        self.assertEqual((cfg.language, cfg.model, cfg.voice_mode), ('en', 'large-v3', 'accurate'))

    def test_profiles_and_language_reach_transcriber(self):
        for mode, language, model, beam in [('fast', 'sv', 'small', 1), ('accurate', 'auto', 'large-v3', 5)]:
            with self.subTest(mode=mode):
                cfg = self.config(f'voice_mode={mode}\nvoice_language={language}\n')
                captured = {}
                def transcribe(path, **kwargs):
                    captured.update(kwargs)
                    return iter([SimpleNamespace(text=' Test speech ')]), SimpleNamespace(language='sv')
                engine = FasterWhisperTranscriber(cfg)
                engine._model = SimpleNamespace(transcribe=transcribe)
                engine._load_initial_prompt = lambda: None
                text, detected = engine._transcribe_wav(Path('test.wav'))
                self.assertEqual(cfg.model, model)
                self.assertEqual(captured['beam_size'], beam)
                self.assertEqual(captured['language'], None if language == 'auto' else language)
                self.assertEqual((text, detected), ('Test speech', 'sv'))

    def test_non_swedish_and_auto_do_not_use_swedish_prompt(self):
        for language in ['en', 'de', 'auto']:
            engine = FasterWhisperTranscriber(self.config(f'voice_language={language}\n'))
            self.assertIsNone(engine._load_initial_prompt())

    def test_invalid_settings_fail_at_load(self):
        for extra in ['voice_mode=typo', 'voice_language=unknown-language']:
            with self.subTest(extra=extra), self.assertRaises(ConfigError):
                self.config(extra)


if __name__ == '__main__':
    unittest.main()
