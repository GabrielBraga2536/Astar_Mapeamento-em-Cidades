from map_making import create_graph, Astar_route, plot_route

def main():
  # orig_address = input("Digite o endereço de origem: ")
  # dest_address = input("Digite o endereço de destino: ")
  orig_address = "4100 George J. Bean Pkwy, Tampa, FL 33607"
  dest_address = "3001 W Dr Martin Luther King Jr Blvd, Tampa, FL 33607"
  # route_type = input("Digite o tipo de rota (walk, bike, drive): ").strip().lower()
  route_type = 'drive'
  
  if route_type not in ['walk', 'bike', 'drive']:
    print("Tipo de rota inválido. Usando 'drive' como padrão.")
    route_type = 'drive'
  
  graph, orig, dest, center = create_graph(orig_address, dest_address, route_type)
  best_route = Astar_route(graph, orig, dest)
  
  plot_route(graph, best_route, orig, dest, center)

if __name__ == "__main__":
  main()