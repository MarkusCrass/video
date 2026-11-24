"""UI smoke tests with Streamlit's AppTest (runs the real app.py script)."""

from __future__ import annotations

import unittest
from pathlib import Path

import helpers  # noqa: F401  (sets up isolated data dir)
from helpers import make_fixtures, video_size

make_fixtures()

from streamlit.testing.v1 import AppTest  # noqa: E402

from studio import config, music  # noqa: E402

APP = str(Path(helpers.ROOT) / "app.py")


def _login(at: AppTest) -> AppTest:
    at.text_input[0].set_value("moon2026")
    at.button[0].click().run()
    return at


class AppTests(unittest.TestCase):
    def test_login_gate_and_wrong_password(self):
        at = AppTest.from_file(APP, default_timeout=120).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs), 0, "main UI must be hidden before login")
        at.text_input[0].set_value("wrong-password")
        at.button[0].click().run()
        self.assertTrue(any("Неверный пароль" in e.value for e in at.error))
        self.assertEqual(len(at.tabs), 0)

    def test_login_shows_three_tabs_and_sidebar(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        self.assertFalse(at.exception)
        labels = [t.label for t in at.tabs]
        self.assertEqual(len(labels), 3)
        self.assertIn("Авто-генератор", labels[0])
        self.assertIn("Редактор видео", labels[1])
        self.assertIn("Библиотека треков", labels[2])
        self.assertTrue(any("Очистить временные файлы" in b.label for b in at.button))

    def test_presets_fill_controls(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        series_btn = next(b for b in at.button if b.key == "preset_series")
        series_btn.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["g_scenes"], 4)
        self.assertEqual(at.session_state["g_duration"], 14)
        self.assertEqual(at.session_state["g_music_vol"], 15)
        self.assertEqual(at.session_state["g_framing"], config.FRAMING_BLUR)
        games_btn = next(b for b in at.button if b.key == "preset_games")
        games_btn.click().run()
        self.assertEqual(at.session_state["g_music_vol"], 100)
        self.assertEqual(at.session_state["g_orig_vol"], 15)
        astro_btn = next(b for b in at.button if b.key == "preset_astro")
        astro_btn.click().run()
        self.assertTrue(at.session_state["g_zoom"])
        self.assertEqual(at.session_state["g_framing"], config.FRAMING_CROP)
        self.assertFalse(at.exception)

    def test_generate_button_shows_error_without_network(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        at.text_input(key="g_query").set_value("")
        next(b for b in at.button if "Сгенерировать" in b.label).click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("поисковый запрос" in e.value.lower() for e in at.error))

    def test_editor_lists_outputs_and_library_empty_state(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        self.assertFalse(at.exception)
        self.assertTrue(len(at.info) >= 1)  # no outputs yet -> hint

    def test_library_lists_tracks_with_delete(self):
        music.save_track("ui_test_track.mp3", FIX_MP3.read_bytes())
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        self.assertFalse(at.exception)
        self.assertTrue(any(b.key == "del_ui_test_track.mp3" for b in at.button))
        next(b for b in at.button if b.key == "del_ui_test_track.mp3").click().run()
        self.assertFalse((config.MUSIC_DIR / "ui_test_track.mp3").exists())
        self.assertFalse(at.exception)

    def test_logout_returns_to_login(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        next(b for b in at.button if "Выйти" in b.label).click().run()
        self.assertEqual(len(at.tabs), 0)

    def test_clear_temp_button(self):
        at = _login(AppTest.from_file(APP, default_timeout=120).run())
        next(b for b in at.button if "Очистить временные" in b.label).click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Удалено временных файлов" in s.value for s in at.success))


FIX_MP3 = make_fixtures()["music"]


class FullFlowTests(unittest.TestCase):
    """Generate in the UI (YouTube mocked) -> open in editor -> render final reel."""

    def test_generate_open_in_editor_and_render(self):
        from unittest import mock

        from studio import youtube

        fixtures = make_fixtures()

        def fake_download(url, target_base, ffmpeg_location):
            target = Path(str(target_base) + ".mp4")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(fixtures["src169"].read_bytes())
            return target

        cands = [youtube.Candidate("ui1", "UI source", "https://youtu.be/ui1", 40.0)]
        at = _login(AppTest.from_file(APP, default_timeout=300).run())
        next(b for b in at.button if b.key == "preset_games").click().run()
        with mock.patch.object(youtube, "search", return_value=cands), \
             mock.patch.object(youtube, "download", side_effect=fake_download):
            next(b for b in at.button if "Сгенерировать" in b.label).click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertEqual(len(at.session_state["g_results"]), 1)
        name = at.session_state["g_results"][0]["name"]
        self.assertTrue((config.OUTPUT_DIR / name).is_file())

        next(b for b in at.button if b.key == f"ed_{name}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["ed_pick"], name)
        self.assertTrue(any("открыт в редакторе" in s.value for s in at.success))

        at.text_input(key="ed_top").set_value("Тест UI")
        at.text_input(key="ed_bottom").set_value("CTA")
        next(b for b in at.button if "Собрать финальный" in b.label).click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        result = at.session_state["ed_result"]
        self.assertIsNotNone(result)
        self.assertTrue(Path(result).is_file())
        self.assertEqual(video_size(Path(result)), (1080, 1920))

if __name__ == "__main__":
    unittest.main(verbosity=2)
