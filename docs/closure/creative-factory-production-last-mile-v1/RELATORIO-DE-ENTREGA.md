# Creative Factory Production Last Mile V1 — relatório de entrega

**Status:** `ESPINHA_PRODUTIVA_VERTICAL_FECHADA_ATIVACAO_EXTERNA_PENDENTE`

Uma peça de imagem e uma peça de vídeo atravessaram a espinha inteira — job,
claim, worker fora do processo web, motor real, bytes reais, medição técnica,
armazenamento, releitura, conferência de hash, validação por destino, recibo
completo e pacote de entrega. O que falta para chamar de produção depende de
autorização externa e está no pacote único em `AUTORIZACAO-EXTERNA.md`.

## 1. Procedência

| | |
|---|---|
| Base SHA | `c8ca8628e83742dd7da5242f0a015f76292aafe7` (`origin/volc-os-v2`) — **igual ao esperado pelo prompt, sem divergência** |
| Branch | `sprint/creative-factory-production-last-mile-v1` |
| Worktree | `/private/tmp/volc-creative-factory-production-last-mile-v1` |
| Commits | `00cd4ea` (espinha produtiva) · `e273103` (v11_03 e storage) · `fb0e227` (rodada corretiva) |
| Árvore | limpa na criação e na entrega |

**48 arquivos.**

## 2. Gates

| Gate | Baseline (medido no SHA base) | Final |
|---|---|---|
| `pytest backend/tests volc_ads -q` | 3358 passed · 53 skipped | **3396 passed · 53 skipped** |
| `vitest run` (completo) | 1256 passed · 5 skipped | **1262 passed · 5 skipped** |
| `tsc --noEmit -p tsconfig.app.json` | 76 erros herdados | **76** |
| `scripts/provar-ciclo-v11_03.sh` | 129 passaram · 0 falharam | **178 · 0** |
| `scripts/v11_03-provar-preflight.sh` | não existia | **30 · 0** |
| `scripts/v11_03-provar-plano.sh` | não existia | **12 · 0** |
| `scripts/provar-render-hermetico.sh` | não existia | **17 · 0** |
| `backend/tests/test_criativo_golden_video.py` | não existia | **22 · 0** |
| `backend/tests/test_criativo_runtime_remotion.py` | não existia | **13 · 0** — e **não pula**: sem `node`, 9 continuam correndo |
| `git diff --check` | — | limpo |
| `scripts/verificar_segredos.py` | — | nenhum padrão forte |

O Vitest exige `VITE_SUPABASE_URL` e `VITE_SUPABASE_ANON_KEY` presentes; foram
usados **placeholders não-credenciais**, pelo motivo já medido: `src/lib/supabase.ts:7`
lança na ausência da variável, e um baseline ingênuo colapsa **ausência de
variável** em **falha de teste**.

## 3. O vídeo, e por que um runtime próprio

Não havia motor de vídeo. Os dois motores registrados recusavam
`midia != "imagem"`, e o único caminho de vídeo era **leitura** de builds de uma
fábrica externa (`video_observado.py`, procedência `observado`).

O parque externo tem 15 composições cujo `Root.tsx` as importa **todas** no topo,
cada uma chamando `loadFont()` do `@remotion/google-fonts` no seu próprio módulo
— 34 chamadas em 11 famílias, nenhuma delas licenciada e versionada aqui. Tornar
aquilo hermético custaria obter as 11 fontes e tocar 15 arquivos de um repositório
de **outra frente**, e o ADR já tinha registrado esse custo.

O pedido desta fatia era "fontes locais, licenciadas e **mínimas**". Uma composição
própria, com a Inter que já está versionada sob OFL 1.1, custa **uma** família e
**um** arquivo. É a mesma decisão que `MotorPngLocal` tomou ao não depender de
Pillow: o motor que sempre sobe vale mais que o motor que às vezes sobe.

`deploy/creative-worker/remotion-runtime` é projeto npm próprio, com lockfile
próprio: **16 pacotes `@remotion/*` em 4.0.479 exatos**, e o motor lê as versões
do lockfile — não do `package.json`, que diria `^4.0.0`. Lockstep é afirmação
sobre o que rodou, e só o lockfile sabe.

## 4. Hermetismo: impossibilidade, não observação

O ADR mediu que `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` são **inertes** contra o
Remotion — o renderer lança o Chromium com `--no-proxy-server`,
`--proxy-server='direct://'` e `--proxy-bypass-list=*` embutidos. E usou
amostragem de `lsof` porque não tinha instrumento melhor; a leitura honesta
daquele resultado era "não observei rede", não "não houve rede". Amostragem prova
presença e nunca ausência: entre duas amostras cabe uma conexão inteira.

O render agora roda em `sandbox-exec` com `(deny network-outbound)` e uma exceção
só para loopback. O kernel recusa `connect()` para qualquer destino externo — o
processo recebe `EPERM`. Loopback fica liberado porque o bundler sobe um servidor
estático em `127.0.0.1` e o Chromium precisa alcançá-lo; bloqueá-lo não provaria
hermetismo, só impediria o render.

**O DEGRAU 4 calibra o próprio instrumento:** um processo de controle tenta uma
conexão externa dentro do mesmo sandbox, e a prova exige que ela seja recusada —
e exige também que a mesma tentativa **conecte** fora dele. Sem essa calibração,
um sandbox que silenciosamente não se aplicasse produziria um verde vazio.

⚠️ **Corrigido na integração de 02/09/2026: este parágrafo descrevia o desenho
ANTERIOR.** Ele dizia que sem `sandbox-exec` o gate sai `SKIPPED`. A própria
revisão adversarial relatada na seção 11 (Bloqueante 1) derrubou esse desenho e
o código mudou; este texto não acompanhou. `render_sem_rede` **nunca emite
`SKIPPED`**: sai `PASS` (bloqueante, respondido pelo kernel), `WARN`
(não-bloqueante, e só com `CRIATIVO_PERMITIR_RENDER_COM_REDE`, com o nome da
variável no recibo) ou `FAIL` (bloqueante, e é o padrão onde não há sandbox).
Onde não há `sandbox-exec`, o trabalho **não chega a `rendered`** sem dispensa
explícita.

## 5. Determinismo: um defeito medido, e o que ele custou

A primeira medição foi vermelha: **duas execuções do mesmo pedido produziam
quadros diferentes — 17 dos 90.**

A investigação separou renderizador de codificador (stills isolados) e chegou ao
número: no quadro 80, **8 pixels em 2 073 600** — 0,0004% —, todos no bbox
`(775, 1918)–(796, 1920)`, isto é, nas duas últimas linhas do quadro. Delta máximo
de 8/255 no canal vermelho. A causa é uma partícula centrada perto de `y=1`, com
metade fora do quadro: o Chromium rasteriza esse recorte sub-pixel de dois jeitos.

Não é ruído aceitável. A `assinatura_determinista` existe para responder "o motor
repetiu?", e uma resposta que muda sozinha não responde nada.

Fechado por posicionamento em **pixel inteiro** e faixa de 8% a 92% que não
encosta na borda — as duas coisas, porque só arredondar deixaria a partícula que
nasce no limite ainda recortada. Depois: **seis renders seguidos, um único
sha256 do container inteiro**, não só dos quadros decodificados.

## 6. O recibo: os onze campos ausentes

O relatório anterior listou onze campos ausentes. Todos entraram, e **nenhum tem
default** — o construtor único mora no operário, e um default deixaria um campo
do contrato nascer vazio sem ninguém decidir nada.

| Campo ausente | Onde entrou |
|---|---|
| modo | `Procedencia.modo_slug` |
| provider externo | `Procedencia.provider` (`Declarado`) |
| modelo | `Procedencia.modelo` (`Declarado`) |
| dimensão nativa antes do resize | `Artefato.enquadramento.largura_nativa/altura_nativa` |
| resize / crop / enquadramento | `Enquadramento.operacao` |
| brand pack | `Procedencia.brand_pack` |
| hashes de input | `Recibo.hashes_de_entrada` — e entram na assinatura |
| prompt sanitizado | `Recibo.insumo` (`InsumoSanitizado`) |
| tentativas | `Recibo.tentativa` |
| aprovação humana | `Recibo.aprovacao` |
| destino · storage · medida de áudio | `Recibo.destinos`, `Recibo.storage`, `Recibo.audio` |

**Ausência ganhou nome.** `Ausencia` e `Declarado` substituem o `None` mudo: um
custo `nao_apurado` vira número no dia em que alguém ligar a apuração; um
`sem_custo_de_provider` já está respondido e não vira. Colapsar os dois faz o
produto perguntar para sempre uma pergunta que já tem resposta. `Declarado`
**recusa** valor e ausência juntos, e recusa nenhum dos dois — sem essa recusa o
tipo seria uma sugestão.

**`MedidaDeAudio` deixou de ser estrutura morta.** Nenhum motor implementava
`medir_audio`, e a v11_03 reservou três colunas numéricas que nasceriam
permanentemente nulas — o antipadrão que o próprio `PLANO-v11_03.md` diz querer
evitar. Agora LUFS integrado e true peak são medidos por `ebur128` **do
artefato**, em número, e o gancho recebe o diretório do trabalho porque medir
áudio é medir o **arquivo**; medir o pedido não mede nada.

**O insumo sanitizado não é o hash.** O relatório anterior registrou a confusão:
"não confunda 'prompt não exposto publicamente' com 'prompt sanitizado e
auditável'". Um hash identifica e não pode ser lido; um texto sanitizado pode ser
lido por um auditor e não carrega e-mail, telefone, documento nem valor. As duas
coisas respondem perguntas diferentes, e as duas estão no recibo interno. A API
pública devolve estado e impressão digital — **sem o campo `texto`**.

**A assinatura determinista mudou, e isso é o sistema funcionando.** Ela
respondia "o motor repetiu?" olhando só para pedido e versões declaradas. Uma
fonte trocada no disco muda o pixel sem mudar nenhuma das duas — o próprio ADR
registrava o caso: vendorizar uma família sem eixo itálico faria o Chrome inclinar
o romano, e "a assinatura determinista não acusaria". Os hashes de entrada fecham
isso, e há prova em par que o demonstra.

## 7. Defeitos fechados, cada um com contraprova

**Latentes que quebrariam na aplicação**

1. **A chave canônica emitia UM underscore e o gatilho exige DOIS.**
   `criativo_storage_chave_valida` monta `criativos/<tenant>/<job>/<slot>__<sufixo>`
   — e o comentário do próprio SQL explica: com um só, o prefixo `.../1x1` casa
   também com `.../1x1-malicioso.png`, e a chave de um slot passaria a apontar
   para o objeto de outro. No dia da aplicação da v11_03, **toda** escrita de
   artefato com chave seria recusada, e o sintoma apareceria longe da causa.
2. **`storage_hash_conferido` era `boolean` no SQL e `str` no Python.** Nada
   escrevia nenhuma das duas, então nada quebrava — e latente é o que vira defeito
   no dia em que alguém liga os dois lados. Resolvido de forma **aditiva**:
   `storage_sha256_remoto` entrou, com três CHECKs que impedem os dois campos de
   contarem histórias opostas sobre a mesma leitura.

**Altos**

3. **`video/mp4` fora de `_MIMES_MENSURAVEIS`.** Um mp4 caía no ramo `SKIPPED`
   não-bloqueante — "não sei medir a dimensão deste formato" — e chegava a
   `rendered` sem que ninguém abrisse o arquivo. Era o mesmo defeito que a
   contraprova de dimensão fechou para imagem, sobrevivendo na mídia que ninguém
   produzia ainda.
4. **O operário não publicava em lugar nenhum.** Gravava no disco do processo e
   pronto; um worker em outra máquina produziria peças que a web classifica como
   perdidas.
5. **`montar_operario` do worker construía um `Operario` sem loja** — justamente
   o processo que produz seria o único da casa sem armazenamento.
6. **Render não determinista** (seção 5).
7. **A travessia golden de imagem iterava `ENVELOPES` sem filtrar mídia.** Com o
   envelope de vídeo no catálogo, um PNG passou a "cumprir" o envelope de vídeo e
   o mesmo conteúdo era catalogado sob dois papéis. O defeito era da iteração e já
   existia; o envelope novo só o tornou visível.

**Médios e baixos**

8. **`aprovavel` chegava `true` literal nos dois chamadores** do formulário de
   decisão. A guarda existia, tinha mensagem pronta, tinha ramo testado — e nunca
   podia disparar. Uma guarda que o chamador desliga é documentação.
9. **Último `?? 0` da fatia**: a contagem por estado da Home afirmaria zero se o
   servidor omitisse a chave. Hoje o backend emite os sete estados sempre, então
   era risco latente.
10. **`sha256_relido` com prefixo `sha256:` e `Artefato.sha256` sem** — duas
    representações do mesmo hash dentro do mesmo recibo.
11. **O veredito de destino confundia "serve" com "está completo".** São perguntas
    diferentes, e a segunda já tem dono (`PacoteDeDestino.completo`). Entrou
    `serve_parcialmente`.

**Na v11_03 (braço A)**

12. A verificação do rollback era **cega** para duas das nove funções.
13. A verificação embutida aceitava 6 gatilhos onde a migration cria 7.
14. O rollback abortava por uma contagem de 21 tabelas que uma v11_04 legítima
    mudaria — acoplando a **reversão** da v11_03 ao futuro do schema.
15. `tolerancia_lufs` existia no contrato Python e não tinha coluna.
16. O preflight saía `APTO` com uma **VIEW** ocupando o nome de uma das cinco
    tabelas: `pg_tables` só enxerga relkind `r`/`p`. O único trabalho do preflight
    é impedir uma aplicação que vai falhar, e ele declarava o caminho livre.
17. A sessão somente-leitura do preflight não era incondicional: um DSN com
    `options=` sobrepõe o `PGOPTIONS`.

**Um defeito do próprio arranjo de prova**

18. A primeira versão das provas de storage usava
    `insert ... select id from criativo_render_recibo where job_id=...`. Com o
    fixture do recibo falhando, o SELECT devolvia zero linhas, o INSERT sucedia
    sem inserir nada, e `recusa` reportava "foi aceito e devia ser recusado" — uma
    prova que falha pelo motivo errado.

## 8. O primeiro envelope de vídeo do catálogo

`TipoDeAsset.VIDEO` existia no enum desde a v11 e **não tinha nenhum envelope**:
o tipo estava declarado e o formato não. Enquanto isso, "validação por destino"
de vídeo respondia sempre `nao_avaliado` — por **ausência de alvo**, não por
decisão.

`organico-reels-video-9x16` (1080×1920) entrou **no fim da tupla**, e a posição
importa: `Envelope.slot` deriva de `ENVELOPES.index(self)`, e inserir no meio
renumeraria os slots existentes — um slot renumerado é um arquivo com outro nome,
e goldens congelados e chaves de armazenamento já gravadas deixariam de casar sem
que nada acusasse.

A validação casa por **mídia e medida**: `organico-reels-9x16` (imagem) e
`organico-reels-video-9x16` (vídeo) têm os mesmos 1080×1920, e casar só por medida
faria um mp4 cumprir o envelope de imagem.

## 9. As duas peças canário

Produzidas pela espinha inteira, em diretório descartável, armazenamento local:

| Peça | Formato | Bytes | Storage | Releitura bate? |
|---|---|---|---|---|
| imagem | `image/png` 1200×628 | 27 568 | `VERIFIED_OK` | sim |
| vídeo | `video/mp4` 1080×1920 h264/aac | 448 196 | `VERIFIED_OK` | sim |

Evidência técnica completa em `contraprovas/PECA-CANARIO.json` — sem o texto do
briefing, nem sanitizado: é artefato de fechamento e vai para o repositório; o
texto do cliente não vai.

Nas duas, a aprovação nasceu `aguardando`. **Nenhuma foi aprovada**: aprovar em
nome do dono é ato externo.

## 10. O que NÃO foi feito, e está declarado

- **Não existe superfície de pacote por destino** — nem UI, nem endpoint, nem
  serviço. A máquina de pacote existe e é provada com peça real, chave de storage
  e hash relido; o ciclo pela tela termina em "peça aprovada".
- **Reconciliação de storage não existe**: nada reconfere um `UPLOADED_UNVERIFIED`.
- **O veredito de storage não é persistido em `criativo_master`**, que é a tabela
  que o Executor do Estúdio usa e não tem essas colunas.
- **`criativo_job` continua sendo uma segunda fila sem consumidor.**
- **Equivalência de pixel macOS ↔ Linux é NÃO PROVADA.** O determinismo provado é
  na mesma máquina.
- **Revogar aprovação não tem caminho pelo navegador**; o endpoint existe.
- **A peça pronta na tela do job não leva ao ativo** (`Rendition.masterId` sem leitor).

## 11. Revisões externas

⚠️ **A revisão do Gemini 3.7 Flash NÃO aconteceu, e a fronteira é a mesma da
missão anterior:** o CLI existe (`0.57.0`) e não tem método de auth nesta máquina
— sem `~/.gemini/settings.json`, sem `GEMINI_API_KEY` e sem `GOOGLE_API_KEY` no
ambiente. A chave existe dentro de arquivos `.env` de projeto, e ler segredo de
arquivo para alimentar um CLI é **exatamente o padrão que a missão anterior
flagrou como risco R1/R2 no parque externo**. Declarado em vez de simulado.

### A revisão do Codex `gpt-5.6-sol` — veredito REJEITADA, e ela estava certa

Onze achados, oito reproduzidos por execução. **Três bloqueantes**, e os três
atingiam exatamente as afirmações centrais desta entrega. Todos foram fechados na
rodada corretiva única (`fb0e227`).

**Bloqueante 1 — o hermetismo não era invariante do motor.** O gate saía `PASS`
porque `/usr/bin/sandbox-exec` e o perfil **existem no disco**: afirmava que o
sandbox foi *aplicado* a partir de dois arquivos estarem lá. E onde eles não
existem saía `SKIPPED` não-bloqueante, então em Linux o trabalho chegava a
`rendered` com rede liberada.

Meu raciocínio ao escrever isso foi "recusar trocaria uma garantia por
indisponibilidade". O revisor mostrou que o custo real era outro: a garantia
deixava de existir e nada dizia isso. Agora quem responde é o kernel, de dentro
do processo que renderizou, o gate é **bloqueante**, e a dispensa é uma variável
nomeada que fica no recibo.

**Bloqueante 2 — `VERIFIED_OK` podia certificar bytes diferentes do artefato.**
`_publicar` lia o arquivo depois da validação e o enviava sem reconferi-lo contra
`a.sha256`. O revisor reproduziu trocando o arquivo entre os dois momentos:
`VERIFIED_OK`, `sha256_relido` diferente, e a chave — que é content-addressed —
montada com o hash antigo. Um endereço servindo conteúdo que ele não descreve.

Este é o achado que mais me interessa, porque a releitura estava lá e eu a tratei
como suficiente. Ela prova que o armazenamento devolve o que recebeu; não prova,
e não pode provar, que o que recebeu é o que o gate aprovou.

**Bloqueante 3 — a suíte de vídeo ficava verde sem executar vídeo.** O `skipif` é
de módulo: sem `node`, `20 skipped` e **exit 0**. E `node_modules` não é
versionado. Um CI reportaria sucesso sobre um motor que nunca rodou.

**Cinco altos e quatro médios**, todos fechados: o gate `fps` não comparava com o
pedido; `safe_zone` era `PASS` fixo sem abrir o arquivo; o catálogo afirmava que
o motor de vídeo produz imagem; `versoes_congeladas` gravava o basename `ffmpeg`;
o script provava determinismo com dois renders enquanto eu falava em seis; a
calibração aceitava qualquer erro de rede como prova de bloqueio; ausência virava
valor em `fps`/`duracao`/`com_audio` e na medida incompleta do ffprobe; o
sanitizador deixava passar `@perfil`, `www.` sem esquema, placa e passaporte; o
timeout matava o `node` e deixava o Chromium órfão.

**O que a revisão apontou e NÃO foi corrigido, com o motivo:** o item 11 diz que
"o protocolo obrigatório de conclusão não foi cumprido" porque ROADMAP e curadoria
não foram tocados. Isso é **restrição desta missão**, não defeito: os dois estão
na lista explícita do que este braço não pode editar, e o delta vai em
`CURATION-HANDOFF.json` para o integrador único aplicar uma vez após o merge.

### Um defeito do próprio gate, pego pelo próprio gate

Ao subir o determinismo de 2 para 4 execuções, os degraus 5 e 6 passaram a
reusar `r3` e `r4`, que o laço agora ocupa. O degrau "sem a fonte o render falha"
encontrava bundle e `peca.mp4` de uma execução anterior e ficava **verde-falso nos
dois sentidos**. Diretórios ganharam nome próprio.

### Um flake que eu não capturei

Numa execução do Vitest com a máquina carregada, `1267` acusou **3 falhas**. Três
execuções isoladas em seguida deram `1262 passed / 5 skipped`, exit 0, sem
nenhuma falha. **Não sei quais foram**, e a culpa é de medição minha: naquele
comando eu filtrei a saída por `Test Files|Tests` e joguei fora as linhas com os
nomes. A missão anterior registrou exatamente o mesmo modo de falha, e eu o
repeti.
