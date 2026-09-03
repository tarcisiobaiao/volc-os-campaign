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

1. **Casamento por substring sem fronteira de palavra.** `_ORGAOS` contém
   `"pis"`, então "epi**sód**io" não casa mas "**pis**ta" casa;
   `_DOCUMENTOS_RESTRITOS` contém `"visto"` (particípio de *ver*) e `"cin"`
   (dentro de "va**cin**a"). Um texto inocente pode disparar
   `AVISO_NAO_OFICIAL_AUSENTE`.
2. **`ANCORA_INCONGRUENTE_COM_DESTINO`** compara tokens da âncora com o caminho
   da URL. Ele foi **promovido a bloqueio** no papel estrito nesta sprint, o que
   aumenta o custo de um falso positivo. Foi medido nos quatro destinos
   preservados e nos dois lidos ao vivo, e disparou onde havia incongruência
   real — mas a heurística é textual.
3. **`_marcas_sem_lastro`** procura nome próprio dentro de uma moldura de
   parceria. Não é NER; ele erra em nome próprio que não é marca.

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
