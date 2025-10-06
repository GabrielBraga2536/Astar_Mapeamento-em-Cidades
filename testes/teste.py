import osmnx as ox
import geopandas as gpd
import pandas as pd
import networkx as nx
from shapely.geometry import Point
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Configurações globais do osmnx
ox.settings.use_cache = True
ox.settings.log_console = False


# -----------------------------
# Funções auxiliares
# -----------------------------
def ensure_gdf(x):
    """Garante que retornamos um GeoDataFrame."""
    if x is None:
        return gpd.GeoDataFrame()
    if isinstance(x, gpd.GeoDataFrame):
        return x
    if isinstance(x, pd.DataFrame):
        if 'geometry' not in x.columns and 'lat' in x.columns and 'lon' in x.columns:
            x = x.copy()
            x['geometry'] = x.apply(lambda r: Point(r['lon'], r['lat']), axis=1)
            return gpd.GeoDataFrame(x, geometry='geometry', crs="EPSG:4326")
        return gpd.GeoDataFrame(x, geometry='geometry') if 'geometry' in x.columns else gpd.GeoDataFrame(x)
    if isinstance(x, list):
        if len(x) == 0:
            return gpd.GeoDataFrame()
        if isinstance(x[0], dict):
            df = pd.DataFrame(x)
            if 'lat' in df.columns and 'lon' in df.columns:
                df['geometry'] = df.apply(lambda r: Point(r['lon'], r['lat']), axis=1)
                return gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
            if 'geometry' in df.columns:
                return gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
        try:
            if hasattr(x[0], 'geom_type'):
                return gpd.GeoDataFrame(geometry=x, crs="EPSG:4326")
        except Exception:
            pass
    return gpd.GeoDataFrame()


def geocode_candidates(address, country_codes='br', max_candidates=5):
    """Usa Nominatim para pegar candidatos de geocodificação."""
    geolocator = Nominatim(user_agent="meu_app_endereco")
    geocode_rl = RateLimiter(geolocator.geocode, min_delay_seconds=1, max_retries=2)
    try:
        results = geocode_rl(address, exactly_one=False, limit=max_candidates, addressdetails=True, country_codes=country_codes)
    except Exception as e:
        print("geopy erro:", e)
        results = None
    candidates = []
    if results:
        for r in results:
            raw = getattr(r, 'raw', {}) or {}
            candidates.append({
                'lat': float(getattr(r, 'latitude', raw.get('lat', None)) or 0.0),
                'lon': float(getattr(r, 'longitude', raw.get('lon', None)) or 0.0),
                'display_name': raw.get('display_name') or str(r),
                'raw': raw
            })
    return candidates


def find_exact_address_point(place_name, street_name, housenumber):
    """Busca no OSM por features com addr:housenumber e addr:street."""
    tags = {'addr:housenumber': housenumber, 'addr:street': street_name}
    try:
        gdf = ox.geometries_from_place(place_name, tags)
    except Exception as e:
        print("Erro ao consultar Overpass:", e)
        return []
    
    if gdf is None or gdf.empty:
        return []
    
    results = []
    for idx, row in gdf.iterrows():
        geometry = row.geometry
        if geometry is None:
            continue
        if geometry.geom_type == 'Point':
            lon = float(geometry.x)
            lat = float(geometry.y)
        else:
            c = geometry.centroid
            lon = float(c.x)
            lat = float(c.y)
        housenum = row.get('addr:housenumber') if 'addr:housenumber' in row.index else None
        street = row.get('addr:street') if 'addr:street' in row.index else row.get('name')
        results.append({
            'lat': lat,
            'lon': lon,
            'housenumber': housenum,
            'street': street,
            'geom_type': geometry.geom_type
        })
    return results


def find_addresses_by_street(place_name, street_name):
    """Procura todas as geometrias que contenham addr:street=<street_name>."""
    tags = {'addr:street': street_name}
    try:
        gdf = ox.geometries_from_place(place_name, tags)
        return gdf
    except Exception as e:
        print("Erro Overpass/osmnx:", e)
        return gpd.GeoDataFrame()


# -----------------------------
# Funções de rota
# -----------------------------
def get_route_graph(place, orig_point, dest_point):
    """Baixa o grafo da cidade e retorna rota mais curta."""
    G = ox.graph_from_place(place, network_type="drive")
    orig_node = ox.distance.nearest_nodes(G, orig_point[1], orig_point[0])  # (lon, lat)
    dest_node = ox.distance.nearest_nodes(G, dest_point[1], dest_point[0])
    route = nx.shortest_path(G, orig_node, dest_node, weight="length")
    return G, route


def plot_route(G, route):
    """Plota o grafo com a rota em destaque."""
    ox.plot_graph_route(G, route, node_size=0, bgcolor="white")


# -----------------------------
# Exemplo de uso
# -----------------------------
if __name__ == "__main__":
    place = "Santos, Brazil"
    orig = "Avenida Doutor Pedro Lessa, 1111, Santos, Brazil"
    dest = "Rua Bolívia, 89, Santos, Brazil"

    # 1) Geocoding
    orig_candidates = geocode_candidates(orig)
    dest_candidates = geocode_candidates(dest)
    print("Origem candidatos:", orig_candidates)
    print("Destino candidatos:", dest_candidates)

    # Pega o primeiro candidato como fallback
    orig_point = (orig_candidates[0]['lat'], orig_candidates[0]['lon']) if orig_candidates else None
    dest_point = (dest_candidates[0]['lat'], dest_candidates[0]['lon']) if dest_candidates else None

    # 2) Tenta achar exato no OSM
    exact_orig = find_exact_address_point(place, "Avenida Doutor Pedro Lessa", "1111")
    if exact_orig:
        orig_point = (exact_orig[0]['lat'], exact_orig[0]['lon'])
    exact_dest = find_exact_address_point(place, "Rua Bolívia", "89")
    if exact_dest:
        dest_point = (exact_dest[0]['lat'], exact_dest[0]['lon'])

    print("Origem final:", orig_point)
    print("Destino final:", dest_point)

    # 3) Gera grafo e rota
    if orig_point and dest_point:
        G, route = get_route_graph(place, orig_point, dest_point)
        print("Rota encontrada com", len(route), "nós.")
        plot_route(G, route)
    else:
        print("Não foi possível determinar origem/destino.")
