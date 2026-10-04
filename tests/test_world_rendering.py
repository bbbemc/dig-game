import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import unittest
import pygame
from config import CELL, MACRO
from world import World
from level import DIRT, EMPTY, STONE, build_level
from tiles import TileArt
from rendering import WorldRenderer
from liquids import LiquidSystem


class WorldRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((320,240))
        cls.art=TileArt(CELL,MACRO)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_dig_preserves_background_and_local_cache(self):
        rows,_,scenery,_=build_level()
        world=World(rows)
        renderer=WorldRenderer(world,self.art,scenery)
        screen=pygame.Surface((320,240))
        renderer.draw_static(screen,(0,0))
        self.assertEqual(renderer.rebuilt_chunks,1)
        before=bytes(world.background)
        i=world.index(18,18)
        self.assertEqual(world.foreground[i],DIRT)
        world.dig(18,18,2)
        self.assertEqual(world.foreground[i],EMPTY)
        self.assertEqual(bytes(world.background),before)
        renderer.draw_static(screen,(0,0))
        self.assertEqual(renderer.rebuilt_chunks,1)
        colors=[screen.get_at((x,y))[:3] for y in range(136,153) for x in range(136,153)]
        self.assertGreater(len(set(colors)),8)
        self.assertTrue(all(sum(color)>25 for color in colors))
        renderer.draw_static(screen,(0,0))
        self.assertEqual(renderer.rebuilt_chunks,0)

    def test_stone_is_solid_without_changing_rear_wall(self):
        world=World([[EMPTY]*10 for _ in range(10)],scale=1)
        i=world.index(5,5)
        rear=world.background[i]
        world.set_terrain(i,STONE)
        self.assertTrue(world.solid(5,5))
        self.assertEqual(world.background[i],rear)

    def test_background_variation_is_reproducible(self):
        a=self.art.background(12,12,1)
        b=self.art.background(12,12,1)
        self.assertIs(a,b)
        self.assertNotEqual(pygame.image.tobytes(a,'RGB'),pygame.image.tobytes(self.art.background(13,12,1),'RGB'))

    def test_partial_water_between_full_cells_has_no_horizontal_gap(self):
        rows=['RRRRRRRR']+['R      R']*6+['RRRRRRRR']
        rows=[list(row) for row in rows]
        for y in (2,3,4):
            rows[y][3]='W'
        world=World([''.join(row) for row in rows])
        liquids=LiquidSystem(world)
        index=world.index(17,17)
        liquids.mass[index]=.125
        liquids._units[index]=128
        renderer=WorldRenderer(world,self.art,{'props':[],'materials':{},'lights':[]})
        screen=pygame.Surface((320,240))
        renderer.draw_static(screen,(0,0))
        point=(17*CELL+CELL//2,17*CELL+1)
        rear=screen.get_at(point)
        renderer.draw_liquids(screen,liquids,(0,0),1,0)
        self.assertNotEqual(screen.get_at(point),rear)
