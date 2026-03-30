# OpenAD — Memória Técnica do Projeto

## Visão Geral
Portal web stateless para autoatendimento de troca de senha no Active Directory.
Empresa. Execução on-premise via Docker. Sem sessões, sem armazenamento de senhas.

## Estrutura de Arquivos
```
OpenAD/
  app/
    __init__.py
    config.py          — Settings carregados de variáveis de ambiente
    ldap_client.py     — Fábrica de conexões: Plain / StartTLS / LDAPS + probe
    ldap_service.py    — Lógica de negócio: lookup DN, auth, unicodePwd modify
    main.py            — FastAPI: rotas, lifecycle, logging de auditoria
    rate_limiter.py    — Sliding window por IP, thread-safe
    validators.py      — Validação UPN (.local OK), senhas, anti-injeção LDAP
    static/
      favicon.webp     — Logo Empresa (asset real, sem alteração)
      index.html       — Frontend vanilla HTML/CSS/JS
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env                 — Runtime config (não versionar)
  .env.example         — Template sem credenciais
  README.md
```

## Parâmetros LDAP Configurados
- LDAP_SERVER: dc01.empresa.local
- LDAP_PORT: 389
- LDAP_DOMAIN: empresa.local
- LDAP_BASE_DN: dc=empresa,dc=local
- LDAP_USE_SSL: false
- LDAP_USE_TLS: false
- LDAP_BIND_USER: svc-openad@empresa.local
- Senha: em .env (não registrada aqui)

## Fluxo de Troca de Senha
1. Validação de input (UPN regex aceita .local, anti-injeção LDAP)
2. Rate limiting por IP (5/300s, sliding window)
3. Conta de serviço faz lookup do DN do usuário (read-only)
4. Usuário faz bind com credenciais atuais (prova de identidade)
5. unicodePwd modify atômico: DELETE encoded_old + ADD encoded_new
6. AD valida GPOs, histórico, complexidade, idade mínima
7. Log de auditoria: ip, upn, timestamp, resultado (sem senhas)

## Modelo de Segurança
- Conta de serviço: somente leitura de DN
- Bind do usuário: prova de identidade antes de qualquer modificação
- unicodePwd: único método que respeita todas as GPOs do AD
- escape_filter_chars: proteção contra injeção LDAP no filtro de busca
- Rate limit: 5 tentativas / 5 min por IP
- Container não-root (appuser)
- Limite de memória 150 MB

## Decisões Técnicas
- ldap_client.py separado de ldap_service.py: conexão vs. negócio
- LDAP_USE_TLS e LDAP_USE_SSL como flags independentes: migração sem refatoração
- probe_service_account() chamado no startup E no /health: estado real em tempo real
- Mensagens de erro em português: UX alinhada ao usuário final
- UPN regex aceita domínios single-label (.local, .corp): requisito do ambiente

## Tecnologias
- Python 3.12-slim
- FastAPI 0.115.6 + uvicorn 0.34.0
- ldap3 2.9.1
- pydantic 2.10.4

## Variáveis de Ambiente Obrigatórias
LDAP_SERVER, LDAP_DOMAIN, LDAP_BASE_DN, LDAP_BIND_USER, LDAP_BIND_PASSWORD

## Limitações Conhecidas
- Rate limiter em memória: reinício do container zera os contadores
- plain LDAP (port 389): adequado para rede interna isolada; usar TLS em redes roteadas
- unicodePwd requer que o DC tenha LDAPS ou que a operação seja feita autenticada
  (cumprido: usuário faz bind antes do modify)
