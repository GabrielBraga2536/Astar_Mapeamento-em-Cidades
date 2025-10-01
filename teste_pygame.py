import os
import math
import osmnx as ox
import networkx as nx
from geopy.geocoders import Nominatim
import pygame
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE
ox.config(use_cache=True, log_console=False)

# ---------- 1) Geocoding ----------
geolocator = Nominatim(user_agent="rota_pygame_app")
orig_address = "4100 George J. Bean Pkwy, Tampa, FL 33607"
dest_address = "3001 W Dr Martin Luther King Jr Blvd, Tampa, FL 33607"
loc_o = geolocator.geocode(orig_address)
loc_d = geolocator.geocode(dest_address)
if not loc_o or not loc_d:
  raise SystemExit("Erro: não foi possível geocodar os endereços.")
orig_point = (loc_o.latitude, loc_o.longitude)
dest_point = (loc_d.latitude, loc_d.longitude)

# ---------- 2) Get graph and route ----------
center = ((orig_point[0] + dest_point[0]) / 2, (orig_point[1] + dest_point[1]) / 2)
G = ox.graph_from_point(center, dist=3000, network_type='drive')
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

orig_node = ox.distance.nearest_nodes(G, orig_point[1], orig_point[0])
dest_node = ox.distance.nearest_nodes(G, dest_point[1], dest_point[0])

# heuristic admissible: great-circle (meters)
def heuristic(u, v):
  y1, x1 = G.nodes[u]['y'], G.nodes[u]['x']
  y2, x2 = G.nodes[v]['y'], G.nodes[v]['x']
  return ox.distance.great_circle_vec(y1, x1, y2, x2)

path = nx.astar_path(G, orig_node, dest_node, heuristic=heuristic, weight='length')

# ---------- 3) Project graph to metric CRS (so coords are in meters/x,y) ----------
G_proj = ox.project_graph(G)
# get route nodes coords in projected CRS
route_xy = [(G_proj.nodes[n]['x'], G_proj.nodes[n]['y']) for n in path]

# For a nicer display, also extract a subset of edges to draw (the whole graph in area)
# get nodes and edges bounding box
xs = [d['x'] for _, d in G_proj.nodes(data=True)]
ys = [d['y'] for _, d in G_proj.nodes(data=True)]
minx, maxx = min(xs), max(xs)
miny, maxy = min(ys), max(ys)

# ---------- 4) Transform projected coords -> screen coords ----------
SCREEN_W, SCREEN_H = 1000, 700
MARGIN = 40

def compute_transform(minx, maxx, miny, maxy, screen_w, screen_h, margin):
  width = maxx - minx
  height = maxy - miny
  # scale to fit screen keeping aspect ratio
  sx = (screen_w - 2 * margin) / width if width != 0 else 1.0
  sy = (screen_h - 2 * margin) / height if height != 0 else 1.0
  s = min(sx, sy)
  def proj(pt):
    x, y = pt
    screen_x = (x - minx) * s + margin
    # invert y for screen coordinates (pygame origin top-left)
    screen_y = screen_h - ((y - miny) * s + margin)
    return int(screen_x), int(screen_y)
  return proj, s

proj_fn, scale = compute_transform(minx, maxx, miny, maxy, SCREEN_W, SCREEN_H, MARGIN)

# Precompute edges to draw (as sequences of screen points)
edges_to_draw = []
for u, v, key, data in G_proj.edges(keys=True, data=True):
  uxy = (G_proj.nodes[u]['x'], G_proj.nodes[u]['y'])
  vxy = (G_proj.nodes[v]['x'], G_proj.nodes[v]['y'])
  pu = proj_fn(uxy)
  pv = proj_fn(vxy)
  edges_to_draw.append((pu, pv))

route_screen = [proj_fn(pt) for pt in route_xy]

# ---------- 5) Pygame visualization + simple animation ----------
pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Rota (A*) - Pygame + OSMnx")
clock = pygame.time.Clock()

# Animation along the route: parametric interpolation between consecutive nodes
# Build a list of points denser than nodes for smooth movement
def densify(points, step_m=5.0, proj_scale=scale):
  # points in projected coords (meters), but we transformed earlier to screen pixels.
  # to densify, operate in projected space then project to screen
  dens = []
  for i in range(len(points) - 1):
    x1, y1 = points[i]
    x2, y2 = points[i + 1]
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    nsteps = max(1, int(dist / step_m))
    for k in range(nsteps):
      t = k / nsteps
      dens.append((x1 + dx * t, y1 + dy * t))
  dens.append(points[-1])
  return dens

route_densified_proj = densify(route_xy, step_m=5.0)
route_densified_screen = [proj_fn(pt) for pt in route_densified_proj]

pos_index = 0
running = True

while running:
  for event in pygame.event.get():
    if event.type == QUIT:
      running = False
    if event.type == KEYDOWN and event.key == K_ESCAPE:
      running = False

  screen.fill((30, 30, 30))  # dark background

  # draw all streets (thin, muted)
  for a, b in edges_to_draw:
    pygame.draw.line(screen, (80, 80, 80), a, b, 1)

  # draw route as thicker line
  if len(route_screen) >= 2:
    pygame.draw.lines(screen, (50, 150, 255), False, route_screen, 4)

  # draw moving vehicle
  if pos_index < len(route_densified_screen):
    px, py = route_densified_screen[pos_index]
    pygame.draw.circle(screen, (255, 50, 50), (px, py), 8)
    pos_index += 1  # speed: 1 step per frame; ajuste se quiser mais rápido
  else:
    # stay at destination
    px, py = route_densified_screen[-1]
    pygame.draw.circle(screen, (50, 200, 50), (px, py), 8)

  # draw origin/destination markers
  orig_scr = proj_fn(route_xy[0])
  dest_scr = proj_fn(route_xy[-1])
  pygame.draw.circle(screen, (0, 200, 0), orig_scr, 6)
  pygame.draw.circle(screen, (200, 0, 0), dest_scr, 6)

  # HUD: simple text
  font = pygame.font.SysFont(None, 20)
  text = font.render(f"Nodes in route: {len(path)}  Steps: {pos_index}/{len(route_densified_screen)}", True, (200, 200, 200))
  screen.blit(text, (10, 10))

  pygame.display.flip()
  clock.tick(60)  # FPS

pygame.quit()
