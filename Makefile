.PHONY: help build check collect site test shell

help:
	@echo "build    constrói a imagem"
	@echo "check    valida os arquivos de configuração"
	@echo "collect  arquiva os Torneios Válidos ainda não arquivados"
	@echo "site     gera a página estática em ./site"
	@echo "test     roda a suíte de testes"
	@echo "shell    abre um shell no container"

build:
	docker compose build

check:
	docker compose run --rm cli

collect:
	docker compose run --rm cli ccc-arena collect

site:
	docker compose run --rm cli ccc-arena site

test:
	docker compose run --rm test

shell:
	docker compose run --rm cli bash
