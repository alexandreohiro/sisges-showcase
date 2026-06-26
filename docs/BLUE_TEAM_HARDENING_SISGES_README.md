# Relatorio Blue Team - SISGES

O relatorio tecnico defensivo completo esta protegido no arquivo:

`docs/BLUE_TEAM_HARDENING_SISGES.7z`

## Como abrir

Use o 7-Zip:

```powershell
& "C:\Program Files\7-Zip\7z.exe" x docs\BLUE_TEAM_HARDENING_SISGES.7z -o<PASTA_DESTINO>
```

O arquivo usa criptografia AES-256 e nomes internos protegidos.

## Regras operacionais

- Nao commitar o arquivo `.7z` sem decisao explicita.
- Nao armazenar a senha no Git, `.env`, README ou historico de terminal compartilhado.
- Nao extrair o relatorio em pasta versionada.
- Apagar copias temporarias em texto claro apos a leitura.
- Tratar o conteudo como documento sensivel de seguranca defensiva.

## Escopo

O relatorio cobre a postura defensiva do SISGES local/pre-producao, incluindo frontend, backend, autenticacao, banco de dados, uploads, logs, monitoramento e resposta a incidentes.
