# Fluxo Rápido de Entrega — Folhas de Alterações

Este fluxo é para produção controlada. Ele prioriza entrega rastreável, não tela bonita.

## 1. Preparar banco

```bash
python -m alembic upgrade head
python -m infra.persistence.seed
```

## 2. Validar ambiente

```bash
python -m ruff check .
python -m pytest
```

Se o teste completo estiver bloqueado por área não relacionada, rodar pelo menos os testes críticos do Compilador, SiCaPEx, cálculo e documentos.

## 3. Importar SiCaPEx

Dry-run:

```bash
python -m scripts.import_sicapex_zip --input data/input/SQL.zip --dry-run --report data/output/folhas/sicapex_dry_run.json
```

Commit:

```bash
python -m scripts.import_sicapex_zip --input data/input/SQL.zip --commit --report data/output/folhas/sicapex_commit.json
```

Conferir pendências críticas:

- identidade ausente;
- data de praça suspeita;
- QMS genérico;
- nome de guerra inválido;
- tempo insuficiente.

## 4. Importar fontes de alterações

```bash
python -m scripts.import_alteracoes_fontes --input data/input/2025 --ano 2025 --commit --report data/output/folhas/alteracoes_2025_import.json
```

Conferir `eventos_sem_associacao.json`, se existir.

## 5. Gerar lote

Dry-run:

```bash
python -m scripts.generate_folhas_alteracoes_batch --ano 2025 --semestre 2 --modelo data/input/modelos/MODELO_FOLHA.odt --output data/output/entrega_final/2025_2sem --dry-run
```

Geração real:

```bash
python -m scripts.generate_folhas_alteracoes_batch --ano 2025 --semestre 2 --modelo data/input/modelos/MODELO_FOLHA.odt --output data/output/entrega_final/2025_2sem --commit --allow-pending-output
```

## 6. Classificar entrega

```bash
python -m scripts.classificar_entrega_folhas --input data/output/entrega_final --output data/output/entrega_final/RELATORIOS
```

Saídas esperadas:

- `folhas_prontas.csv`
- `folhas_revisar.csv`
- `folhas_bloqueadas.csv`
- `resumo_entrega.txt`
- `checklist_assinatura.txt`

## 7. Revisar e promover

```bash
python -m scripts.validate_folha_output --folder data/output/entrega_final/REVISAR --recursive --output data/output/entrega_final/revisao_final/validacao_revisar.json
```

```bash
python -m scripts.promote_revisar_to_prontas --input data/output/entrega_final --output data/output/entrega_final_revisada
```

## 8. Empacotar

```bash
python -m scripts.pack_entrega_secretaria --input data/output/entrega_final_revisada --output data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

## 9. Conferir antes da assinatura

- Abrir `CHECKLIST_ASSINATURA_REVISADO.txt`.
- Conferir amostra.
- Conferir folhas em `REVISAR_MANUALMENTE`.
- Não assinar `BLOQUEADAS`.
- Registrar ciência de tempo pendente quando houver warning.

## 10. Hotfix individual

Quando apenas uma folha precisar correção:

```bash
python -m scripts.rebuild_folha_individual --identidade 9990000001 --ano 2025 --semestre 2 --modelo data/input/modelos/MODELO_FOLHA.odt --output data/output/entrega_final/hotfix --allow-pending-output
```

O hotfix deve preservar versão anterior e gerar nova validação.

## Pós-entrega e controle operacional

Depois de gerar o pacote revisado, use o comando operacional único da secretaria para validar, registrar e resumir a entrega sem reprocessar folhas.

Diagnóstico geral:

```bash
python -m scripts.secretaria_operacional diagnostico
```

Validar pacote revisado:

```bash
python -m scripts.secretaria_operacional validar-pacote --pacote data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

Validar documentação:

```bash
python -m scripts.secretaria_operacional validar-docs
```

Listar pendências:

```bash
python -m scripts.secretaria_operacional listar-pendencias --input data/output/entrega_final_revisada
```

Gerar checklist final:

```bash
python -m scripts.secretaria_operacional gerar-checklist --input data/output/entrega_final_revisada
```

Registrar entrega:

```bash
python -m scripts.secretaria_operacional registrar-entrega --pacote data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip --responsavel "NOME DO OPERADOR"
```

Resumo operacional:

```bash
python -m scripts.secretaria_operacional resumo
```

Esses comandos não geram novas folhas. Eles validam pacote, documentação, pendências, checklist e registro final.

## Release operacional

A release operacional é o congelamento da entrega. Ela copia o pacote revisado, hashes, relatórios, checklist, pendências e registro de entrega para `data/releases/`, gerando manifesto e README próprios.

Criar release:

```bash
python -m scripts.secretaria_release criar --nome secretaria_folhas_2025_revisado --pacote data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip
```

Validar release:

```bash
python -m scripts.secretaria_release validar --release data/releases/secretaria_folhas_2025_revisado
```

Resumo:

```bash
python -m scripts.secretaria_release resumo --release data/releases/secretaria_folhas_2025_revisado
```

Regras:

- a release é o congelamento da entrega;
- o pacote revisado não deve ser alterado;
- qualquer nova geração exige nova release;
- o SHA-256 é a prova de integridade;
- `data/output/` e `data/releases/` não devem ser commitados.
