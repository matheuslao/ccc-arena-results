# Sem backend no MVP: o JSON é a interface

O MVP entrega dados versionados em JSON e uma página estática; não há servidor. A administração — início da Temporada, tabela de Aliases, descarte manual de um Torneio — é feita editando arquivos de configuração no repositório.

Um backend (FastAPI) só passa a se justificar quando existir um consumidor máquina (bot, planilha, app), a necessidade de servir HTML dinamicamente, ou uma UI de administração com login. Como o arquivo JSON é a interface, adicionar o FastAPI depois é trocar a camada de cima sem tocar no modelo de dados nem na coleta.

Um leitor futuro que estranhe a ausência de backend deve tratar isso como decisão deliberada, não como esquecimento.
