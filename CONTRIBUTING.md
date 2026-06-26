# Contribuindo com o SisGeS

Este repositório é mantido por um único responsável técnico (`@alexandreohiro`). Não há expectativa de contribuições externas regulares, mas este documento existe para manter consistência entre sessões de trabalho e para qualquer colaborador futuro.

## Stack e setup

- Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic.
- Setup: `python -m pip install -e ".[dev]"`.
- Banco local padrão: SQLite em `data/sisges.db` (nunca commitar `data/`).

## Antes de qualquer commit

```bash
python -m ruff check .
python -m pytest
```

Ambos devem passar limpos. Não existe exceção para "vou corrigir depois" — se um teste quebrar, o commit não deve seguir até ser corrigido ou o teste ajustado deliberadamente.

## Convenção de commits

O histórico já segue [Conventional Commits](https://www.conventionalcommits.org/) na prática (`feat(...)`, `fix(...)`, `security(...)`, `chore(...)`, `docs(...)`). Continue esse padrão:

```
<tipo>(<escopo>): <resumo no imperativo>

<corpo opcional explicando o porquê, não o o-quê>
```

Tipos usados no projeto: `feat`, `fix`, `security`, `chore`, `docs`, `test`, `refactor`.

## Arquitetura e camadas

A estrutura pretendida por módulo de negócio em `modules/<nome>/` é:

```
domain/         # entidades, regras e value objects, sem dependência de framework
application/    # casos de uso/serviços, orquestram domain + infra
infrastructure/ # repositories e adaptadores concretos (SQLAlchemy, etc.)
interfaces/     # schemas Pydantic de entrada/saída (contrato HTTP)
```

**Nem todo módulo segue as 4 camadas hoje** — módulos mais simples (`auth`, `users`, `permissions`, `ops_center`, `militar_360`, `acoes_sugeridas`, `consistencia`, `quadro`, `tarefas`, `ctsm`) têm só `application/services.py`. Isso é aceitável para lógica simples, mas se um módulo crescer a ponto de acumular regra de domínio real (validações, invariantes, máquina de estados), ele deve crescer para `domain/`, não empilhar tudo em `services.py`. Ver `docs/arquitetura.md` para o detalhamento completo e o estado atual de cada módulo.

Regra de transação: repositórios **não fazem `commit()`**. A fronteira transacional é `infra/persistence/transactions.py::atomic(db)`, usada por serviços de aplicação e rotas. Não reintroduza `commit()` em repository — isso já foi corrigido uma vez (ver `docs/reconstrucao_backend_fase4.md`).

## Segurança e dados pessoais

Este sistema processa dados pessoais reais de militares (CPF, identidade, endereço, situação funcional). Antes de qualquer commit que toque fixtures de teste, scripts de importação ou exemplos em docs:

- Nunca use dados reais em testes, fixtures ou exemplos — use dados sintéticos.
- Nunca commite arquivos em `data/` (já coberto pelo `.gitignore`, mas confira antes de `git add -A`).
- Segredos (`SISGES_SECRET_KEY`, `SISGES_VAULT_KEY`, credenciais de banco) nunca em texto no repositório — só via variável de ambiente ou GitHub Secrets.
- Se encontrar um caminho absoluto pessoal (`C:\Users\...`, `D:\Usuarios\...`) hardcoded em código ou doc, trate como bug de privacidade/portabilidade, não como cosmético.

## Pull requests

Para mudanças não triviais, abra PR contra `develop` (não contra `main`). `main` reflete o que está pronto para release; `develop` é a branch de integração. O CI (Fase 4 do roadmap de infraestrutura) deve passar antes do merge.
