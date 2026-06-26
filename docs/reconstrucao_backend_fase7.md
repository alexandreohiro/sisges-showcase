# Reconstrucao tecnica do backend SISGES - Fase 7

Data: 2026-05-03

## 1. Diagnostico da fase

O modelo `CTSMModel` existia no banco, mas nao havia modulo web, servico de aplicacao nem fluxo de emissao documental. O calculo de tempo ja gerava snapshots aprovados em `calculo_tempo_servico`, e `documents` ja possuia rastreabilidade documental, mas CTSM ainda nao consumia esses dados.

## 2. Arquitetura-alvo

- `modules/ctsm/application/services.py`: caso de uso para criar CTSM a partir de calculo aprovado e emitir documento.
- `apps/web/routes/ctsm.py`: API HTTP do modulo CTSM.
- `infra/persistence/models.py`: vinculos opcionais `document_id` e `folha_id`, alem de metadados de emissao.
- `documents`: registro final do artefato emitido.
- `calculo_tempo_servico`: fonte juridico-operacional do snapshot aprovado.

## 3. Arquivos criados/alterados

- Criados: `modules/ctsm/*`, `apps/web/routes/ctsm.py`, `tests/unit/test_ctsm_service.py`.
- Alterados: `infra/persistence/models.py`, `infra/persistence/seed.py`, `apps/web/app.py`, `apps/web/routes/__init__.py`.
- Migration: `migrations/versions/20260503_0003_ctsm_document_links.py`.

## 4. Codigo por arquivo

Endpoints:

- `GET /ctsm`
- `GET /ctsm/{ctsm_id}`
- `POST /ctsm/from-calculo`
- `POST /ctsm/{ctsm_id}/emitir`

Fluxo principal:

1. Localiza snapshot aprovado em `calculo_tempo_servico`.
2. Carrega militar vinculado.
3. Monta `conteudo_json` juridico-documental versionado (`ctsm.v1`).
4. Cria registro CTSM.
5. Emite artefato textual inicial em `data/outputs`.
6. Registra o documento em `documents` com hash e metadados.
7. Atualiza CTSM com `document_id`, status e dados de emissao.

## 5. Criterios de aceite

- CTSM deve ser consultavel por API.
- CTSM deve poder ser criado a partir de calculo aprovado.
- Documento emitido deve ser registrado em `documents`.
- Registro CTSM deve guardar `document_id`.
- O conteudo deve carregar snapshot do militar e do calculo.
- Admin e operador devem receber permissoes basicas de CTSM via seed.
- Testes automatizados devem passar.

## 6. Riscos restantes

- O artefato emitido nesta fase e textual (`.txt`) para garantir rastreabilidade executavel; ODT/PDF oficial deve ser conectado ao pipeline documental da Fase 5.
- Ainda nao ha revisao/aprovacao juridica multi-etapa para CTSM.
- `folha_id` foi preparado como vinculo opcional, mas a criacao automatica de folha relacionada ainda nao foi implementada.
- Nao ha constraint unica impedindo multiplas CTSM para o mesmo calculo.

## 7. Rollback

1. Remover router `ctsm` de `apps/web/app.py`.
2. Reverter `modules/ctsm`.
3. Executar downgrade da migration `20260503_0003`, se aplicada.
4. Reverter permissoes CTSM no seed, se necessario.
5. Remover artefatos `data/outputs/ctsm-*.txt` gerados em testes manuais.
