import math
import osmnx as ox
import networkx as nx
from geopy.geocoders import Nominatim
import pygame
from pygame.locals import (
  QUIT, KEYDOWN, K_ESCAPE, K_PLUS, K_MINUS, K_EQUALS, K_a, K_d, K_w, K_s,
  K_LEFT, K_RIGHT, K_UP, K_DOWN, K_c,
  MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEMOTION
)

ox.config(use_cache=True, log_console=False)

#* Geocoding
# Utiliza o Nominatim (OpenStreetMap) para converter endereços em coordenadas (lat, lon)
geolocator = Nominatim(user_agent="rota_pygame_app")
orig_address = "4100 George J. Bean Pkwy, Tampa, FL 33607"
dest_address = "3001 W Dr Martin Luther King Jr Blvd, Tampa, FL 33607"

# O  geolocator funciona via requests HTTP, então cuidado com limites de uso
# (veja https://nominatim.org/release-docs/latest/api/Overview/)
loc_o = geolocator.geocode(orig_address)
loc_d = geolocator.geocode(dest_address)

# Verifica se geocoding foi bem-sucedido
if not loc_o or not loc_d:
  raise SystemExit("Erro: não foi possível geocodar os endereços.")

# coordenadas (lat, lon) da origem e destinos
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

# ---------- UI Palette (Waze-like) ----------
COL_BG = (26, 28, 32)          # fundo bem escuro
COL_ROAD_CASING = (37, 39, 45) # contorno das vias
COL_ROAD_INNER = (210, 213, 220)  # interior clarinho das vias
COL_PRIMARY_INNER = (225, 230, 240)
COL_ROUTE_OUTLINE = (245, 250, 255)
COL_ROUTE = (70, 150, 255)     # azul da rota
COL_TEXT = (230, 230, 235)
COL_MUTED = (140, 145, 155)
COL_START = (0, 210, 120)
COL_END = (235, 70, 70)
COL_VEHICLE = (70, 180, 255)

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
    return float(screen_x), float(screen_y)
  return proj, s

proj_fn, scale = compute_transform(minx, maxx, miny, maxy, SCREEN_W, SCREEN_H, MARGIN)

# Camera state (zoom/pan)
cam_zoom = 1.0
cam_off_x = 0.0
cam_off_y = 0.0

def apply_camera(px, py):
  cx, cy = SCREEN_W * 0.5, SCREEN_H * 0.5
  vx = (px - cx) * cam_zoom + cx + cam_off_x
  vy = (py - cy) * cam_zoom + cy + cam_off_y
  return int(vx), int(vy)

# Precompute edges as projected pairs and classify width
def classify_edge(data):
  hw = data.get('highway', 'residential')
  if isinstance(hw, list):
    hw = hw[0] if hw else 'residential'
  # largura base por tipo
  if hw in ('motorway', 'trunk'):
    return 6
  if hw in ('primary', 'secondary'):
    return 4
  if hw in ('tertiary', 'residential', 'unclassified', 'living_street'):
    return 2
  return 2

edges_proj = []  # (uxy, vxy, width, highway)
for u, v, key, data in G_proj.edges(keys=True, data=True):
  uxy = (G_proj.nodes[u]['x'], G_proj.nodes[u]['y'])
  vxy = (G_proj.nodes[v]['x'], G_proj.nodes[v]['y'])
  w = classify_edge(data)
  hw = data.get('highway', 'residential')
  if isinstance(hw, list):
    hw = hw[0] if hw else 'residential'
  edges_proj.append((uxy, vxy, w, hw))

route_screen_base = [proj_fn(pt) for pt in route_xy]

# ---------- 5) Pygame visualization + simple animation ----------
pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Rota (A*) - Pygame + OSMnx")
clock = pygame.time.Clock()
font_small = pygame.font.SysFont(None, 18)
font = pygame.font.SysFont(None, 22)
font_bold = pygame.font.SysFont(None, 26)

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
route_densified_screen_base = [proj_fn(pt) for pt in route_densified_proj]

# Route stats
def compute_route_stats(G, path):
  total_len = 0.0
  total_time = 0.0
  for u, v in zip(path[:-1], path[1:]):
    data = min(G.get_edge_data(u, v).values(), key=lambda d: d.get('length', 0))
    total_len += data.get('length', 0.0)
    total_time += data.get('travel_time', 0.0)
  return total_len, total_time

total_len_m, total_time_s = compute_route_stats(G, path)
def fmt_km(m):
  return f"{m/1000:.1f} km" if m >= 1000 else f"{int(m)} m"

def fmt_eta(s):
  m = int(round(s/60))
  if m < 60:
    return f"{m} min"
  h = m // 60
  mm = m % 60
  return f"{h} h {mm} min"

def draw_rounded_rect(surface, rect, color, radius=12, border=0, border_color=(0,0,0)):
  pygame.draw.rect(surface, border_color, rect, border_radius=radius) if border>0 else None
  inner = pygame.Rect(rect)
  if border>0:
    inner.inflate_ip(-2*border, -2*border)
  pygame.draw.rect(surface, color, inner, border_radius=max(0, radius- (border>0)))

def draw_top_bar(surface, title):
  # barra superior com efeito de translucidez
  bar_h = 60
  overlay = pygame.Surface((SCREEN_W, bar_h), pygame.SRCALPHA)
  overlay.fill((20, 22, 26, 220))
  surface.blit(overlay, (0, 0))
  # pseudo search box
  box = pygame.Rect(16, 12, SCREEN_W-32, 36)
  draw_rounded_rect(surface, box, (40,43,50), radius=12)
  txt = font.render(title, True, COL_TEXT)
  surface.blit(txt, (box.x+12, box.y+8))

def draw_bottom_sheet(surface, lines):
  h = 110
  overlay = pygame.Surface((SCREEN_W, h), pygame.SRCALPHA)
  overlay.fill((20, 22, 26, 220))
  surface.blit(overlay, (0, SCREEN_H-h))
  box = pygame.Rect(12, SCREEN_H-h+8, SCREEN_W-24, h-16)
  draw_rounded_rect(surface, box, (40,43,50), radius=14)
  y = box.y + 10
  for ln in lines:
    surface.blit(font, (0,0)) if False else None
    t = font.render(ln, True, COL_TEXT)
    surface.blit(t, (box.x+12, y))
    y += 26

def draw_polyline_with_casing(surface, pts_proj, width, inner_color, casing_color):
  # map pontos projetados -> base screen -> camera
  pts = [apply_camera(*proj_fn(p)) for p in pts_proj]
  if len(pts) < 2:
    return
  # casing (mais grosso)
  pygame.draw.lines(surface, casing_color, False, pts, max(1, width+4))
  # inner
  pygame.draw.lines(surface, inner_color, False, pts, width)

def draw_segment_with_casing(surface, p1_proj, p2_proj, width, inner_color, casing_color):
  a = apply_camera(*proj_fn(p1_proj))
  b = apply_camera(*proj_fn(p2_proj))
  pygame.draw.line(surface, casing_color, a, b, max(1, width+4))
  pygame.draw.line(surface, inner_color, a, b, width)

curr_heading = None
HEADING_LOOKAHEAD = 15
HEADING_ALPHA = 0.15  # suavização (0-1)
# Offset opcional para calibrar o triângulo do veículo (radianos). Ajuste para +-math.pi/2 se notar rotação de 90°.
ANGLE_OFFSET = 0.0

def get_target_heading(idx):
  if len(route_densified_proj) < 2:
    return 0.0
  i0 = max(0, min(idx, len(route_densified_proj)-1))
  i1 = max(0, min(idx + HEADING_LOOKAHEAD, len(route_densified_proj)-1))
  x1, y1 = route_densified_proj[i0]
  x2, y2 = route_densified_proj[i1]
  dx, dy = x2 - x1, y2 - y1
  if abs(dx) < 1e-6 and abs(dy) < 1e-6:
    return None
  return math.atan2(dy, dx)

def angle_lerp(current, target, alpha):
  # interpola levando em conta wrap de -pi a pi
  if current is None:
    return target
  if target is None:
    return current
  delta = (target - current + math.pi) % (2*math.pi) - math.pi
  return current + alpha * delta

def draw_vehicle(surface, pos_idx):
  global curr_heading
  if pos_idx >= len(route_densified_proj):
    pos_idx = len(route_densified_proj)-1
  # posição na tela
  ps = apply_camera(*proj_fn(route_densified_proj[pos_idx]))
  # orientação suavizada
  target = get_target_heading(pos_idx)
  curr_heading = angle_lerp(curr_heading, target, HEADING_ALPHA)
  ang = curr_heading if curr_heading is not None else (target or 0.0)
  # Ajuste para sistema de tela (eixo Y invertido): ângulo de tela = -ang + offset
  ang_screen = -ang + ANGLE_OFFSET
  size = 12
  pts = [
    (ps[0] + math.cos(ang_screen)*size,     ps[1] + math.sin(ang_screen)*size),
    (ps[0] + math.cos(ang_screen+2.5)*size*0.7, ps[1] + math.sin(ang_screen+2.5)*size*0.7),
    (ps[0] + math.cos(ang_screen-2.5)*size*0.7, ps[1] + math.sin(ang_screen-2.5)*size*0.7),
  ]
  pygame.draw.polygon(surface, COL_VEHICLE, [(int(x), int(y)) for x,y in pts])
  pygame.draw.polygon(surface, COL_ROUTE_OUTLINE, [(int(x), int(y)) for x,y in pts], 2)

pos_index = 0
running = True
dragging = False
last_mouse = (0, 0)

while running:
  for event in pygame.event.get():
    if event.type == QUIT:
      running = False
    if event.type == KEYDOWN and event.key == K_ESCAPE:
      running = False
    if event.type == KEYDOWN:
      # Zoom
      if event.key in (K_PLUS, K_EQUALS):
        cam_zoom = min(3.0, cam_zoom * 1.15)
      if event.key == K_MINUS:
        cam_zoom = max(0.5, cam_zoom / 1.15)
      # Center on vehicle
      if event.key == K_c:
        # centraliza no veículo atual
        if pos_index < len(route_densified_proj):
          vx, vy = proj_fn(route_densified_proj[pos_index])
        else:
          vx, vy = proj_fn(route_densified_proj[-1])
        cx, cy = SCREEN_W*0.5, SCREEN_H*0.5
        # resolver offset para que apply_camera(vx,vy) == (cx,cy)
        cam_off_x = cx - (vx - cx) * cam_zoom - cx
        cam_off_y = cy - (vy - cy) * cam_zoom - cy
    # Mouse drag pan
    if event.type == MOUSEBUTTONDOWN and event.button == 1:
      dragging = True
      last_mouse = event.pos
    if event.type == MOUSEBUTTONUP and event.button == 1:
      dragging = False
    if event.type == MOUSEMOTION and dragging:
      mx, my = event.pos
      lx, ly = last_mouse
      dx, dy = mx - lx, my - ly
      cam_off_x += dx
      cam_off_y += dy
      last_mouse = (mx, my)
    # Mouse wheel zoom com ancoragem no cursor
    if event.type == pygame.MOUSEWHEEL:
      # fator de zoom
      zoom_factor = 1.1 ** event.y
      new_zoom = max(0.5, min(3.5, cam_zoom * zoom_factor))
      if abs(new_zoom - cam_zoom) > 1e-6:
        mx, my = pygame.mouse.get_pos()
        cx, cy = SCREEN_W*0.5, SCREEN_H*0.5
        # ponto base sob o cursor antes do zoom
        base_x = cx + (mx - cx - cam_off_x) / cam_zoom
        base_y = cy + (my - cy - cam_off_y) / cam_zoom
        cam_zoom = new_zoom
        # ajuste offset para manter (mx,my) no mesmo ponto do mapa
        cam_off_x = mx - (base_x - cx) * cam_zoom - cx
        cam_off_y = my - (base_y - cy) * cam_zoom - cy

  # pan com teclas pressionadas
  keys = pygame.key.get_pressed()
  pan_speed = 8
  if keys[K_LEFT] or keys[K_a]:
    cam_off_x += pan_speed
  if keys[K_RIGHT] or keys[K_d]:
    cam_off_x -= pan_speed
  if keys[K_UP] or keys[K_w]:
    cam_off_y += pan_speed
  if keys[K_DOWN] or keys[K_s]:
    cam_off_y -= pan_speed

  screen.fill(COL_BG)  # dark background

  # draw all streets (LOD + thickness dependente do zoom)
  for (pa, pb, w, hw) in edges_proj:
    # filtra ruas menores quando afastado para evitar poluição visual
    if cam_zoom < 0.8 and hw in ('residential', 'living_street', 'service', 'unclassified', 'tertiary'):
      continue
    if cam_zoom < 0.65 and hw in ('secondary',):
      continue
    width_px = max(1, min(12, int(w * cam_zoom)))
    draw_segment_with_casing(screen, pa, pb, width_px, COL_ROAD_INNER, COL_ROAD_CASING)

  # draw route as thicker line
  if len(route_xy) >= 2:
    # contorno claro + rota azul (espessura também escala levemente)
    route_w = max(3, min(10, int(6 * cam_zoom)))
    draw_polyline_with_casing(screen, route_xy, route_w, COL_ROUTE, COL_ROUTE_OUTLINE)

  # draw moving vehicle
  if pos_index < len(route_densified_screen_base):
    draw_vehicle(screen, pos_index)
    pos_index += 1  # speed: 1 step per frame; ajuste se quiser mais rápido
  else:
    # stay at destination
    draw_vehicle(screen, len(route_densified_screen_base)-1)

  # draw origin/destination markers
  orig_scr = apply_camera(*proj_fn(route_xy[0]))
  dest_scr = apply_camera(*proj_fn(route_xy[-1]))
  pygame.draw.circle(screen, COL_ROUTE_OUTLINE, orig_scr, 9)
  pygame.draw.circle(screen, COL_START, orig_scr, 7)
  pygame.draw.circle(screen, COL_ROUTE_OUTLINE, dest_scr, 9)
  pygame.draw.circle(screen, COL_END, dest_scr, 7)

  # HUD: simple text
  draw_top_bar(screen, f"Rota: {orig_address} -> {dest_address}")
  stats = [
    f"{fmt_eta(total_time_s)} • {fmt_km(total_len_m)}",
    f"Nós da rota: {len(path)}  •  Passos: {pos_index}/{len(route_densified_screen_base)}",
    "Controles: +/- zoom  •  Setas/WASD pan  •  C centralizar"
  ]
  draw_bottom_sheet(screen, stats)

  pygame.display.flip()
  clock.tick(60)  # FPS

pygame.quit()