# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- Pacote Python instalável, com o comando de linha de comando `ccc-arena`.
- Validação dos quatro arquivos de configuração, acumulando todos os problemas e apontando o arquivo e o campo de cada um.
- Arquivos de configuração com os padrões da Temporada 2026: fuso `America/Sao_Paulo`, time `cavaleiros-do-centro`, melhores 75%, presença mínima de 50% e mínimo de 3 torneios para eleger campeão.
- Ambiente reprodutível em Docker, com `Dockerfile`, `docker-compose.yml` e alvos `make` para `build`, `check`, `test` e `shell`.
- Suíte de testes do validador de configuração.
- Licença MIT e Código de Conduta.

### Notas

- Nenhuma versão foi publicada ainda: tudo o que está listado acima está em desenvolvimento.
- A apuração da Temporada 2026 começa na 16ª edição (2026-09-20). O histórico anterior não entra no Ranking (ver [ADR-0004](docs/adr/0004-temporada-com-janela-explicita.md)).
