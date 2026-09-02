# Pacote único de autorização externa

> Nada aqui foi executado. Esta missão fechou o que é local e parou na fronteira
> que exige decisão de quem responde pela produção. Cada item traz o que já está
> pronto, o que falta, o risco e como reverter.

**Base:** `c8ca8628` · **HEAD:** `e273103` · **Branch:** `sprint/creative-factory-production-last-mile-v1`

## Confirmação de envelope

| Ato externo | Ocorrências nesta missão |
|---|---|
| Migration aplicada no Supabase oficial | **0** |
| Escrita no Supabase oficial | **0** |
| Leitura do Supabase oficial | **0** |
| Bucket criado ou configurado | **0** |
| Provider pago chamado (Gemini, OpenAI, Replicate, Pexels, KIE) | **0** |
| Prompt ou asset enviado a API externa | **0** |
| Google Ads · Meta · YouTube · TikTok · Postiz · n8n | **0** |
| Publicação em qualquer plataforma | **0** |
| Aprovação de peça em nome do usuário | **0** |
| Deploy · push · merge · alteração de `main` | **0** |
| Escrita nos parques externos (`/Users/mac/volc-factory`) | **0** — somente leitura |

Os únicos Postgres tocados foram clusters que `initdb` cria e `pg_ctl stop`
destrói dentro de `mktemp -d`, dentro da própria sessão de teste.

Duas operações de rede aconteceram, e são de **instalação de dependência local**,
não de produto: `npm install` do runtime Remotion (registro público do npm) e o
download do Chrome Headless Shell que o Remotion faz na primeira execução. As
duas escrevem apenas dentro de `deploy/creative-worker/remotion-runtime/node_modules`,
que é ignorado pelo git. O **render** em si não abre conexão — é essa a prova do
item 4 abaixo.

---

## 1. Aplicar a v11_03 no Supabase oficial · P17-T03

**Pronto.** O ciclo `aplicar → operar → reverter → reaplicar` passa com
**178 provas, 0 falhas** em cluster descartável (`scripts/provar-ciclo-v11_03.sh`),
contra 129 no início desta missão. As 49 provas novas cobrem quatro defeitos e
dois achados adversariais que estavam abertos, todos com contraprova vermelha
registrada em `braco-a/PACOTE-v11_03.md`.

**Novo nesta missão, e é o que muda o risco da aplicação:**

- a verificação do rollback deixou de ser **cega** para duas das nove funções;
- a verificação embutida da migration deixou de aceitar 6 gatilhos onde cria 7;
- o rollback deixou de abortar por uma contagem de tabelas que uma v11_04
  legítima mudaria, e passou a conferir **por nome**, com escape auditável;
- `tolerancia_lufs` ganhou coluna — o contrato Python tinha um campo sem par;
- `storage_sha256_remoto` entrou: o veredito booleano guardava "bateu?" e perdia
  "o que voltou?", que é a única pergunta útil no dia de um mismatch.

**Preflight que não existia:** `scripts/preflight-v11_03.sh` confere, **sem
aplicar nada**, contra um DSN passado por argumento: as 5 tabelas
`criativo_render_%` devem estar ausentes ou vazias; as 21 tabelas da v11_01/02
devem existir **como tabelas**; `service_role` deve ter `BYPASSRLS`; nenhuma das
9 funções pode existir com outra assinatura. Ele é **fail-closed**: o que ele não
conseguiu conferir sai como `NAO CONFERIDO`, nunca como sucesso — e há 30 provas
de que ele acusa quando há o que acusar.

**Identidade dos arquivos** (confira antes de aplicar; se um `sha256` divergir, pare):

| Arquivo | sha256 |
|---|---|
| `supabase/migrations/v11_03_execucao_criativa.sql` | `3aa77687f27d77c598fd88c827079f7f8f538d3e9b364fb0734306406d80db80` |
| `supabase/migrations/v11_03_rollback.sql` | `861ead45e024ccb8aa1fbd5bdec420b5fbaf9563bbfbee289a583c20399da07b` |
| `scripts/preflight-v11_03.sh` | `8d6d4d1f7c3b146f03df44a17e71e2f5b9fbd7f5b9489edd15d3c834ba767539` |
| `scripts/provar-ciclo-v11_03.sh` | `9b09a94fd9f59470e9d183317b5caf30206a03e2e5cb6a034af4c54a0d2377dc` |
| `scripts/provas-v11_03.sql` | `5cae318a0ad6212734a03141dbcc9708e10ea6a3cce762ead83fbf0e26215a57` |
| `scripts/provas-papeis-v11_03.sql` | `4ebaa7066a4400b61ad38b53ad717c6e1916693ac1859f2db3be569941a15f02` |

**Falta:** a decisão. Ela é a **D6** de `docs/closure/fable-global-v1/OPEN-DECISIONS.md`
e nada indica que foi tomada.

**Risco:** cinco tabelas e sete gatilhos novos em `public`. Nenhum objeto
existente é alterado.

**Rollback:** `v11_03_rollback.sql`, exercitado no mesmo ciclo — não é arquivo que
nunca rodou. Ele agora aceita `-v v11_03_base_encolhida=confirmo` como escape
explícito quando a base encolheu de propósito; **o default continua abortando**.

**Roteiro executável completo:** `braco-a/PACOTE-v11_03.md`.

## 2. Backup conferido antes de qualquer aplicação

O servidor mantém `/root/backups/`. **Conferir o backup é conferir a restauração**:
um arquivo com data recente não é prova de que ele volta. O passo 2 do PACOTE
descreve restaurar o dump mais recente num cluster descartável e contar as
tabelas — e o PACOTE declara, com todas as letras, que esse passo é **roteiro, não
evidência**: nenhum dump foi tirado nem restaurado nesta missão.

Autorização pedida: executar essa restauração de conferência.

## 3. Criar e configurar o bucket `criativos`

**Estado factual:** o bucket **não existe**. Nesta missão nada foi consultado no
Supabase oficial, então o que se sabe é o que a missão anterior mediu em
27/08/2026: `select * from storage.buckets` devolveu zero linhas.

**Pronto:** `ArmazenamentoSupabase` está escrito e **desarmado**, atrás da mesma
porta `ArmazenamentoConferivel` que o adaptador local cumpre. A máquina de
verificação — upload, releitura, comparação de bytes **e** sha256 — agora tem
consumidor de produção: o operário publica e relê, e `VERIFIED_OK` só existe
depois da releitura. Isso foi provado com **duas peças reais** (item 7).

**Falta:** criar o bucket **privado**, com política de acesso, e trocar
`armazenamento_padrao()` para o adaptador remoto **por configuração**. Hoje a
troca exige editar `armazenamento.py:689` — o ADR exige config, não edição de
código, e essa lacuna continua aberta.

**Risco:** bucket público por conveniência é a forma mais comum de vazar peça de
cliente. O produto já usa URL assinada de TTL curto e escopo de uma chave.

⚠️ **Antes de ligar o adaptador remoto**, note que a chave canônica mudou nesta
missão: ela emitia `<slot>_<hash>` com **um** underscore e o gatilho
`criativo_storage_chave_valida` exige **dois**. No dia da aplicação da v11_03,
toda escrita de artefato com chave seria recusada — e o sintoma apareceria longe
da causa. Está corrigido e provado, mas qualquer objeto gravado com a chave
antiga estará em outro endereço.

## 4. Um executor remoto para o worker

**Pronto:** `python -m app.criativo.bancada.worker` é processo real, provado por
`subprocess` — e agora produz **vídeo** além de imagem, pela mesma porta. O
recibo é assinado por `worker-<pid>`, e há prova de que esse pid **não é** o do
processo de teste.

**Novo:** o worker herda a loja da bancada. Antes ele construía um operário sem
armazenamento — justamente o processo que produz seria o único sem publicar, e
uma peça feita em outra máquina apareceria para a web como perdida.

**Falta:** onde ele roda. `docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md`
deixa essa decisão (Decisão 5) explicitamente para o dono do produto. Não há
Dockerfile, unit systemd nem entrada de Procfile que suba o worker.

⚠️ **Equivalência de pixel macOS ↔ Linux é NÃO PROVADA.** O Chrome Headless Shell
baixado é `mac-arm64` e o compositor instalado é `@remotion/compositor-darwin-arm64`.
O determinismo provado nesta missão é **na mesma máquina**. Gerar um "hash
aprovado" aqui e compará-lo com um render de Linux colapsaria local ≠ produção.

⚠️ **Não rode render pesado na mesma máquina do Supabase operacional**
(`178.156.196.149`, 4 GB): ffmpeg e Chromium concorrem por memória com o Postgres
que serve o produto inteiro.

## 5. Credenciais por referência ao Cofre

O caminho criativo exige, **por nome**: `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `CRIATIVO_URL_SECRET`, `GEMINI_API_KEY`
(com `GOOGLE_API_KEY` como fallback declarado), `OPENAI_API_KEY`, `PEXELS_API_KEY`,
`KIE_API_KEY`.

**Regra inegociável:** credencial entra por referência nominal ao Cofre, nunca por
varredura de disco. Os dois padrões flagrados no parque externo pela missão
anterior — um hook que carrega o `.env` de um projeto de **cliente**, outro que
colhe chave varrendo templates de terceiros por regex — continuam inadmissíveis.

Esta missão respeitou isso numa decisão concreta: a revisão factual do **Gemini
não aconteceu** porque o CLI não tem método de auth nesta máquina, e buscar a
chave dentro de arquivos `.env` de projeto seria exatamente o padrão flagrado.

## 6. Geração paga, se necessária

**Não é necessária para nada que esta missão prova.** Os motores locais
(`png-local`, `tipografico-local`, `remotion-local`) produzem sem rede e sem custo.

O custo agora tem **produtor e razão nomeada**: um motor local declara
`sem_custo_de_provider`, e um motor sem porta de custo declara `nao_apurado` —
que não é a mesma coisa e não é zero. Há prova de que `None` não vira `0`.

⚠️ Se um motor pago for ligado, **ligue a apuração junto**. O recibo tem os
campos e agora tem a porta (`motor.custo(encomenda)`); ligar o provider sem ligar
a apuração faria todo trabalho nascer com `sem_custo_de_provider` permanente, que
seria uma afirmação falsa em vez de uma ausência honesta.

## 7. Persistência real, peça canário e validação no destino

**Duas peças canário já existem**, produzidas pela espinha inteira em diretório
descartável, com armazenamento **local** e releitura conferida
(`contraprovas/PECA-CANARIO.json`):

| Peça | Formato | Bytes | sha256 | Storage |
|---|---|---|---|---|
| imagem | `image/png` 1200×628 | 27 568 | `31dbc13fa0f54399e45999c80dc861b164afabb8ec679ec91fe7cda32b34be54` | `VERIFIED_OK` |
| vídeo | `video/mp4` 1080×1920 | 448 196 | `3e5ae27082f61c8456172c1a7726229b72db8469a2f632cb8aaa3fd97d5e7164` | `VERIFIED_OK` |

Nas duas, `sha256_relido == sha256_do_artefato` e a aprovação nasceu
`aguardando`. **Nenhuma foi aprovada** — aprovar em nome do dono é ato externo.

Ordem pedida, e só depois de 1–4:

1. um job real atravessa o worker **remoto** e grava em `criativo_render_*`;
2. o artefato sobe ao **bucket** e é relido — `VERIFIED_OK` só depois da releitura;
3. **uma pessoa** aprova a peça canário, com finalidade escrita;
4. validação no destino (upload como rascunho, sem ativar).

## 8. Publicação — sempre separada

Publicar é ato distinto de tudo acima e exige autorização própria. Nenhuma rota
desta missão publica; `PacoteDeDestino.publicacao_automatica` é `ClassVar` fixo em
`False` e há sentinela que o afirma, além de uma varredura que recusa qualquer URL
de plataforma dentro do recibo.

---

## Decisão de licença do Remotion — inalterada e ainda pendente

Esta missão **acrescentou** um runtime Remotion ao repositório
(`deploy/creative-worker/remotion-runtime`, 4.0.479 em lockstep pelo lockfile), o
que torna a decisão **mais urgente**, não menos.

O ADR afirma que a Free License cobre organização de até 3 pessoas e que acima
disso exige Company License paga, com **preços NÃO CONFIRMADOS**. Enquanto isso
não for verificado em fonte oficial vigente e decidido, vídeo produzido por
Remotion permanece `blocked_by_external_authorization` para faturamento — não
`unknown`, e muito menos gratuito.

Três perguntas que só o dono responde: quantas pessoas a VOLC tem para efeito da
licença (contratados do mesmo projeto somam); se o `<Player>` vai ao app; e qual
opção cobre a pipeline.

## O que continua ausente, e está declarado

- **Superfície de pacote por destino no frontend e endpoint HTTP.** A máquina de
  pacote existe, é provada por teste com peça real, chave de storage e hash
  relido — e não tem rota nem tela. O ciclo pela UI termina em "peça aprovada".
- **Aprovação humana real** não foi executada, por decisão.
- **Reconciliação de storage** não existe: nada reconfere um
  `UPLOADED_UNVERIFIED` que ficou assim por falha de rede.
- **Persistência do veredito de storage** em `criativo_master` — as colunas não
  existem nessa tabela, e é ela que o Executor do Estúdio usa.
- **`criativo_job` (Estúdio) continua sendo uma segunda fila sem consumidor.**
  O modo `fila` recusa servi-la, com o motivo escrito. A ponte
  `criativo_job → criativo_render_job` não existe.
