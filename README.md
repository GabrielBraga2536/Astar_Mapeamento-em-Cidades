# A* Mapeamento em Cidades

Projeto de pathfinding com OSMnx + NetworkX, exibido em uma interface Pygame.

## Requisitos

- Python 3.12+
- Dependências em `requirements.txt`

## Instalação

```bash
pip install -r requirements.txt
```

Se estiver no Windows e o Pygame reclamar do `pkg_resources`, é apenas um aviso de depreciação do setuptools, pode ser ignorado.

## Como executar

```bash
python main.py
```

## Teclado

- + / =: Zoom in
- -: Zoom out
- Setas ou WASD: Pan (arrastar o mapa)
- C: Centralizar a câmera no veículo
- ESC: Sair

### Mouse

- Botão esquerdo pressionado + arrastar: Pan
- Roda do mouse: Zoom ancorado no cursor

## Notas

- A barra superior mostra uma caixa de busca fictícia com o título da rota. O painel inferior exibe ETA e distância total, além de estatísticas da rota.
- As ruas são desenhadas com “casing” (contorno) e interior claro para melhor contraste no tema escuro; a rota ativa aparece em azul com contorno claro.
- A espessura e a densidade das vias se ajustam ao nível de zoom (LOD) para reduzir sobreposição quando afastado.
- A orientação do veículo é suavizada (lookahead + interpolação) para evitar oscilações bruscas.
- Endereços de origem/destino podem ser alterados no início do `teste_pygame.py`.