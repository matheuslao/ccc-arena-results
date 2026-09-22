.PHONY: help build check collect test shell

help:
	@echo "build    constrói a imagem"
	@echo "check    valida os arquivos de configuração"
	@echo "collect  arquiva os Torneios Válidos ainda não arquivados"
	@echo "test     roda a suíte de testes"
	@echo "shell    abre um shell no container"

build:
	docker compose build

check:
	docker compose run --rm cli

collect:
	docker compose run --rm cli ccc-arena collect

test:
	docker compose run --rm test

shell:
	docker compose run --rm cli bash
