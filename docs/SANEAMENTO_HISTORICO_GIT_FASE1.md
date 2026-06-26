# Saneamento do histórico git — Fase 1 (incidente de exposição de dados pessoais)

Data: 2026-06-23

## 1. Diagnóstico da fase

O repositório `https://github.com/alexandreohiro/sisges` estava com visibilidade **pública** no GitHub, com o branch `develop` já enviado ao remote. O branch `main` remoto continha apenas o commit automático de inicialização do GitHub (`Initialize repository`, único arquivo `.gitkeep`), sem dado sensível.

Auditoria do histórico local (67 commits, 24/04/2026 a 28/05/2026) confirmou exposição real de dados pessoais de militares:

- 7.369 paths distintos sob `data/` já versionados em algum commit (2.115 PDF, 1.690 TXT, 1.451 ODT, 1.136 JSON, 926 ZIP, 48 CSV, 1 DB), 2.124 deles com posto/nome no próprio nome do arquivo.
- `data/sisges.db` real de **184.946.688 bytes** num commit antigo (mais uma segunda versão de 32.997.376 bytes).
- `.venv/` inteiro commitado (4.690 arquivos adicionados na história — binários de bibliotecas Python, incluindo `.pyd`/`.dll`).
- Varredura dedicada de CPF em texto plano: **322 ocorrências de padrão compatível com CPF** confirmadas em 898 blobs `.json/.txt/.csv` sob `data/`.
- `gitleaks` (v8.30.1) rodado sobre toda a história: 64 achados, 100% falsos positivos (senha de fixture de teste e ruído de bibliotecas vendorizadas dentro de `.venv/`) — nenhum segredo real de produção encontrado.
- Dois arquivos binários fora de `data/` também expostos: `tests/e2e/fixtures/sample.pdf` e `tests/e2e/fixtures/template.odt` (hoje vazios e não rastreados).
- Seis commits anteriores do tipo `chore(repo): stop tracking ...` mostravam que a limpeza já tentada antes era só "parar de rastrear daqui para frente" — a história continuava recuperável via `git checkout` de qualquer commit antigo.

## 2. Decisão e ações executadas

1. Containment imediato solicitado ao operador do repositório: tornar a visibilidade privada manualmente via GitHub UI (não havia `gh` CLI autenticado disponível para fazer isso programaticamente).
2. Ferramental instalado fora do `.venv` do projeto: `git-filter-repo` 2.47.0 (via `pip install --user`) e `gitleaks` 8.30.1 (binário standalone).
3. Mirror de segurança criado e validado (`git clone --mirror` + `git fsck --full`) antes de qualquer reescrita.
4. Trabalho em andamento (17 arquivos modificados + 22 novos, relacionados a folhas/declarações) commitado como checkpoint de segurança antes da reescrita, para não correr risco de perda.
5. Reescrita de histórico executada:

   ```
   git-filter-repo --invert-paths --path data --path .venv --path .env \
     --path tests/e2e/fixtures/sample.pdf --path tests/e2e/fixtures/template.odt --force
   ```

6. Branch local obsoleto `backup/pre-clean-large-db` (confirmado nunca enviado ao remote, e também já reescrito pelo filter-repo) removido.
7. Histórico saneado enviado ao GitHub: `git push origin develop --force` e `git push origin main --force` (este último sobrescrevendo apenas o `.gitkeep` automático).
8. Verificação independente: clone novo direto do GitHub, auditado do zero — zero ocorrências de `data/`, `.venv/`, `.env` ou dos dois fixtures binários em qualquer branch; maior blob remanescente é código-fonte (~65 KB).

## 3. Resultado

| Métrica | Antes | Depois |
|---|---|---|
| Tamanho de `.git/` | ~130 MB | ~1,05 MB |
| Maior blob na história | 184,9 MB (`data/sisges.db`) | ~65 KB (código-fonte) |
| Paths sensíveis sob `data/` na história | 7.369 | 0 |
| Arquivos `.venv/` na história | 4.690 | 0 |
| Segredos reais encontrados (gitleaks) | 0 (confirmado antes e depois) | 0 |

## 4. Riscos residuais (não eliminados por esta fase)

- **O repositório esteve público com esses dados por um período não determinado antes desta correção.** Qualquer pessoa que tenha clonado, feito fork ou usado ferramentas de scraping automatizado durante essa janela pode já ter uma cópia completa do histórico antigo, fora do controle deste repositório. Reescrever o histórico no GitHub não revoga cópias já feitas.
- GitHub pode manter objetos antigos "soltos" (dangling) acessíveis por hash direto por um tempo após um force-push, até a rotina de garbage collection da plataforma rodar. Para mitigação máxima, considerar abrir um chamado com o suporte do GitHub pedindo purga de cache para commits específicos.
- Não foi verificado neste processo se existem forks do repositório. Recomenda-se checar manualmente em GitHub → aba "Insights" → "Forks".
- `.gitignore` atual já impede que os mesmos arquivos voltem a ser commitados a partir de agora, mas não há ainda um scan automático de segredos/PII no fluxo de CI (entra na Fase 4 do plano de ação).

## 5. Critério de aceite

- [x] Visibilidade do GitHub revertida para privada (ação manual do operador).
- [x] `.git/` local reduzido de ~130 MB para ~1 MB.
- [x] Zero ocorrências de `data/`, `.venv/`, `.env` em `git log --all --name-only` no histórico local e no clone de verificação.
- [x] `gitleaks detect` limpo (sem segredos reais) antes e depois.
- [x] `pytest` (372 testes) e `ruff check .` continuam verdes após a reescrita.
- [x] Branch obsoleto de backup removido.
- [x] Push do histórico saneado confirmado por clone independente.

## 6. Rollback

Caso necessário reverter esta limpeza (não recomendado, reabriria a exposição): o mirror de segurança pré-reescrita está em `C:\caminho\para\sisges-MIRROR-BACKUP-20260623.git`, fora da árvore de trabalho do projeto.
