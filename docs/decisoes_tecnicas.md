# Decisões técnicas (ADR resumido)

Formato curto: contexto → decisão → consequência. Ordenado cronologicamente.

## 1. Stack: Python/FastAPI mantido, não reescrito em Java/PHP

**Contexto:** o ambiente de TI típico do Exército Brasileiro opera majoritariamente com PHP e Java. Avaliou-se reescrever o backend para aderir a esse padrão.

**Decisão:** manter Python/FastAPI/SQLAlchemy. Reescrever ~43 mil linhas e 372+ testes já validados teria custo de meses sem ganho funcional. Em vez disso, "aderir ao padrão" significa: contrato de API explícito e versionado (OpenAPI), deploy padronizado atrás de Nginx/IIS como reverse proxy, empacotamento como serviço (systemd/Windows Service) ou container Docker, e documentação operacional que não pressupõe fluência em Python.

**Consequência:** equipes acostumadas a PHP/Java operam o sistema via contrato HTTP e scripts de operação, sem precisar ler o código Python.

## 2. SQLite para dev, MySQL para homologação/produção

**Contexto:** SQLite é suficiente para desenvolvimento local rápido, mas não é adequado para uso multiusuário real.

**Decisão:** manter SQLite como padrão de dev (zero setup) e adotar MySQL 8 como banco de homologação/produção. Backlog completo de migração já documentado em `docs/PLANO_EVOLUCAO_MYSQL_CLEAN_ARCH.md` e `docs/PLANO_MIGRACAO_MYSQL_SEGURA.md`.

**Consequência:** `infra/persistence/db.py` precisa de pool configurável e tipos de coluna explícitos (sem depender de comportamento permissivo do SQLite) antes da migração real de dados.

## 3. Autenticação por cookie de sessão assinado, não JWT

**Contexto:** o sistema serve um frontend server-rendered/SPA confiável (mesma organização), não uma API pública multi-tenant.

**Decisão:** `itsdangerous.URLSafeTimedSerializer` com cookie httponly, em vez de JWT. Mais simples de revogar (invalidação de sessão não exige blocklist de token).

**Consequência:** integração com terceiros externos exigiria um mecanismo de autenticação adicional (não implementado, fora de escopo atual).

## 4. CSRF double-submit cookie

**Decisão:** cookie `csrf_token` (não-httponly, legível por JS) + header `X-CSRF-Token`, comparados com `secrets.compare_digest`. Habilitado por padrão em prod, desabilitado por padrão em dev.

## 5. Chave do vault de credenciais separada da chave de sessão

**Contexto:** até 2026-06-23, `modules/acessos/application/credential_vault.py` derivava sua chave Fernet do mesmo `SISGES_SECRET_KEY` usado para assinar cookies de sessão — um único segredo cobrindo duas superfícies de ameaça diferentes.

**Decisão:** introduzir `SISGES_VAULT_KEY` como segredo independente, com a mesma postura de validação em prod que `SISGES_SECRET_KEY` (obrigatório, comprimento mínimo, deve ser diferente do secret de sessão). `CRYPTO_VERSION` avançado para `v2`.

**Consequência:** registros de auditoria cifrados com a chave antiga (`v1`) tornam-se ilegíveis após a troca. Como a base era só de desenvolvimento/teste no momento da correção, a tabela foi truncada em vez de migrada — ver `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md`.

## 6. Saneamento de histórico git: privado com filter-repo + público com história nova

**Contexto:** o histórico git acumulou, ao longo do desenvolvimento, dados pessoais reais de militares (PDFs/ODTs/JSON com nomes e CPF) sob `data/`, além de `.venv/` inteiro. O repositório esteve publicamente exposto no GitHub por um período antes de ser detectado.

**Decisão:** em vez de tentar uma única limpeza "perfeita" e publicar o mesmo repositório, foram criados dois repositórios com tratamento diferente:
- `alexandreohiro/sisges` (privado): histórico existente limpo via `git filter-repo`, mantido para uso operacional contínuo. Risco residual aceito por ser acesso controlado.
- `alexandreohiro/sisges-showcase` (público): história nova, nascida de uma cópia auditada da árvore de trabalho atual, sem nenhum vínculo de objeto git com o histórico antigo. Risco residual eliminado por construção, não por subtração.

**Consequência:** o repositório público não tem o histórico granular de commits do desenvolvimento real — trade-off aceito porque o objetivo é portfólio/transparência de arquitetura, não arqueologia de processo. Detalhe completo em `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md` e `FASE2.md`.

## 7. CI/CD: GitHub Actions

**Decisão:** GitHub Actions como plataforma de CI/CD, reaproveitando os scripts de gate já existentes (`scripts/sisges_release_gate.py`, `scripts/security_preflight.py`, `scripts/mysql_hardening_gate.py`) em vez de recriar verificações dentro de workflows YAML.

## 8. Licenciamento: "All Rights Reserved" customizado, não open-source permissivo

**Contexto:** o código será publicado para avaliação técnica/portfólio, mas processa dados de um sistema militar real e não deve ser livremente reimplantado por terceiros.

**Decisão:** `LICENSE` própria, sem cláusula de uso/cópia/implantação por terceiros, em vez de MIT/Apache/BSL.

**Consequência:** PRs externos ficam sem modelo contratual claro de contribuição (não é o caso de uso esperado — ver `CONTRIBUTING.md`).
