# Contribuindo

## Pré-requisitos

Docker e Docker Compose. Nada mais precisa estar instalado na sua máquina — o Python e as dependências vivem dentro da imagem.

## Rodando o projeto

```bash
make build   # constrói a imagem
make check   # valida os arquivos de configuração
make test    # roda a suíte de testes
make shell   # abre um shell no container
```

Se preferir falar direto com o Compose:

```bash
docker compose run --rm cli
docker compose run --rm test
```

## Escopo do trabalho

O [README](README.md) mostra o que já está pronto e o que ainda falta — é de lá que se tira o que fazer.

Antes de começar algo grande, combine no grupo: assim você não trabalha em algo que já está em andamento, nem em algo fora do escopo do MVP.

## Antes de escrever código

1. Leia o [`CONTEXT.md`](CONTEXT.md) e use o vocabulário dele. Se um conceito que você precisa não está lá, ou você está inventando linguagem que o projeto não usa, ou existe uma lacuna real — vale parar e conversar.
2. Leia os ADRs em [`docs/adr/`](docs/adr/) que tocam a área que você vai mexer.
3. Se a sua mudança contrariar um ADR, **diga isso explicitamente** no PR, em vez de sobrescrever em silêncio.

## Regras do projeto

- **Configuração é dado, não código.** Limiares — a fração dos melhores N, o piso de presença, o mínimo de torneios, a duração, as variantes permitidas — vivem em [`config/`](config/). Não os escreva dentro do Python.
- **O arquivo é canônico.** O Resultado é o score oficial do Lichess. Nunca recalculamos pontuação.
- **Sem backend.** Nada de servidor, banco de dados ou login neste projeto (ADR-0003).
- **A execução padrão não sobrescreve** um Torneio já arquivado. Atualizar é sempre um pedido explícito, para que uma correção humana nunca seja desfeita por uma recoleção automática.
- **Nada desaparece em silêncio.** Um candidato que não casar com as regras vira registro no relatório de pendências, não um descarte invisível.
- **Documentação em português do Brasil.** README, ADRs, glossário, comentários, mensagens de erro e nomes de teste são escritos em pt-BR. Ficam de fora apenas textos legais e identificadores de máquina, como caminhos de arquivo e chaves de configuração.

## Testes

- Rode `make test` antes de abrir um PR.
- Todo comportamento novo entra com teste.
- Teste **comportamento observável**, não estrutura interna. Um teste não deve saber como o Ranking é calculado por dentro — apenas que, dados tais Torneios Válidos e tal configuração, a ordem e os totais são estes.
- Fixtures são **gravadas da API real**, nunca JSON inventado à mão.
- Nenhum teste toca a rede.

## Fluxo de contribuição

1. Escolha uma parte que ainda não está pronta.
2. Implemente e cubra com testes.
3. Rode `make check && make test` até ficar verde.
4. Abra o PR descrevendo o que mudou e por quê.
