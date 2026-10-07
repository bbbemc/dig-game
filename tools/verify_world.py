"""Reproducible visual/regression scenarios and actual CPU frame-cost sampling."""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import pygame
from config import CELL, MACRO, SCREEN_W, SCREEN_H, FPS
from main import Game
from tiles import TileArt
from level import DIRT, EMPTY


def stats(values):
    ordered=sorted(values)
    return {'mean_ms':statistics.mean(values),'p95_ms':ordered[int((len(ordered)-1)*.95)],'max_ms':max(values)}


def clear_box(world,x0,y0,x1,y1):
    for y in range(y0,y1):
        for x in range(x0,x1):
            i=world.index(x,y)
            if world.foreground[i] == DIRT:
                world.set_terrain(i,EMPTY)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/dig-world-polish-review'))
    parser.add_argument('--frames',type=int,default=600)
    parser.add_argument('--native',action='store_true',help='Show and pace the real window at 60 FPS.')
    parser.add_argument('--scenario',choices=('all','normal','fluid-heavy'),default='all')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.native and os.environ.get('SDL_VIDEODRIVER')=='dummy':
        del os.environ['SDL_VIDEODRIVER']
    pygame.init()
    screen=pygame.display.set_mode((SCREEN_W,SCREEN_H))
    pygame.display.set_caption('Dig Game — Stage 1 verification')
    art=TileArt(CELL,MACRO)
    report={}
    game=Game(art)
    game.draw(screen)
    assert game.player.grounded and not game.player.overlaps_terrain()
    pygame.image.save(screen,str(args.output/'stage1-start.png'))
    game.player.pos.update(8*MACRO,9*MACRO)
    game.player.rect.topleft=round(game.player.pos.x),round(game.player.pos.y)
    game.player.drop_to_ground()
    game.draw(screen)
    pygame.image.save(screen,str(args.output/'stage1-ladder-and-exit.png'))
    game=Game(art)
    clear_box(game.world,15*5,4*5,19*5,5*5)
    game.draw(screen)
    pygame.image.save(screen,str(args.output/'stage1-released-water.png'))
    game=Game(art)
    # Dig through the corridor floor so both enemies can drop into lava.
    clear_box(game.world,13*5,10*5,19*5,11*5)
    game.player.pos.update(3*MACRO,3*MACRO)
    game.player.rect.topleft=round(game.player.pos.x),round(game.player.pos.y)
    for frame in range(70):
        game.state='play'; game.hp=100
        game.update(1/FPS)
        if frame in (24,45,69):
            game.draw(screen)
            pygame.image.save(screen,str(args.output/f'waterfall-{frame:03}.png'))
    for scenario in ('normal','fluid-heavy'):
        if args.scenario!='all' and args.scenario!=scenario:
            continue
        game=Game(art)
        if scenario=='fluid-heavy':
            # Release the upper water basin through the corridor and into lava.
            clear_box(game.world,15*5,4*5,19*5,5*5)
            clear_box(game.world,16*5,10*5,17*5,11*5)
            game.player.pos.update(3*MACRO,3*MACRO)
            game.player.rect.topleft=round(game.player.pos.x),round(game.player.pos.y)
            game.player.drop_to_ground()
        costs, fluid, render, physics, processed, intervals, present=[],[],[],[],[],[],[]
        clock=pygame.time.Clock()
        captures=[]
        for frame in range(args.frames):
            interval=clock.tick_busy_loop(FPS) if args.native else 1000/FPS
            start=time.perf_counter()
            if any(event.type==pygame.QUIT for event in pygame.event.get()):
                pygame.quit()
                return
            # Keep benchmarking the world if the avatar gets hit in a QA scene.
            game.state='play'; game.hp=100
            game.update(1/FPS)
            game.draw(screen)
            elapsed=(time.perf_counter()-start)*1000
            present_start=time.perf_counter()
            if args.native:
                pygame.display.flip()
            present_ms=(time.perf_counter()-present_start)*1000
            if frame>20:
                costs.append(elapsed)
                fluid.append(game.metrics['fluid_ms'])
                render.append(game.metrics['render_ms'])
                physics.append(game.metrics['physics_ms'])
                processed.append(game.liquids.last_processed)
                intervals.append(interval)
                present.append(present_ms)
            if scenario=='fluid-heavy' and frame in (15,45,120,300,args.frames-1):
                captures.append((args.output/f'reaction-{frame:03}.png',screen.copy()))
        # PNG compression is deliberately outside the measured gameplay loop.
        for path,capture in captures:
            pygame.image.save(capture,str(path))
        assert not game.player.overlaps_terrain()
        assert abs(game.liquids.total_mass+game.liquids.reacted_mass-game.liquids.initial_mass)<1e-8
        report[scenario]={'work':stats(costs),'fluid':stats(fluid),'render':stats(render),'physics':stats(physics),
                          'active_final':len(game.liquids.active),'processed_max':max(processed),
                          'reaction_final':len(game.liquids.reactions),'reacted_mass':game.liquids.reacted_mass,
                          'world_cells':game.world.width*game.world.height,
                          'visible_chunks':game.renderer.visible_chunks}
        if args.native:
            report[scenario]['frame']=stats(intervals)
            report[scenario]['present']=stats(present)
    pygame.quit()
    (args.output/'profile.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
