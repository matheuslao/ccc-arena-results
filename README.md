# Arena dos Cavaleiros — Resultados

Sistematiza o acompanhamento da **Arena dos Cavaleiros**, o torneio semanal (domingo, 19h) da comunidade **Cavaleiros do Centro** no Lichess: coleta o resultado de cada edição, arquiva e deriva o Ranking da Temporada e dos Recortes (mês e semestre), numa página pública.

## Por que existe

Cada domingo gera uma classificação que fica isolada dentro do próprio torneio. Responder "quem está ganhando a temporada?" exige abrir torneio por torneio e somar na mão — e ainda decidir sozinho como comparar quem jogou doze domingos com quem jogou quatro. Sem histórico consolidado e sem regra explícita, não há como premiar os primeiros colocados com justiça, transparência e reprodutibilidade.

## Como funciona

O Python é o motor inteiro, rodando como **CLI** — não há servidor, banco de dados nem login (ver [ADR-0003](docs/adr/0003-sem-backend-no-mvp.md)).

1. **Coleta** — descobre os Torneios Válidos pela API do Lichess.
2. **Arquiva** — grava a Classificação final e os PGN no repositório.
3. **Deriva** — calcula o Ranking da Temporada, dos meses e dos semestres.
4. **Publica** — gera uma página estática a partir dos dados derivados.

O Lichess é a nascente; **este repositório é a fonte da verdade** (ver [ADR-0001](docs/adr/0001-arquivo-canonico-no-repositorio.md)).

## Estado atual

| Parte | Situação |
| --- | --- |
| Validação de configuração (`ccc-arena config check`) | pronto |
| Descoberta e classificação de candidatos (`ccc-arena discover`) | pronto |
| Arquivamento dos Torneios Válidos (`ccc-arena collect`) | pronto |
| Atualização e correções de escopo (`ccc-arena refresh`/`refresh-all`) | pronto |
| Ranking da Temporada (`ccc-arena rank`) | pronto |
| Ranking — Recortes (mês e semestre) | pronto |
| Aliases no Ranking | pronto |
| Site — Ranking da Temporada (`ccc-arena site`) | pronto |
| Site — Torneios e Jogadores | pronto |
| Site — Recortes (mês e semestre) | pronto |
| Automação semanal e publicação | pronto |

## Como rodar

Tudo roda em Docker.

```bash
make build    # constrói a imagem
make check    # valida os arquivos de configuração
make collect  # arquiva os Torneios Válidos ainda não arquivados
make site     # gera a página estática em ./site
make test     # roda a suíte de testes
make shell    # abre um shell no container
```

Sem o `make`:

```bash
docker compose run --rm cli                       # ccc-arena config check
docker compose run --rm cli ccc-arena discover    # candidatos a Torneio Válido (usa a API do Lichess)
docker compose run --rm cli ccc-arena collect     # arquiva os Torneios Válidos em ./archive
docker compose run --rm cli ccc-arena refresh-all # rebaixa os torneios arquivados
docker compose run --rm cli ccc-arena rank        # Ranking da Temporada
docker compose run --rm cli ccc-arena rank --month 2026-09   # Ranking de um Recorte
docker compose run --rm cli ccc-arena site        # gera a página estática em ./site
docker compose run --rm test                      # pytest
```

## Automação

Um workflow do GitHub Actions roda todo domingo à noite (20:30 em `America/Sao_Paulo`), logo após a arena, e também por disparo manual (`workflow_dispatch`). Ele coleta os Torneios Válidos, regenera a página e a publica no GitHub Pages; o arquivo em `archive/` é commitado quando muda, e nada é commitado quando não há torneio novo.

Para ligar isso uma vez no repositório:

1. **Settings → Pages → Source: GitHub Actions** — a publicação é feita pelo workflow, não por branch.
2. **Settings → Actions → General → Workflow permissions:** permitir leitura e escrita (o workflow precisa de `contents: write` para commitar o arquivo).

Uma queda do Lichess não derruba a página: a coleta é tentada, mas o site é regerado do arquivo já versionado.

## As regras do Ranking

- Só entram **Torneios Válidos**: arena do time, restrita a membros, com 1 hora de duração e nome no padrão "Arena dos Cavaleiros".
- **Melhores N**: conta apenas os melhores 75% dos Resultados do período.
- **Elegibilidade a prêmio**: presença em pelo menos 50% dos Torneios Válidos do período.
- **Recorte com menos de 3 torneios** não elege campeão.
- **Campeão** é o melhor jogador **elegível** — o título não vai para quem não tem presença suficiente.
- Desempate: mais primeiros lugares → melhor Resultado individual → mais torneios jogados.
- Correções manuais de escopo (`include`/`exclude`) vivem na configuração, não no arquivo.

Todos esses valores são **configuração, não código** — veja [`config/`](config/).

## Estrutura

```
config/                 as regras, como dado
src/ccc_arena_results/  o motor (CLI)
tests/                  a suíte de testes
docs/adr/               decisões de arquitetura
```

## Documentação

- [`CONTEXT.md`](CONTEXT.md) — o glossário do domínio. Todo mundo usa esses termos.
- [`docs/adr/`](docs/adr/) — as decisões que não são óbvias pelo código.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — como contribuir.
- [`CHANGELOG.md`](CHANGELOG.md) — o que mudou.

## Licença

[MIT](LICENSE) — use, copie e modifique à vontade.

Ao participar, você concorda com o [Código de Conduta](CODE_OF_CONDUCT.md).
