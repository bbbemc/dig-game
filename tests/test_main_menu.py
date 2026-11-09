import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from audio import sounds
from config import SCREEN_H, SCREEN_W
from menu_scene import MenuEnvironment, ParallaxCamera, VOID_COLOR
from ui import GameUI, MENU_OPTIONS, SETTINGS_ITEMS


class MainMenuSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))

    def setUp(self):
        self.surface = pygame.Surface((SCREEN_W, SCREEN_H))
        self.ui = GameUI()

    def test_main_menu_has_only_play_settings_exit_and_no_continue(self):
        self.assertEqual(MENU_OPTIONS, ("PLAY", "SETTINGS", "EXIT"))
        self.assertEqual(self.ui.menu_options, ("PLAY", "SETTINGS", "EXIT"))
        self.assertNotIn("CONTINUE", self.ui.menu_options)

        # Advance past intro and draw
        for _ in range(180):
            self.ui.update(1 / 60, None)
        self.ui.draw_menu(self.surface, (0, 0))
        labels = [label for _, label in self.ui.buttons]
        self.assertEqual(labels, ["PLAY", "SETTINGS", "EXIT"])
        self.assertNotIn("CONTINUE", labels)

    def test_cinematic_intro_progression_starts_dark_and_reveals_in_order(self):
        # 1. At t = 0.0s, screen is completely dark
        p0 = self.ui.intro_progress(0.0)
        self.assertEqual(p0["bg_alpha"], 0.0)
        self.assertEqual(p0["light_alpha"], 0.0)
        self.assertEqual(p0["particle_alpha"], 0.0)
        self.assertEqual(p0["actor_alpha"], 0.0)
        self.assertEqual(p0["title_alpha"], 0.0)
        self.assertEqual(p0["option_alphas"], [0.0, 0.0, 0.0])

        self.ui.draw_menu(self.surface, (480, 320))
        self.assertEqual(self.surface.get_at((720, 320))[:3], VOID_COLOR[:3])

        # 2. At t = 0.6s, background and ambient light are fading in before title/options
        p_early = self.ui.intro_progress(0.6)
        self.assertGreater(p_early["bg_alpha"], 0.2)
        self.assertGreater(p_early["light_alpha"], 0.0)
        self.assertEqual(p_early["title_alpha"], 0.0)
        self.assertEqual(p_early["option_alphas"], [0.0, 0.0, 0.0])

        # 3. At t = 1.5s, particles and miner are visible and title is scaling up
        p_mid = self.ui.intro_progress(1.5)
        self.assertGreater(p_mid["particle_alpha"], 0.5)
        self.assertGreater(p_mid["actor_alpha"], 0.5)
        self.assertGreater(p_mid["title_alpha"], 0.2)
        self.assertGreater(p_mid["title_scale"], 0.88)
        self.assertEqual(p_mid["option_alphas"], [0.0, 0.0, 0.0])

        # 4. At t = 2.05s, options appear one by one in staggered order (PLAY > SETTINGS > EXIT)
        p_stagger = self.ui.intro_progress(2.05)
        a_play, a_settings, a_exit = p_stagger["option_alphas"]
        self.assertGreater(a_play, a_settings)
        self.assertGreater(a_settings, a_exit)
        self.assertGreater(a_exit, 0.0)

        # 5. By t = 2.6s, intro is complete
        p_done = self.ui.intro_progress(2.6)
        self.assertTrue(p_done["complete"])
        self.assertAlmostEqual(p_done["title_alpha"], 1.0, places=3)
        self.assertAlmostEqual(p_done["title_scale"], 1.0, places=2)
        self.assertEqual(p_done["option_alphas"], [1.0, 1.0, 1.0])

    def test_six_layer_parallax_depths_and_mouse_interpolation(self):
        env = self.ui.menu_env
        depths = [env.LAYER_DEPTHS[i] for i in range(1, 7)]
        self.assertEqual(len(depths), 6)
        # Distant layers move slower than foreground layers
        for earlier, later in zip(depths, depths[1:]):
            self.assertLess(earlier, later)

        cam = ParallaxCamera()
        # Move mouse to right/bottom edge and verify smooth interpolation (not instant snap)
        cam.update(1 / 60, (SCREEN_W, SCREEN_H))
        self.assertGreater(cam.smooth_x, 0.0)
        self.assertLess(cam.smooth_x, cam.MAX_MOUSE_X)
        first_x = cam.smooth_x
        for _ in range(30):
            cam.update(1 / 60, (SCREEN_W, SCREEN_H))
        self.assertGreater(cam.smooth_x, first_x)

        dx_far, _ = cam.offset_for(env.LAYER_DEPTHS[1])
        dx_near, _ = cam.offset_for(env.LAYER_DEPTHS[5])
        self.assertGreater(abs(dx_near), abs(dx_far))

    def test_environmental_animations_update_cleanly(self):
        env = MenuEnvironment()
        initial_firefly_pos = [(p["x"], p["y"]) for p in env.fireflies]
        for _ in range(120):
            env.update(1 / 60, (600, 300))
        moved_firefly_pos = [(p["x"], p["y"]) for p in env.fireflies]
        self.assertNotEqual(initial_firefly_pos, moved_firefly_pos)
        self.assertGreater(len(env.lava_bubbles), 0)
        self.assertGreater(len(env.fuse_sparks), 0)
        self.assertGreater(len(env.cavern_embers), 0)
        # Multi-size dust particles (2px, 3px, 4px)
        dust_sizes = {d["size"] for d in env.ceiling_dust}
        self.assertTrue({2, 3, 4}.issubset(dust_sizes))
        # Hanging chains, pulley bucket & foreground silhouette layer
        self.assertEqual(len(env.chain_frames), 3)
        self.assertEqual(len(env.pulley_frames), 3)
        self.assertIsNotNone(env.layer_fg_details)
        # Miner idle frames include breathing, hat tilt, glance, blink, and lamp states
        for pose in ("stand", "breath", "hat", "glance"):
            self.assertIn((pose, False, True), env.miner_frames)
            self.assertIn((pose, True, False), env.miner_frames)
        # Title shimmer frames pre-baked cleanly
        self.assertGreater(len(self.ui._title_shimmer_frames), 10)

    def test_keyboard_and_mouse_navigation_on_main_menu(self):
        for _ in range(180):
            self.ui.update(1 / 60, None)
        self.ui.draw_menu(self.surface, (10, 10))
        self.assertEqual(self.ui.selected_index, 0)  # PLAY

        # Keyboard DOWN -> SETTINGS -> EXIT -> wraps to PLAY
        self.ui.handle_menu_key(pygame.K_DOWN)
        self.assertEqual(self.ui.selected_index, 1)
        self.ui.handle_menu_key(pygame.K_s)
        self.assertEqual(self.ui.selected_index, 2)
        self.ui.handle_menu_key(pygame.K_DOWN)
        self.assertEqual(self.ui.selected_index, 0)

        # Mouse hover over EXIT selects index 2
        buttons = dict((label, rect) for rect, label in self.ui.buttons)
        self.ui.handle_mouse_motion(buttons["EXIT"].center)
        self.assertEqual(self.ui.selected_index, 2)

    def test_settings_panel_controls_volumes_fullscreen_and_back(self):
        for _ in range(180):
            self.ui.update(1 / 60, None)

        # Select SETTINGS and open panel
        self.ui.selected_index = 1
        action = self.ui.handle_menu_key(pygame.K_RETURN)
        self.assertEqual(action, "SETTINGS")
        self.assertTrue(self.ui.settings_open)

        # Animate Settings panel sliding in
        for _ in range(45):
            self.ui.update(1 / 60, None)
        self.assertGreater(self.ui.settings_progress, 0.95)
        self.ui.draw_menu(self.surface, (0, 0))

        # Row 0: Music Volume adjustment
        self.assertEqual(SETTINGS_ITEMS[self.ui.settings_index], "MUSIC VOLUME")
        initial_music = self.ui.music_volume
        self.ui.handle_menu_key(pygame.K_LEFT)
        self.assertAlmostEqual(self.ui.music_volume, initial_music - 0.10, places=2)

        # Row 1: SFX Volume adjustment (syncs with global SoundBank)
        self.ui.handle_menu_key(pygame.K_DOWN)
        self.assertEqual(SETTINGS_ITEMS[self.ui.settings_index], "SFX VOLUME")
        self.ui.handle_menu_key(pygame.K_LEFT)
        self.assertAlmostEqual(sounds().volume, self.ui.sfx_volume, places=2)

        # Row 2: Fullscreen toggle
        toggled_states = []
        self.ui.on_toggle_fullscreen = lambda state: toggled_states.append(state)
        self.ui.handle_menu_key(pygame.K_DOWN)
        self.assertEqual(SETTINGS_ITEMS[self.ui.settings_index], "FULLSCREEN")
        self.ui.handle_menu_key(pygame.K_RETURN)
        self.assertTrue(self.ui.fullscreen)
        self.assertEqual(toggled_states, [True])

        # Row 3: Back button returns smoothly to Main Menu
        self.ui.handle_menu_key(pygame.K_DOWN)
        self.assertEqual(SETTINGS_ITEMS[self.ui.settings_index], "BACK")
        self.ui.handle_menu_key(pygame.K_RETURN)
        self.assertFalse(self.ui.settings_open)
        for _ in range(45):
            self.ui.update(1 / 60, None)
        self.assertLess(self.ui.settings_progress, 0.05)

    def test_play_and_exit_transitions(self):
        for _ in range(180):
            self.ui.update(1 / 60, None)

        started = []
        self.ui.on_start_play = lambda: (started.append(True), setattr(self.ui, "screen", "game"))
        self.ui.selected_index = 0
        self.ui.handle_menu_key(pygame.K_RETURN)
        self.assertIsNotNone(self.ui.menu_transition)
        self.assertEqual(self.ui.menu_transition["action"], "PLAY")

        # Advance 0.5s -> should have switched to gameplay mid-transition
        for _ in range(32):
            self.ui.update(1 / 60, None)
        self.assertEqual(started, [True])
        self.assertEqual(self.ui.screen, "game")

        # Advance remaining 1.0s -> transition finishes cleanly
        for _ in range(65):
            self.ui.update(1 / 60, None)
        self.assertIsNone(self.ui.menu_transition)

        # Test EXIT transition
        self.ui.open_menu(replay_intro=False)
        exited = []
        self.ui.on_exit_game = lambda: exited.append(True)
        self.ui.selected_index = 2
        self.ui.handle_menu_key(pygame.K_RETURN)
        self.assertEqual(self.ui.menu_transition["action"], "EXIT")
        for _ in range(35):
            self.ui.update(1 / 60, None)
        self.assertTrue(self.ui.exit_requested)
        self.assertEqual(exited, [True])


if __name__ == "__main__":
    unittest.main()
