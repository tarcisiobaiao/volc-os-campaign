# Incidente crítico — `JWT_SECRET` é o segredo público de demonstração

**Aberto em:** 26/08/2026 · **Classificação:** crítico
**Estado:** **ABERTO — risco temporariamente aceito pelo dono em 26/08/2026**
**Descoberto por:** auditoria adversarial da fatia U0+H0 (lente de segurança)
**Verificado por:** comparação sanitizada no `.env` vivo de `/root/supabase/docker/`

> Nenhum segredo, token, JWT ou hash reversível aparece neste documento, nem
> apareceu em qualquer log desta verificação. O que foi impresso: booleanos, o
> claim `role` (público por construção) e o comprimento do segredo.

---

## 1. O que foi verificado

> ⚠️ **O escopo cresceu depois desta abertura.** A auditoria dos demais defaults
> mostrou que **13 de 17 segredos críticos** são o valor publicado — o `.env`
> inteiro é o arquivo de exemplo. Não é só o JWT. Ver
> [`INCIDENTE-JWT-RUNBOOK.md`](./INCIDENTE-JWT-RUNBOOK.md) §2.
>
> E a exposição é **menor** do que este documento estimou: só a 443 responde da
> internet. Mas isso não ajuda, porque `/pg/` (pg-meta, SQL arbitrário) passa
> por ela protegido por uma chave que está publicada — não é preciso forjar
> nada. Ver §3 do runbook.

| verificação | resultado |
|---|---|
| `JWT_SECRET` existe no `.env` vivo | sim (60 caracteres) |
| `JWT_SECRET` **é idêntico ao segredo público de demonstração** do Supabase self-hosted | **SIM** |
| `ANON_KEY` é assinada por esse segredo | sim · `role: anon` |
| `SERVICE_ROLE_KEY` é assinada por esse segredo | sim · `role: service_role` |
| `https://database.agenciavolc.com.br/rest/v1/` responde da internet pública | sim (401 sem credencial) |
| o host está no bundle publicado do frontend | sim |

**Veredito: `DEFAULT_INSEGURO`.**

O issuer `supabase-demo` sozinho **não** provaria nada — é só um claim. O que
prova é a igualdade do segredo, medida diretamente contra o `.env` vivo.

## 2. Por que isto é crítico

O `JWT_SECRET` é o que separa "um token que nós emitimos" de "um token que
qualquer pessoa fabricou". Ele é a chave HMAC que o GoTrue e o PostgREST usam
para validar **toda** credencial que chega.

Sendo ele um valor público, publicado na documentação do Supabase e presente em
milhares de repositórios:

- **qualquer pessoa pode forjar um JWT com `role: service_role`**, em segundos,
  sem exploit e sem acesso ao servidor;
- `service_role` tem `BYPASSRLS`: o RLS de nada adianta contra ele;
- o endereço da instância é público — está no bundle do frontend e responde da
  internet aberta.

**Alcance medido:** 65 tabelas em `public`, das quais apenas 27 têm RLS ligado —
e o RLS é irrelevante para `service_role`. Leitura e escrita irrestritas.

Isto **anula a Fase 1A inteira.** Fechar os proxies genéricos, tirar o
`X-API-Key` do bundle e pôr portão nas 66 rotas do FastAPI protegem a porta da
frente; esta é uma chave mestra publicada.

⚠️ **Não executei nenhum teste ativo.** Não forjei token, não fiz requisição
autenticada, não li dado por essa via. A conclusão vem da igualdade do segredo,
que é suficiente e não exige demonstração.

## 3. Efeito nesta rodada — **revogado em 26/08/2026**

⚠️ **A parada foi levantada pelo dono.** O parágrafo abaixo descreve o estado
entre a abertura do incidente e o aceite do risco, e fica como registro.

A preparação de migrations voltou a andar; a **aplicação em produção** continua
exigindo autorização própria, como sempre exigiu — e por motivo de processo, não
por causa do incidente.

> **A preparação de migrations está PARADA**, conforme a instrução recebida. A
v9_03 e a v9_04 estão escritas e validadas em cluster descartável, e **não**
avançam para pacote executável enquanto este incidente estiver aberto.

O motivo é operacional, não cerimonial: aplicar schema numa instância cuja
credencial administrativa é pública transforma cada migration numa mudança que
qualquer pessoa pode desfazer, refazer ou observar. E a rotação vai exigir
reiniciar serviços — encavalar as duas janelas multiplica o que pode dar errado
sem que se saiba qual das duas causou.

## 4. Plano coordenado de rotação — **não executado**

> Nada abaixo foi rodado. É um plano para o dono aprovar, agendar e executar com
> janela declarada.

### Antes de tocar em qualquer coisa

1. **Janela declarada.** A rotação **derruba toda sessão ativa** e invalida todas
   as chaves em uso. Não é operação de horário comercial.
2. **Backup do banco**, verificado — não só criado. `/root/backups/`.
3. **Cópia do `.env` vivo** com carimbo, fora do servidor. Já existe em
   `~/.ssh/volc-supabase-live.env` (chmod 600); confirmar que está atual.
4. **Inventário de consumidores.** Tudo que carrega uma das duas chaves precisa
   ser trocado no mesmo dia, ou quebra:

   | consumidor | onde | chave |
   |---|---|---|
   | frontend (Vercel) | `VITE_SUPABASE_ANON_KEY` no painel | anon |
   | backend FastAPI | `.env` / `.env.server` | service_role |
   | funções serverless `api/` | variáveis do projeto na Vercel | service_role |
   | Edge Functions | injetadas pelo Supabase — trocam sozinhas | service_role |
   | fluxos n8n | credencial do Supabase em cada fluxo | service_role |
   | scripts locais | `.env` de desenvolvimento | ambas |

   ⚠️ **O inventário do n8n é o mais arriscado**: são fluxos que ninguém vê
   quebrar até a próxima execução agendada. Levantar a lista ANTES.

### A rotação

5. **Gerar um `JWT_SECRET` novo** com entropia real (≥ 40 bytes aleatórios).
6. **Emitir `ANON_KEY` e `SERVICE_ROLE_KEY` novas** assinadas por ele, com os
   mesmos claims (`role`, `iss`, `iat`, `exp`) — o `exp` das atuais é
   `1799535600`; decidir se o novo mantém validade longa ou passa a ser curta.
7. **Escrever as três no `/root/supabase/docker/.env`.**
8. **Reiniciar a pilha**: `docker compose up -d` em `/root/supabase/docker/`.

   ⚠️ **A armadilha do Kong.** O `kong.yml` é gerado por um entrypoint
   `eval echo` que remove aspas não escapadas. Antes de reiniciar, conferir que
   `origins: - \"*\"` continua escapado no template — senão o YAML gerado sai
   com âncora inválida e o Kong **não sobe**, derrubando o site inteiro. Backups
   em `kong.yml.bak-*` na mesma pasta.

9. **Trocar as chaves em todos os consumidores** do inventário do passo 4.
10. **Republicar o frontend** — a `anon` velha está no bundle e continuaria sendo
    servida até um deploy novo.

### Depois

11. **Provar que a chave velha morreu**: uma requisição com a `anon` antiga tem
    de responder 401.
12. **Provar que a nova vive**: login, leitura do inventário, uma rota do
    backend.
13. **Varrer o histórico** por indício de uso indevido — `pg_stat_statements`,
    logs do Kong, contagens que não batam. ⚠️ A janela de logs do contêiner
    rotaciona; o que passou pode não estar mais lá.
14. **Fechar o incidente** com data, quem executou e o que foi verificado.

### Controle compensatório, se a rotação não puder ser hoje

⚠️ **CORREÇÃO.** A primeira versão deste parágrafo oferecia "restringir por
origem no Kong". **Está errado, e foi retirado.**

CORS e restrição por `Origin` são instruções que o **navegador** obedece. `curl`,
um script, ou qualquer cliente que não seja navegador simplesmente não as
aplica — e quem tem a chave publicada não vai usar navegador. Não é controle de
segurança: é compatibilidade entre páginas.

Controles reais, e nenhum foi aplicado:

- **allowlist de IP no firewall de nuvem** — fecha 443 a tudo que não seja
  Vercel, n8n e escritório;
- **autenticação no proxy** (Cloudflare Access na frente do Caddy);
- **manutenção controlada**, com 443 fechado.

Os três reduzem o alcance sem resolver a causa, e **têm relógio** (ADR-15):
aceite nominal, prazo, controle e data de reavaliação. Detalhe em
[`INCIDENTE-JWT-RUNBOOK.md`](./INCIDENTE-JWT-RUNBOOK.md) §9.

## 5. O que NÃO fazer

- **Não rotacionar sem o inventário de consumidores.** A metade que ninguém
  lembrou quebra em silêncio, e o modo de descobrir é um fluxo que deixou de
  rodar.
- **Não reiniciar o Kong sem conferir o `kong.yml`.**
- **Não tratar como resolvido por ter trocado só a `service_role`.** As três
  andam juntas: as chaves são derivadas do segredo.
- **Não aplicar v9_03 / v9_04 antes.** Ver §3.

## 6. Registro de risco (ADR-15) — **preenchido**

| campo | conteúdo |
|---|---|
| **aceite** | **Tarcisio Bely**, 26/08/2026 |
| **estado** | **aberto — risco temporariamente aceito** |
| **justificativa** | priorização do desenvolvimento interno; o VOLC O.S. permanece interno, restrito e em desenvolvimento |
| **prazo** | **até o gate de pré-lançamento** |
| **controle compensatório** | nenhum ativo — o aceite é do risco cru |
| **reavaliação** | imediata, a qualquer um dos gatilhos abaixo |

### O que o dono declarou saber ao aceitar

- 13 segredos críticos permanecem com valores públicos de demonstração;
- o endpoint responde pela internet;
- existe risco de acesso privilegiado;
- **ausência de evidência não comprova ausência de exploração** — e a janela de
  log do gateway cobre 31 dias de uma instância de 6 meses.

### Gatilhos que obrigam reavaliação imediata

Qualquer um destes **reabre o incidente como bloqueador**, sem discussão nova:

1. abertura para terceiros;
2. entrada de novos usuários externos;
3. ampliação material de dados sensíveis;
4. **evidência de exploração**;
5. mudança da exposição da infraestrutura;
6. início do checklist de lançamento.

### O que o aceite NÃO faz

Ele **não** resolve, **não** mitiga e **não** fecha. A rotação completa é **gate
obrigatório** antes de disponibilizar o sistema a terceiros ou considerar o
produto pronto para operação externa.

Continuam preservados e válidos: as evidências
(`/root/incidente-jwt-20260826`, 51 MB, dir 700 / arquivos 600), o
[runbook](./INCIDENTE-JWT-RUNBOOK.md), o inventário de consumidores, a auditoria
sanitizada, e a proibição de imprimir ou versionar segredo.

O que o aceite libera é uma coisa só: **o desenvolvimento local e a conclusão do
Hub deixam de ficar bloqueados por ele.**
