# Logs Estruturados de Segurança SISGES

## Objetivo

Registrar anomalias de segurança em formato previsivel para auditoria defensiva, Wazuh, Fail2ban, SIEM ou coleta local.

## Logger

```text
sisges.security
```

## Contrato do evento

Campos minimos:

```json
{
  "security_event": true,
  "security_event_schema": "sisges-security-event-v1",
  "event_category": "security",
  "event_type": "UPLOAD_REJECTED",
  "event_code": "UPLOAD_MAGIC_INVALIDO"
}
```

Quando `SISGES_LOG_FORMAT=json`, o formatador adiciona tambem:

- `timestamp`;
- `level`;
- `logger`;
- `message`;
- `environment`.

## Eventos atuais

### UPLOAD_REJECTED

Emitido quando um upload e recusado pela politica defensiva.

Codigos esperados:

- `UPLOAD_EXTENSION_INVALIDA`;
- `UPLOAD_MIME_INVALIDO`;
- `UPLOAD_MAGIC_INVALIDO`;
- `UPLOAD_TAMANHO_EXCEDIDO`;
- `UPLOAD_VAZIO`.

Campos uteis:

- `upload_filename`;
- `extension`;
- `content_type`;
- `expected_magic`;
- `detected_magic`;
- `max_bytes`;
- `size_bytes`.

### CSRF_VALIDATION_FAILED

Emitido quando uma requisicao mutavel autenticada falha na validacao CSRF.

Codigos esperados:

- `CSRF_TOKEN_MISSING`;
- `CSRF_TOKEN_INVALID`.

Campos uteis:

- `client_ip`;
- `method`;
- `path`;
- `session_cookie_present`;
- `csrf_cookie_present`;
- `csrf_header_present`.

## Regras defensivas sugeridas

- Mais de 5 `CSRF_VALIDATION_FAILED` no mesmo IP em 5 minutos: revisar sessao, bloquear IP se recorrente.
- Mais de 3 `UPLOAD_MAGIC_INVALIDO` no mesmo IP/usuario em 10 minutos: bloquear tentativa de upload suspeito.
- `UPLOAD_TAMANHO_EXCEDIDO` recorrente: revisar limite e origem antes de aumentar `client_max_body_size`.
- `UPLOAD_EXTENSION_INVALIDA` com extensoes executaveis: tratar como alerta alto.

## Comandos de validacao

```powershell
python -m pytest tests/test_security_logging.py
python -m pytest tests/test_csrf_protection.py tests/test_upload_magic_validation.py
python -m ruff check .
```

## Observacoes

- Os logs nao substituem bloqueio de permissao no backend.
- Dados sensiveis nao devem ser enviados ao log como payload bruto.
- Arquivos rejeitados devem ser tratados como evidencia operacional apenas quando houver procedimento formal de incidente.
