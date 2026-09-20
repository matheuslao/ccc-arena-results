.PHONY: help build check test shell

help:
	@echo "build  constrói a imagem"
	@echo "check  valida os arquivos de configuração"
	@echo "test   roda a suíte de testes"
	@echo "shell  abre um shell no container"

build:
	docker compose build

check:
	docker compose run --rm cli

test:
	docker compose run --rm test

shell:
	docker compose run --rm cli bash
