# Reconstrucao tecnica do backend SISGES - Fase 3

Data: 2026-05-03

## 1. Diagnostico da fase

A autenticacao existente funcionava, mas ainda usava segredo default em `tokens.py`, cookie com `secure=False` fixo, erros inconsistentes e sessao puramente baseada no payload assinado. Isso deixava o sistema fragil para producao e dificultava invalidar usuarios desativados.

## 2. Decisoes arquiteturais

- A rota publica permanece igual: `/auth/login`, `/auth/logout`, `/auth/me`.
- O formato de sucesso permanece igual: `{"ok": true, "user": ...}` e `{"user": ...}`.
- Erros de auth passam a usar `detail.code` e `detail.message`.
- O cookie segue configuravel por ambiente via `infra/config.py`.
- O token assinado agora carrega identificador de sujeito (`sub`) e tipo de token, nao mais o snapshot completo do usuario.
- `/auth/me` reconsulta o usuario no banco e recalcula papeis/permissoes.

## 3. Configuracao de seguranca

Variaveis adicionadas:

- `SISGES_SESSION_COOKIE_NAME`
- `SISGES_SESSION_COOKIE_SECURE`
- `SISGES_SESSION_COOKIE_SAMESITE`
- `SISGES_SESSION_COOKIE_PATH`
- `SISGES_SESSION_MAX_AGE_SECONDS`

Regras:

- `SISGES_SECRET_KEY` e obrigatorio em `prod`.
- Em `prod`, o segredo precisa ter pelo menos 32 caracteres.
- Cookie `secure` fica `true` por padrao em `prod`.
- `SameSite=None` exige cookie `secure`.

## 4. Fluxo revisado

Login:

1. Recebe usuario/senha.
2. Usa mensagem generica para usuario inexistente, inativo ou senha incorreta.
3. Gera cookie HTTP-only com flags por ambiente.
4. Retorna payload publico do usuario atual.

Me:

1. Le cookie configurado.
2. Valida assinatura e expiracao.
3. Recarrega usuario no banco.
4. Rejeita usuario inexistente ou inativo.
5. Recalcula permissoes atuais.

Logout:

1. Remove cookie com os mesmos parametros de path/samesite/secure.

## 5. Tratamento tecnico para dados pessoais sensiveis

Esta fase nao criptografa dados existentes. Recomendacao para as proximas fases:

- mascarar CPF, identidade, telefone e endereco nas respostas onde dado completo nao for necessario;
- registrar auditoria para leitura/exportacao de dados pessoais;
- limitar acesso por permissao granular;
- definir politica de retencao para arquivos em `data/outputs` e uploads temporarios;
- avaliar criptografia por coluna ou por arquivo para documentos sensiveis;
- evitar dados pessoais em logs.

## 6. Criterios de aceite

- `prod` sem segredo forte falha cedo.
- Cookie de sessao e HTTP-only.
- Cookie e `secure` por padrao em `prod`.
- Login invalido retorna erro padronizado.
- `/auth/me` rejeita sessao de usuario desativado.
- `pytest` e `ruff` passam.

## 7. Riscos e compatibilidade

- O formato de sucesso foi preservado.
- O formato de erro mudou de string solta para objeto `{code, message}`. Essa e uma mudanca controlada para padronizar erros; se algum frontend dependia de `detail` como string, precisa adaptar.
- Tokens antigos emitidos antes da Fase 3 nao contem `sub`/`token_type` e serao rejeitados. A estrategia de migracao e logout/login dos usuarios.

## 8. Rollback

- Reverter `infra/config.py`, `infra/security/tokens.py`, `modules/auth/application/services.py`, `apps/web/dependencies/auth.py`, `apps/web/routes/auth.py` e testes de auth.
- Usuarios e banco nao sao alterados pela fase.

