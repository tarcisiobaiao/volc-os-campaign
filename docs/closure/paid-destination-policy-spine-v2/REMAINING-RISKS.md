# RISCOS REMANESCENTES — o que esta sprint NÃO fechou

Escrito antes do handoff, e não depois, porque uma lista de riscos redigida no
fim de um relatório vira parágrafo de rodapé. Cada item abaixo foi **medido ou
lido no código**, não imaginado.

---

## 1 · O que o portão não alcança, por construção

### 1.1 · A publicação acontece dentro de um subprocesso

O backend não escreve no WordPress. Ele dispara `run-volc`/`funnelforge resume`
com `--publish`, e o motor — que carrega a credencial — escreve. Um portão em
Python pode **recusar o disparo**; ele não pode parar o motor no meio, e uma
invocação por terminal (`funnelforge run … --publish`) não passa por ele.

É por isso que o portão **dentro** do motor não é opcional, e é por isso que
"barreira 2" tem duas metades. Resíduo declarado: quem tiver shell na máquina do
motor publica sem portão. Fechar isso exige mover a credencial para fora do
alcance do CLI, o que é outra sprint.

### 1.2 · O portão lê HTML servido, não a tela renderizada

`texto_visivel` agora descarta bloco escondido por **CSS inline** e por atributo
(`display:none`, `visibility:hidden`, `hidden`, `aria-hidden`). Ele **não**
resolve folha de estilo externa: uma classe `.oculto{display:none}` definida em
`<style>` continua invisível para o portão. Resolver cascata exige motor de
renderização.

### 1.3 · Uma URL, um HTML

`PaginaObservada` carrega um `html`. A comparação móvel × desktop é feita por
**hash de variante**, não por conteúdo: o portão sabe dizer que os dois diferem,
mas não varre o HTML móvel como conteúdo. Uma renderização móvel que suprimisse
as disclosures seria observada como divergência de dispositivo, e não como
disclosure ausente.

---

## 2 · Versões que não cobrem tudo que decide o veredito

`policy_contract_version` é uma string mantida à mão, e `policy_source_version`
é o hash da matriz de fontes. **Nenhuma das duas cobre o código dos detectores**
— as expressões regulares e limiares de `varredura.py` — nem as tabelas de
severidade de `contrato.py`.

Consequência concreta: mover um código de `_RISCO_SEMPRE` para `_BLOQUEIA_NO_PAGO`
muda o veredito de toda página avaliada, e os dois campos de versão do recibo
ficam idênticos. Um recibo emitido antes pareceria reaproveitável.

É o mesmo defeito que `versao_da_fonte()` foi escrita para evitar ("número
manual mente"), agora um nível acima. **Não foi fechado.** Já existe precedente
de conserto no repositório: `scripts/inventariar_motor_video.py` calcula um
`source_fingerprint_sha256` do próprio código.

---

## 3 · Autorização que continua vindo do chamador

`hosts_declarados` e `adtech_declarada` são listas que o chamador passa. Elas
desligam quatro códigos de bloqueio (`LINK_EXTERNO_NAO_CLASSIFICADO`,
`BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO`, `SCRIPT_TERCEIRO_NAO_DECLARADO`,
`MARCA_TERCEIRA_SEM_LASTRO`) e **nada verifica a procedência delas**.

A regra nova reduz muito o dano no papel estrito — no `paid_destination` um host
declarado continua sendo hyperlink externo e continua bloqueando — mas em
`editorial_solution` a declaração ainda é a única prova.

---

## 4 · Falsos bloqueios ainda possíveis

Um portão que reprova demais é desligado pela operação, e portão desligado não
protege nada. Três fontes conhecidas de falso positivo, todas medidas:

1. ~~Casamento por substring sem fronteira de palavra~~ — **corrigido**.
   `_contar_termo` passou a exigir fronteira de palavra, e `"cin"`/`"visto"`
   saíram de `_DOCUMENTOS_RESTRITOS` (voltam pela forma não ambígua: "visto
   americano", "carteira de identidade nacional"). Travado por
   `test_rc11_documento_restrito_exige_a_palavra_inteira`.
2. **`ANCORA_INCONGRUENTE_COM_DESTINO`** foi promovido a bloqueio e **devolvido
   a risco na mesma sprint**. Medido no papel estrito, ele reprovava CTA interno
   banal: "Simule agora" → `/rec/calculadora-do-saque/`, "Continuar" →
   `/rec/regras-do-fgts/`. A regra exige interseção de tokens entre a âncora e o
   caminho, e um CTA bom quase nunca repete o slug — ele diz o que o leitor
   GANHA, não onde ele vai. Continua sendo emitido como risco, e o operador o lê.
3. **`_marcas_sem_lastro`** procura nome próprio dentro de uma moldura de
   parceria. Não é NER; ele erra em nome próprio que não é marca. O substantivo
   que ABRE a moldura ("Empresas como…") deixou de ser colhido como marca —
   era falso bloqueio medido —, mas a heurística continua textual.

O vazamento de profundidade de botão — que marcava **todo** link posterior ao
primeiro `wp-block-button` como `em_botao` e fabricava `PAGINA_PONTE` — **foi
corrigido** nesta sprint.

---

## 5 · O que a evidência não sustenta, e continua não sustentando

**A notificação literal da suspensão nunca foi lida.** Nada nesta sprint muda
isso. `ROOT-CAUSE-ANALYSIS.md` permanece em `HYPOTHESIS_PARTIALLY_SUPPORTED`, e
nenhum artefato produzido aqui pode ser citado como prova da causa.

E uma pergunta que a recon levantou e **não** foi resolvida: `canario.exigir`
restringe a criação de campanha a um `customer_id` específico, enquanto a conta
suspensa mostrava campanhas que a tabela local não registrava. Isso **sugere um
caminho de criação fora de `/subir`** — n8n, o CLI `volc_ads`, ou a própria
interface do Google Ads. Se existir, **nenhuma das três barreiras cobre o
caminho que efetivamente causou o incidente.** Não foi possível determinar isso
lendo código.

---

## 6 · O estado ao vivo, em 2026-09-03

Medido nesta sprint por leitura pública read-only:

- `/r/fgts-saque-aniversario/` — os sete links `caixa.gov.br` de âncora numérica
  **não existem mais**. Mas o formato monetário malformado **continua**, e
  `www.fabiolobo.com.br` continua sem classificação declarada.
- `/r/antecipacao-saque-aniversario-fgts/` — **onze bloqueios**, sem identidade
  de operador, sem contato, sem aviso de não-vínculo. A Fase A1 do
  `LIVE-REMEDIATION-PLAN.md` **não foi executada**.
- Os outros **oito** destinos `/r/` de `creditoup.com.br` e os **quatro** de
  `portalmundomais.com` **não foram lidos** nesta sprint.

Enquanto a Fase A não estiver completa, qualquer campanha apontando para esses
destinos aponta para página que o portão reprova — e agora o portão está no
caminho, então ela será recusada em `/provar` e em `/subir`.

---

## 6bis · ⚠️ A PARADA OPERACIONAL: nada emite recibo de escopo `live`

Este é o risco mais importante da lista, e ele foi encontrado pela revisão de
olhos frescos **medindo o caminho inteiro**, não lendo código.

O recibo do portão 2 carimba a impressão do **artefato** — o corpo que o motor
escreveu. A barreira 3 lê a página **no ar**, que é esse corpo dentro do tema do
WordPress: cabeçalho, menu, rodapé institucional, slots de anúncio. São dois
documentos diferentes por construção, e as impressões nunca batem.

A primeira versão comparava os dois. Efeito medido: `DERIVA_AO_VIVO` e
`RECIBO_DE_OUTRO_CONTEUDO` em **100% das páginas reais** — `/provar` retinha o
selo sempre, `/subir` devolvia 409 sempre, e **nenhuma página jamais viraria
destino de campanha**. Um portão que nunca aprova é indistinguível de um portão
quebrado.

A correção não isenta: sem aprovação do mesmo escopo, a deriva é **inobservável**,
e `live_drift` está em `NAO_APLICAVEL_E_DESCONHECIDO_EM`, então a ausência
**reprova**. O destino continua inelegível; o que muda é o MOTIVO, que passa a
ser verdadeiro e acionável ("ninguém reauditou esta página ao vivo") em vez de
falso ("o conteúdo mudou").

**A consequência operacional, dita sem suavização:** enquanto nada emitir um
recibo de escopo `live`, **nenhum destino fica elegível para campanha**. É
fail-closed — portanto seguro, e é o desfecho correto para "ninguém verificou
esta página no ar". Mas é uma parada real: a operação não sobe campanha nenhuma
até que exista o ato que registra a aprovação ao vivo.

Esse ato não foi construído nesta sprint porque ele exige **escrita no
Supabase**, que a missão proíbe. O desenho está pronto para recebê-lo: basta que
o caminho de reauditoria emita `emitir_recibo(..., escopo_da_impressao="live")` e
o pendure em `paginas_publicadas` pelo mesmo `anexar_recibo` que o motor usa.

**Pergunta que fica para o operador:** a reauditoria ao vivo deve ser um ato
explícito (um botão "reauditar destino") ou o próprio `/provar` deve gravar o
recibo `live` quando a avaliação passa em tudo menos na deriva? A segunda é mais
cômoda e é circular — ela aprova a si mesma. A primeira é mais lenta e é honesta.
A decisão não é técnica.

---

## 6ter · O tema do WordPress entra na avaliação ao vivo

Consequência do mesmo desalinhamento, medida na mesma revisão: qualquer
hyperlink externo que o **tema** renderiza — crédito "Orgulhosamente com
WordPress", ícone de rede social, link de autor — é invisível para os portões 1
e 2 (que veem só o artefato) e vira `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO` no
portão 3.

O operador recebe uma recusa que **não tem como consertar mexendo no conteúdo do
funil**. A política interna ("recusa TODO hyperlink externo clicável") foi
escrita pensando no corpo editorial, e o portão 3 a aplica a um documento que
inclui a navegação do site.

**Não foi consertado nesta sprint**, e enfraquecer a regra desfaria o núcleo do
trabalho. O conserto correto é o site declarar os hosts do próprio tema — o
contrato já tem o campo (`adtech_declarada`) e nada o preenche. É trabalho de
uma sprint seguinte, e é pré-requisito para a operação usar a barreira 3.

---

## 7 · O que fica para o integrador

- Aplicar a atualização de Roadmap/curadoria **uma única vez**, a partir de
  `CURATION-HANDOFF.json`. Nenhuma fonte compartilhada foi tocada nesta branch.
- Decidir sobre `GATE-RECEIPTS.json` do pacote anterior: seus cinco recibos
  foram emitidos contra `policy_source_version df252bc25e636d78`, e a matriz
  agora é `43472d43866cbf19`. Pela regra da própria espinha, eles estão
  desatualizados. **Regenerá-los quebraria as citações do pacote de apelação**;
  não regenerá-los deixa o pacote citando uma versão de política que não existe
  mais. Esta sprint **não** os tocou, de propósito, e o delta v1→v2 vive num
  arquivo separado (`GATE-RECEIPTS-V2.json`).
- Decidir sobre as rotas de documento de governo: a política *Government
  documents and services* muda com efeito em **05/10/2026**.
