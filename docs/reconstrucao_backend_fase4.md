# Reconstrucao tecnica do backend SISGES - Fase 4

Data: 2026-05-03

## 1. Diagnostico da fase

Antes desta fase, os repositorios faziam `commit()` diretamente. Isso quebrava atomicidade em casos de uso compostos: uma folha podia ser gravada antes da tarefa/notificacao, um documento podia ser registrado fora de uma fronteira clara, e o calculo de tempo aplicava ajustes e snapshot com commit interno acoplado ao servico.

## 2. Decisao arquitetural

Foi criado um padrao transacional pequeno e explicito em `infra/persistence/transactions.py`.

Regra adotada:

- repositorios podem `add`, `flush` e `refresh`;
- repositorios nao fazem `commit`;
- servicos de aplicacao e rotas HTTP definem a fronteira de commit/rollback com `atomic(db)`;
- fluxos compostos devem ficar dentro de uma unica unidade transacional.

Essa abordagem preserva a estrutura atual e evita criar uma camada de Unit of Work pesada antes de haver necessidade real.

## 3. Fluxos revisados

### Folha + tarefa + notificacao

`FolhasService.create_folha_with_task()` agora executa a criacao da folha, tarefa, evento e notificacao dentro de `atomic(db)`. Se qualquer etapa falhar, o rollback remove todas as entidades criadas na tentativa.

### Compilador + documento gerado

`DocumentService.register_document()` agora controla uma transacao propria para registrar metadados de documento gerado. Quando for chamado dentro de um fluxo maior no futuro, `atomic(db)` suporta composicao por profundidade.

Observacao: limpeza de arquivo ODT fisico em caso de falha de banco ainda pertence a Fase 5, junto com o redesenho do pipeline documental.

### Calculo + snapshot

`CalculoTempoServicoConsolidador.approve_and_save()` agora aplica diff e grava snapshot dentro de `atomic(db)`. O preview/diff continua fora da transacao de escrita.

## 4. Erros HTTP

Foi adicionado `apps/web/errors.py` com helpers para erro padronizado:

```json
{
  "detail": {
    "code": "CODIGO_DO_ERRO",
    "message": "Mensagem legivel"
  }
}
```

Rotas tocadas nesta fase passam a usar erro estruturado para `404` e `400`.

## 5. Arquivos principais

- `infra/persistence/transactions.py`: fronteira transacional reutilizavel.
- `apps/web/errors.py`: helpers de erro HTTP padronizado.
- `modules/*/infrastructure/*repository.py`: repositorios sem `commit`.
- `modules/folhas/application/services.py`: fluxo composto atomico.
- `modules/documents/application/services.py`: registro de documento com transacao.
- `modules/calculo_tempo_servico/application/services.py`: aprovacao/snapshot atomicos.
- `apps/web/routes/*`: rotas de escrita usando `atomic(db)` ou servicos transacionais.

## 6. Criterios de aceite

- Nenhum repositorio operacional deve chamar `commit`.
- `FolhasService.create_folha_with_task()` deve fazer rollback completo se a tarefa falhar.
- Registro de documento gerado deve persistir metadados com transacao.
- Calculo aprovado deve aplicar diff e snapshot na mesma transacao.
- `python -m pytest` deve passar.
- `python -m ruff check .` deve passar.

## 7. Riscos e trade-offs

- Algumas rotas simples ainda controlam transacao diretamente. Isso e aceitavel nesta fase para evitar criar servicos artificiais sem regra de negocio adicional.
- O padrao `atomic(db)` faz rollback da transacao inteira em falha, mesmo em uso aninhado. Isso e intencional para evitar commit parcial silencioso.
- O arquivo fisico gerado pelo compilador ainda nao participa de rollback; isso sera tratado na Fase 5 com workspace por execucao e limpeza segura.

## 8. Rollback

Para rollback da Fase 4:

1. Reverter `infra/persistence/transactions.py` e chamadas a `atomic(db)`.
2. Restaurar commits internos nos repositorios.
3. Reverter `apps/web/errors.py` e erros estruturados se o frontend ainda depender de `detail` string.
4. Nenhuma migration de banco foi adicionada nesta fase.

