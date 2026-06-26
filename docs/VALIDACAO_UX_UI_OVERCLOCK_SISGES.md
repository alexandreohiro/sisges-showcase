# Validacao UX/UI Overclock SISGES

Esta etapa valida se as telas operacionais principais continuam abrindo, renderizando texto esperado e respondendo dentro de limite local aceitavel. Ela complementa os testes backend, health smoke, release gate e overclock de API.

## Escopo

Perfil versionado:

- `ops/ux_ui/critical_pages.json`

Telas cobertas:

- Ops Center;
- Gestao de Pessoal;
- Tarefas;
- Compilador;
- Folhas;
- Declaracoes;
- Quadro;
- Notificacoes.

## Regras

- Nao usar dados reais novos.
- Nao alterar `data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip`.
- Nao alterar `data/releases/secretaria_folhas_2025_revisado`.
- Evidencias ficam em `data/output/ux_ui_overclock/`.
- Screenshots, JSONs e TXTs gerados nao devem ser commitados.
- O teste autenticado deve usar usuario local de homologacao criado por variaveis de ambiente, sem senha em arquivo.

## Preparacao

Backend:

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.sisges_health_smoke
```

Frontend:

```powershell
cd C:\caminho\para\web-sisges-v0
npm.cmd run build
npm.cmd run dev
```

Se a porta `3000` estiver ocupada, usar `3001` e ajustar a URL base do relatorio manual.

## Validacao do perfil

```powershell
cd C:\caminho\para\sisges
.\.venv\Scripts\python.exe -m scripts.ux_ui_overclock_validate `
  --profile ops/ux_ui/critical_pages.json
```

## Relatorio esperado

O relatorio UX/UI deve usar o schema:

```json
{
  "schema_version": "sisges-ux-ui-overclock-report-v1",
  "status": "OK",
  "frontend_url": "http://127.0.0.1:3000",
  "backend_url": "http://127.0.0.1:8000",
  "pages": [
    {
      "path": "/tarefas",
      "label": "Tarefas",
      "ok": true,
      "loaded_ms": 1000,
      "expected_text_found": true,
      "console_errors": 0
    }
  ]
}
```

Validar relatorio:

```powershell
.\.venv\Scripts\python.exe -m scripts.ux_ui_overclock_validate `
  --profile ops/ux_ui/critical_pages.json `
  --report data/output/ux_ui_overclock/RELATORIO_UX_UI_OVERCLOCK.json `
  --output-txt data/output/ux_ui_overclock/VALIDACAO_UX_UI_OVERCLOCK.txt
```

## Uso no release gate

Depois de gerar o relatorio autenticado pelo navegador, o gate de release pode anexar e validar essa evidencia sem reabrir o browser:

```powershell
.\.venv\Scripts\python.exe -m scripts.sisges_release_gate `
  --allow-missing-git `
  --ux-ui-report data/output/ux_ui_overclock/RELATORIO_UX_UI_OVERCLOCK.json `
  --output-json data/output/sisges_release_gate_ux_ui_report.json `
  --output-txt data/output/sisges_release_gate_ux_ui_report.txt
```

Se o relatorio UX/UI estiver ausente, invalido, com pagina critica falhando ou com texto esperado ausente, o gate fica `PENDENTE`. O gate nao gera screenshots nem altera a release congelada; ele apenas consome o JSON/TXT de evidencia ja produzido em `data/output/ux_ui_overclock/`.

## Criterio de aceite

- Login renderiza e autentica.
- Rotas criticas carregam.
- Texto esperado aparece.
- Console nao registra erro.
- Cada pagina fica abaixo de `max_page_load_ms` no perfil.
- Nenhuma tela fica presa em carregamento.
- Tempos locais ficam abaixo do limite do perfil.
- JSON/TXT de evidencia sao gerados.
- `npm.cmd run build` passa.
- `ruff check .` passa no backend.
