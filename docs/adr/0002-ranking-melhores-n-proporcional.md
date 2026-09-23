# Ranking por "melhores N" proporcional, com elegibilidade por presença

O Ranking de um Recorte soma apenas os melhores 75% dos Resultados de cada jogador no período (arredondando para cima), e só concorre ao pódio quem teve Participação em pelo menos 50% dos Torneios Válidos do Recorte. Um Recorte só elege campeão se tiver ao menos 3 Torneios Válidos.

Alternativas consideradas: **soma simples** (favorece quem aparece todos os domingos, não quem joga melhor, e ignora quem entra tarde no ano); **média por participação** (pune quem joga muito); **pontos de colocação** (recria uma pontuação que o Lichess já entrega pronta e oficial).

Os dois parâmetros — fração do "melhores N" e piso de presença — são de configuração e podem ser calibrados sem reprocessar dados. Como alteram o Ranking, devem permanecer estáveis dentro de uma Temporada.
