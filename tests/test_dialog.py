"""The miner's stage intro message box."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W
from dialog import (BOX, CHARS_PER_SECOND, FADE_TIME, MAX_LINES, NAME_COLOR, NAME_SIZE,
                    NAME_TAB, PORTRAIT, PORTRAIT_ART, PORTRAIT_SCALE, SHOW_TIME,
                    STAGE_DIALOGUES, TEXT_COLOR, TEXT_LEFT, TEXT_SIZE, TEXT_TOP,
                    TEXT_WIDTH, StageDialog, dialogue_for, wrap_text)
from main import Game
from tiles import TileArt
from ui import GameUI


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)
        cls.fonts = GameUI().fonts
        cls.font = cls.fonts[TEXT_SIZE]

    def test_every_stage_and_the_boss_room_have_a_line(self):
        for stage in range(1, 6):
            self.assertEqual(dialogue_for(Game(self.art, stage=stage)),
                             STAGE_DIALOGUES[stage])
        boss_room = Game(self.art, stage=5, bonus_room=True)
        self.assertEqual(dialogue_for(boss_room), STAGE_DIALOGUES['boss'])

    def test_other_bonus_rooms_stay_quiet(self):
        self.assertIsNone(dialogue_for(Game(self.art, stage=1, bonus_room=True)))

    def test_lines_wrap_inside_the_box(self):
        self.assertLessEqual(TEXT_LEFT + TEXT_WIDTH, BOX.right)
        self.assertGreaterEqual(TEXT_LEFT, PORTRAIT.right)      # clear of the bust
        for text in STAGE_DIALOGUES.values():
            lines = wrap_text(self.font, text, TEXT_WIDTH)
            self.assertLessEqual(len(lines), MAX_LINES)
            self.assertEqual(' '.join(lines), text)
            for line in lines:
                self.assertLessEqual(self.font.size(line)[0], TEXT_WIDTH)
        tallest = TEXT_TOP + MAX_LINES * self.font.get_linesize()
        self.assertLessEqual(tallest, BOX.bottom)

    def test_text_types_out_then_the_dialog_expires(self):
        dialog = StageDialog()
        dialog.start(STAGE_DIALOGUES[1])
        self.assertEqual(dialog.visible_chars, 0)
        dialog.update(0.5)
        self.assertEqual(dialog.visible_chars, CHARS_PER_SECOND // 2)
        dialog.update(SHOW_TIME - 0.5)
        self.assertTrue(dialog.active)
        self.assertEqual(dialog.alpha, 255)
        dialog.update(FADE_TIME / 2)
        self.assertLess(dialog.alpha, 255)
        dialog.update(FADE_TIME)
        self.assertFalse(dialog.active)

    def test_dismiss_closes_it_at_once(self):
        dialog = StageDialog()
        dialog.start(STAGE_DIALOGUES[2])
        dialog.dismiss()
        self.assertFalse(dialog.active)

    def test_ui_start_opens_the_intro_unless_told_not_to(self):
        ui = GameUI()
        game = Game(self.art, stage=3)
        ui.start(game)
        self.assertEqual(ui.dialog.text, STAGE_DIALOGUES[3])
        ui.start(game, intro=False)
        self.assertFalse(ui.dialog.active)

    def test_control_prompts_wait_for_the_intro(self):
        ui = GameUI()
        game = Game(self.art, stage=1)
        ui.start(game)
        ui.update(1.0, game)
        self.assertEqual(ui.prompt_time, 0.0)
        ui.dialog.dismiss()
        ui.update(1.0, game)
        self.assertEqual(ui.prompt_time, 1.0)

    def _drawn(self, text, time):
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
        surface.fill((255, 0, 255))
        dialog = StageDialog()
        dialog.start(text)
        dialog.update(time)
        dialog.draw(surface, self.fonts)
        return surface

    def test_box_spans_the_foot_of_the_screen_and_leaves_the_rest_alone(self):
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
        surface.fill((255, 0, 255))
        StageDialog().draw(surface, self.fonts)         # inactive: no pixels
        self.assertEqual(surface.get_at(BOX.center)[:3], (255, 0, 255))

        surface = self._drawn(STAGE_DIALOGUES['boss'], SHOW_TIME)
        self.assertEqual((BOX.x, BOX.w, BOX.bottom), (0, SCREEN_W, SCREEN_H))
        for x in (BOX.x + 2, BOX.centerx, BOX.right - 3):
            color = surface.get_at((x, BOX.bottom - 30))
            self.assertLess(max(color[:3]), 70)         # dark panel, edge to edge
        # Above the box only the bust and the name tab are drawn.
        self.assertEqual(surface.get_at((BOX.centerx + 100, BOX.y - 2))[:3], (255, 0, 255))
        self.assertEqual(surface.get_at((PORTRAIT.centerx, PORTRAIT.y - 2))[:3],
                         (255, 0, 255))
        self.assertEqual(surface.get_at((NAME_TAB.right + 4, NAME_TAB.centery))[:3],
                         (255, 0, 255))

    def test_line_is_typed_in_cream_beside_the_portrait(self):
        text = STAGE_DIALOGUES[1]
        area = pygame.Rect(TEXT_LEFT, TEXT_TOP, TEXT_WIDTH, self.font.get_linesize())

        def cream(surface):
            return sum(surface.get_at((x, y))[:3] == TEXT_COLOR
                       for x in range(area.x, area.right) for y in range(area.y, area.bottom))

        self.assertEqual(cream(self._drawn(text, 0.0)), 0)
        half = cream(self._drawn(text, 0.5))
        self.assertGreater(half, 0)
        self.assertGreater(cream(self._drawn(text, SHOW_TIME)), half)

    def test_name_tab_sits_on_the_box_next_to_the_portrait(self):
        self.assertGreaterEqual(NAME_TAB.x, PORTRAIT.right)
        self.assertLess(NAME_TAB.y, BOX.y)
        self.assertGreaterEqual(NAME_TAB.bottom, BOX.y)     # no gap under the tab
        surface = self._drawn(STAGE_DIALOGUES[1], 1.0)
        name = [surface.get_at((x, y))[:3] for x in range(NAME_TAB.x, NAME_TAB.right)
                for y in range(NAME_TAB.y, BOX.y)]
        self.assertIn(NAME_COLOR, name)
        self.assertLessEqual(self.fonts[NAME_SIZE].size('- MINER -')[0], NAME_TAB.w - 12)

    def test_portrait_is_a_crisp_bust_standing_over_the_box(self):
        art = pygame.image.load(PORTRAIT_ART)
        self.assertEqual(PORTRAIT.size, (art.get_width() * PORTRAIT_SCALE,
                                         art.get_height() * PORTRAIT_SCALE))
        self.assertEqual(PORTRAIT.bottom, SCREEN_H)
        self.assertLess(PORTRAIT.y, BOX.y - 40)             # head and hat above the box
        surface = self._drawn(STAGE_DIALOGUES[1], 1.0)
        hat = [surface.get_at((x, y)) for x in range(PORTRAIT.x, PORTRAIT.right, 2)
               for y in range(PORTRAIT.y, BOX.y, 2)]
        yellow = [c for c in hat if c.r > 200 and c.g > 150 and c.b < 120]
        self.assertGreater(len(yellow), 300)

    def test_fade_lets_the_game_show_through(self):
        solid = self._drawn(STAGE_DIALOGUES[1], SHOW_TIME)
        fading = self._drawn(STAGE_DIALOGUES[1], SHOW_TIME + FADE_TIME * 0.8)
        spot = (BOX.centerx, BOX.bottom - 30)
        self.assertGreater(fading.get_at(spot).r, solid.get_at(spot).r + 100)

    def test_bottom_hud_gives_way_while_the_box_is_up(self):
        calls = []
        ui = GameUI()
        ui.key_inventory = lambda surface, game: calls.append('keys')
        ui.speed_potion_timer = lambda surface, game: calls.append('potion')
        game = Game(self.art, stage=1)
        screen = pygame.display.get_surface()
        ui.start(game)
        ui.draw_game(screen, game, (0, 0))
        self.assertEqual(calls, [])
        ui.dialog.dismiss()
        ui.draw_game(screen, game, (0, 0))
        self.assertEqual(calls, ['keys', 'potion'])


if __name__ == "__main__":
    unittest.main()
