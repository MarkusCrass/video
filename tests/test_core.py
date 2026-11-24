"""Unit + pipeline tests for the studio core (no network needed)."""

from __future__ import annotations

import os
import random
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_fixtures, video_size

FIX = make_fixtures()

from studio import config, editor, generator, music, presets, renderer, security, storage, textart, youtube  # noqa: E402
from studio.ffmpeg_tools import FFmpegError, detect_cut_points, probe  # noqa: E402


class TextArtTests(unittest.TestCase):
    def test_overlay_is_full_frame_png_with_text(self):
        out = textart.render_overlay(config.WORK_DIR / "t_overlay.png", top="Заголовок 🌙",
                                     bottom="Пиши ЛУНА в комментарии 👇", style="gold", size="L")
        from PIL import Image
        img = Image.open(out)
        self.assertEqual(img.size, (1080, 1920))
        self.assertEqual(img.mode, "RGBA")
        alpha = img.getchannel("A")
        self.assertGreater(alpha.getbbox()[3] - alpha.getbbox()[1], 100)  # has drawn boxes

    def test_emoji_dropped_without_emoji_font(self):
        if textart.EMOJI_AVAILABLE:
            self.skipTest("emoji font installed")
        self.assertEqual(textart.preview_text("Привет 🌙 мир 👇"), "Привет мир")
        self.assertTrue(textart.has_emoji("🌙"))
        self.assertFalse(textart.has_emoji("Текст"))

    def test_empty_texts_render_transparent_canvas(self):
        out = textart.render_overlay(config.WORK_DIR / "empty_overlay.png")
        from PIL import Image
        self.assertIsNone(Image.open(out).getchannel("A").getbbox())

    def test_wrapping_keeps_all_words(self):
        font = textart._font(64)
        lines = textart._wrap("один два три четыре пять шесть семь восемь девять десять", font, 500, 64)
        words = " ".join(seg[1] for line in lines for seg in line if seg[0] == "text").split()
        self.assertEqual(len(words), 10)
        self.assertGreater(len(lines), 1)

    def test_bad_style_rejected(self):
        with self.assertRaises(ValueError):
            textart.render_overlay(config.WORK_DIR / "bad.png", top="x", style="neon")


class ProbeAndSearchTests(unittest.TestCase):
    def test_probe_reads_duration_and_streams(self):
        info = probe(FIX["src169"])
        self.assertAlmostEqual(info.duration, 40.0, delta=0.2)
        self.assertTrue(info.has_audio)
        self.assertTrue(info.has_video)
        self.assertFalse(probe(FIX["src916"]).has_audio)

    def test_probe_missing_file(self):
        with self.assertRaises(FFmpegError):
            probe(config.WORK_DIR / "nope.mp4")

    def test_parse_search_output_skips_bad_lines_and_live(self):
        text = "\n".join([
            '{"id": "a1", "title": "Ok", "url": "https://www.youtube.com/watch?v=a1", "duration": 120}',
            "not json",
            '{"id": "a1", "title": "Duplicate", "duration": 120}',
            '{"id": "live", "title": "Live", "is_live": true}',
            '{"id": "b2", "title": "NoDuration", "duration": null}',
        ])
        found = youtube.parse_search_output(text)
        self.assertEqual([c.video_id for c in found], ["a1", "b2"])
        self.assertEqual(found[1].url, "https://www.youtube.com/watch?v=b2")

    def test_usable_filter_limits(self):
        long_video = youtube.Candidate("x", "t", "u", 16 * 60)
        short_video = youtube.Candidate("y", "t", "u", 5)
        unknown = youtube.Candidate("z", "t", "u", None)
        self.assertFalse(youtube.is_usable(long_video, 10))
        self.assertFalse(youtube.is_usable(short_video, 10))
        self.assertTrue(youtube.is_usable(unknown, 10))

    def test_search_empty_query(self):
        with self.assertRaises(youtube.YouTubeError):
            youtube.search("   ", 5)

    def test_cut_points_run(self):
        self.assertIsInstance(detect_cut_points(FIX["src169"], max_seconds=10), list)


class RendererTests(unittest.TestCase):
    def test_pick_segments_prefers_cut_points_and_spacing(self):
        rng = random.Random(1)
        starts = renderer.pick_segments(60, 4, 3.5, [10.0, 20.0, 30.0, 40.0, 50.0], rng)
        self.assertEqual(len(starts), 4)
        self.assertTrue(all(s in (10.0, 20.0, 30.0, 40.0, 50.0) for s in starts))
        self.assertEqual(starts, sorted(starts))

    def test_pick_segments_random_fallback_and_errors(self):
        starts = renderer.pick_segments(30, 3, 5, None, random.Random(2))
        self.assertEqual(len(starts), 3)
        self.assertTrue(all(3 <= s <= 25 for s in starts))
        with self.assertRaises(ValueError):
            renderer.pick_segments(4, 1, 5)

    def test_scene_length_math(self):
        self.assertAlmostEqual(renderer.scene_length(14, 4, "cut"), 3.5)
        self.assertAlmostEqual(renderer.scene_length(10, 1, "fade"), 10)
        self.assertAlmostEqual(
            renderer.scene_length(12, 3, "fade") * 3 - 2 * config.TRANSITION_SECONDS, 12, places=6)

    def test_clip_blur_crop_zoom_and_noaudio(self):
        blur = renderer.build_scene_clip(FIX["src169"], 2, 3, config.WORK_DIR / "t_blur.mp4",
                                         framing=config.FRAMING_BLUR)
        crop = renderer.build_scene_clip(FIX["src169"], 2, 3, config.WORK_DIR / "t_crop.mp4",
                                         framing=config.FRAMING_CROP, zoom=True, orig_volume=0.15)
        silent = renderer.build_scene_clip(FIX["src916"], 1, 3, config.WORK_DIR / "t_noaudio.mp4",
                                           framing=config.FRAMING_BLUR, has_audio=False)
        for clip in (blur, crop, silent):
            self.assertEqual(video_size(clip), (1080, 1920))
            self.assertAlmostEqual(probe(clip).duration, 3.0, delta=0.15)
        self.assertTrue(probe(silent).has_audio)  # silent track is generated

    def test_bad_framing(self):
        with self.assertRaises(ValueError):
            renderer.framing_filter("weird", "0:v", "x")

    def test_compose_cut_and_fade_with_all_layers(self):
        clip = config.WORK_DIR / "t_blur.mp4"
        overlay = config.WORK_DIR / "t_overlay.png"
        textart.render_overlay(overlay, top="Тест", bottom="CTA")
        cut = renderer.compose_final([clip, clip, clip], [3, 3, 3], config.WORK_DIR / "t_cut.mp4", total=9,
                                     overlay_png=overlay, music=FIX["music"], music_gain=0.15,
                                     music_offset=5, voice=FIX["voice"], voice_gain=1.0)
        self.assertEqual(video_size(cut), (1080, 1920))
        self.assertAlmostEqual(probe(cut).duration, 9.0, delta=0.15)
        fade = renderer.compose_final([clip, clip], [3.0, 3.0], config.WORK_DIR / "t_fade.mp4",
                                      total=5.6, transition=renderer.TRANSITION_FADE, soft_edges=True,
                                      music=FIX["music"], music_gain=0.5)
        self.assertAlmostEqual(probe(fade).duration, 5.6, delta=0.2)
        single = renderer.compose_final([clip], [3], config.WORK_DIR / "t_single.mp4", total=3,
                                        voice=FIX["voice_m4a"])
        self.assertEqual(video_size(single), (1080, 1920))

    def test_compose_validation(self):
        with self.assertRaises(ValueError):
            renderer.compose_final([], [], config.WORK_DIR / "x.mp4", total=3)
        with self.assertRaises(ValueError):
            renderer.compose_final([FIX["src169"]], [1, 2], config.WORK_DIR / "x.mp4", total=3)


class PresetAndMusicTests(unittest.TestCase):
    def test_presets_are_consistent(self):
        keys = {p.key for p in presets.PRESETS}
        self.assertEqual(keys, {"astro", "series", "games"})
        series = presets.preset_by_key("series")
        self.assertEqual(series.scenes, 4)
        self.assertAlmostEqual(series.duration / series.scenes, 3.5)
        games = presets.preset_by_key("games")
        self.assertEqual(games.music_volume, 100)
        self.assertEqual(games.orig_volume, 15)
        with self.assertRaises(KeyError):
            presets.preset_by_key("nope")

    def test_music_library_save_dedupe_resolve_delete(self):
        first = music.save_track("Мой трек 1.mp3", b"ID3fake")
        second = music.save_track("Мой трек 1.mp3", b"ID3other")
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())
        self.assertEqual(music.safe_filename("../../evil name.exe"), "evil name.mp3")
        self.assertNotIn("/", music.safe_filename("../../x/y.wav"))
        self.assertEqual(music.resolve_track(music.MUSIC_NONE), None)
        self.assertIsNotNone(music.resolve_track(music.MUSIC_RANDOM, random.Random(0)))
        self.assertEqual(music.resolve_track(first.name), first)
        self.assertTrue(music.delete_track(first.name))
        self.assertFalse(music.delete_track("../../etc/passwd"))

    def test_security(self):
        self.assertTrue(security.check_password("moon2026"))
        self.assertFalse(security.check_password("moon2027"))
        state: dict = {}
        for _ in range(security.MAX_ATTEMPTS):
            security.register_failure(state)
        self.assertGreater(security.lock_remaining(state), 0)


class StorageTests(unittest.TestCase):
    def test_cleanup_removes_only_old_temp_files(self):
        old = config.TMP_DIR / "sources" / "old.mp4"
        new = config.TMP_DIR / "sources" / "new.mp4"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"x" * 10)
        new.write_bytes(b"y" * 10)
        two_days = time.time() - 48 * 3600
        os.utime(old, (two_days, two_days))
        removed = storage.cleanup_old_temp()
        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_clear_temp_and_refuse_outside(self):
        stray = config.TMP_DIR / "work" / "stray.bin"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"z")
        self.assertGreaterEqual(storage.clear_temp(), 1)
        self.assertFalse(stray.exists())
        self.assertTrue(config.TMP_DIR.exists())
        with self.assertRaises(PermissionError):
            storage.remove_path(Path("/etc/hostname"))
        info = storage.disk_info()
        self.assertGreater(info.total, 0)


class GeneratorPipelineTests(unittest.TestCase):
    """Full batch run with YouTube search/download replaced by local fixtures."""

    def _candidates(self):
        return [
            youtube.Candidate("long1", "Очень длинное видео", "https://youtu.be/long1", 3000.0),
            youtube.Candidate("bad1", "Недоступное видео", "https://youtu.be/bad1", 120.0),
            youtube.Candidate("ok1", "Хороший ролик 1", "https://youtu.be/ok1", 40.0),
            youtube.Candidate("ok2", "Хороший ролик 2", "https://youtu.be/ok2", None),
            youtube.Candidate("ok3", "Хороший ролик 3", "https://youtu.be/ok3", 40.0),
        ]

    def _fake_download(self, url, target_base, ffmpeg_location):
        if "bad1" in url:
            raise youtube.YouTubeError("Video unavailable")
        target = Path(str(target_base) + ".mp4")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FIX["src169"].read_bytes())
        return target

    def test_batch_skips_bad_and_long_sources_and_builds_reels(self):
        logs: list[str] = []
        progress_calls: list[str] = []
        opts = generator.BatchOptions(query="test", count=2, duration=8, scenes=1,
                                      framing=config.FRAMING_BLUR, music_choice=music.MUSIC_NONE,
                                      top_text="Тестовый заголовок", bottom_text="Пиши ЛУНА")
        with mock.patch.object(youtube, "search", return_value=self._candidates()), \
             mock.patch.object(youtube, "download", side_effect=self._fake_download):
            result = generator.generate_batch(opts, progress=lambda f, t: progress_calls.append(t),
                                              log_fn=logs.append, rng=random.Random(3))
        self.assertEqual(len(result.items), 2)
        for item in result.items:
            self.assertTrue(item.path.exists())
            self.assertEqual(video_size(item.path), (1080, 1920))
            self.assertAlmostEqual(probe(item.path).duration, 8.0, delta=0.2)
        self.assertTrue(any("Пропуск" in m and "Недоступ" in m or "Video unavailable" in m for m in logs))
        self.assertTrue(any("слишком длинных" in n for n in result.notes))
        self.assertTrue(any(t.startswith("Скачивание") for t in progress_calls))
        self.assertTrue(any(t.startswith("Монтаж") for t in progress_calls))
        self.assertEqual(progress_calls[-1], "Готово")

    def test_series_preset_four_scenes_with_music_and_fade(self):
        preset = presets.preset_by_key("series")
        opts = generator.BatchOptions(
            query=preset.query, count=1, duration=preset.duration, scenes=preset.scenes,
            transition=preset.transition, framing=preset.framing, zoom=preset.zoom,
            soft_edges=preset.soft_edges, music_choice=music.MUSIC_RANDOM,
            music_volume=preset.music_volume / 100, orig_volume=preset.orig_volume / 100)
        cands = [youtube.Candidate("ok1", "Серия", "https://youtu.be/ok1", 40.0)]
        with mock.patch.object(youtube, "search", return_value=cands), \
             mock.patch.object(youtube, "download", side_effect=self._fake_download), \
             mock.patch.object(music, "list_tracks", return_value=[FIX["music"]]):
            result = generator.generate_batch(opts, rng=random.Random(9))
        self.assertEqual(len(result.items), 1)
        out = result.items[0].path
        self.assertAlmostEqual(probe(out).duration, 14.0, delta=0.25)
        self.assertEqual(result.items[0].music_name, FIX["music"].name)

    def test_zoom_and_fade_scene_preset(self):
        preset = presets.preset_by_key("astro")
        opts = generator.BatchOptions(query=preset.query, count=1, duration=preset.duration,
                                      scenes=preset.scenes, transition=preset.transition,
                                      framing=preset.framing, zoom=preset.zoom,
                                      soft_edges=preset.soft_edges, music_choice=music.MUSIC_NONE)
        cands = [youtube.Candidate("ok1", "Night", "https://youtu.be/ok1", 40.0)]
        with mock.patch.object(youtube, "search", return_value=cands), \
             mock.patch.object(youtube, "download", side_effect=self._fake_download):
            result = generator.generate_batch(opts, rng=random.Random(4))
        self.assertEqual(video_size(result.items[0].path), (1080, 1920))

    def test_no_results_raises_user_message(self):
        opts = generator.BatchOptions(query="nothing", count=1, duration=10)
        with mock.patch.object(youtube, "search", return_value=[]):
            with self.assertRaises(generator.GenerationError) as ctx:
                generator.generate_batch(opts)
        self.assertIn("не найдено", str(ctx.exception))

    def test_all_downloads_fail(self):
        opts = generator.BatchOptions(query="x", count=2, duration=10)
        cands = [youtube.Candidate("bad1", "t", "https://youtu.be/bad1", 60.0)]
        with mock.patch.object(youtube, "search", return_value=cands), \
             mock.patch.object(youtube, "download", side_effect=youtube.YouTubeError("blocked")):
            with self.assertRaises(generator.GenerationError):
                generator.generate_batch(opts)

    def test_validation_messages(self):
        bad = [
            generator.BatchOptions(query="", count=1, duration=10),
            generator.BatchOptions(query="x", count=16, duration=10),
            generator.BatchOptions(query="x", count=1, duration=30),
            generator.BatchOptions(query="x", count=1, duration=7, scenes=4),
        ]
        for opts in bad:
            with self.assertRaises(generator.GenerationError):
                opts.validate()


class EditorTests(unittest.TestCase):
    def test_trim_voice_music_text(self):
        opts = editor.EditOptions(
            start=2.0, end=9.0, framing=config.FRAMING_CROP, orig_volume=0.0,
            music_path=FIX["music"], duck_volume=0.13, voice_path=FIX["voice"],
            top_text="Заголовок", center_text="По центру", bottom_text="Подписывайтесь",
            text_style="black", text_size="L", soft_edges=True)
        out = editor.render_edit(FIX["src169"], opts, rng=random.Random(5))
        self.assertEqual(video_size(out), (1080, 1920))
        self.assertAlmostEqual(probe(out).duration, 7.0, delta=0.2)
        self.assertTrue(out.parent == config.OUTPUT_DIR)

    def test_no_audio_source_and_no_text(self):
        opts = editor.EditOptions(start=0, end=5, music_path=None, music_volume=0.0)
        out = editor.render_edit(FIX["src916"], opts)
        self.assertAlmostEqual(probe(out).duration, 5.0, delta=0.2)

    def test_too_short_selection(self):
        with self.assertRaises(editor.EditError):
            editor.render_edit(FIX["src169"], editor.EditOptions(start=3, end=3.5))

    def test_missing_file(self):
        with self.assertRaises(editor.EditError):
            editor.render_edit(config.WORK_DIR / "missing.mp4", editor.EditOptions())


if __name__ == "__main__":
    unittest.main(verbosity=2)
