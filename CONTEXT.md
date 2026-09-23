# Arena dos Cavaleiros — Resultados

Contexto que transforma as arenas semanais do time **Cavaleiros do Centro** no Lichess em um histórico de resultados e em rankings de temporada que a comunidade possa consultar e celebrar.

## Language

**Torneio**:
Uma arena do Lichess com id próprio, data de início, ritmo e classificação final. É o dado bruto, coletado do Lichess.
_Avoid_: partida, jogo, evento

**Edição**:
O número de ordem de um Torneio Válido na série contínua do grupo (ex.: "16ª edição").
_Avoid_: rodada, etapa, fase

**Torneio Válido**:
Um Torneio que satisfaz as condições da Temporada: arena do time Cavaleiros do Centro, restrita a membros, com 1 hora de duração e nome no padrão "Arena dos Cavaleiros". Só Torneios Válidos entram no Ranking.
_Avoid_: torneio oficial, competição

**Temporada**:
O período apurado, com início e fim explícitos e configuráveis. É a unidade oficial do pódio.
_Avoid_: ano, campeonato, liga, circuito

**Recorte**:
Uma janela de calendário (mês ou semestre) dentro de uma Temporada, sobre a qual se calcula um Ranking próprio. É sempre uma leitura da mesma base, nunca um estado paralelo.
_Avoid_: temporada mensal, temporada semestral

**Resultado**:
A pontuação final oficial de um jogador em um Torneio — o score da Arena do Lichess, já com bônus de Berserk e de sequência de vitórias. Não é recalculado por nós.
_Avoid_: nota, pontos

**Classificação**:
A posição final de um jogador em um Torneio, com sua pontuação e performance, na ordem publicada pelo Lichess.
_Avoid_: tabela, resultado do torneio

**Performance**:
A rating de desempenho do jogador no Torneio, publicada pelo Lichess. É o desempate dentro de um Torneio; para nós serve como critério de desempate entre Torneios.
_Avoid_: rating, elo

**Ranking**:
A ordenação dos jogadores em uma Temporada ou Recorte, somando os melhores N Resultados de cada um, com desempates.
_Avoid_: placar, leaderboard, pontuação da temporada

**Participação**:
A presença de um jogador em um Torneio Válido. Como o Torneio é restrito ao time, jogar implica ter sido membro do time naquela data.
_Avoid_: inscrição, presença, adesão

**Alias**:
Usuários do Lichess que são a mesma pessoa (ex.: troca de nick). Mapeados manualmente; o Ranking trata todos os aliases de uma pessoa como um único jogador.
_Avoid_: conta, perfil

**Elegibilidade ao Pódio**:
A condição de um jogador poder figurar no pódio de um Recorte: ter Participação suficiente no Recorte, além de constar no Ranking.
_Avoid_: habilitado, classificado

**Melhores N**:
A regra de agregação do Ranking: contam apenas os N melhores Resultados do jogador no período, com N proporcional ao número de Torneios Válidos do Recorte.
_Avoid_: descarte, corte
