# Reconstrucao tecnica do backend SISGES - Fase 2

Data: 2026-05-03

## 1. Diagnostico da fase

A Fase 1 deixou a aplicacao importavel, testes executaveis e modelos sem duplicacoes perigosas. A Fase 2 trata a base de dados como contrato evolutivo: o schema precisa ser versionado, a configuracao de banco precisa sair do hardcode e o seed nao pode depender de credencial padrao fraca.

## 2. Arquitetura de banco alvo

- `infra/config.py`: configuracao central de ambiente, debug, banco e segredo.
- `infra/persistence/db.py`: cria engine SQLAlchemy a partir de `SISGES_DATABASE_URL`.
- `migrations/`: estrutura Alembic.
- `migrations/versions/20260503_0001_baseline_schema.py`: baseline inicial do schema atual.
- `infra/persistence/seed.py`: seed idempotente para permissoes, papeis e feature flags.

Decisao: a migration inicial usa a metadata SQLAlchemy atual como baseline. Isso permite criar bancos novos e registrar o estado de bancos existentes sem reescrever manualmente todas as tabelas nesta etapa. Trade-off: migrations futuras devem ser explicitas e nao devem depender da metadata viva.

## 3. Configuracao por ambiente

Variaveis principais:

- `SISGES_ENV`: `dev`, `test` ou `prod`.
- `SISGES_DATABASE_URL`: URL SQLAlchemy do banco.
- `SISGES_DEBUG`: debug por ambiente.
- `SISGES_SECRET_KEY`: segredo de sessao, tratado com rigor na Fase 3.

Comportamento:

- `dev`: usa `sqlite:///data/sisges.db` se `SISGES_DATABASE_URL` nao for informado.
- `test`: usa `sqlite:///data/sisges_test.db` se `SISGES_DATABASE_URL` nao for informado.
- `prod`: exige `SISGES_DATABASE_URL` explicitamente.

## 4. Seed revisado

O seed agora:

- cria/atualiza permissoes de forma idempotente;
- cria/atualiza papeis de forma idempotente;
- cria feature flags ausentes sem sobrescrever flags existentes;
- nao cria usuario `dev` com senha `123456`;
- so cria/atualiza usuario inicial quando `SISGES_BOOTSTRAP_ADMIN_USERNAME` e `SISGES_BOOTSTRAP_ADMIN_PASSWORD` forem informados;
- exige senha de bootstrap com no minimo 12 caracteres.

## 5. Plano de migracao do banco atual

Para ambiente local existente:

1. Fazer backup do banco atual:

```bash
copy data\sisges.db data\sisges.backup.db
```

2. Garantir que o schema legado esta coerente com os modelos atuais. Se o banco for antigo, aplicar scripts legados necessarios antes do Alembic:

```bash
python scripts\migrate_ops_1a.py
python scripts\migrate_gp_import_2.py
python scripts\migrate_gp_time_phase1.py
```

3. Registrar/aplicar baseline Alembic:

```bash
python -m alembic upgrade head
```

4. Aplicar seed:

```bash
python -m infra.persistence.seed
```

5. Criar admin inicial somente com senha forte explicita:

```bash
set SISGES_BOOTSTRAP_ADMIN_USERNAME=admin
set SISGES_BOOTSTRAP_ADMIN_PASSWORD=<senha-forte-com-12-ou-mais-caracteres>
python -m infra.persistence.seed
```

## 6. Indices e constraints revisados

O baseline preserva os indices/constraints declarados nos modelos atuais:

- `users.username` e `users.email` unicos e indexados.
- `roles.name` unico e indexado.
- `permissions.key` unico e indexado.
- `militar.identidade` e `militar.cpf` unicos.
- campos de consulta frequente em `militar`, `tarefa`, `folha_alteracao`, `documents` e `calculo_tempo_servico` indexados.
- tabelas associativas `user_roles` e `role_permissions` com chave primaria composta.

Pendencia: a Fase 2 nao adiciona novas constraints por migration incremental porque o banco legado ainda precisa ser validado contra dados reais antes de endurecer integridade.

## 7. Criterios de aceite

- `python -m alembic upgrade head` executa com sucesso.
- `python -m infra.persistence.seed` executa sem criar credencial fraca.
- `python -m pytest` passa.
- `python -m ruff check .` passa.
- `SISGES_ENV=prod` sem `SISGES_DATABASE_URL` falha cedo.
- App continua importando e registrando as rotas existentes.

## 8. Riscos restantes

- A migration baseline baseada em metadata deve ser substituida por migrations explicitas a partir da proxima alteracao de schema.
- Bancos SQLite antigos podem precisar dos scripts legados antes de receber o baseline Alembic.
- Usuarios fracos ja existentes no banco nao sao removidos automaticamente; a rotacao/desativacao deve ser feita operacionalmente antes de producao.

## 9. Rollback

- Restaurar backup `data\sisges.backup.db` se a migracao local falhar.
- Reverter arquivos `alembic.ini`, `migrations/`, `infra/config.py`, `infra/persistence/db.py`, `infra/persistence/seed.py`, `.env.example`, README e docs da fase.
- Nenhum dado e removido pelo seed revisado.

