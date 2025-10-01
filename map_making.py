import osmnx as ox
import networkx as nx
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium

ox.settings.log_console = False
ox.settings.use_cache = True

def heuristic(u, v, Graph):
  # Usa distância geodésica (metros) entre os nodos u e v
  y1 = Graph.nodes[u]['y']; x1 = Graph.nodes[u]['x']
  y2 = Graph.nodes[v]['y']; x2 = Graph.nodes[v]['x']
  
  return ox.distance.great_circle_vec(y1, x1, y2, x2)

def safe_geocode(address, geolocator, geocode_fn, timeout=10):
  """Tenta geocodificar: primeiro geopy (RateLimiter), depois fallback para osmnx.geocode."""
  try:
    # geopy RateLimiter - evita 429 Too Many Requests
    geocode_rate_limited = RateLimiter(geocode_fn, min_delay_seconds=1, max_retries=2, error_wait_seconds=2.0)
    res = geocode_rate_limited(address, timeout=timeout)
    if res:
      # geopy retorna um objeto com latitude/longitude
      if hasattr(res, 'latitude') and hasattr(res, 'longitude'):
        return (res.latitude, res.longitude)
      # osmnx.geocode (quando passada diretamente) pode retornar (lat, lon) tuple
      if isinstance(res, (tuple, list)) and len(res) >= 2:
        return (float(res[0]), float(res[1]))
  except Exception as e:
    print(f"[safe_geocode] geopy falhou para '{address}': {e}")
  
  # fallback para osmnx.geocode (usa o provedor interno — também pode levantar exceção)
  try:
    print(f"[safe_geocode] Tentando fallback osmnx.geocode para '{address}'")
    pt = ox.geocoder.geocode(address)  # retorna (lat, lon)
    if pt and isinstance(pt, (tuple, list)) and len(pt) >= 2:
      return (float(pt[0]), float(pt[1]))
  except Exception as e:
    print(f"[safe_geocode] osmnx.geocode falhou para '{address}': {e}")
  
  return None

def create_graph(orig_address, dest_address, route_type):
  # Cria o grafo da área entre os dois endereços
  geolocator = Nominatim(user_agent="app_rotas")
  
  # Busca as coordenadas dos endereços requeridos
  orig_coords = safe_geocode(orig_address, geolocator, geolocator.geocode)
  dest_coords = safe_geocode(dest_address, geolocator, geolocator.geocode)
  
  # print(f"Origem: {local_orig}, Destino: {local_dest}")
  
  # Verifica se os endereços foram encontrados
  # if local_orig is None or local_dest is None:
  #   raise ValueError("Endereço de origem ou destino inválido.")
  
  # Obtém as coordenadas dos endereços (latitude e longitude)
  # orig_coords = (local_orig.lat, local_orig.lon)
  # dest_coords = (local_dest.lat, local_dest.lon)
  
  # Define o ponto central entre os dois endereços (Origem, Destino)
  # Pelas coordenadas, fazemos a média para encontrar o ponto central
  center = ((orig_coords[0] + dest_coords[0]) / 2, (orig_coords[1] + dest_coords[1]) / 2)
  
  # Cria o grafo da área ao redor do ponto central
  # A distância (dist) é em metros
  graph = ox.graph_from_point(center, dist=10000, network_type=route_type, simplify=True)
  
  return graph, orig_coords, dest_coords, center

def Astar_route(graph, orig_coords, dest_coords):

  # Encontra o nó mais próximo das coordenadas de origem e destino
  orig_node = ox.distance.nearest_nodes(graph, orig_coords[1], orig_coords[0])
  dest_node = ox.distance.nearest_nodes(graph, dest_coords[1], dest_coords[0])
  
  # Calcula a rota usando o algoritmo A* da biblioteca NetworkX
  # "route" é uma lista de nós que compõem o caminho mais curto por meio do grafo
  # O peso de cada aresta é definido pelo atributo 'length' (comprimento em metros)
  route = nx.astar_path(graph, orig_node, dest_node, heuristic=lambda u, v: heuristic(u, v, graph), weight='length')
  
  return route

def plot_route(graph, route, orig_coords, dest_coords, center):
  try:
    graph = ox.add_edge_speeds(graph)         # adiciona 'speed_kph' (quando possível)
  except Exception as e:
    print("add_edge_speeds falhou:", e)
  
  # criar travel_time se possível
  try:
    graph = ox.add_edge_travel_times(graph)   # adiciona 'travel_time' quando tem 'length' e 'speed_kph'
  except Exception as e:
    print("add_edge_travel_times falhou:", e)

  # Como reforço: garanta que todas as arestas tenham 'speed_kph' e 'travel_time'
  DEFAULT_KPH = 30.0
  for u, v, k, data in graph.edges(keys=True, data=True):
    if 'speed_kph' not in data or data.get('speed_kph') in (None, 0):
      # tente extrair de maxspeed
      maxs = data.get('maxspeed')
      if isinstance(maxs, str):
        import re
        m = re.search(r'(\d+(\.\d+)?)', maxs)
        if m:
          data['speed_kph'] = float(m.group(1))
        else:
          data['speed_kph'] = DEFAULT_KPH
      elif isinstance(maxs, (int, float)):
        data['speed_kph'] = float(maxs)
      else:
        data['speed_kph'] = DEFAULT_KPH
    
    if 'travel_time' not in data or data.get('travel_time') in (None, 0):
      length_m = data.get('length', 0.0)
      sp = data.get('speed_kph', DEFAULT_KPH)
      data['travel_time'] = float(length_m * 3.6 / float(sp))
  
  # Helper local para obter atributos das arestas da rota (substitui utils_graph.get_route_edge_attributes)
  def get_route_edge_attributes(G, route_nodes, attr):
    valores = []
    for u, v in zip(route_nodes[:-1], route_nodes[1:]):
      # Pode haver múltiplas arestas paralelas (multidigraph)
      if G.has_edge(u, v):
        edge_data = G.get_edge_data(u, v)
        # edge_data é um dict (key->data) em MultiDiGraph
        if isinstance(edge_data, dict):
          # pega a primeira variante que tiver o atributo
            # garante ordem estável
          for k in sorted(edge_data.keys()):
            data = edge_data[k]
            if attr in data:
              valores.append(data[attr])
              break
        else:
          # Graph simples
          if attr in edge_data:
            valores.append(edge_data[attr])
    return valores

  # Calcula o comprimento total da rota (em metros) e o tempo estimado de viagem (em segundos)
  route_length = sum(get_route_edge_attributes(graph, route, 'length'))
  route_time = sum(get_route_edge_attributes(graph, route, 'travel_time'))
  
  # Gera uma lista de coordenadas (latitude, longitude) para cada nó na rota
  route_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in route]
  
  # Criar o mapa centralizado no ponto médio com o Folium
  map = folium.Map(location=center, zoom_start=14)
  
  # Configura os marcadores de origem e destino e a linha da rota
  folium.Marker(orig_coords, popup="Origem", icon=folium.Icon(color='green')).add_to(map)
  folium.Marker(dest_coords, popup="Destino", icon=folium.Icon(color='red')).add_to(map)
  folium.PolyLine(route_coords, color="blue", weight=5, opacity=0.8).add_to(map)
  
  folium.map.Marker(
    route_coords[len(route_coords)//2],
    icon=folium.DivIcon(html=f"<div style='font-size:12px;background:white;padding:4px;border-radius:4px;'>"
                        f"Dist: {route_length:.0f} m • Tempo: {route_time/60:.1f} min</div>")
  )
  
  map.save("route_map.html")
  print("Mapa salvo como 'route_map.html'")