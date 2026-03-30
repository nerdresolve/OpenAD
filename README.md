# OpenAD — Portal de Autoatendimento de Senhas do Active Directory

Portal web seguro e auditável para que colaboradores do Empresa alterem suas próprias senhas no Active Directory, sem intervenção da equipe de TI.

---

## Visão Geral

O OpenAD é uma aplicação web stateless construída com FastAPI que expõe um único formulário de alteração de senha. O backend autentica o usuário diretamente no AD via LDAP, executa a operação de troca de senha respeitando todas as GPOs configuradas no domínio, e registra cada tentativa em log estruturado — sem armazenar ou transmitir senhas em nenhum ponto.

**Características principais:**

- Autenticação via bind LDAP com as credenciais atuais do usuário
- Conta de serviço dedicada para lookup de DN (leitura somente)
- Suporte a LDAP (389), StartTLS e LDAPS (636) sem refatoração
- Rate limiting por IP para proteção contra brute force
- Healthcheck ativo que sonda a conectividade LDAP a cada requisição
- Interface em português, identidade visual Empresa
- Execução em container Docker não-root com limite de memória

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                     │
│  index.html (HTML/CSS/JS vanilla)                           │
│  POST /api/change-password                                  │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────────────────┐
│  FastAPI (uvicorn, porta 8000)                              │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │  main.py     │  │ validators.py │  │ rate_limiter.py  │ │
│  │  (routing,   │  │ (UPN, senha,  │  │ (sliding window, │ │
│  │   logging,   │  │  LDAP inj.)   │  │  por IP)         │ │
│  │   lifespan)  │  └───────────────┘  └──────────────────┘ │
│  └──────┬───────┘                                           │
│         │                                                   │
│  ┌──────▼───────────────────────────────────────────────┐  │
│  │  ldap_service.py (lógica de negócio)                 │  │
│  │  1. lookup DN via conta de serviço                   │  │
│  │  2. bind com credenciais do usuário                  │  │
│  │  3. modify unicodePwd (DELETE old + ADD new)         │  │
│  └──────┬───────────────────────────────────────────────┘  │
│         │                                                   │
│  ┌──────▼───────────────────────────────────────────────┐  │
│  │  ldap_client.py (fábrica de conexões)                │  │
│  │  build_server() / open_connection() / probe()        │  │
│  └──────┬───────────────────────────────────────────────┘  │
└─────────┼───────────────────────────────────────────────────┘
          │ LDAP / StartTLS / LDAPS
┌─────────▼───────────────────────────────────────────────────┐
│  Active Directory — Domain Controller                       │
│  dc01.empresa.local  empresa.local                             │
└─────────────────────────────────────────────────────────────┘
```

### Separação de responsabilidades

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Leitura de variáveis de ambiente; validação de configuração |
| `ldap_client.py` | Fábrica de conexões LDAP; suporte a Plain/StartTLS/LDAPS; probe de healthcheck |
| `ldap_service.py` | Lógica de negócio: lookup de DN, autenticação do usuário, operação de troca de senha |
| `validators.py` | Validação de UPN, tamanho e formato de senhas, proteção contra injeção LDAP |
| `rate_limiter.py` | Controle de taxa por IP (sliding window, thread-safe) |
| `main.py` | Roteamento HTTP, ciclo de vida da aplicação, logging de auditoria |

### Fluxo de autenticação e troca de senha

```
Usuário preenche formulário
        │
        ▼
[1] Validação de input (UPN, tamanho, caracteres proibidos)
        │
        ▼
[2] Rate limiting por IP (5 tentativas / 5 minutos)
        │
        ▼
[3] Conta de serviço (svc-openad) faz bind ao AD
        │  → busca DN do usuário via (userPrincipalName=<upn>)
        │  → desconecta
        ▼
[4] Usuário faz bind com suas próprias credenciais
        │  → prova de identidade: se falhar, retorna erro 52e
        ▼
[5] Modify unicodePwd: DELETE senha_atual + ADD senha_nova (operação atômica)
        │  → AD valida: histórico, complexidade, idade mínima, GPOs
        ▼
[6] Resposta ao usuário + entrada no log de auditoria
```

---

## Pré-requisitos

- Docker Engine 24+ e Docker Compose v2+
- Acesso de rede à porta 389 (ou 636) do Domain Controller a partir do host Docker
- Conta de serviço no AD com permissão de leitura no diretório (`svc-openad`)
- Python 3.12+ apenas se for executar fora do Docker (desenvolvimento local)

---

## Preparação do Ambiente

### 1. Criar o arquivo `.env`

```bash
cp .env.example .env
```

Edite `.env` com os valores do seu ambiente. **Nunca versione este arquivo.**

### 2. Variáveis de ambiente — referência completa

| Variável | Obrigatória | Descrição |
|---|---|---|
| `LDAP_SERVER` | Sim | Endereço IP ou hostname do Domain Controller |
| `LDAP_PORT` | Não | Porta LDAP. Padrão: `389`. Use `636` para LDAPS |
| `LDAP_DOMAIN` | Sim | Nome do domínio AD (ex: `empresa.local`) |
| `LDAP_BASE_DN` | Sim | Base DN para buscas (ex: `dc=empresa,dc=local`) |
| `LDAP_USE_SSL` | Não | `true` para LDAPS (TLS implícito, porta 636). Padrão: `false` |
| `LDAP_USE_TLS` | Não | `true` para StartTLS (upgrade na porta 389). Padrão: `false` |
| `CA_CERT_PATH` | Condicional | Caminho do certificado CA dentro do container. Necessário quando `LDAP_USE_SSL=true` ou `LDAP_USE_TLS=true` com CA interna |
| `LDAP_BIND_USER` | Sim | UPN da conta de serviço (ex: `svc-openad@empresa.local`) |
| `LDAP_BIND_PASSWORD` | Sim | Senha da conta de serviço |
| `RATE_LIMIT_MAX` | Não | Máximo de tentativas por IP na janela. Padrão: `5` |
| `RATE_LIMIT_WINDOW` | Não | Janela de tempo em segundos. Padrão: `300` |
| `LOG_LEVEL` | Não | Nível de log: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Padrão: `INFO` |

---

## Configuração LDAP

### Ambiente atual (Empresa)

```env
LDAP_SERVER=dc01.empresa.local
LDAP_PORT=389
LDAP_DOMAIN=empresa.local
LDAP_BASE_DN=dc=empresa,dc=local
LDAP_USE_SSL=false
LDAP_USE_TLS=false
LDAP_BIND_USER=svc-openad@empresa.local
LDAP_BIND_PASSWORD=<senha_da_conta_de_servico>
```

### Exemplo genérico (outro ambiente)

```env
LDAP_SERVER=dc01.empresa.com.br
LDAP_PORT=389
LDAP_DOMAIN=empresa.com.br
LDAP_BASE_DN=dc=empresa,dc=com,dc=br
LDAP_USE_SSL=false
LDAP_USE_TLS=false
LDAP_BIND_USER=svc-openad@empresa.com.br
LDAP_BIND_PASSWORD=<senha-da-conta-de-servico>
```

### Permissões necessárias para a conta de serviço

A conta `svc-openad` (ou equivalente) precisa apenas de:

- **Read** em `userPrincipalName` e `distinguishedName` para todos os objetos de usuário no escopo do `LDAP_BASE_DN`
- **Sem** permissão de escrita — a operação de senha é executada pelo próprio usuário autenticado

---

## Execução via Docker

### Build e inicialização

```bash
# Build da imagem e start do container
docker compose up -d --build

# Verificar status
docker compose ps

# Acompanhar logs em tempo real
docker compose logs -f openad
```

### Acesso

Após o start, acesse via browser:

```
http://<ip-do-host>:8000
```

### Parar o serviço

```bash
docker compose down
```

### Rebuild após alterações de código

```bash
docker compose up -d --build --force-recreate
```

---

## Healthcheck e Validação da Integração LDAP

### Endpoint `/health`

O endpoint `/health` executa um bind real com a conta de serviço a cada chamada, refletindo o estado atual da conectividade com o AD.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

**Resposta quando saudável (HTTP 200):**
```json
{
  "status": "ok",
  "ldap": "LDAP connection successful."
}
```

**Resposta quando degradado (HTTP 503):**
```json
{
  "status": "degraded",
  "ldap": "LDAP connection failed: LDAPSocketOpenError"
}
```

### Healthcheck do Docker

O `docker-compose.yml` configura um healthcheck nativo:

```yaml
healthcheck:
  test: ["CMD", "python", "-c",
         "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

Verifique o estado do container:

```bash
docker inspect openad --format='{{.State.Health.Status}}'
# healthy | unhealthy | starting
```

### Validação manual da conectividade LDAP

```bash
# Teste de bind com ldapsearch (requer ldap-utils instalado no host)
ldapsearch -x -H ldap://dc01.empresa.local:389 \
  -D "openad.connect@empresa.local" \
  -w "SUA_SENHA" \
  -b "dc=empresa,dc=local" \
  "(userPrincipalName=usuario@empresa.local)" dn
```

---

## Estrutura de Pastas

```
OpenAD/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuração via variáveis de ambiente
│   ├── ldap_client.py     # Fábrica de conexões LDAP (Plain/StartTLS/LDAPS)
│   ├── ldap_service.py    # Lógica de troca de senha no AD
│   ├── main.py            # FastAPI: rotas, lifecycle, logging de auditoria
│   ├── rate_limiter.py    # Rate limiting por IP (sliding window)
│   ├── validators.py      # Validação de UPN e senhas
│   └── static/
│       ├── favicon.webp   # Logo Empresa
│       └── index.html     # Frontend (HTML/CSS/JS vanilla)
├── .env                   # Configuração de runtime (não versionar)
├── .env.example           # Template sem credenciais
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── claude.md              # Memória técnica do projeto (uso interno)
└── progress.txt           # Log de execução (uso interno)
```

---

## Logs e Troubleshooting

### Formato dos logs

Todos os logs seguem o padrão estruturado `chave=valor`, sem dados sensíveis:

```
2025-01-15T10:23:41 level=INFO logger=openad startup ldap_probe=ok
2025-01-15T10:24:05 level=INFO logger=openad ldap.lookup status=ok upn=joao@empresa.local
2025-01-15T10:24:05 level=INFO logger=openad ldap.auth status=ok upn=joao@empresa.local
2025-01-15T10:24:05 level=INFO logger=openad ldap.change_password status=success upn=joao@empresa.local
2025-01-15T10:24:05 level=INFO logger=openad change_password_success ip=10.0.0.5 upn=joao@empresa.local ts=2025-01-15T10:24:05+00:00
```

### Visualizar logs do container

```bash
# Logs em tempo real
docker compose logs -f openad

# Últimas 100 linhas
docker compose logs --tail=100 openad

# Filtrar por operação
docker compose logs openad | grep "change_password"

# Filtrar falhas de autenticação
docker compose logs openad | grep "bind_failed"
```

### Erros comuns e diagnóstico

| Erro nos logs | Causa provável | Solução |
|---|---|---|
| `ldap_probe=failed LDAPSocketOpenError` | DC inacessível na porta configurada | Verificar firewall, IP e porta do DC |
| `ldap_probe=failed LDAPBindError` | Credenciais da conta de serviço inválidas | Revisar `LDAP_BIND_USER` e `LDAP_BIND_PASSWORD` |
| `ldap.lookup status=not_found` | UPN não existe no diretório | Usuário digitou UPN incorreto; confirmar domínio |
| `ldap.auth status=bind_failed` + `data 52e` | Senha atual incorreta | Usuário deve verificar a senha atual |
| `ldap.auth status=bind_failed` + `data 775` | Conta bloqueada | Desbloquear via ADUC ou aguardar expiração do lockout |
| `ldap.change_password status=error constraint violation` | Nova senha não atende a GPO | Usuário deve usar senha mais complexa ou aguardar idade mínima |
| `config_missing field=LDAP_SERVER` | Variável de ambiente ausente | Verificar o arquivo `.env` e reiniciar o container |
| `rate_limit_exceeded` | Muitas tentativas do mesmo IP | Aguardar a janela de 5 minutos ou ajustar `RATE_LIMIT_*` |

### Ativar modo DEBUG temporariamente

```bash
# Editar .env e definir:
LOG_LEVEL=DEBUG

# Reiniciar
docker compose up -d --force-recreate
```

> **Atenção:** O modo DEBUG pode expor detalhes da estrutura LDAP nos logs. Não usar em produção de forma permanente.

---

## Considerações de Segurança

### O que o OpenAD garante

- **Senhas nunca são logadas ou armazenadas** em nenhum ponto da aplicação
- **Conta de serviço com privilégio mínimo**: apenas leitura de DN, sem escrita
- **Autenticação pelo próprio usuário**: a troca de senha exige que o usuário prove sua identidade atual com bind direto ao AD
- **Proteção contra injeção LDAP**: UPN é sanitizado com `escape_filter_chars` antes de qualquer consulta
- **Rate limiting por IP**: 5 tentativas por janela de 5 minutos, configurável
- **Container não-root**: processo uvicorn executa como `appuser`
- **Limite de memória**: 150 MB enforced pelo Docker
- **API interna**: docs Swagger/ReDoc/OpenAPI desabilitados

### Recomendações adicionais para produção

1. **Coloque um reverse proxy na frente** (nginx, Traefik) com TLS encerrado no proxy. Nunca exponha a porta 8000 diretamente à internet.
2. **Restrinja o CORS** se o domínio for fixo: edite `allow_origins` em `main.py`.
3. **Use LDAPS ou StartTLS** em qualquer ambiente onde o tráfego passe por redes não totalmente confiáveis.
4. **Rotacione periodicamente** a senha da conta `svc-openad` e atualize o `.env`.
5. **Proteja o arquivo `.env`**: permissões `600`, nunca comitar em git.
6. **Configure log rotation** nos arquivos do Docker (já configurado para 10 MB / 3 arquivos).
7. **Monitore o endpoint `/health`** com seu sistema de monitoramento (Zabbix, Prometheus, Uptime Kuma, etc.).

### Sobre plain LDAP (porta 389 sem TLS)

A configuração atual usa LDAP simples na porta 389. Isso é aceitável em redes internas isoladas (LAN/VLAN segmentada), onde o tráfego entre o container e o DC não atravessa segmentos não confiáveis.

Se o tráfego precisar atravessar roteadores, VPNs ou redes compartilhadas, ative StartTLS ou LDAPS conforme o guia abaixo.

---

## Guia de Migração para LDAPS / StartTLS

A arquitetura do OpenAD foi projetada para que a migração para TLS não exija nenhuma alteração de código — apenas variáveis de ambiente.

### Migração para StartTLS (porta 389 com upgrade)

```env
LDAP_PORT=389
LDAP_USE_TLS=true
# Se o DC usa CA interna, adicionar:
# CA_CERT_PATH=/certs/ca.crt
```

### Migração para LDAPS (porta 636, TLS implícito)

```env
LDAP_PORT=636
LDAP_USE_SSL=true
# Se o DC usa CA interna, adicionar:
# CA_CERT_PATH=/certs/ca.crt
```

### Exportar e montar o certificado CA (se necessário)

1. Exportar o certificado raiz do AD CS em formato PEM.
2. Colocar o arquivo `ca.crt` em um diretório do host, por exemplo `/opt/openad/certs/`.
3. Adicionar volume no `docker-compose.yml`:

```yaml
services:
  openad:
    volumes:
      - /opt/openad/certs:/certs:ro
```

4. Definir no `.env`:

```env
CA_CERT_PATH=/certs/ca.crt
```

5. Reiniciar:

```bash
docker compose up -d --force-recreate
```

### Verificar TLS após a migração

```bash
# Testar LDAPS diretamente
openssl s_client -connect dc01.empresa.local:636 -showcerts

# Verificar no healthcheck
curl -s http://localhost:8000/health
```

---

## Boas Práticas de Operação em Produção

### Atualizações de versão

```bash
# Pull das alterações, rebuild e reinício sem downtime perceptível
git pull
docker compose up -d --build --force-recreate
```

### Backup de configuração

O único estado persistente do OpenAD é o arquivo `.env`. Faça backup seguro deste arquivo (cofre de senhas, secrets manager).

### Rotação de credenciais

Ao alterar a senha da conta `svc-openad` no AD:

1. Atualizar `LDAP_BIND_PASSWORD` no `.env`
2. Reiniciar o container: `docker compose up -d --force-recreate`
3. Verificar healthcheck: `curl http://localhost:8000/health`

### Monitoramento recomendado

```bash
# Verificação simples de saúde (pode ser usado em scripts de monitoramento)
curl -sf http://localhost:8000/health && echo "OK" || echo "DEGRADED"

# Contar alterações bem-sucedidas nas últimas 24h
docker compose logs openad | grep "change_password_success" | grep "$(date +%Y-%m-%d)" | wc -l

# Detectar picos de tentativas bloqueadas por rate limit
docker compose logs openad | grep "rate_limit_exceeded" | tail -20
```

### Limpeza de logs antigos

Os logs do Docker são rotacionados automaticamente (10 MB / 3 arquivos, configurado no `docker-compose.yml`). Nenhuma ação manual necessária.

---

## Requisitos de Sistema

| Componente | Mínimo |
|---|---|
| Docker Engine | 24.0+ |
| Docker Compose | v2.0+ |
| RAM alocada ao container | 150 MB (enforced) |
| CPU | 0.1 vCPU (carga típica) |
| Disco | ~200 MB (imagem Python slim + dependências) |
| Rede | Acesso à porta 389 (ou 636) do DC |

---

## Dependências Python

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
ldap3==2.9.1
pydantic==2.10.4
```
