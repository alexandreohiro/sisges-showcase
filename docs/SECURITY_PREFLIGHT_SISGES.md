# Security Preflight SISGES

## Objetivo

Validar rapidamente se o ambiente local/homologacao do SISGES possui os artefatos e configuracoes defensivas minimas antes de retomar deploy, MySQL, Nginx ou homologacao fullstack.

O preflight nao migra banco, nao cria usuario, nao altera dados e nao toca nos pacotes congelados.

## Comando local

```powershell
python -m scripts.security_preflight
```

## Preflight do host Windows/Nginx

```powershell
python -m scripts.host_security_preflight --json
```

Com validação de sintaxe do Nginx:

```powershell
python -m scripts.host_security_preflight --check-nginx-syntax --json
```

Com validação de portas:

```powershell
python -m scripts.host_security_preflight --check-ports --json
```

## Comando com MySQL estatico

```powershell
python -m scripts.security_preflight --mysql-url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --json
```

## Comando com validacao de conexao

```powershell
python -m scripts.security_preflight --mysql-url "mysql+pymysql://sisges_app:SENHA@127.0.0.1:3306/sisges?charset=utf8mb4" --connect-mysql --json
```

## Gate de producao

```powershell
python -m scripts.security_preflight --require-prod --json
```

Com `--require-prod`, passam a ser bloqueantes:

- cookie `Secure`;
- `SameSite=strict`;
- CSRF ativo;
- debug desativado;
- logs em JSON.

## Saida em arquivo

```powershell
python -m scripts.security_preflight --output-json data/output/security_preflight.json --output-txt data/output/security_preflight.txt
```

Arquivos em `data/output` nao devem ser versionados.

## Checks cobertos

- Nginx defensivo presente.
- Headers e rate limit no `sisges.conf`.
- Contrato de logs estruturados de seguranca.
- Relatorio Blue Team protegido.
- Plano MySQL seguro.
- SQL de usuarios MySQL.
- Script de verificacao de grants.
- Checklist backup/restore.
- `.env.mysql.example`.
- PyMySQL declarado.
- Gate MySQL para URL de aplicacao.
- Postura runtime de cookie, CSRF, debug e logs.

## Uso operacional

Rodar antes de:

- trocar SQLite por MySQL;
- executar Alembic contra MySQL;
- expor ambiente via Nginx;
- retomar homologacao fullstack;
- gerar relatorio de prontidao defensiva.

## Validacao complementar do frontend

No repositorio do frontend, validar se o cliente envia e renova token CSRF:

```powershell
npm.cmd run validate:csrf-client
npm.cmd run build
```

Tambem e possivel chamar essa verificacao a partir do preflight do backend:

```powershell
python -m scripts.security_preflight --frontend-dir C:\caminho\para\web-sisges-v0 --check-frontend-csrf --json
```

Essa validacao complementa o gate do backend quando `SISGES_CSRF_ENABLED=true`.
Sem ela, o backend pode estar corretamente endurecido, mas a interface pode falhar em operacoes mutaveis autenticadas.
