# Execucao Local LAN do SISGES

Este procedimento sobe o SISGES para uso em rede local com:

- frontend: `http://localhost:3001`
- backend: `http://localhost:3031`
- acesso em outro dispositivo: `http://<ip-da-maquina>:3001`

Use `3031` como backend operacional quando a porta `3030` ficar presa por processo antigo no Windows. A release operacional das Folhas de Alteracoes nao e reprocessada por estes comandos.

## Portas oficiais desta etapa

| Camada | Porta | Uso |
| --- | ---: | --- |
| Frontend Next.js | 3001 | Interface web acessivel por PC/celular na LAN |
| Backend FastAPI | 3031 | API, healthcheck, autenticacao e rotas operacionais |

Se outro projeto estiver usando uma dessas portas, primeiro pare as portas oficiais. Se a porta continuar presa, use outra porta temporaria e atualize o `.env.local` do frontend.

## Backend

No PowerShell:

```powershell
cd "C:\caminho\para\sisges"
powershell -ExecutionPolicy Bypass -File .\scripts\start_sisges_backend_lan.ps1
```

Com origens LAN explicitas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_sisges_backend_lan.ps1 -FrontendOrigins "http://localhost:3001,http://127.0.0.1:3001,http://192.168.0.109:3001,http://10.67.171.173:3001"
```

Valide:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:3031/health
```

## Frontend

No PowerShell:

```powershell
cd "C:\caminho\para\web-sisges-v0"
powershell -ExecutionPolicy Bypass -File .\scripts\start-sisges-frontend.ps1 -Build
```

Se o backend estiver em outra porta:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-sisges-frontend.ps1 -BackendPort 3031 -Build
```

Valide:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:3001/folhas
```

Acesse pela rede:

```text
http://192.168.0.109:3001
http://10.67.171.173:3001
```

Use o IP da interface que esta na mesma rede do dispositivo cliente. Se o PC cliente estiver no cabo, a maquina que hospeda o SISGES tambem precisa estar alcancavel pela rede cabeada.

## Validacao operacional LAN

Depois de subir backend e frontend, rode:

```powershell
cd "C:\caminho\para\sisges"
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_lan.ps1
```

O validador confere:

- portas `3001` e `3031` ouvindo;
- backend `/health`;
- backend `/openapi.json`;
- rota frontend `/folhas`;
- CORS para origens locais e LAN.

Com URLs customizadas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_lan.ps1 -FrontendUrl "http://localhost:3001" -BackendUrl "http://localhost:3031"
```

## Gate operacional fullstack

Para validar LAN, backend Folhas, backend Gestao de Pessoal, frontend UX e rotas locais em um unico comando:

```powershell
cd "C:\caminho\para\sisges"
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_operational_stack.ps1
```

Para incluir build do frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_operational_stack.ps1 -Build
```

Para incluir smoke autenticada de Folhas, defina credenciais somente na sessao atual:

```powershell
$env:SISGES_API_BASE_URL="http://localhost:3031"
$env:SISGES_SMOKE_USERNAME="<usuario>"
$env:SISGES_SMOKE_PASSWORD="<senha>"
powershell -ExecutionPolicy Bypass -File .\scripts\validate_sisges_operational_stack.ps1 -AuthSmoke
```

Nao grave senha em arquivo de configuracao, README, script ou historico Git.

## Parar portas oficiais

No backend:

```powershell
cd "C:\caminho\para\sisges"
powershell -ExecutionPolicy Bypass -File .\scripts\stop_sisges_ports.ps1
```

Para portas customizadas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_sisges_ports.ps1 -Ports 3001,3031
```

## Observacoes

- O frontend em producao local usa `.env.local`; se mudar a porta do backend, rode o script do frontend novamente com `-Build`.
- Para acesso de outros PCs na rede cabeada, use o IP da interface que esta na mesma rede desses PCs.
- Se abrir pelo celular no Wi-Fi, use o IP da interface Wi-Fi.
- Se houver erro de CORS, confira se a origem `http://<ip>:3001` foi adicionada em `SISGES_FRONTEND_ORIGINS`.
- Para conferir IPs locais no Windows, rode `ipconfig`.
- Para conferir listeners, rode `netstat -ano | findstr ":3001 :3031"`.
- Nao use os scripts de execucao local para gerar pacote final ou mexer na release congelada.
