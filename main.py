"""Dig Game: grounded exploration, permanent cave walls and fixed-step liquids."""
import argparse
import json
import math
import time
from pathlib import Path
import pygame
from config import (CELL, SCALE, MACRO, SCREEN_W, SCREEN_H, FPS, PHYSICS_HZ,
                    FLUID_HZ, MAX_FRAME_DT, DIG_REACH, DIG_RADIUS)
from config import (PRECISE_FRAME_PACING, CAMERA_FOLLOW, SHAKE_DECAY, MOTE_LIMIT,
                    EMBER_INTERVAL)
from level import build_level, validate_level, WATER, LAVA
from world import World
from physics import Player, Actor
from liquids import LiquidSystem
from tiles import TileArt
from rendering import WorldRenderer
from effects import Particles
from lighting import Lighting
from actors import MinerSprite


class Game:
    def __init__(self, art, lighting=None):
        rows, entities, scenery, self.optional_rooms = build_level()
        self.density = validate_level(rows, entities)
        self.world = World(rows)
        self.world.sculpt(scenery.get('sculpt', {}))
        self.liquids = LiquidSystem(self.world)
        self.renderer = WorldRenderer(self.world, art, scenery)
        self.lighting = lighting or Lighting((SCREEN_W, SCREEN_H))
        x,y = entities['P'][0]
        self.player = Player(self.world,x*MACRO,y*MACRO)
        self.player.drop_to_ground()
        x,y = entities['E'][0]
        self.boss = Actor(self.world,x*MACRO,y*MACRO,size=MACRO,speed=0)
        self.boss.drop_to_ground()
        self.monsters = []
        for n,(x,y) in enumerate(entities['M']):
            actor = Actor(self.world,x*MACRO,y*MACRO,size=24,speed=32)
            actor.direction = 1 if n%2 else -1
            actor.drop_to_ground()
            self.monsters.append(actor)
        self.particles = Particles()
        self.miner = MinerSprite()
        self.hp, self.state = 100, 'play'
        self.physics_accumulator = self.fluid_accumulator = self.world_time = 0.0
        self.hurt_timer = 0.0
        self.jump_pending = False
        self.last_dig = None
        self.dig_x = None
        # Presentation only: a smoothed view, trauma-based shake, emitters.
        self.view = pygame.Vector2(self.camera())
        self.render_camera = self.camera()
        self.shake = self.view_time = 0.0
        self.was_swimming = False
        self.reactions_seen = 0
        self.ember_clock = self.mote_clock = 0.0
        self.draw_calls = 0
        self.metrics = {'physics_ms':0.,'fluid_ms':0.,'particles_ms':0.,'render_ms':0.}

    def touches(self, rect, kind):
        for y in range(max(0,rect.top//CELL), min(self.world.height,(rect.bottom-1)//CELL+1)):
            for x in range(max(0,rect.left//CELL), min(self.world.width,(rect.right-1)//CELL+1)):
                i = self.world.index(x,y)
                if self.liquids.types.get(i) == kind and self.liquids.mass.get(i,0) > .06:
                    # A partial cell only touches the actor below its surface.
                    surface = (y+1)*CELL-min(1,self.liquids.mass[i])*CELL
                    if rect.bottom > surface:
                        return True
        return False

    def camera(self):
        """Target view: the player centred, clamped to the world."""
        return (round(max(0,min(self.player.pos.x+self.player.size/2-SCREEN_W/2,
                                self.world.pixel_width-SCREEN_W))),
                round(max(0,min(self.player.pos.y+self.player.size/2-SCREEN_H/2,
                                self.world.pixel_height-SCREEN_H))))

    def follow_camera(self, dt):
        """Ease the drawn view toward the target; shake only on big events."""
        target = pygame.Vector2(self.camera())
        if (target - self.view).length() > SCREEN_W:
            self.view.update(target)  # restarts and teleports cut, not pan
        else:
            self.view += (target - self.view) * (1 - math.exp(-CAMERA_FOLLOW * dt))
        self.view_time += dt
        self.shake = max(0.0, self.shake - SHAKE_DECAY * dt)
        jolt = self.shake * self.shake * 4
        x = round(self.view.x + math.sin(self.view_time * 47) * jolt)
        y = round(self.view.y + math.cos(self.view_time * 41) * jolt)
        self.render_camera = (max(0, min(x, self.world.pixel_width - SCREEN_W)),
                              max(0, min(y, self.world.pixel_height - SCREEN_H)))

    def excavate(self, target):
        center = self.player.rect.centerx//CELL,self.player.rect.centery//CELL
        if (target[0]-center[0])**2+(target[1]-center[1])**2 > DIG_REACH**2:
            self.last_dig = None
            return
        self.dig_x = target[0]*CELL+CELL//2
        # A dragged stroke cannot excavate distant terrain via a stale endpoint.
        start = self.last_dig or target
        if (start[0]-center[0])**2+(start[1]-center[1])**2 > DIG_REACH**2:
            start = target
        removed = self.world.dig_line(start,target,DIG_RADIUS)
        self.particles.dirt(self.world,removed,self.renderer.debris_colors)
        self.last_dig = target

    def update(self, dt, horizontal=0, jump=False, vertical=0):
        dt = min(max(dt,0),MAX_FRAME_DT)
        self.metrics['physics_ms'] = self.metrics['fluid_ms'] = 0.
        if self.state != 'play':
            self.dig_x = None
            self.follow_camera(dt)
            return
        self.world_time += dt
        self.physics_accumulator += dt
        self.jump_pending |= jump
        physics_dt, fluid_dt = 1/PHYSICS_HZ,1/FLUID_HZ
        while self.physics_accumulator + 1e-10 >= physics_dt:
            start = time.perf_counter()
            on_ladder = self.renderer.ladder_at(self.player.rect)
            swimming = self.touches(self.player.rect,WATER)
            fall_speed = self.player.velocity.y
            self.player.update(physics_dt,horizontal,self.jump_pending,swimming,
                               vertical if on_ladder else 0,ladder_attached=on_ladder)
            if self.player.landed and fall_speed > 300:
                self.particles.dust(self.player.rect.centerx,self.player.rect.bottom,
                                    min(1.0,(fall_speed-300)/260))
            self.jump_pending = False
            for actor in self.monsters:
                actor.update(physics_dt,actor.direction)
                if actor.hit_wall:
                    actor.direction *= -1
            self.boss.update(physics_dt,0)
            self.physics_accumulator -= physics_dt
            self.fluid_accumulator += physics_dt
            self.metrics['physics_ms'] += (time.perf_counter()-start)*1000
            if self.fluid_accumulator + 1e-10 >= fluid_dt:
                start = time.perf_counter()
                self.liquids.step(fluid_dt)
                self.fluid_accumulator -= fluid_dt
                self.metrics['fluid_ms'] += (time.perf_counter()-start)*1000
        self.hurt_timer = max(0,self.hurt_timer-dt)
        if self.touches(self.player.rect,LAVA):
            self.hp,self.state = 0,'lose'
        elif self.hurt_timer == 0 and (any(self.player.rect.colliderect(a.rect) for a in self.monsters)
                                      or self.player.rect.colliderect(self.boss.rect)):
            self.hp -= 20
            self.hurt_timer = .8
            if self.hp <= 0:
                self.state = 'lose'
        if self.touches(self.boss.rect,LAVA):
            self.state = 'win'
            self.shake = min(1.0, self.shake + 0.7)
        start = time.perf_counter()
        self.emit(dt)
        self.particles.update(dt)
        self.miner.update(dt,self.player,self.dig_x)
        self.dig_x = None
        self.metrics['particles_ms'] = (time.perf_counter()-start)*1000
        self.follow_camera(dt)

    def emit(self, dt):
        """Ambient particles and feedback; none of it touches the simulation."""
        swimming = self.touches(self.player.rect,WATER)
        if swimming and not self.was_swimming and abs(self.player.velocity.y) > 60:
            self.particles.splash(self.player.rect.centerx,self.player.rect.centery,
                                  min(1.0,abs(self.player.velocity.y)/300))
        self.was_swimming = swimming
        # Several cells starting to cool at once is the one quake-worthy event.
        reactions = len(self.liquids.reactions)
        if reactions - self.reactions_seen >= 8:
            self.shake = min(0.45, self.shake + 0.22)
        self.reactions_seen = reactions
        rnd = self.particles.random
        surfaces = self.renderer.lava_surfaces
        self.ember_clock += dt
        while self.ember_clock >= EMBER_INTERVAL:
            self.ember_clock -= EMBER_INTERVAL
            if surfaces:
                x, y = surfaces[rnd.randrange(len(surfaces))]
                self.particles.ember(x+rnd.uniform(0,CELL),y)
        self.mote_clock += dt
        if self.mote_clock >= 0.3:
            self.mote_clock = 0.0
            lamps = self.renderer.visible_lamps
            if lamps and self.particles.count(0.0) < MOTE_LIMIT:
                x, y = lamps[rnd.randrange(len(lamps))]
                self.particles.mote(x+rnd.uniform(-46,46),y+rnd.uniform(-34,30))

    def light_sources(self):
        renderer = self.renderer
        for light in renderer.lights:
            if renderer.supported(light['item']):
                yield (light['kind'],light['x'],light['y'],light['radius'],light['color'],light['phase'])
        for mx, my in renderer.visible_lava:
            if (mx+my*2)%3 == 0:
                yield ('lava',mx*MACRO+MACRO//2,my*MACRO+MACRO//2,128,(255,112,44),(mx*7+my)%6)
        for mx, my in renderer.visible_water:
            if (mx*3+my)%4 == 0:
                yield ('water',mx*MACRO+MACRO//2,my*MACRO+MACRO//2,72,(36,84,140),(mx+my*5)%6)

    def draw(self, screen):
        start = time.perf_counter()
        # A zero-time follow cuts to the player after a teleport (restart,
        # scripted views) even when no update ran since the move.
        self.follow_camera(0)
        camera = self.render_camera
        renderer = self.renderer
        renderer.draw_static(screen,camera)
        renderer.draw_animated(screen,camera,self.world_time)
        renderer.draw_liquids(screen,self.liquids,camera,
                              self.fluid_accumulator*FLUID_HZ,self.world_time)
        for actor in self.monsters:
            draw_actor(screen,actor,(220,75,65),camera)
        draw_actor(screen,self.boss,(158,52,184),camera)
        self.miner.draw(screen,self.player,camera,self.hurt_timer)
        self.particles.draw(screen,camera)
        renderer.draw_foreground(screen,camera)
        self.lighting.draw(screen,camera,self.world_time,self.light_sources(),
                           self.miner.head(self.player))
        self.metrics['render_ms'] = (time.perf_counter()-start)*1000
        self.draw_calls = (renderer.draw_calls+self.lighting.draw_calls+
                           len(self.monsters)+2+len(self.particles.items))


def draw_actor(screen, actor, color, camera):
    # Monster and boss artwork remain the project's placeholder shapes.
    box = actor.rect.move(-camera[0],-camera[1])
    if not box.colliderect(screen.get_rect()):
        return
    # Outline stays inside the collision bounds, so feet visually meet the floor.
    pygame.draw.rect(screen,(19,19,25),box,border_radius=3)
    pygame.draw.rect(screen,color,box.inflate(-4,-2),border_radius=2)
    pygame.draw.rect(screen,(240,240,215),(box.x+box.w//3,box.y+box.h//3,4,4))


def main(argv=None):
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=0,help='Exit after N frames for smoke testing.')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--uncapped',action='store_true')
    parser.add_argument('--profile',type=Path,help='Save measured frame/system costs as JSON.')
    args = parser.parse_args(argv)
    if args.headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    os.environ['SDL_RENDER_SCALE_QUALITY'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W,SCREEN_H),vsync=0)
    pygame.display.set_caption('Dig Game — Underground')
    art = TileArt(CELL,MACRO)
    lighting = Lighting((SCREEN_W,SCREEN_H))
    font,big_font,debug_font = pygame.font.SysFont(None,24),pygame.font.SysFont(None,54),pygame.font.SysFont('monospace',16)
    game = Game(art,lighting)
    clock = pygame.time.Clock()
    frames,debug,running = 0,False,True
    costs,frame_times,samples = [],[],[]
    while running:
        tick = clock.tick_busy_loop if PRECISE_FRAME_PACING else clock.tick
        raw_frame_dt = tick(0 if args.uncapped else FPS)/1000
        frame_dt = min(raw_frame_dt,MAX_FRAME_DT)
        if args.uncapped:
            frame_dt = 1/FPS  # Reproducible benchmark simulation time.
        start = time.perf_counter()
        jump = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    game = Game(art,lighting)
                elif event.key == pygame.K_F3:
                    debug = not debug
                elif event.key in (pygame.K_SPACE,pygame.K_w,pygame.K_UP):
                    jump = True
        keys = pygame.key.get_pressed()
        horizontal = int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        vertical = int(keys[pygame.K_s] or keys[pygame.K_DOWN])-int(keys[pygame.K_w] or keys[pygame.K_UP])
        if game.state == 'play' and pygame.mouse.get_pressed()[0]:
            mx,my = pygame.mouse.get_pos()
            cx,cy = game.render_camera
            game.excavate(((mx+cx)//CELL,(my+cy)//CELL))
        else:
            game.last_dig = None
        game.update(frame_dt,horizontal,jump,vertical)
        game.draw(screen)
        layer = min(4,game.player.rect.centery//(25*MACRO)+1)
        pygame.draw.rect(screen,(18,17,24),(0,0,SCREEN_W,35))
        hud = f'HP {game.hp}   B{layer}   A/D: move   Space/W: jump   W/S: ladder   Mouse: dig   R: restart   F3: stats'
        screen.blit(font.render(hud,True,(245,237,223)),(10,7))
        if debug:
            metrics = game.metrics
            player = game.player.rect
            lines = [f'{clock.get_fps():5.1f} FPS  frame {raw_frame_dt*1000:5.2f} ms',
                     f'physics {metrics["physics_ms"]:.2f}  liquid {metrics["fluid_ms"]:.2f}  render {metrics["render_ms"]:.2f} ms',
                     f'active {len(game.liquids.active)}  cooling {len(game.liquids.reactions)}',
                     f'chunks {game.renderer.visible_chunks}  dirty {len(game.world.dirty_chunks)}  rebuilt {game.renderer.rebuilt_chunks}',
                     f'tiles {game.renderer.visible_tiles}  draw calls {game.draw_calls}  lights {game.lighting.visible}',
                     f'visible liquid {game.renderer.visible_liquids}  particles {len(game.particles.items)}',
                     f'player x {player.x} y {player.y}  cell {player.centerx//CELL},{player.bottom//CELL}']
            panel = pygame.Surface((580,146),pygame.SRCALPHA)
            panel.fill((12,14,22,225))
            screen.blit(panel,(10,45))
            for n,line in enumerate(lines):
                screen.blit(debug_font.render(line,True,(219,231,243)),(18,52+n*19))
        if game.state != 'play':
            label = big_font.render('YOU WIN!' if game.state=='win' else 'YOU LOSE',True,(255,245,222))
            screen.blit(label,label.get_rect(center=screen.get_rect().center))
            label = font.render('Press R to restart',True,(255,245,222))
            screen.blit(label,label.get_rect(center=(SCREEN_W//2,SCREEN_H//2+42)))
        cpu_cost = (time.perf_counter()-start)*1000
        present_start = time.perf_counter()
        pygame.display.flip()
        game.metrics['present_ms'] = (time.perf_counter()-present_start)*1000
        frames += 1
        # Discard warmup cache builds from steady-state cost statistics.
        if frames > 20:
            costs.append(cpu_cost)
            frame_times.append(raw_frame_dt*1000)
            samples.append(game.metrics.copy())
        if args.frames and frames >= args.frames:
            running = False
    if args.profile:
        import statistics
        def stats(values):
            values = sorted(values)
            return {'mean_ms':statistics.mean(values) if values else 0,
                    'p95_ms':values[int((len(values)-1)*.95)] if values else 0,
                    'max_ms':max(values,default=0)}
        report = {'pygame':pygame.version.ver,'frames':frames,'work':stats(costs),'frame':stats(frame_times),
                  'systems':{key:stats([s[key] for s in samples]) for key in game.metrics},
                  'fluid_active':len(game.liquids.active),'reaction_cells':len(game.liquids.reactions)}
        args.profile.parent.mkdir(parents=True,exist_ok=True)
        args.profile.write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    pygame.quit()


if __name__ == '__main__':
    main()
