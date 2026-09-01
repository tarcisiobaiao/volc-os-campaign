# Pacote único de autorização externa

> Nada aqui foi executado. Esta missão fechou o que é local e parou na fronteira
> que exige decisão de quem responde pela produção. Cada item traz o que já está
> pronto, o que falta, o risco e como reverter.

**Base:** `b6e226ab` · **Branch:** `sprint/creative-factory-production-spine-v1`

## Confirmação de envelope

| Ato externo | Ocorrências nesta missão |
|---|---|
| Migration aplicada no Supabase oficial | **0** |
| Escrita no Supabase oficial | **0** |
| Leitura do Supabase oficial | **0** |
| Google Ads / Meta / YouTube / TikTok / Postiz | **0** |
| n8n real | **0** |
| Deploy · push · merge · alteração de `main` | **0** |
| Geração paga (API de provider) | **0** |
| Escrita nos parques externos | **0** — somente leitura e `shasum` |

O único Postgres tocado foi um cluster que `initdb` cria e `pg_ctl stop` destrói
dentro de `mktemp -d`, dentro da própria sessão de teste.

---

## 1. Aplicar a v11_03 no Supabase oficial · P17-T03

**Pronto.** `supabase/migrations/v11_03_execucao_criativa.sql` e o rollback
correspondente passam o ciclo `aplicar → operar → reverter → reaplicar` com
**129 provas, 0 falhas**, em cluster descartável
(`scripts/provar-ciclo-v11_03.sh`, reexecutado nesta missão).

**Novo nesta missão:** o adapter Python `DepositoPostgres` agora exercita essas
tabelas pelo mesmo contrato do SQLite — **35 provas** contra o schema real. A
migration deixou de ser SQL que ninguém chama.

**Falta:** a decisão. Ela é a **D6** de `docs/closure/fable-global-v1/OPEN-DECISIONS.md`
e nada indica que foi tomada.

**Risco:** cinco tabelas e sete gatilhos novos em `public`. Nenhum objeto
existente é alterado. Verificação prévia obrigatória: `criativo_render_%` deve
devolver zero linhas antes de aplicar.

**Rollback:** `v11_03_rollback.sql`, exercitado no mesmo ciclo — não é um arquivo
que nunca rodou.

**Pendência que o roadmap não cita:** os 13 índices de chave estrangeira das
v11_01/v11_02 continuam pendentes (`supabase/migrations/README.md:1097`).

## 2. Backup conferido antes de qualquer aplicação

O servidor mantém `/root/backups/`. **Conferir o backup é conferir a restauração**:
um arquivo com data recente não é prova de que ele volta. Autorização pedida:
restaurar o dump mais recente num cluster descartável e contar as tabelas.

## 3. Criar e configurar o bucket `criativos`

**Estado factual:** o bucket **não existe**. `select * from storage.buckets`
devolveu zero linhas em 27/08/2026. E o nome `criativos` é hoje um **default de
parâmetro**, não configuração validada (`armazenamento.py:248`) — nenhum chamador
passa outro valor porque nenhum chamador existe.

**Pronto:** `ArmazenamentoSupabase` está escrito e desarmado. Esta missão
acrescentou a máquina de verificação de bytes e o preflight que **falha fechado**
quando o bucket não existe, em vez de cair para local em silêncio.

**Falta:** criar o bucket **privado**, com política de acesso, e ligar o adapter.

**Risco:** bucket público por conveniência é a forma mais comum de vazar peça de
cliente. O produto já usa URL assinada de TTL curto e escopo de uma chave —
nenhum caminho depende de bucket aberto.

## 4. Um executor remoto para o worker

**Pronto:** `python -m app.criativo.bancada.worker` é um processo real, provado
com `subprocess` — reivindica, renova lease, produz, assina recibo, sobrevive a
SIGTERM e devolve o trabalho quando morre de SIGKILL.

**Falta:** onde ele roda. `DespachoDeFila` já é durável em qualquer ambiente e é
o único aceitável em serverless; o que não existe é a máquina que hospeda o
worker. `docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md` deixa essa decisão
(Decisão 5) explicitamente para o dono do produto.

⚠️ **Não rode render pesado na mesma máquina do Supabase operacional**
(`178.156.196.149`, 4 GB). Render de vídeo com ffmpeg e Chromium concorre por
memória com o Postgres que serve o produto inteiro.

## 5. Credenciais por referência ao Cofre

O caminho criativo exige, **por nome**: `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `CRIATIVO_URL_SECRET`, `GEMINI_API_KEY`
(com `GOOGLE_API_KEY` como fallback declarado), `OPENAI_API_KEY`, `PEXELS_API_KEY`,
`KIE_API_KEY`.

**Regra inegociável, e ela vem de dois achados medidos no parque:**
credencial entra por referência nominal ao Cofre, nunca por varredura de disco.

- `veo_hook.py:8-13` carrega o `.env` de um projeto de **cliente**
  (`.../aprova-plataforma-alvo-hybrid/materials/.env`), e esse arquivo existe
  nesta máquina.
- `wan_hook.py:22-31` colhe chave do Replicate varrendo templates de terceiros
  por regex `r8_[A-Za-z0-9]{30,}`. Verificado por contagem, sem ler valor: um
  arquivo casa aqui — o script acharia uma chave.

Nenhum dos dois padrões pode entrar num adapter do VOLC O.S. A interface com o
Cofre é da lane `sprint/asset-vault-onepassword-production-v1`; esta missão não
a invade e mantém o adapter desarmado.

## 6. Geração paga, se necessária

Não é necessária para nada que esta missão prova. Os motores locais (`png-local`,
`tipografico-local`) produzem sem rede e sem custo. Custo continua registrado
como **`None` = não apurado**, e há teste provando que isso não é zero.

Se um motor pago for ligado, o recibo já tem os campos (`custo_estimado_usd`,
`custo_real_usd`) — mas **nenhum produtor os escreve hoje**. Ligar provider pago
sem ligar a apuração faria todo trabalho nascer com custo nulo permanente.

## 7. Persistência real, peça canário e validação no destino

Nesta ordem, e só depois de 1–4:

1. um job real atravessa o worker remoto e grava em `criativo_render_*`;
2. o artefato sobe ao bucket e é **relido** — `VERIFIED_OK` só depois da releitura;
3. uma peça canário por destino, com aprovação humana registrada;
4. validação no destino (upload como rascunho, sem ativar).

## 8. Publicação — sempre separada

Publicar é ato distinto de tudo acima e exige autorização própria. Nenhuma rota
desta missão publica, e o `DespachoDeFila` não tem caminho para plataforma.

---

## Decisão de licença do Remotion — pré-requisito de faturar vídeo

Registrada à parte porque **não é técnica**. O ADR afirma que a Free License
cobre organização de até 3 pessoas e que acima disso exige Company License paga,
com **preços NÃO CONFIRMADOS**. Enquanto isso não for verificado em fonte oficial
vigente e decidido, vídeo produzido por Remotion é `blocked_by_external_authorization`
para faturamento — não `unknown`, e muito menos gratuito.
