# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- Pacote Python instalável, com o comando de linha de comando `ccc-arena`.
- Descoberta e classificação de candidatos a Torneio Válido (`ccc-arena discover`), varrendo as arenas do time e as arenas criadas pelos organizadores configurados.
- Porta única de acesso ao Lichess, com adaptador HTTP de produção (uma requisição por vez e recuo exponencial em `429`) e adaptador de fixtures gravadas da API real nos testes.
- Classificação pura de Torneio Válido, com as oito checagens do spec e a evidência das que passaram e falharam.
- Arquivamento dos Torneios Válidos (`ccc-arena collect`): Classificação final, PGN e metadados no arquivo canônico do [ADR-0001](docs/adr/0001-arquivo-canonico-no-repositorio.md), com a contagem de partidas derivada do `sheet`.
- Relatório de pendências versionado (`archive/pendencias.json`): candidatos que falham checagens, Torneios Válidos fora de Temporada e anomalias de Edição.
- Correções manuais de escopo: `exclude` tira um torneio que casaria com as regras; `include` arquiva um que falharia, marcando `validation.override`.
- Atualização explícita (`ccc-arena refresh <id>` e `ccc-arena refresh-all`): rebaixa e reescreve torneios arquivados; sem pedido explícito, a coleta de rotina não altera o que já existe.
- Ranking da Temporada (`ccc-arena rank`): soma dos melhores N proporcionais, elegibilidade por presença e os três desempates na ordem, com os valores que tornam a ordem explicável.
- Recortes de mês e semestre (`ccc-arena rank --month`/`--semester`), recortados pela janela da Temporada e ancorados no fuso de referência.
- Aliases no Ranking: usernames da mesma pessoa somam um único jogador, numa única linha que exibe todas as usernames. A tabela vive em `aliases.json` e vale ao recalcular, sem recoletar.
- Site estático (`ccc-arena site`): a página da Temporada, pré-renderizada a partir dos dados derivados, com o Ranking, o pódio, a decomposição de cada jogador (contados, descartados, total) e a explicação das regras com os valores correntes. Os dados derivados em JSON são publicados junto; a página lê só o arquivo e nunca a API do Lichess.
- Páginas de Torneios e Jogadores: a lista de Torneios Válidos com data, jogadores e vencedor; a Classificação final de cada Torneio, com score e Performance; e a página de cada jogador com todos os seus Resultados. A navegação liga Ranking, Torneios e Jogadores nos dois sentidos, e o jogador com alias aparece consolidado.
- Recortes no site: uma página e um JSON por mês e por semestre com ao menos um Torneio Válido na Temporada, com o N e a presença próprios de cada janela. A página da Temporada lista os Recortes, e cada Recorte volta para ela.
- Automação semanal: um workflow do GitHub Actions roda após a arena de domingo (e por disparo manual), coleta os Torneios Válidos, regenera o site, commita o arquivo quando muda e publica a página no GitHub Pages.
- Janela de Temporada no fuso de referência (módulo `season`), com o início e o fim inclusivos.
- Validação dos quatro arquivos de configuração, acumulando todos os problemas e apontando o arquivo e o campo de cada um.
- Arquivos de configuração com os padrões da Temporada 2026: fuso `America/Sao_Paulo`, time `cavaleiros-do-centro`, melhores 75%, presença mínima de 50% e mínimo de 3 torneios para eleger campeão.
- Ambiente reprodutível em Docker, com `Dockerfile`, `docker-compose.yml` e alvos `make` para `build`, `check`, `collect`, `test` e `shell`.
- Suíte de testes do validador de configuração.
- Licença MIT e Código de Conduta.

### Corrigido

- O `editionPattern` padrão passou a ignorar caixa, para reconhecer os nomes reais das edições antigas ("Ed", "ed", "Edição") e não só os novos.
- O Ranking ignorava o total ao ordenar: usava só os critérios de desempate, o que colocava quem somou mais pontos atrás de quem somou menos. Agora o total é o critério primário e os desempates só desempatam — inclusive na escolha do campeão.

### Notas

- Nenhuma versão foi publicada ainda: tudo o que está listado acima está em desenvolvimento.
- A Temporada 2026 apura o ano inteiro (2026-01-01 a 2026-12-31). Três torneios antigos que não casavam com as regras entram por `include` (`KRHH63Yz`, `KPfmJoD9`, `6ehIpwWG`), sem afrouxar as regras para os torneios futuros (ver [ADR-0004](docs/adr/0004-temporada-com-janela-explicita.md)).
- O site está no ar em <https://matheuslao.github.io/ccc-arena-results/>, e o workflow semanal passa a mantê-lo atualizado sozinho.
