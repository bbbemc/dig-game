"""R asks before restarting the stage."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
import unittest
from unittest import mock

import pygame

import main
from config import CELL, MACRO, SCREEN_H, SCREEN_W
from main import Game
from tiles import TileArt
from ui import CREAM, GOLD_BRIGHT, ORANGE, ORANGE_RED, RESTART_SIGN, GameUI


class RestartConfirmUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def playing(self, stage=1):
        ui = GameUI()
        game = Game(self.art, stage=stage)
        ui.start(game)
        return ui, game

    def test_opens_over_the_game_and_no_goes_back_where_it_came_from(self):
        ui, _ = self.playing()
        self.assertFalse(ui.confirm_restart_open)
        ui.open_restart_confirm()
        self.assertTrue(ui.confirm_restart_open)
        ui.close_restart_confirm()
        self.assertEqual(ui.screen, 'game')
        ui.screen = 'paused'
        ui.open_restart_confirm()
        ui.open_restart_confirm()           # a second R changes nothing
        ui.close_restart_confirm()
        self.assertEqual(ui.screen, 'paused')

    def test_shortcut_keys_decide_at_once(self):
        ui, _ = self.playing()
        ui.open_restart_confirm()
        self.assertEqual(ui.handle_restart_confirm_key(pygame.K_y), 'CONFIRM RESTART')
        for key in (pygame.K_n, pygame.K_ESCAPE):
            self.assertEqual(ui.handle_restart_confirm_key(key), 'CANCEL RESTART')
        for key in (pygame.K_SPACE, pygame.K_w, pygame.K_r, pygame.K_q):
            self.assertIsNone(ui.handle_restart_confirm_key(key))

    def test_highlight_starts_on_yes_and_moves_with_a_and_d(self):
        ui, _ = self.playing()
        ui.open_restart_confirm()
        self.assertEqual(ui.confirm_restart_choice, 'YES')
        for confirm in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e):
            self.assertEqual(ui.handle_restart_confirm_key(confirm), 'CONFIRM RESTART')
        for right, left in ((pygame.K_d, pygame.K_a), (pygame.K_RIGHT, pygame.K_LEFT)):
            self.assertIsNone(ui.handle_restart_confirm_key(right))
            self.assertEqual(ui.confirm_restart_choice, 'NO')
            for confirm in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e):
                self.assertEqual(ui.handle_restart_confirm_key(confirm), 'CANCEL RESTART')
            self.assertIsNone(ui.handle_restart_confirm_key(left))
            self.assertEqual(ui.confirm_restart_choice, 'YES')
        ui.handle_restart_confirm_key(pygame.K_d)
        ui.close_restart_confirm()
        ui.open_restart_confirm()
        self.assertEqual(ui.confirm_restart_choice, 'YES')     # reset each time

    def test_hud_and_intro_line_stand_still_behind_the_sign(self):
        ui, game = self.playing()
        ui.update(0.5, game)
        typed, prompt = ui.dialog.time, ui.prompt_time
        ui.open_restart_confirm()
        ui.update(3.0, game)
        self.assertEqual((ui.dialog.time, ui.prompt_time), (typed, prompt))
        ui.close_restart_confirm()
        ui.update(0.25, game)
        self.assertEqual(ui.dialog.time, typed + 0.25)

    def drawn(self, ui, game):
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
        surface.fill((200, 200, 200))
        with mock.patch.object(ui, 'draw_game'):        # leave the grey untouched
            ui.draw(surface, game, (0, 0))
        return surface

    def test_sign_sits_in_the_middle_over_a_darkened_screen(self):
        ui, game = self.playing()
        ui.open_restart_confirm()
        surface = self.drawn(ui, game)
        self.assertEqual(RESTART_SIGN.size, (380, 180))
        self.assertEqual(RESTART_SIGN.center, (SCREEN_W // 2, SCREEN_H // 2))
        # Black at alpha 150 over the whole screen: 200 -> about 82.
        for spot in ((0, 0), (SCREEN_W - 1, SCREEN_H - 1), (RESTART_SIGN.x - 3, 320)):
            shade = surface.get_at(spot)[:3]
            self.assertEqual(len(set(shade)), 1)
            self.assertAlmostEqual(shade[0], 200 * (255 - 150) / 255, delta=2)
        inside = [surface.get_at((x, y))[:3] for x in range(RESTART_SIGN.x, RESTART_SIGN.right)
                  for y in range(RESTART_SIGN.y, RESTART_SIGN.bottom)]
        self.assertNotIn((82, 82, 82), inside)          # the sign is solid
        for color in (ORANGE, CREAM, ORANGE_RED):       # title, message, YES
            self.assertIn(color, inside)

    def test_both_buttons_are_drawn_clickable_and_one_is_highlighted(self):
        ui, game = self.playing()
        ui.open_restart_confirm()
        surface = self.drawn(ui, game)
        (yes, yes_action), (no, no_action) = ui.buttons
        self.assertEqual((yes_action, no_action), ('CONFIRM RESTART', 'CANCEL RESTART'))
        self.assertLess(yes.right, no.x)
        for rect in (yes, no):
            self.assertTrue(RESTART_SIGN.inflate(-24, -24).contains(rect.inflate(8, 8)))
        self.assertEqual(ui.click(yes.center), 'CONFIRM RESTART')
        self.assertEqual(ui.click(no.center), 'CANCEL RESTART')
        self.assertIsNone(ui.click((5, 5)))

        def highlighted(surface, rect):
            return surface.get_at((rect.x - 4, rect.centery))[:3] == GOLD_BRIGHT

        self.assertTrue(highlighted(surface, yes))
        self.assertFalse(highlighted(surface, no))
        ui.handle_restart_confirm_key(pygame.K_d)
        surface = self.drawn(ui, game)
        self.assertFalse(highlighted(surface, yes))
        self.assertTrue(highlighted(surface, no))

    def test_message_and_labels_fit(self):
        ui, _ = self.playing()
        board = RESTART_SIGN.inflate(-24, -24)
        message = 'Are you sure you want to restart this stage?'
        self.assertLess(ui.fonts[20].size(message)[0], board.w - 16)
        for label in ('[Y / ENTER] YES', '[N / ESC] NO'):
            self.assertLess(ui.fonts[20].size(label)[0], 160 - 24)

    def test_mouse_hover_moves_the_highlight(self):
        ui, game = self.playing()
        ui.open_restart_confirm()
        self.drawn(ui, game)
        (yes, _), (no, _) = ui.buttons
        ui.handle_mouse_motion(no.center)
        self.assertEqual(ui.confirm_restart_choice, 'NO')
        ui.handle_mouse_motion((5, 5))                  # off the buttons: stays put
        self.assertEqual(ui.confirm_restart_choice, 'NO')
        ui.handle_mouse_motion(yes.center)
        self.assertEqual(ui.confirm_restart_choice, 'YES')


def press(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode='', scancode=0, mod=0)


class RestartConfirmLoopTests(unittest.TestCase):
    """The real main loop, fed scripted key presses."""

    def run_game(self, script, frames, stage='1'):
        """``script`` maps a frame number to the keys pressed on it.

        Returns one (screen, game, seconds the game has simulated) per frame.
        """
        seen = []
        simulated = {}
        real_draw, real_update = GameUI.draw, Game.update

        def events(*args, **kwargs):
            return [press(key) for key in script.get(len(seen), ())]

        def update(game, dt, *args, **kwargs):
            simulated[id(game)] = simulated.get(id(game), 0.0) + dt
            return real_update(game, dt, *args, **kwargs)

        def draw(ui, surface, game, mouse):
            real_draw(ui, surface, game, mouse)
            seen.append((ui.screen, game, simulated.get(id(game), 0.0)))

        argv = ['main.py', '--headless', '--stage', stage, '--frames', str(frames)]
        with mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(pygame.event, 'get', events), \
                mock.patch.object(pygame, 'quit'), \
                mock.patch.object(Game, 'update', update), \
                mock.patch.object(GameUI, 'draw', draw):
            main.main()
        return seen

    def test_r_pauses_and_asks_instead_of_restarting(self):
        seen = self.run_game({10: [pygame.K_r]}, frames=40)
        first = seen[0][1]
        self.assertEqual(seen[9][0], 'game')
        self.assertTrue(all(screen == 'confirm_restart' for screen, _, _ in seen[10:]))
        self.assertTrue(all(game is first for _, game, _ in seen))      # no restart
        self.assertGreater(seen[9][2], 0)
        self.assertEqual(seen[-1][2], seen[9][2])       # time stood still

    def test_no_and_escape_return_to_the_same_game(self):
        for cancel in (pygame.K_n, pygame.K_ESCAPE):
            seen = self.run_game({5: [pygame.K_r], 10: [cancel]}, frames=30)
            self.assertEqual(seen[9][0], 'confirm_restart')
            self.assertEqual(seen[10][0], 'game')       # Esc did not open the pause menu
            self.assertEqual(seen[-1][0], 'game')
            self.assertIs(seen[-1][1], seen[0][1])
            self.assertGreater(seen[-1][2], seen[9][2])     # and it runs again

    def test_yes_enter_and_e_restart_the_stage(self):
        for confirm in (pygame.K_y, pygame.K_RETURN, pygame.K_e):
            seen = self.run_game({5: [pygame.K_r], 10: [confirm]}, frames=20)
            self.assertEqual(seen[10][0], 'game')
            self.assertIsNot(seen[10][1], seen[0][1])
            self.assertEqual(seen[10][1].stage_number, 1)

    def test_moving_the_highlight_to_no_makes_enter_cancel(self):
        seen = self.run_game({5: [pygame.K_r], 8: [pygame.K_d], 10: [pygame.K_RETURN]},
                             frames=20)
        self.assertEqual(seen[10][0], 'game')
        self.assertIs(seen[-1][1], seen[0][1])

    def test_other_keys_do_nothing_while_the_sign_is_up(self):
        seen = self.run_game({5: [pygame.K_r],
                              8: [pygame.K_SPACE, pygame.K_w, pygame.K_r, pygame.K_F3]},
                             frames=20)
        self.assertEqual(seen[-1][0], 'confirm_restart')
        self.assertIs(seen[-1][1], seen[0][1])
        self.assertEqual(seen[-1][2], seen[5][2])       # no jump: nothing was simulated

    def test_from_the_pause_menu_no_goes_back_to_the_pause_menu(self):
        seen = self.run_game({5: [pygame.K_ESCAPE], 8: [pygame.K_r], 12: [pygame.K_n]},
                             frames=20)
        self.assertEqual([seen[n][0] for n in (5, 8, 12)],
                         ['paused', 'confirm_restart', 'paused'])
        self.assertIs(seen[-1][1], seen[0][1])

    def test_r_on_the_game_over_screen_still_retries_at_once(self):
        real_init = Game.__init__
        made = []

        def init(game, *args, **kwargs):
            real_init(game, *args, **kwargs)
            if not made:
                game.state = 'lose'         # the first game starts already lost
            made.append(game)

        with mock.patch.object(Game, '__init__', init):
            seen = self.run_game({5: [pygame.K_r]}, frames=12)
        self.assertEqual(seen[5][0], 'game')
        self.assertIsNot(seen[5][1], seen[0][1])
        self.assertEqual(seen[5][1].state, 'play')


if __name__ == "__main__":
    unittest.main()
