# Handoff — caminho governado `create_paused` da Meta, v1

> **Nenhuma chamada real à Meta aconteceu nesta missão.** Nenhum objeto foi
> criado, em nenhuma conta. A migration continua candidata e não aplicada em
> lugar nenhum. Tudo abaixo foi provado localmente, com transporte hermético e
> PostgreSQL descartável.

Worktree `/private/tmp/volc-os-operacao-80-20`, branch
`execution/volc-os-operacao-80-20`, base `37258f1c`.

---

## 1. O que existia, e o que faltava

A lane anterior (`meta-creation-engine-operator-experience-v1`) terminou com o
motor pronto e **nenhuma rota montada**. `PROVA-VALIDATE-ONLY-REAL.md` registra
doze sondas a `criar`, `nascer`, `aprovar`, `habilitar` e `ativar` — todas 404.
`criar_pausada` existia em `executor.py`, completo e testado, **sem um único
chamador de produção**.

Faltavam quatro coisas, e três delas eram o mesmo problema visto de ângulos
diferentes:

1. **Nada persistia a validação.** `validate_only` devolvia a prova ao navegador
   e a esquecia. Qualquer aprovação construída sobre isso confiaria no cliente
   para afirmar "eu fui validado".
2. **Não havia aprovação durável.** O `AutorizacaoMeta` do executor já exigia
   `approval_id` e hash, mas ninguém os produzia.
3. **Não havia rota.** O ato de criar não existia.
4. **Passo AMBÍGUO era terminal.** Risco 3 de `REMAINING-RISKS.md` da lane
   anterior: a saga marcava ambiguidade corretamente e se recusava a reenviar,
   e o recibo ficava aberto para sempre.

---

## 2. O que esta missão implementou

### Três rotas, três atos, nenhuma fazendo o trabalho da outra

```
POST /api/trafego/meta/local/criacao/aprovar          decide. Não cria.
POST /api/trafego/meta/local/criacao/criar-pausada    cria. Não decide.
POST /api/trafego/meta/local/criacao/reconciliar      lê. Não reenvia.
POST /api/trafego/meta/local/criacao/recibo           projeta o recibo sanitizado.
```

Elas vivem em `backend/app/routers/trafego_meta_criacao.py`, **módulo separado**
do plano de controle seguro. A separação não é organizacional: ela impede que a
autoridade de criação viaje junto de rotas que nunca deveriam tê-la, e mantém
verdadeira a frase do topo de `trafego_meta_validacao.py`.

**Não existe rota de ativação**, aqui ou em lugar nenhum — e agora isso é
provado por varredura do **app inteiro**, não de um router. O tripwire anterior
olhava só `trafego_meta_validacao.router`; ele teria continuado verde depois
desta mudança enquanto deixava de significar qualquer coisa.

### O recibo durável do `validate_only`

Tabela nova `trafego_meta_validation_receipt`, escrita pelo servidor depois de a
Meta responder `success`. A aprovação referencia uma linha real, com `UNIQUE`
para que um recibo autorize uma aprovação e só uma.

Se `META_CREATE_LEDGER_WRITE_ENABLED` estiver fechada, a validação continua
valendo e a resposta declara `prova_duravel.registrada = false` com o motivo — e
a aprovação falha fechada depois, por falta de recibo.

### A aprovação

Vinculada a ator, conta opaca, `plan_sha256`, manifesto ordenado, orçamento em
minor units, moeda, quantidade de operações, expiração curta (15 min na rota,
teto de 1h no `CHECK`), timestamp do servidor e a confirmação humana de
nascimento PAUSED — esta última recusada pelo próprio `CHECK`, não só pela rota.

### A criação

Recebe **duas referências** e nenhum payload Meta. O servidor relê o pedido do
operador gravado na aprovação, revalida-o pelo contrato inteiro, recompila e
confere três hashes: o que a tela mostrou, o que ficou gravado e o que acabou de
compilar.

⚠️ **A aprovação é lida antes do Keychain.** Um `approval_id` expirado, de outra
pessoa ou de outro plano nunca chega perto da credencial. O teste que prova isso
substitui `_credencial_salva` por uma armadilha que falha se for chamada.

### A reconciliação

Fecha o beco sem saída do risco 3. Percorre o plano aprovado contra a conta real,
**só lendo**:

| Leitura | Conclusão |
|---|---|
| um objeto, read-back completo confere **e** nasceu depois do recibo | fecha como CRIADO |
| listagem completa, nada encontrado, passo com ≥120 s | fecha como NÃO ENCONTRADO |
| listagem incompleta, dois homônimos, read-back divergente, objeto anterior ao despacho, tipo sem `created_time` | **permanece AMBIGUO** |

Nenhum `POST` sai dessa rota. Não conseguir provar a ausência não é prová-la.

⚠️ Nome igual não prova nascimento — a unicidade que o contrato garante vale
dentro do lote, não dentro da conta. Por isso a identidade tem três camadas:
nome, read-back completo e `created_time` posterior ao `prepared_at`. E por isso
um **`AdCreative` nunca é fechado por leitura**: a Marketing API não expõe
`created_time` para criativos, e inventar a prova seria pior do que não tê-la.

### A tela

Enquanto fechado: *"Criação PAUSED ainda fechada neste servidor"*, com a causa em
linguagem de operador e **nenhum controle de criação na árvore** — nem
desabilitado. Um botão cinzento ensinaria que a criação está a um clique.

Aberto: resumo exato (conta, orçamento, campanha, conjunto, quantidade de
criativos e anúncios, tudo PAUSED, hash, validação), checkbox *"Confirmo a
criação real destes objetos em estado PAUSED"*, confirmação digitada
`CRIAR PAUSADA` comparada literalmente nos dois lados, **Aprovar plano** e
**Criar campanha PAUSED** separados, trava síncrona de duplo clique, e recibo
mais read-back sanitizados.

---

## 3. Decisões que merecem discussão

### Por que a aprovação guarda o pedido do operador

Porque a missão exige que a criação receba **apenas** a referência da aprovação.
Sem o pedido gravado o servidor não teria como reconstruir o payload.

O que fica no banco são referências **opacas** e o texto do operador. O
identificador da conta, o `page_id` e o `image_hash` continuam vivendo só dentro
do processo, em `ReferenciasMetaResolvidas`, e são re-resolvidos a cada
recompilação. Se a Página ou a imagem mudarem de identidade entre a aprovação e
a criação, o hash recompilado diverge e a criação para. Essa é a propriedade
desejada, e ela é consequência de guardar o pedido em vez do payload.

### Por que 502, e não 422 nem 504

422 é "a Meta olhou e recusou": prova que nada nasceu. 504, na rota de validação,
é "ninguém respondeu, pode retentar" — seguro porque `validate_only` não cria.
Ambiguidade depois de um despacho de **criação** não é nenhuma das duas: houve
pedido e o resultado é desconhecido. Reaproveitar o 504 ensinaria que retentar é
aceitável, e retentar depois de um despacho duplica a campanha.

### Por que `validation_id` é UNIQUE, mesmo custando uma revalidação

Reaprovar depois de expirar passa a exigir validar de novo. É deliberado: uma
prova de trinta minutos atrás não descreve a conta agora — saldo, Página e
biblioteca de imagens mudam sem avisar. E mata o replay de uma prova antiga.

### Por que a fixture de teste do ledger recusa

`_LedgerEmMemoria` devolve AMBIGUO na reentrada de um passo em voo e recusa passo
fora do manifesto, reproduzindo as RPCs. Um dublê complacente faria os testes de
duplicação passarem sem que a garantia existisse.

---

## 4. O que continua impossível

- Criar qualquer coisa sem as duas flags abertas.
- Aprovar sem um recibo de `validate_only` gravado pelo servidor para o mesmo
  hash, conta e ator, dentro da janela.
- Criar um plano diferente do aprovado — três hashes precisam coincidir.
- Criar um filho antes de o pai estar CRIADO no ledger.
- Levar qualquer objeto a ACTIVE ou ENABLE: não há payload, rota nem botão.
- Reenviar depois de um despacho ambíguo.
- Ver um identificador da Meta, `image_hash`, URL assinada ou token no
  navegador.

---

## 5. A rodada corretiva, e o que ela mudou de opinião

Codex revisou o commit em modo somente-leitura e devolveu **oito achados**, com
veredito REPROVADO. Sete eram reais. Dois deles eram caminhos concretos de
**duplicar uma campanha na conta**, e nenhum dos dois era óbvio:

**O plano inteiro é a identidade errada.** O `plan_sha256` cobre todas as
operações. Mudar a headline de um anúncio muda o hash do plano — e deixa o
payload da Campaign byte a byte idêntico. Como uma falha no AdSet **libera** o
plano para nova aprovação, o caminho existia inteiro: aprovar, criar a campanha,
falhar no conjunto, corrigir a headline, aprovar de novo, e a mesma campanha
nasce pela segunda vez. A identidade que importa não é a do plano; é a do
**objeto na conta**: `(conta, nome do passo, payload resolvido)`.

**Ambiguidade não é permissão para concluir ausência.** Um passo vira `AMBIGUOUS`
assim que uma segunda chamada reentra nele — e isso pode acontecer com a
primeira ainda dentro do `await` do `POST`. A reconciliação, correndo nesse
instante, listaria a conta, não acharia nada, fecharia FALHO, e o `POST`
original criaria o objeto depois, com o livro já dizendo que ele não existe.

Um achado foi **rejeitado**: o revisor apontou que o `AdCreative` nasce `ACTIVE`.
A receita aprovada declara literalmente "Creative não é veiculável", e não existe
payload que faça a Meta pausá-lo. Mudar isso seria mudar a receita.

E de um achado o **remédio** foi recusado: o revisor propôs fechar o recibo
depois do read-back. Isso perderia o id numa queda entre o `POST` e o `INSERT`. A
ordem ficou; o que entrou foi `readback_error`, o registro durável da
divergência.

A adjudicação completa está em `REVISAO-ADVERSARIAL-CODEX.md`, com o relatório
do revisor na íntegra.

---

## 6. Estado de P11-T05

**Continua `partial`. Não promover.**

O que esta missão acrescentou é o caminho governado *implementado e provado
localmente*. O que continua faltando para `done` é o que sempre faltou: a
migration aplicada em janela oficial autorizada, e o primeiro canário Meta
PAUSED real com read-back — nenhum dos dois autorizado nesta missão.
