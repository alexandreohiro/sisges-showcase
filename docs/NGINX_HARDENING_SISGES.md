# Nginx Defensivo para SISGES Local

## Objetivo

Usar o Nginx como proxy reverso defensivo na frente do SISGES local/pre-producao.

Topologia:

- Frontend Next.js: `http://127.0.0.1:3000`
- Backend FastAPI: `http://127.0.0.1:8000`
- Entrada via Nginx: `http://localhost`
- API via Nginx: `http://localhost/api/*`

## Arquivo

Configuracao pronta:

`ops/nginx/sisges.conf`

O arquivo foi estruturado como configuracao principal completa, com blocos `events`
e `http`, para permitir uso direto com `nginx.exe -c`.

## Aplicacao em Windows

1. Instalar Nginx.
2. Usar `ops/nginx/sisges.conf` diretamente com `-c`, ou adaptar o conteudo caso queira incluir apenas o bloco `server` em outro `nginx.conf`.
3. Testar:

```powershell
nginx -t
```

4. Recarregar:

```powershell
nginx -s reload
```

Se `nginx` nao estiver no PATH, usar o caminho completo do executavel.

## Validacoes

```powershell
curl http://localhost/
curl http://localhost/api/health
```

Preflight local do host:

```powershell
python -m scripts.host_security_preflight --json
```

Validar sintaxe do Nginx usando o executavel local:

```powershell
python -m scripts.host_security_preflight --check-nginx-syntax --json
```

Validar portas esperadas:

```powershell
python -m scripts.host_security_preflight --check-ports --json
```

O login deve passar por:

`POST http://localhost/api/auth/login`

O Nginx encaminha para a rota real do FastAPI:

`POST http://127.0.0.1:8000/auth/login`

## Observacoes

- Para producao, trocar `server_name localhost` pelo dominio real.
- Para producao, usar TLS e redirecionar HTTP para HTTPS.
- Ajustar `client_max_body_size` se o fluxo documental exigir uploads maiores.
- Revisar a Content Security Policy apos cada nova biblioteca visual do frontend.
- O Nginx reduz risco, mas nao substitui validacao de permissao no backend.
