# Gestao de pessoal - importacao PDF e antiguidade

Data: 2026-05-06

## Diagnostico

O modulo de gestao de pessoal listava militares por nome e aceitava importacao textual, mas nao tratava a ficha SiCaPEx em PDF nem separava efetivo em ativos/inativos na OM. Para uso operacional, a relacao de ativos precisa vir por antiguidade.

## Arquitetura

- `modules/gestao_pessoal/application/pdf_importer.py`: extracao e normalizacao de ficha SiCaPEx PDF.
- `modules/gestao_pessoal/application/antiguidade.py`: ranking deterministico por posto/graduacao, data de incorporacao e idade.
- `GestaoPessoalRepository.list_efetivo_om`: separa ativos e inativos na OM.
- `POST /gestao-pessoal/parse-pdf`: valida e analisa PDF sem gravar.
- `POST /gestao-pessoal/from-pdf`: valida, extrai e cria/atualiza militar por identidade funcional ou CPF.
- `GET /gestao-pessoal/efetivo-om`: retorna `ativos_na_om` e `inativos_na_om`.

## Regra de antiguidade

1. Posto/graduacao por precedencia militar.
2. Data de incorporacao mais antiga primeiro.
3. Data de nascimento mais antiga primeiro.
4. Nome completo como desempate estavel.

## Campos extraidos do PDF

Nome completo, nome de guerra, posto/graduacao, OM atual, situacao, status, identidade funcional, identidade civil, CPF, CP, Prec-CP, PIS/PASEP, titulo eleitoral, nascimento, filiacao, escolaridade, religiao, dados medicos, contato, QAS/QMS, RM, local da OM, data de turma, ultima promocao, data de apresentacao na OM e data de incorporacao/praca.

## Requisito de completude da ficha SiCaPEx

Toda importacao nova de `FICHA CADASTRO - SiCaPEx` deve preservar a ficha completa extraida do PDF em `militar.ficha_cadastro_json`, alem dos campos normalizados usados pelas telas operacionais.

Contrato minimo do JSON:

- `schema_version`: versao do contrato interno, iniciando em `sicapex_ficha_cadastro.v1`.
- `source`: sistema de origem, tipo documental, nome do arquivo e hash SHA-256 quando houver PDF.
- `coverage`: quantidade de linhas e secoes capturadas.
- `fields`: campos normalizados usados pelo cadastro principal do militar.
- `sections`: linhas extraidas agrupadas por secao da ficha, como dados pessoais, documentos, afastamentos, alteracoes, dependentes, habilitacoes, movimentacoes, promocoes, situacoes regulamentares, TAF e TAT.
- `tables`: leitura estruturada inicial das secoes recorrentes, mantendo `raw` quando uma linha ainda nao puder ser decomposta com seguranca.

Decisao tecnica: nesta etapa, a ficha completa fica em JSON para preservar compatibilidade progressiva e evitar criar dezenas de tabelas instaveis antes de estabilizar fixtures reais de PDF. Campos juridicamente/operacionalmente consultados com frequencia devem migrar depois para tabelas relacionais especificas, mantendo o JSON como trilha de auditoria do documento de origem.

Dados pessoais sensiveis: o JSON contem CPF, filiacao, dependentes, dados medicos, dados bancarios e historico funcional. O acesso deve permanecer protegido por permissao de gestao de pessoal, com log/auditoria em evolucao futura.

## Riscos

PDF SiCaPEx possui marcas d'agua e quebras instaveis. O parser e deterministico e ajustado ao formato observado, mas novos layouts devem ser cobertos com fixtures adicionais.

## Rollback

Aplicar downgrade da migration `20260506_0005`, remover os campos `ficha_cadastro_*` dos schemas/modelos, remover a montagem do JSON em `pdf_importer.py` e manter os campos normalizados ja existentes.
