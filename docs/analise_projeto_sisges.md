# Analise tecnica do projeto SISGES

Data da analise: 2026-05-03

## Contexto

O SISGES e um backend Python para um Sistema de Gerenciamento de Secretaria. Pelo codigo atual, o dominio principal atende rotinas administrativas de secretaria, com foco em gestao de pessoal militar, compilacao de documentos, folhas de alteracao, tarefas, documentos gerados, calculo de tempo de servico, usuarios, papeis, permissoes e feature flags.

O projeto ja possui uma aplicacao FastAPI funcional, templates HTML/Jinja2, persistencia SQLite com SQLAlchemy, autenticacao por cookie assinado e modulos organizados por dominio. A aplicacao importa corretamente e registra 55 rotas.

## Stack identificada

- Linguagem: Python >= 3.11.
- Web/API: FastAPI, Uvicorn.
- Renderizacao server-side: Jinja2.
- Banco: SQLite em `data/sisges.db`.
- ORM: SQLAlchemy 2.x.
- Upload/parser: `python-multipart`, `pdfplumber`.
- Autenticacao: cookie `session_token` assinado com `itsdangerous`.
- Senhas: PBKDF2-SHA256 com salt aleatorio.
- Empacotamento: `setuptools` via `pyproject.toml`.

## Estrutura principal

- `apps/web`: aplicacao FastAPI, rotas, templates e assets estaticos.
- `apps/web/routes`: endpoints HTTP por modulo.
- `apps/web/dependencies`: container simples e dependencias de autenticacao.
- `infra/persistence`: engine SQLAlchemy, modelos, seed e repositorios compartilhados.
- `infra/security`: hash de senha e tokens de sessao.
- `infra/pdf`: extracao, OCR e deteccao de blocos/tabelas em PDF.
- `infra/odt`: renderizacao e mapeamento de templates ODT.
- `modules`: modulos de negocio por contexto.
- `shared`: contratos, erros, tipos e utilitarios transversais.
- `tests`: testes unitarios, integracao e e2e, mas dependencias de teste nao estao declaradas.

## Modulos de negocio

### Auth, users, roles e permissions

O sistema tem autenticacao por login/senha, armazenamento de hash de senha e autorizacao por permissoes. O seed cria papeis `dev`, `admin`, `operador` e `consulta`, alem de permissoes base e operacionais.

Pontos fortes:

- Separacao minima entre rota, servico e repositorio.
- Permissoes aplicadas nas rotas criticas via `require_permission`.
- Hash de senha implementado sem armazenamento em texto puro.

Riscos:

- `SISGES_SECRET_KEY` tem fallback fixo de desenvolvimento.
- Cookie de sessao e definido com `secure=False`, inadequado para producao HTTPS.
- Nao ha estrategia clara de invalidacao de sessao, rotacao de segredo ou revogacao.
- Usuario `dev` seedado com senha padrao `123456` e permissao ampla.

### Gestao pessoal

E o nucleo operacional mais desenvolvido. O modulo cadastra militares, consulta dados, atualiza registros, importa dados a partir de texto e gerencia periodos de servico. O schema de militar e amplo e cobre identificacao, filiacao, contato, situacao militar, dados funcionais e campos usados por calculo.

Pontos fortes:

- Modelagem rica de pessoa/militar.
- Rotas protegidas por permissoes.
- Repositorios com operacoes diretas e simples.
- Parser textual para acelerar cadastro/importacao.

Riscos:

- Ha duplicacao de campos em `MilitarUpdate`.
- Campos sensiveis como CPF, identidade, endereco, telefone e dados pessoais nao tem mascaramento, criptografia ou politica de retencao.
- Unicidade de `cpf` e `identidade` depende do banco, mas os erros sao retornados genericamente.

### Compilador, PDF e ODT

O compilador processa textos/PDFs, extrai estrutura de folhas, resolve pendencias canonicas e gera ODT a partir de template. Tambem registra documento gerado no modulo de documentos.

Pontos fortes:

- Pipeline separado em dominio, aplicacao e infraestrutura.
- Fluxo explicito de pendencias antes de gerar ODT.
- Possibilidade de salvar campos resolvidos em gestao pessoal.

Riscos:

- Uploads sao gravados em arquivos temporarios sem rotina explicita de limpeza.
- Validacao de tipo/tamanho de arquivo nao esta evidente.
- Caminhos de saida sao locais e relativos a `data/outputs`, sem camada de armazenamento preparada para multiusuario/producao.

### Folhas, tarefas e notificacoes

Criar uma folha gera uma tarefa automaticamente e pode criar notificacao para responsavel. Isso indica uma integracao operacional util entre modulos.

Pontos fortes:

- Evento de folha e tarefa sao criados no mesmo fluxo.
- O desenho ja permite rastrear origem e responsavel.

Riscos:

- O repositorio de tarefa faz `commit` interno; depois o servico adiciona evento/notificacao e faz novo commit. Isso enfraquece atomicidade do caso de uso.
- Nao ha maquina de estados formal para status de folha/tarefa.

### Calculo de tempo de servico

O modulo consolida periodos, classifica buckets de tempo, gera preview, calcula diff de respostas, aplica ajustes aprovados e grava snapshot historico.

Pontos fortes:

- Fluxo maduro: preview, complemento, diff, aprovacao e persistencia.
- Snapshot inclui justificativas, pendencias e base legal.
- Regras ficam isoladas em servico de aplicacao.

Riscos:

- O servico esta muito grande e acumula parsing, classificacao, diff, persistencia e serializacao.
- A base legal ainda e tratada como referencia parametrizavel/fallback quando nao ha legislacao cadastrada.
- Ha campos usados no calculo (`tempo_servico_publico_*`) que aparecem no schema, mas nao estao claramente modelados no trecho de `MilitarModel` analisado.

## Problemas tecnicos prioritarios

1. `infra/persistence/models.py` tem duplicacoes relevantes:
   - `MilitarModel.periodos_servico` e declarado duas vezes.
   - `MilitarPeriodoServicoModel` repete `__tablename__`, colunas e relacionamento dentro da mesma classe.
   - Isso pode mascarar coluna, sobrescrever atributos e tornar migrations/schema imprevisiveis.

2. Dependencias de teste nao estao declaradas:
   - `python -m pytest -q` falhou porque `pytest` nao esta instalado.
   - O repositorio possui testes, mas o ambiente oficial nao permite executa-los de forma reprodutivel.

3. Documentacao operacional esta incompleta:
   - `README.md` tem blocos markdown quebrados e encoding corrompido.
   - `docs/arquitetura.md`, `docs/requisitos.md`, `docs/roadmap.md` e `docs/decisoes_tecnicas.md` estao vazios.

4. Configuracao de producao ainda e fraca:
   - SQLite local em `data/sisges.db`.
   - `.env` existe no repositorio local.
   - `.gitignore` esta vazio.
   - Segredo e cookie usam configuracao insegura por padrao.

5. Transacoes estao espalhadas:
   - Repositorios fazem `commit`.
   - Servicos tambem fazem `commit`.
   - Isso dificulta rollback atomico em casos de uso multi-entidade.

6. Encoding/texto:
   - Varias mensagens aparecem com caracteres corrompidos por encoding.
   - Isso afeta UX, logs, testes de string e documentacao.

## Plano tecnico recomendado

### Fase 1 - Higiene de base e confiabilidade

- Corrigir `.gitignore` para excluir `.venv`, `__pycache__`, banco local, logs, outputs gerados e `.env`.
- Declarar dependencias de desenvolvimento/teste, incluindo `pytest`.
- Corrigir README com comandos oficiais de setup, run, test e lint/typecheck.
- Corrigir encoding dos arquivos fonte/documentacao para UTF-8 consistente.
- Remover duplicacoes dos modelos SQLAlchemy e alinhar schemas Pydantic com modelos reais.

Criterio de pronto:

- Aplicacao importa.
- `pytest` roda.
- `Base.metadata.create_all` cria schema sem sobrescrita inesperada.
- README permite subir o backend do zero.

### Fase 2 - Banco e migrations

- Introduzir Alembic ou mecanismo formal de migracao.
- Separar banco local de desenvolvimento, teste e producao.
- Criar seed idempotente para papeis/permissoes sem senha padrao insegura.
- Revisar indices e constraints para consultas de gestao pessoal, folhas e tarefas.

Criterio de pronto:

- Schema e versionado.
- Ambiente de teste usa banco isolado.
- Seed nao cria credenciais fracas por padrao.

### Fase 3 - Seguranca e LGPD

- Exigir `SISGES_SECRET_KEY` em ambiente nao-dev.
- Configurar cookie seguro por ambiente: `secure=True` em producao, `httponly=True`, `samesite` revisado.
- Implementar politica para usuario inicial/admin.
- Padronizar respostas de erro de autenticacao.
- Definir tratamento de dados pessoais: mascaramento, auditoria, retencao e controle de acesso.

Criterio de pronto:

- Nao ha segredo default valido para producao.
- Fluxos de login/logout/me tem testes.
- Dados pessoais criticos tem politica tecnica documentada.

### Fase 4 - Arquitetura de aplicacao

- Mover commits para camada de caso de uso/servico, deixando repositorios sem commit automatico.
- Reduzir tamanho do servico de calculo separando classificacao, diff, legislacao e persistencia.
- Formalizar estados de tarefa, folha e documento.
- Padronizar formato de erro da API.

Criterio de pronto:

- Casos de uso multi-entidade sao atomicos.
- Regras complexas tem testes unitarios.
- API retorna erros consistentes.

### Fase 5 - Compilador e documentos

- Validar tipo, extensao e tamanho dos uploads.
- Limpar arquivos temporarios apos processamento.
- Versionar templates ODT e registrar hash/versao no documento gerado.
- Adicionar testes com fixtures reais reduzidas para PDF/ODT.

Criterio de pronto:

- Upload invalido e recusado.
- Arquivos temporarios nao acumulam.
- Documento gerado tem rastreabilidade minima.

### Fase 6 - Observabilidade e operacao

- Padronizar logs estruturados.
- Adicionar healthcheck com status de banco.
- Documentar variaveis de ambiente.
- Criar script oficial de inicializacao de banco.
- Preparar opcao de deploy com banco externo se o sistema sair de uso local.

Criterio de pronto:

- Operador sabe diagnosticar app, banco e erros comuns.
- Healthcheck diferencia app vivo de banco indisponivel.

## Prioridades imediatas

P0:

- Corrigir duplicacoes em `infra/persistence/models.py`.
- Declarar e rodar testes.
- Corrigir `.gitignore` e evitar versionar artefatos locais/sensiveis.
- Revisar configuracao de auth para nao permitir defaults inseguros em producao.

P1:

- Introduzir migrations.
- Corrigir README e docs principais.
- Tornar transacoes atomicas nos casos de uso compostos.
- Cobrir auth, gestao pessoal, folhas/tarefas e calculo com testes.

P2:

- Refatorar calculo de tempo de servico em componentes menores.
- Fortalecer pipeline PDF/ODT.
- Adicionar observabilidade e healthcheck de banco.
- Formalizar regras de dados pessoais e auditoria.

## Validacao executada

- `git status --short`: sem alteracoes antes da analise.
- `git branch --show-current`: branch `develop`.
- `python -m pytest -q`: falhou porque `pytest` nao esta instalado.
- `python -c "from apps.web.app import app; ..."`: aplicacao importou e registrou 55 rotas.
