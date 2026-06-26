# Política de Segurança

## Escopo

O SisGeS processa dados pessoais reais de militares (identificação, CPF, endereço, situação funcional, histórico de serviço). Qualquer vulnerabilidade que possa expor, vazar ou permitir acesso não autorizado a esses dados é tratada com **severidade alta** por padrão, independentemente da complexidade técnica do exploit.

## Como reportar

Envie um e-mail para **vieiraalexandre515@gmail.com** com:

- Descrição da vulnerabilidade e impacto potencial.
- Passos para reproduzir (ou prova de conceito, se aplicável).
- Versão/commit afetado.

**Não abra issue pública para vulnerabilidades.** Issues públicas são só para bugs funcionais sem impacto de segurança ou exposição de dados.

## O que NÃO fazer

- Não execute varredura automatizada, força bruta ou testes de carga contra qualquer instância real/operacional do sistema sem autorização explícita prévia.
- Não baixe, copie ou retenha dados pessoais reais encontrados durante a investigação — reporte a existência do problema, não extraia evidência além do mínimo necessário para a prova de conceito.
- Não divulgue publicamente antes de uma correção ser publicada (coordenação de disclosure).

## Prazo de resposta esperado

- Confirmação de recebimento: até 5 dias úteis.
- Avaliação inicial de severidade: até 10 dias úteis.
- Correção para achados de severidade alta (exposição de dados pessoais, bypass de autenticação/autorização, injeção): prioridade imediata após confirmação.

## Histórico relevante

Este projeto já passou por um processo de saneamento de histórico git por exposição acidental de dados pessoais em commits antigos — ver `docs/SANEAMENTO_HISTORICO_GIT_FASE1.md` e `docs/SANEAMENTO_HISTORICO_GIT_FASE2.md`. Reportar proativamente é sempre preferível a um achado externo.
