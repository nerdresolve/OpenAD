<div align="center">

<img src="docs/brand/banner.svg" alt="OpenAD: troca de senha do Active Directory, sem chamado para o TI" width="100%">

Um formulário de três campos que troca a senha de uma pessoa no Active
Directory. Sem sessão, sem banco, sem senha guardada em lugar nenhum.

[![Licença](https://img.shields.io/badge/licen%C3%A7a-todos%20os%20direitos%20reservados-7C3AED)](LICENSE.md) ![Stack](https://img.shields.io/badge/FastAPI-Python%203.12-7C3AED) ![Runtime](https://img.shields.io/badge/imagem-150%20MB%20enforced-A855F7) ![Estado](https://img.shields.io/badge/estado-em%20produ%C3%A7%C3%A3o-0F7A42)

[A tela](#a-tela) · [Como funciona](#como-funciona) · [Rodar](#rodar) · [Configurar](#configurar) · [Segurança](#segurança) · [Licença](#licença)

</div>

---

## O que é

"Esqueci minha senha" é o chamado mais comum de qualquer service desk, e o
mais caro em proporção ao que resolve: alguém do TI para o que está fazendo,
confirma a identidade de quem ligou e digita a senha nova no ADUC.

O OpenAD tira o TI do meio. A pessoa abre a página, prova quem é com a senha
atual e escolhe a nova. O Active Directory continua sendo a autoridade: quem
valida complexidade, histórico e idade mínima é a GPO do domínio, não este
código.

<div align="center">
<img src="docs/capturas/portal.webp" alt="O portal de troca de senha" width="62%">
</div>

---

## A tela

<table>
<tr>
<td width="50%"><img src="docs/capturas/erro.webp" alt="Validação recusando a nova senha"><br><sub><b>Recusa</b> · o motivo aparece no campo, não num alerta genérico</sub></td>
<td width="50%"><img src="docs/capturas/sucesso.webp" alt="Senha alterada com sucesso"><br><sub><b>Sucesso</b> · sem redirecionar, sem sessão para encerrar</sub></td>
</tr>
</table>

> Não são mockups: é a aplicação rodando, com a validação real do backend
> respondendo. A força da senha é medida no navegador só para dar retorno
> imediato — quem decide se a senha vale é o AD.

---

## Como funciona

A troca acontece em três passos, e nenhum deles guarda a senha.

```
[1] valida entrada          UPN, tamanho, caracteres de injeção LDAP
         │
[2] rate limit por IP       5 tentativas / 5 min, janela deslizante
         │
[3] resolve o DN            conta de serviço, leitura apenas
         │
[4] bind com a senha atual  ← a prova de identidade acontece aqui
         │
[5] modify unicodePwd       o AD aplica histórico, complexidade e GPO
         │
[6] log de auditoria        ip, upn, resultado. Nunca a senha.
```

### Três decisões que valem registro

**A prova de identidade é um bind, não uma comparação.** O passo 4 abre uma
conexão LDAP com o UPN e a senha atual que a pessoa digitou. Se o bind falha,
a senha está errada — e quem diz isso é o domínio, com o código de erro dele
(`52e` senha incorreta, `775` conta bloqueada, `533` conta desabilitada). O
OpenAD não tem uma tabela de usuários para consultar, porque não tem banco.

**Quem escreve é a conta de serviço, e isso é deliberado.** O caminho mais
óbvio seria a própria pessoa executar o `unicodePwd` com `DELETE` da senha
antiga e `ADD` da nova. Ele funciona, mas esbarra na **idade mínima de senha**:
se a GPO exige que a senha tenha ao menos um dia de vida, a troca é recusada
justamente em quem acabou de receber uma senha provisória do suporte — o caso
mais comum. Então, depois de a pessoa provar quem é no passo 4, o
`MODIFY_REPLACE` é feito pela conta de serviço, que tem `Reset Password`
delegado. A idade mínima não se aplica a um reset administrativo; histórico e
complexidade continuam valendo.

O preço dessa decisão é uma conta com poder de redefinir senha na OU. Ela é a
credencial mais sensível da instalação, e a seção de [segurança](#segurança)
trata dela.

**O `/health` faz um bind de verdade a cada chamada.** Um healthcheck que só
responde "o processo está de pé" mente: o container fica verde enquanto
ninguém consegue trocar senha nenhuma porque o DC está fora. Aqui o endpoint
autentica a conta de serviço e devolve `503` quando o diretório não responde.
Custa um bind por chamada, e é o que torna o monitoramento honesto.

---

## Rodar

Precisa de **Docker** e de acesso de rede à porta 389 (ou 636) do Domain
Controller.

```bash
cp .env.example .env     # preencha o servidor, o domínio e a conta de serviço
docker compose up -d --build
```

A aplicação sobe em `http://localhost:8000`. Para acompanhar:

```bash
docker compose logs -f openad
docker inspect openad --format='{{.State.Health.Status}}'   # healthy | unhealthy
```

### Sem Docker, para desenvolver

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Verificar a integração com o AD

```bash
curl -s http://localhost:8000/health
```

```json
{ "status": "ok", "ldap": "LDAP connection successful." }
```

`503` com `"status": "degraded"` significa que o bind da conta de serviço
falhou — credencial errada, DC inacessível ou porta bloqueada. O log diz qual:

```
level=ERROR logger=openad ldap.probe status=failed server=dc01 port=389 error=LDAPSocketOpenError
```

---

## Configurar

Tudo vem de variável de ambiente. Nenhum valor sensível tem padrão no código,
e o `.env` não entra no Git.

| Variável | Obrigatória | O que é |
|---|---|---|
| `LDAP_SERVER` | sim | Hostname ou IP do Domain Controller |
| `LDAP_PORT` | — | `389` (padrão) ou `636` para LDAPS |
| `LDAP_DOMAIN` | sim | Domínio AD, ex. `empresa.local` |
| `LDAP_BASE_DN` | sim | Base das buscas, ex. `dc=empresa,dc=local` |
| `LDAP_USE_TLS` | — | `true` liga StartTLS na 389 |
| `CA_CERT_PATH` | condicional | Certificado da CA interna dentro do container |
| `LDAP_BIND_USER` | sim | UPN da conta de serviço |
| `LDAP_BIND_PASSWORD` | sim | Senha dela |
| `RATE_LIMIT_MAX` | — | Tentativas por IP na janela. Padrão `5` |
| `RATE_LIMIT_WINDOW` | — | Janela em segundos. Padrão `300` |
| `LOG_LEVEL` | — | `INFO` (padrão), `DEBUG`, `WARNING`, `ERROR` |

### A marca é sua

O portal é a cara de quem opera, não a de quem escreveu o código. Estas
variáveis repintam a tela sem editar HTML nem reconstruir a imagem — o
frontend lê `GET /api/branding` ao carregar e se aplica:

| Variável | Padrão |
|---|---|
| `BRAND_NAME` | `OpenAD` |
| `BRAND_LOGO_URL` | `/static/brand-mark.svg` |
| `BRAND_COLOR` | `#7C3AED` |
| `BRAND_COLOR_ACCENT` | `#A855F7` |
| `BRAND_FOOTER` | vazio, usa `BRAND_NAME` |
| `BRAND_UPN_EXAMPLE` | `usuario@empresa.local` |

Para usar um logo próprio, monte o arquivo em `/app/app/static/` e aponte
`BRAND_LOGO_URL` para ele. Vale também uma URL externa.

`BRAND_UPN_EXAMPLE` merece atenção: é o texto do campo de usuário. Deixá-lo no
padrão faz a pessoa adivinhar o formato que o seu domínio espera.

---

## Por dentro

```
app/
  main.py           rotas, ciclo de vida, log de auditoria
  ldap_service.py   a regra: resolve DN, autentica, troca a senha
  ldap_client.py    fábrica de conexão: plain, StartTLS, probe
  validators.py     UPN, tamanho de senha, anti-injeção LDAP
  rate_limiter.py   janela deslizante por IP, thread-safe
  config.py         todo o ambiente entra por aqui
  static/           a página, o logo e o favicon
```

A separação entre `ldap_client` e `ldap_service` é o que permite migrar de
LDAP puro para StartTLS mexendo só em variável de ambiente: o serviço não sabe
como a conexão foi construída.

### Escolhas de arquitetura

| Decisão | Por quê |
|---|---|
| **Sem banco de dados** | Não há sessão, cadastro nem histórico para guardar. O AD é o estado. |
| **Sem framework no frontend** | Uma página, três campos. HTML e JS puro entregam isso em 21 KB, sem build. |
| **Rate limit em memória** | Uma instância, um processo. Reiniciar zera os contadores — aceitável para brute force, que é medido em minutos. Várias réplicas exigiriam Redis. |
| **Docs do Swagger desligados** | `docs_url=None`. A API tem dois endpoints e um público que não os chama à mão. |
| **Um worker, 150 MB** | O trabalho é I/O de rede. Mais workers só multiplicariam conexões ociosas com o DC. |

---

## Segurança

**A senha nunca é gravada.** Não entra em log, não vai para disco, não fica em
sessão. Ela existe no processo pelo tempo do bind e do modify.

**A conta de serviço é a credencial mais sensível daqui.** Ela precisa de
leitura no diretório e de `Reset Password` delegado na OU dos usuários — e só.
Não dê Domain Admin. Delegue no escopo mínimo, guarde a senha em cofre e
rotacione:

```bash
# depois de trocar a senha dela no AD
docker compose up -d --force-recreate
curl -s http://localhost:8000/health
```

**Ligue o TLS.** Em LDAP puro, o bind do passo 4 trafega a senha da pessoa em
claro. Numa VLAN isolada até o DC isso é um risco contido; em qualquer rede
roteada, não é:

```env
LDAP_USE_TLS=true
CA_CERT_PATH=/certs/ca.crt   # se o DC usa CA interna
```

```yaml
# docker-compose.yml
volumes:
  - /opt/openad/certs:/certs:ro
```

Sem `CA_CERT_PATH`, o TLS sobe sem validar o par — cifra o tráfego, mas não
protege contra um intermediário. Serve para laboratório, não para produção.

**Não exponha a porta 8000 na internet.** Este é um portal interno. Ponha um
reverse proxy com TLS na frente e, se o domínio for fixo, restrinja o
`allow_origins` em `main.py`, hoje em `*`.

**O `LOG_LEVEL=DEBUG` conta demais.** Ele revela a estrutura do diretório nos
logs. Use para diagnosticar e desligue depois.

### O que os logs registram

Formato `chave=valor`, sem nada sensível:

```
level=INFO logger=openad change_password_attempt ip=198.51.100.24 upn=joao@empresa.local ts=2026-03-30T10:24:05+00:00
level=INFO logger=openad ldap.auth status=ok upn=joao@empresa.local
level=INFO logger=openad ldap.change_password status=success upn=joao@empresa.local
```

| Nos logs | O que aconteceu |
|---|---|
| `ldap.auth status=bind_failed` + `data 52e` | Senha atual incorreta |
| `ldap.auth status=bind_failed` + `data 775` | Conta bloqueada |
| `ldap.lookup status=not_found` | O UPN não existe no diretório |
| `status=failed ... constraint violation` | A nova senha bateu na GPO |
| `insufficientAccessRights` | Falta `Reset Password` delegado à conta de serviço |
| `rate_limit_exceeded` | Mesmo IP, mais de 5 tentativas em 5 minutos |
| `config_missing field=...` | Variável obrigatória ausente no `.env` |

---

## Limitações conhecidas

- **O rate limit não sobrevive ao restart** e não é compartilhado entre
  réplicas. Uma instância por trás de um proxy é o desenho suportado.
- **`X-Forwarded-For` é lido sem lista de proxies confiáveis.** Atrás de um
  reverse proxy que reescreve o cabeçalho, correto; exposto direto, o IP do
  rate limit pode ser forjado. É mais um motivo para não publicar a 8000.
- **Não há recuperação de senha esquecida.** Trocar exige saber a senha atual.
  Quem não sabe ainda precisa do service desk — o OpenAD resolve o volume, não
  o caso extremo.
- **Sem MFA.** A prova de identidade é a senha atual, e só.
- **A interface está em português**, com as mensagens de erro do AD
  traduzidas à mão.

---

## Licença

**© 2026 NerdResolve. Todos os direitos reservados.** Veja [LICENSE.md](LICENSE.md).

O repositório é público para avaliação técnica e demonstração de portfólio. O
código pode ser lido e estudado; não há licença de uso, cópia ou
redistribuição.

---

<div align="center">

<img src="docs/brand/nerdresolve-mark.png" alt="" width="42">

**OpenAD**, desenvolvido por [NerdResolve](https://nerdresolve.com)

Quer um portal assim na sua infraestrutura? **contact@nerdresolve.com**

</div>
