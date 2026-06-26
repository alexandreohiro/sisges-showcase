# História pública saneada — Fase 2

Data: 2026-06-23

## 1. Diagnóstico da fase

Mesmo após a Fase 1 (filter-repo no repositório privado), o histórico reescrito ainda é "história derivada de uma história contaminada". Para a versão pública, decidiu-se não depender de subtração: nascer de uma cópia nova, auditada, sem nenhum vínculo de objeto git com o histórico antigo.

## 2. Decisão

- Repositório privado `alexandreohiro/sisges` permanece como ferramenta operacional interna, com histórico completo (já saneado na Fase 1).
- Novo repositório público `alexandreohiro/sisges-showcase` nasce de uma exportação (`git archive`) do estado atual de `develop`, num diretório totalmente novo, sem `.git` herdado.
- Confirmado **0 forks e 0 watchers** no repositório privado antes de prosseguir (sem cópias externas conhecidas da janela em que esteve público).

## 3. Achados adicionais durante a preparação do snapshot

Antes de finalizar, uma varredura de padrão "11 dígitos" no snapshot atual (não na história) encontrou 12 arquivos com o caminho absoluto pessoal do desenvolvedor (`D:\Usuarios\<11 dígitos>\...`) hardcoded — 3 em código real (`scripts/secretaria_dataset.py`, `scripts/sisges_release_gate.py`, `scripts/validate_sisges_operational_stack.ps1`, como defaults de path) e 9 em documentação (exemplos de comando). Corrigido na própria Fase 2, antes do commit público:

- Os 3 scripts passaram a usar variáveis de ambiente (`SISGES_SECRETARIA_INPUT_DIR`, `SISGES_FRONTEND_PATH`) com fallback relativo/genérico, em vez de caminho fixo de um desenvolvedor específico.
- Os 9 documentos passaram a usar `C:\caminho\para\...` como placeholder.
- `sisges.egg-info/` (5 arquivos), rastreado desde antes da regra `*.egg-info/` existir no `.gitignore`, também foi removido do rastreamento.

Essa correção foi commitada no repositório privado (`f8419d5` e `90d1d0d`) antes de gerar o snapshot final, então o público já nasce sem esse problema.

## 4. Execução

1. `git archive --format=tar develop` exportado para diretório novo `sisges-showcase` (fora da árvore do projeto privado).
2. Adicionados `LICENSE` (All Rights Reserved, uso restrito — ver arquivo) e nota de proveniência no `README.md` explicando a relação entre os dois repositórios.
3. Varredura final no snapshot: 0 ocorrências de caminho pessoal, 0 `data/`/`.venv/`/`.env`, 442 arquivos, ~2 MB.
4. `git init`, commit único auditado, branch renomeado para `main`.
5. `gitleaks detect` sobre o novo histórico: mesmos 39 falsos positivos já conhecidos (senha de fixture de teste), nenhum segredo real.
6. Repositório criado via `gh repo create alexandreohiro/sisges-showcase --private` (privado primeiro, de propósito) e push inicial.
7. Verificação independente: clone novo a partir do GitHub, reauditado do zero — 442 arquivos, 1 commit, 0 ocorrências sensíveis.
8. Só então: `gh repo edit alexandreohiro/sisges-showcase --visibility public`. Confirmado via API: `visibility: PUBLIC`.

## 5. Resultado

| Repositório | Visibilidade | Histórico | Tamanho |
|---|---|---|---|
| `alexandreohiro/sisges` | Privado | Completo (saneado na Fase 1) | ~1 MB (`.git/`) |
| `alexandreohiro/sisges-showcase` | Público | 1 commit | ~2 MB (conteúdo) |

## 6. Critério de aceite

- [x] Repositório público criado a partir de cópia auditada, não de subtração de histórico.
- [x] Zero dados sensíveis confirmados por clone independente antes de tornar público.
- [x] Repositório privado permanece privado e separado, recebendo o desenvolvimento contínuo.
- [x] README público explica a relação entre os dois repositórios.
- [x] LICENSE presente, restringindo uso/reprodução por terceiros.

## 7. Pendências para fases seguintes

- LICENSE/CONTRIBUTING/SECURITY.md/templates de issue e PR ainda precisam de tratamento mais completo (Fase 3).
- `sisges-showcase` ainda não tem CI próprio nem branch protection (Fase 3/4) — por ora é um snapshot estático.
- Não há automação para portar mudanças futuras do privado para o público; isso é manual, fora do escopo deste plano.
