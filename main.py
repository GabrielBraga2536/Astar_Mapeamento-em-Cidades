import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString

G = ox.graph_from_place("Santos, Brasil", network_type="drive")
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

orig_point = (-23.561414, -46.655881)
dest_point = (-23.558861, -46.662527)

orig = ox.nearest_nodes(G, X=orig_point[1], Y=orig_point[0])
dest = ox.nearest_nodes(G, X=dest_point[1], Y=dest_point[0])

path = nx.shortest_path(G, orig, dest, weight="travel_time")
print("Nós na rota:", path)


edge_geoms = []

for u, v in zip(path[:-1], path[1:]):
  data = G.get_edge_data(u, v)
  # se houver multiedges, pega a primeira
  e = list(data.values())[0]
  geom = e.get("geometry")
  if geom is None:
    # criar LineString simples a partir das coordenadas dos nós
    pt_u = (G.nodes[u]["x"], G.nodes[u]["y"])
    pt_v = (G.nodes[v]["x"], G.nodes[v]["y"])
    geom = LineString([pt_u, pt_v])
  edge_geoms.append({"u": u, "v": v, "length": e.get("length"), "geometry": geom})
route_gdf = gpd.GeoDataFrame(edge_geoms, geometry="geometry", crs="EPSG:4326")

route_gdf.to_file("rota.geojson", driver="GeoJSON")
print("Rota salva em rota.geojson")