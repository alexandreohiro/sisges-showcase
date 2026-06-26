# Handoff para o frontend (SisGeS)

Este documento é o ponto de partida para o time que vai assumir/reescrever o
frontend (`web-sisges-v0`, Next.js 16 / React 19) consumindo o backend SisGeS
via HTTP/JSON. É a entrega da **Fase 9 — Handoff para o frontend** do roadmap
de infraestrutura (`docs/roadmap.md`).

Não é um tutorial de Next.js — é um mapa do que este backend específico exige
do cliente HTTP: como autenticar, como lidar com CSRF, qual o formato dos
erros, e onde está o contrato formal de rotas.

## 1. Visão geral rápida

- Backend: Python 3.11, FastAPI + SQLAlchemy 2.x, monolito modular.
- A app FastAPI é construída em `apps/web/app.py` (`create_app()`, instância
  final exportada como `app`). Registra ~20 routers (auth, users, roles,
  gestão de pessoal, compilador, folhas, tarefas, etc.) e dois middlewares:
  CSRF (`CsrfProtectionMiddleware`) e CORS (`CORSMiddleware`).
- Para entender **o que cada módulo faz** (sem ler Python), leia
  `docs/requisitos.md` — tabela de módulo → responsabilidade.
- Para entender **como o código está organizado** (camadas, pastas,
  pipeline do compilador, etc.), leia `docs/arquitetura.md`.
- CORS: a lista de origens permitidas vem de `DEFAULT_ORIGINS` em
  `apps/web/app.py`, mais o que estiver em `SISGES_FRONTEND_ORIGINS` (CSV).
  `allow_credentials=True` está habilitado — obrigatório para cookies de
  sessão funcionarem cross-origin em dev (`localhost:3000`/`3001` já estão
  na lista padrão).

## 2. Autenticação: sessão por cookie assinado

O backend **não usa JWT**. A sessão é um token assinado com
`itsdangerous.URLSafeTimedSerializer` (ver `infra/security/tokens.py`,
`SALT = "sisges-auth"`, chave = `SISGES_SECRET_KEY`). O token vai dentro de
um cookie HTTP comum — o frontend nunca precisa decodificá-lo, só preservá-lo.

Rotas relevantes (`apps/web/routes/auth.py`):

- `POST /auth/login` — body `{"username": str, "password": str}`. Em caso de
  sucesso, seta o cookie de sessão (`Set-Cookie`) e retorna
  `{"ok": true, "user": {...}, "csrf_token": "..."}`. Em caso de falha,
  retorna 401 com o shape de erro padrão (seção 4).
- `POST /auth/logout` — invalida o cookie de sessão e o cookie CSRF
  (`delete_cookie`). Retorna `{"ok": true}`.
- `GET /auth/me` — retorna `{"user": {...}}` se a sessão for válida; 401 caso
  contrário (`AUTH_NOT_AUTHENTICATED`).
- `GET /auth/csrf` — gera/renova o cookie CSRF sem precisar de login
  (útil para a tela de login, já que `/auth/login` é uma rota exempta de
  CSRF — ver seção 3).

Nome do cookie de sessão: `settings.session_cookie_name`, default
`"session_token"` (configurável via `SISGES_SESSION_COOKIE_NAME`). Atributos
relevantes do cookie (`infra/config.py`):

- `httponly=True` — **o frontend não tem acesso ao valor via JS**, nem
  precisa: o navegador o envia automaticamente em toda request same-site/
  cross-site permitida.
- `secure` — `true` sempre em prod (`SISGES_ENV=prod` recusa subir sem isso);
  em dev é `false` por padrão.
- `samesite` — `strict` obrigatório em prod; `lax` em dev por padrão.
- `max_age` — `SISGES_SESSION_MAX_AGE_SECONDS`, default 12h (43200s).

**Implicação prática para o frontend**: todo `fetch`/`axios` para o backend
precisa ir com `credentials: "include"` (fetch) ou `withCredentials: true`
(axios), senão o navegador não envia nem recebe os cookies. Como o cookie é
`httponly`, não há "token" para guardar em `localStorage` ou `Authorization:
Bearer` — a sessão vive inteiramente no cookie gerenciado pelo navegador.
Login/logout fluem assim:

1. Frontend faz `POST /auth/login` com credenciais, `credentials: "include"`.
2. Backend responde com `Set-Cookie` (sessão + CSRF) e o corpo já traz
   `user` e `csrf_token` — o frontend pode guardar `csrf_token` em memória
   (não precisa ler o cookie) para montar o header CSRF nas próximas
   requests (seção 3).
3. Para saber se a sessão ainda é válida (ex.: ao montar a app), chamar
   `GET /auth/me`; 401 significa "deslogado", sem necessidade de inspecionar
   cookies no client.
4. `POST /auth/logout` limpa os dois cookies no servidor.

## 3. CSRF: double-submit cookie

Implementado em `apps/web/middleware/csrf.py` (`CsrfProtectionMiddleware`).
Padrão double-submit: o servidor seta um cookie CSRF legível por JS
(`httponly=False`, propositalmente) e exige que o **mesmo valor** seja
reenviado em um header a cada request mutável.

- Cookie: nome em `settings.csrf_cookie_name`, default `"csrf_token"`
  (configurável via `SISGES_CSRF_COOKIE_NAME`).
- Header: nome em `settings.csrf_header_name`, default `"X-CSRF-Token"`
  (configurável via `SISGES_CSRF_HEADER_NAME`).
- O frontend deve ler o cookie `csrf_token` (ele não é `httponly`, então
  `document.cookie` funciona) **ou** guardar o `csrf_token` retornado no
  corpo de `POST /auth/login` / `GET /auth/csrf`, e enviá-lo de volta no
  header `X-CSRF-Token` em toda request mutável.

Quando a verificação se aplica (`CsrfProtectionMiddleware.dispatch`):

- **Métodos seguros são ignorados**: `GET`, `HEAD`, `OPTIONS`, `TRACE` nunca
  são checados.
- **Métodos mutáveis** (`POST`, `PUT`, `PATCH`, `DELETE`, etc.) são checados,
  **exceto** nos paths em `CSRF_EXEMPT_PATHS`: `/auth/login`, `/auth/logout`,
  `/auth/csrf`, `/health`, `/health/live`, `/health/ready`.
- Se não houver cookie de sessão na request, a checagem é pulada (não há
  sessão para proteger ainda — cobre o caso de login).
- Se houver sessão mas faltar cookie CSRF ou header CSRF, retorna `403` com
  `code: "CSRF_TOKEN_MISSING"`.
- Se os dois existirem mas não forem iguais (comparação constant-time),
  retorna `403` com `code: "CSRF_TOKEN_INVALID"`.
- A checagem inteira é desabilitada se `SISGES_CSRF_ENABLED=false` (default:
  habilitado em prod, desabilitado em dev/test) — então em dev local pode
  parecer que "não faz diferença" enviar o header; **enviar sempre**, porque
  prod exige.

Resumo prático: depois de logar, para qualquer `POST/PUT/PATCH/DELETE` que
não seja login/logout, o frontend precisa adicionar o header
`X-CSRF-Token: <valor do cookie csrf_token>`.

## 4. Forma padronizada de erro HTTP

A maioria dos erros de aplicação usa o helper `apps/web/errors.py`
(`http_error`, `not_found`, `bad_request`) ou o equivalente em
`apps/web/dependencies/auth.py` (`auth_http_exception`). Ambos produzem o
mesmo shape, porque internamente é só um `HTTPException` do FastAPI com
`detail` estruturado:

```json
{
  "detail": {
    "code": "AUTH_NOT_AUTHENTICATED",
    "message": "Nao autenticado."
  }
}
```

- `detail.code`: string estável, em `SCREAMING_SNAKE_CASE`, pensada para o
  frontend tomar decisão programática (ex.: redirecionar para login em
  `AUTH_NOT_AUTHENTICATED`, mostrar toast genérico em outros).
- `detail.message`: texto em português, para exibição direta ao usuário ou
  log — não deve ser usado para lógica condicional (pode mudar de wording).
- Status code HTTP varia por caso (`401` não-autenticado, `403` sem
  permissão / CSRF, `404` não encontrado, `400` request inválida, etc.) — o
  `code` dentro de `detail` é o identificador fino, o status HTTP é a
  categoria.

**Exceção importante**: erros de validação de payload feitos automaticamente
pelo FastAPI/Pydantic (corpo de request malformado, campo obrigatório
faltando, tipo errado) **não passam pelo helper acima** — não há
`exception_handler` customizado registrado em `apps/web/app.py` para
`RequestValidationError`. Esses casos retornam o shape **padrão do
FastAPI**, com `status_code 422`:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "username"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

Ou seja: o frontend precisa tratar `detail` como **polimórfico** —
`object` com `code`/`message` para erros de aplicação, ou `array` de
objetos de validação do Pydantic para 422 de schema. Uma forma simples de
diferenciar: checar `Array.isArray(body.detail)` antes de tentar ler
`body.detail.code`.

Exemplos de `code` usados hoje (não exaustivo — ver `docs/openapi.json` e o
código de cada módulo para a lista completa): `AUTH_NOT_AUTHENTICATED`,
`AUTH_FORBIDDEN`, `AUTH_DEV_MODE_REQUIRED`, `CSRF_TOKEN_MISSING`,
`CSRF_TOKEN_INVALID` (este último vem direto do middleware, não do helper de
`errors.py`, mas com o mesmo shape `{"detail": {"code", "message"}}`).

## 5. Healthcheck (não autenticado, sem CSRF)

Útil para o frontend exibir status de disponibilidade ou em smoke tests:

- `GET /health/live` — processo vivo, não toca banco.
- `GET /health/ready` — inclui status real do banco; `503` se banco
  indisponível.
- `GET /health` — diagnóstico completo (inclui ambiente, debug, banco).

Nenhum dos três exige sessão nem CSRF (estão em `CSRF_EXEMPT_PATHS` e não
dependem de `get_current_user`).

## 6. Contrato formal: OpenAPI

O contrato de rotas, schemas de request/response e tags é gerado nativamente
pelo FastAPI (`app.openapi()`), exportado para **`docs/openapi.json`** pelo
script `scripts/export_openapi.py`.

```bash
python -m scripts.export_openapi
# ou com saída customizada:
python -m scripts.export_openapi --output docs/openapi.json
```

O script importa a instância `app` de `apps.web.app` em processo (sem subir
servidor nem usar `TestClient`/uvicorn) e serializa `app.openapi()` com
`json.dumps(..., indent=2, ensure_ascii=False)`.

**Regra para o time de frontend e para quem mantém o backend**: sempre que
uma rota, schema Pydantic ou tag mudar, regenerar `docs/openapi.json` e
commitar o arquivo atualizado junto da mudança de rota. É a fonte de verdade
para gerar tipos/clients (ex. `openapi-typescript`, `orval`) no novo
frontend — evita o time de frontend precisar inspecionar rotas manualmente
ou ler `apps/web/routes/*.py` para descobrir shape de payload.

No snapshot gerado nesta fase, o schema cobre 139 paths (`info.title:
"SisGeS"`, `info.version: "0.1.0"`).

## 7. Para entender o domínio sem ler Python

- `docs/requisitos.md`: tabela módulo → responsabilidade (auth, users,
  gestão de pessoal, cálculo de tempo de serviço, compilador, folhas,
  declarações, documents, validação, tarefas, quadro, ctsm, ops_center,
  militar_360, consistência, ações sugeridas, feature flags) — é o ponto de
  partida para entender **o que** o sistema faz.
- `docs/arquitetura.md`: mapa de pastas e camadas (`apps/`, `modules/`,
  `infra/`, `shared/`), pipeline do compilador, autenticação/segurança,
  observabilidade — é o ponto de partida para entender **como** o backend
  está organizado, caso seja necessário consultar o código-fonte.
- `docs/roadmap.md`: estado do roadmap de infraestrutura (o que já foi
  concluído, o que está em andamento) — relevante para saber se uma
  característica do backend (ex. MySQL, observabilidade) já está
  consolidada ou ainda em construção.

## 8. Checklist rápido de integração

- [ ] Cliente HTTP com `credentials: "include"` / `withCredentials: true`
      em todas as chamadas ao backend.
- [ ] Fluxo de login chama `POST /auth/login`, guarda `csrf_token` da
      resposta (ou lê do cookie `csrf_token`).
- [ ] Toda chamada mutável (`POST`/`PUT`/`PATCH`/`DELETE`) fora de
      `/auth/login`, `/auth/logout`, `/auth/csrf` envia o header
      `X-CSRF-Token`.
- [ ] Tratamento de erro genérico sabe diferenciar `detail` objeto
      (`{code, message}`) de `detail` array (422 de validação Pydantic).
      Erros de validação Pydantic (`422`) trazem `loc` com segmentos
      `"body"`, `"query"` ou `"path"` — útil para exibir erros inline
      nos campos do formulário correto.
- [ ] `401` em qualquer chamada autenticada redireciona para login
      (sessão expirada/inválida).
- [ ] Geração de tipos/cliente a partir de `docs/openapi.json`, regenerado
      via `python -m scripts.export_openapi` sempre que o backend mudar
      contrato.

## 9. Dados de teste: use apenas fixtures sintéticas

Este sistema manipula dados pessoais reais de militares (nome completo,
CPF, posto, histórico funcional). Todo e qualquer dado usado em:

- fixtures de testes automatizados (Jest/Vitest/Playwright/cy)
- seeds/mocks de desenvolvimento local do frontend
- screenshots, gravações de screen ou exemplos em documentação

**deve ser gerado sinteticamente**, nunca copiado do backend operacional.
Use bibliotecas como [`@faker-js/faker`](https://fakerjs.dev/) com locale
`pt_BR` para gerar nomes, CPFs e datas plausíveis porém fictícios.

**Nunca commite arquivos com dados reais** (PDFs, ODTs, `.db`, ZIPs de
exportação) no repositório do frontend — a mesma regra que vigora no
backend (`data/` está em `.gitignore` e os workflows de CI verificam isso
com `gitleaks`). Qualquer PRcontendo dado real deve ser considerado
incidente de privacidade e tratado como tal.
