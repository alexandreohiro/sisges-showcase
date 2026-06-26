# Reconstrucao tecnica do backend SISGES - Fase 5

Data: 2026-05-03

## 1. Diagnostico executivo

O compilador existia como conjunto funcional de endpoints, parser e render ODT, mas ainda operava como upload direto:

- arquivos temporarios eram criados com `delete=False` e podiam sobrar no disco;
- upload nao validava extensao, MIME, tamanho nem arquivo vazio;
- templates ODT nao tinham versao tecnica rastreavel;
- documento gerado era registrado com poucos metadados;
- nao havia `trace_id` por execucao;
- hashes de entrada, template e saida nao eram registrados;
- o pipeline estava concentrado na rota HTTP, dificultando teste, auditoria e evolucao.

## 2. Arquitetura proposta

A Fase 5 introduz um subsistema documental incremental, sem reescrever parser/render existentes.

Camadas:

- `apps/web/routes/compilador.py`: adaptador HTTP, permissao, upload e resposta.
- `infra/pipeline/uploads.py`: politica de validacao de upload.
- `infra/pipeline/workspace.py`: workspace temporario isolado por execucao.
- `infra/pdf`: extracao PDF ja existente.
- `modules/compilador/application/pipeline.py`: orquestrador auditavel do pipeline.
- `infra/odt/templates.py`: registro/versionamento de templates ODT por hash.
- `infra/odt`: render ODT ja existente.
- `modules/documents`: registro final de metadados do documento.
- `shared/utils/hashing.py`: hash SHA-256 de artefatos.

## 3. Fluxograma textual

1. Receber upload HTTP com permissao.
2. Validar metadados do upload:
   - extensao;
   - MIME type;
   - tamanho maximo;
   - arquivo vazio.
3. Criar workspace temporario isolado com `trace_id`.
4. Salvar entrada no workspace.
5. Calcular SHA-256 e tamanho da entrada.
6. Extrair texto do PDF.
7. Validar e limpar texto.
8. Normalizar semantica da Parte 1.
9. Parsear `CompilationRecord`.
10. Enriquecer com gestao de pessoal quando possivel.
11. Validar pendencias canonicas.
12. Registrar template ODT versionado por SHA-256.
13. Renderizar ODT no workspace.
14. Mover output final para `data/outputs`.
15. Calcular SHA-256 e tamanho do output.
16. Registrar documento gerado com `trace_id`, hashes, versao do template e metadados.
17. Limpar workspace automaticamente.

## 4. Decisoes tecnicas

### Validacao de upload

`infra/pipeline/uploads.py` define politicas explicitas:

- PDF: `.pdf`, `application/pdf`, maximo 25 MB.
- ODT: `.odt`, `application/vnd.oasis.opendocument.text` ou `application/octet-stream`, maximo 10 MB.

Decisao: `application/octet-stream` foi aceito para ODT porque alguns browsers/sistemas enviam ODT assim. A validacao estrutural posterior exige ZIP valido com `content.xml`.

### Workspace temporario

`PipelineWorkspaceManager` cria um diretorio por execucao em `data/temp/compilador` e remove tudo ao sair do contexto.

Trade-off: se o processo morrer abruptamente, lixo pode permanecer. A mitigacao operacional da Fase 6 deve incluir rotina de limpeza por idade.

### Versionamento de template

`OdtTemplateRegistry` salva templates em `data/templates/odt/<sha12>.odt`. A versao tecnica e o prefixo de 12 caracteres do SHA-256 completo.

Decisao: versionamento por conteudo evita duplicidade, e permite reexecutar ou auditar geracoes com o mesmo template.

### Registro documental

`DocumentModel` recebeu campos opcionais:

- `trace_id`;
- `template_sha256`;
- `template_version`;
- `input_sha256`;
- `output_sha256`;
- `metadata_json`.

Esses campos nao quebram registros antigos e foram adicionados por migration incremental.

## 5. Arquivos entregues

- `infra/pipeline/uploads.py`: validacao de upload.
- `infra/pipeline/workspace.py`: workspace temporario com limpeza.
- `infra/odt/templates.py`: versionamento de template ODT.
- `shared/utils/hashing.py`: SHA-256 de artefatos.
- `modules/compilador/application/pipeline.py`: pipeline documental auditavel.
- `apps/web/routes/compilador.py`: endpoints usando pipeline e respostas com rastreabilidade.
- `infra/persistence/models.py`: novos campos de rastreabilidade em `documents`.
- `modules/documents/application/services.py`: registro de metadados documentais.
- `migrations/versions/20260503_0002_document_pipeline_metadata.py`: migration incremental.
- `tests/unit/test_compilador_pipeline.py`: testes de upload/workspace/template.

## 6. Criterios de aceite

- Upload PDF invalido deve retornar erro estruturado `400`.
- Upload ODT invalido deve retornar erro estruturado `400`.
- Arquivo vazio deve ser rejeitado.
- Workspace temporario deve ser removido ao final da execucao.
- Template ODT deve ser validado como ZIP com `content.xml`.
- Template ODT deve ser versionado por hash.
- Documento gerado deve registrar `trace_id`, `template_version`, `template_sha256`, `input_sha256` quando houver entrada PDF, `output_sha256` e metadados.
- `python -m pytest` deve passar.
- `python -m ruff check .` deve passar.
- Import da app deve registrar rotas sem erro.

## 7. Riscos restantes

- OCR real, deteccao de blocos/tabelas e politicas avancadas de erro por etapa ainda dependem da evolucao dos modulos `infra/pdf/block_detector.py`, `infra/pdf/table_detector.py` e `infra/pdf/ocr.py`.
- A limpeza de temporarios e feita por contexto; limpeza de diretorios antigos apos queda abrupta fica para operacao/Fase 6.
- A resposta HTTP ainda preserva formatos historicos para compatibilidade, entao algumas falhas de render continuam retornando `success=false` em vez de HTTP 500.
- O registro de template versionado armazena arquivo local. Para ambiente distribuido, isso deve migrar para storage compartilhado.

## 8. Rollback

Para rollback da Fase 5:

1. Reverter `apps/web/routes/compilador.py` para o fluxo anterior.
2. Remover uso de `CompilerDocumentPipeline` do container.
3. Reverter novos componentes em `infra/pipeline`, `infra/odt/templates.py` e `shared/utils/hashing.py`.
4. Executar downgrade da migration `20260503_0002` se ela tiver sido aplicada.
5. Remover arquivos gerados em `data/templates/odt` e outputs criados durante testes manuais.
