# Contrato do motor criativo para a UI — o que o Worker 3 chama

*Worker 1 (creative-runtime) → Worker 3 (UI `/criativos`). Branch
`sprint/traffic-creative-operational-closure-v1`.*

> **Estado.** Escrito no início da rodada como contrato de integração e
> **atualizado contra o código já entregue** (commits `fbb7f3e`, `5efd756`,
> `ac0e12a`). Todo campo abaixo foi copiado de um envelope real. Se algo aqui
> divergir do código, **o código é a autoridade** — me avise, não contorne.

---

## 1. Onde o caminho mora

Um só módulo, e ele é a **extensão da bancada que já existia** — não um segundo
caminho:

```
backend/app/criativo/bancada/servico.py
```

O Worker 3 **não** deve importar `volc_ads.criativo.*` nem
`volc_ads.criativo_ponte` a partir da camada HTTP. Tudo que a tela precisa sai
das cinco funções abaixo, já em tipos JSON-nativos (`str`, `int`, `float`,
`bool`, `None`, `list`, `dict`). Não há `datetime`, `Enum`, `bytes` nem
`dataclass` no retorno — há teste que serializa o envelope com `json.dumps` sem
`default=`.

```python
from app.criativo.bancada import servico

servico.receitas_locais()          # o que esta máquina sabe produzir
servico.produzir_local(...)        # enfileira + executa, devolve o envelope
servico.estado_da_producao(...)    # o envelope de uma produção existente
servico.ambiente_da_bancada()      # se dá para produzir aqui, e por que não
servico.motores_disponiveis()      # já existia; ganhou `natureza`/`publicavel`
```

---

## 2. As cinco assinaturas

### 2.1 `receitas_locais()`

```python
def receitas_locais() -> list[dict[str, Any]]
```

Sem argumentos. Nunca levanta. Retorno real:

```json
{
  "receita_id": "display-minimo",
  "canal": "DISPLAY",
  "rotulo": "Display — o mínimo que o canal aceita",
  "motor_slug": "png-local",
  "disponivel": true,
  "natureza": "local",
  "publicavel": false,
  "exigencia_fonte": "matriz-api/display.md §3 (proto ResponsiveDisplayAdInfo)",
  "exigencia_provisoria": false,
  "saidas": [
    {"slot": "0-imagem_marketing",          "papel": "marketing",
     "tipo": "imagem_marketing",            "largura": 600, "altura": 314},
    {"slot": "1-imagem_marketing_quadrada", "papel": "marketing_quadrada",
     "tipo": "imagem_marketing_quadrada",   "largura": 320, "altura": 320}
  ]
}
```

Duas receitas hoje: `display-minimo` e `demand-gen-minimo`. `saidas` é **derivado
da régua** do canal (`volc_ads/criativo/requisitos.yaml`) — obrigatórios do canal
mais o que os tetos combinados exigem no conjunto. Não é lista escrita à mão: se
o YAML mudar, esta lista muda junto. Há teste comparando os dois.

`disponivel: false` significa que o motor não está registrado nesta máquina —
mostre a receita desabilitada, não a esconda.

---

### 2.2 `produzir_local(...)`

```python
def produzir_local(
    *,
    receita_id: str,
    tenant_id: str,
    insumo: str,
    intencao: str = "",
    seed: int = 0,
    destino: str = "ensaio",     # "ensaio" | "producao"
) -> dict[str, Any]
```

Enfileira **e executa** o trabalho na bancada e devolve o **mesmo envelope** de
`estado_da_producao` (§3).

| Parâmetro | Obrigatório | O quê |
|---|---|---|
| `receita_id` | sim | um `receita_id` de `receitas_locais()` |
| `tenant_id` | sim | dono do trabalho; entra na chave de idempotência |
| `insumo` | sim | o briefing/prompt. String vazia é recusada |
| `intencao` | não | a que campanha/tema o lote serve; default `receita_id` |
| `seed` | não | semente do motor. Mesma semente ⇒ mesmos bytes |
| `destino` | não | para onde o payload iria. Ver §5 |

**Idempotência.** Duas chamadas com os mesmos argumentos convergem para o **mesmo
`trabalho_id`** e não produzem de novo. Inquilinos diferentes com o mesmo pedido
são trabalhos diferentes. Isso é da bancada, não desta camada.

**Nunca levanta por erro de entrada.** Receita desconhecida, insumo vazio, tenant
vazio, destino desconhecido, motor ausente, ambiente serverless — tudo volta como
envelope com `erro` preenchido e `trabalho_id: null` (§4). Levantar obrigaria a
rota a adivinhar o status HTTP a partir do texto da exceção. Erro de programação
(assinatura errada) continua sendo `TypeError`, como deve ser.

⚠️ O render roda **no processo do request**, de forma síncrona. Para estas
receitas isso é da ordem de dezenas de milissegundos — o motor é stdlib e não
fala com ninguém. **Não estenda esse padrão para motor pago.** E consulte
`ambiente_da_bancada()` antes de oferecer o botão: em ambiente sem processo de
vida longa a produção é recusada por construção (§2.4).

---

### 2.3 `estado_da_producao(...)`

```python
def estado_da_producao(
    trabalho_id: str, *, tenant_id: str, destino: str = "ensaio"
) -> dict[str, Any] | None
```

`None` quando não existe trabalho com esse id **para esse inquilino**. `None`
significa "não existe / não é seu" — a rota traduz para 404. Não é "existe e está
vazio". Um inquilino não lê o trabalho do outro; há teste.

---

### 2.4 `ambiente_da_bancada()`

```python
def ambiente_da_bancada() -> dict[str, Any]
```

```jsonc
{"ambiente": "local", "pode_produzir": true, "motivo": null,
 "despachante": "sincrono-local", "duravel": false, "sincrono": true}
```

Em Vercel/Lambda/Cloudflare: `pode_produzir: false` e `motivo` com o texto. Use
isso para **desabilitar o botão** em vez de deixar o operador clicar e receber
erro. `duravel: false` é dito em voz alta: o despachante local não sobrevive à
morte do processo.

---

### 2.5 `motores_disponiveis()` (já existia)

Inalterada, exceto que `png-local` agora aparece na lista e cada item ganhou
`"natureza"` e `"publicavel"`.

---

## 3. O envelope — campo a campo

Copiado de uma execução real (`recibo` e listas truncados):

```jsonc
{
  "trabalho_id": "52d19151-2848-4f8a-98c6-95dd1170b648",  // string | null
  "tenant_id": "volc",
  "receita_id": "display-minimo",
  "canal": "DISPLAY",                    // string | null
  "intencao": "display-minimo",
  "insumo": "banner do FGTS de setembro",
  "seed": 0,
  "chave_de_idempotencia": "feb02e70…",

  "estado": "rendered",   // queued|claimed|running|validating|rendered|failed|cancelled|null
  "terminal": true,       // estado ∈ {rendered, failed, cancelled}
  "tentativa": 1,
  "max_tentativas": 3,
  "criado_em": "2026-09-01T10:47:05.353798+00:00",

  "motor": {
    "slug": "png-local", "versao": "1.0.0",
    "natureza": "local", "publicavel": false,
    "versoes": {"adaptador": "1.0.0", "algoritmo": "blocos-1", "zlib": "1.2.12"}
  },

  "falha": null,          // ou {"codigo", "mensagem", "permanente", …}
  "erro":  null,          // ou {"codigo", "mensagem"} — §4

  "recibo": { … },        // o Recibo da bancada em JSON. ⚠️ carrega caminho de
                          // disco: é diagnóstico, NÃO renderize cru na tela
  "assinatura_determinista": "8c63f184…",   // string | null

  "assets": [ … ],                 // §3.1
  "artefatos_perdidos": [],        // §3.3
  "entrega": { … }                 // §3.2 — null quando NÃO foi tentada
}
```

### 3.1 `assets[]`

Uma entrada por artefato do recibo que ainda existe em disco **e foi medido a
partir dos bytes** — nunca do que o motor declarou.

```jsonc
{
  "identidade": "cri_08f2409a3376d09f38a3",
  "conteudo_hash": "sha256:08f2409a…",
  "slot": "0-imagem_marketing",
  "papel": "marketing",              // string | null (tipo sem papel neste canal)
  "tipo": "imagem_marketing",
  "mime": "image/png",               // string | null
  "largura": 600,                    // int | null  ⚠️ null = não medido, nunca 0
  "altura": 314,
  "bytes_totais": 537,
  "natureza": "local",
  "publicavel": false,
  "origem": "gerado",
  "procedencia": {
    "motor": "png-local",
    "versao_do_motor": "1.0.0",
    "insumo": "banner do FGTS de setembro",
    "insumo_hash": "911f3046e5fd6a97",
    "pedido": "52d19151-…",          // o trabalho_id
    "quando": "2026-09-01T10:47:05.356887+00:00",
    "custo_usd": null,               // ⚠️ null, nunca 0.0 — §5
    "nota": "`quando` é o `terminado_em` do recibo da bancada, não um relógio lido aqui"
  }
}
```

**Sem caminho de disco.** Nenhum campo de `assets`, `entrega`, `falha`, `erro` ou
`motor` carrega `/var/folders/...` nem `~/.volc-os/...`; há teste. Se a tela
precisar exibir a peça, isso é outra fatia (rota de bytes) e **ainda não existe**
— não invente um caminho a partir do `recibo`.

### 3.2 `entrega`

O resultado de atravessar a **ponte canônica**
(`volc_ads/criativo_ponte.imagens_de_display` / `imagens_de_demand_gen`) até o
contrato de canal.

```jsonc
{
  "tentada": true,
  "destino": "ensaio",               // o que foi pedido em produzir_local
  "ok": true,                        // há payload montável?
  "canal": "DISPLAY",
  "veredito": {
    "ok": true,                      // ⚠️ ≠ entrega.ok — ver abaixo
    "aprovados": 2,
    "reprovados": 0,
    "provisorio": false,
    "fonte": "matriz-api/display.md §3 (proto ResponsiveDisplayAdInfo)",
    "violacoes": ["[aviso/gerar_mais] Q3.abaixo_do_recomendado @logo_quadrado: 0 de 1 recomendados"]
  },
  "linhagem": [{"nome","papel","identidade","conteudo_hash","motor",
                "versao_do_motor","insumo","insumo_hash","pedido","quando",
                "origem","mime","largura","altura","bytes_totais","custo_usd",
                "derivado_de","id_externo","exigencia_fonte",
                "exigencia_provisoria","confirmada"}],
  "recusas": [],                     // uma linha por descarte
  "avisos": [],                      // natureza não declarada, etc.
  "naturezas": {"cri_08f2409a3376d09f38a3": "local"}   // cada asset do lote
}
```

⚠️ **`veredito.ok` e `entrega.ok` são perguntas diferentes.** A primeira é "os
arquivos são bons"; a segunda é "há payload montável". Um lote aprovado cujos
bytes a ponte recusou tem `veredito.ok = true` e `ok = false`, e o motivo está em
`recusas`. **A tela tem de mostrar `recusas`** — sem elas ela diz "aprovado"
sobre uma entrega que não saiu.

⚠️ Em **Display**, `ok == true` pode coexistir com `recusas` não-vazio (a ponte
entrega o que sobrou). Em **Demand Gen** não pode: qualquer recusa zera o payload.
É deliberado e está declarado no código.

`violacoes` são strings já formatadas: `[severidade/classe] CÓDIGO @alvo: detalhe`.
`severidade` é `erro` ou `aviso` — um `aviso` **não** derruba o lote (o exemplo
acima é um lote aprovado). Não pinte aviso de vermelho.

### 3.3 `artefatos_perdidos[]`

Lista de strings. Não-vazia quando o recibo aponta um arquivo que sumiu do disco
entre o render e a leitura. Aquele artefato **não vira asset** — a alternativa
seria um asset fantasma descrevendo um arquivo que não existe mais.

---

## 4. Como a tela distingue os desfechos

`ausente ≠ zero ≠ falha ≠ não aplicável`. **`assets == []` aparece em três dos
quatro desfechos** — ele nunca pode ser a pergunta que a tela faz. Leia nesta
ordem:

| # | Condição | O que aconteceu | O que a tela mostra |
|---|---|---|---|
| 1 | `erro != null` | O pedido nem virou trabalho. `trabalho_id` e `estado` são `null`. | `erro.mensagem`. **Não** é falha de render. |
| 2 | `estado == "failed"` | Existiu e terminou mal. `falha.codigo` diz por quê; `falha.permanente` diz se retentar adianta. | Causa explícita. Botão de retomar só se `permanente == false`. |
| 3 | `terminal == false` | Em andamento. `assets` vazio é **pendência**. | Estado em andamento. Nunca "nenhum criativo". |
| 4 | `estado == "rendered"` | Produziu. `assets` não-vazio e `recibo != null`. | As peças + a etiqueta de natureza (§5). |

E dentro do desfecho 4:

| Condição | Significado |
|---|---|
| `entrega == null` | A travessia **não foi tentada** (o trabalho não chegou a `rendered`, ou o canal não tem porta na ponte). **Não** é "reprovou" nem "zero imagens". |
| `entrega.ok == false` e `veredito.ok == false` | O lote não serve. Mostre `veredito.violacoes`. |
| `entrega.ok == false` e `veredito.ok == true` | O lote é bom; a ponte descartou os arquivos. Mostre `recusas` — é aqui que cai a recusa de promover ensaio a produção. |
| `entrega.ok == true` | Há payload montável. `linhagem` tem uma entrada por imagem. |

**Códigos de `erro.codigo`** (desfecho 1):

| Código | Quando |
|---|---|
| `receita_desconhecida` | `receita_id` fora de `receitas_locais()` |
| `insumo_vazio` | `insumo` em branco |
| `tenant_vazio` | `tenant_id` em branco |
| `destino_desconhecido` | `destino` fora de `{"ensaio","producao"}` |
| `canal_sem_regua` | a receita aponta um canal sem régua de arquivo |
| `motor_indisponivel` | o motor não está registrado nesta máquina |
| `ambiente_sem_processo_longo` | Vercel/Lambda/Cloudflare — render no request é recusado |

Em todos eles **nenhum trabalho é criado** (há teste comparando a contagem por
estado antes e depois).

**Códigos de `falha.codigo`** (desfecho 2, vindos da bancada):
`motor_desconhecido` · `motor_recusou` · `gate_reprovou` · `falha_inesperada`.

---

## 5. A regra que a UI **não pode** quebrar

> **Peça local/fixture nunca é apresentada como produção.**

Três coisas garantem isso do meu lado, e a quarta é sua:

1. `Procedencia.natureza` viaja em todo asset — `producao` | `local` | `fixture`
   | `nao_declarada`. O motor desta fatia declara `local`, sempre.
2. A ponte **recusa** asset de natureza `local`/`fixture` quando
   `destino == "producao"`. A recusa é nomeada e aparece em `entrega.recusas`;
   `entrega.ok` fica `false` com `veredito.ok` `true`.
3. `publicavel` é derivado (`natureza == "producao"`), nunca um booleano gravado
   que pode ficar velho.
4. **Sua parte:** onde `publicavel == false`, a tela rotula a peça como ensaio.
   Nada de selo de "pronto para subir", nada de botão de publicar habilitado.

Corolário: **`custo_usd` é `null`, não `0.0`.** O motor local não custa dinheiro,
mas `0.0` é uma afirmação de custo apurado, e um relatório de COGS que soma esses
zeros fecha bonito e está errado. Renderize ausência como "—", nunca "US$ 0,00".

---

## 6. Exemplo de rota (referência, não obrigação)

```python
@router.get("/criativos/receitas")
def receitas():
    return {"receitas": servico.receitas_locais(),
            "ambiente": servico.ambiente_da_bancada()}

@router.post("/criativos/produzir")
def produzir(corpo: PedidoDeProducao):
    envelope = servico.produzir_local(
        receita_id=corpo.receita_id, tenant_id=corpo.tenant_id,
        insumo=corpo.insumo, intencao=corpo.intencao or "",
        seed=corpo.seed or 0, destino=corpo.destino or "ensaio",
    )
    if envelope["erro"] is not None:
        # 503 para `ambiente_sem_processo_longo`, 400 para o resto:
        # um é condição da plataforma, o outro é culpa de quem chamou.
        codigo = envelope["erro"]["codigo"]
        status = 503 if codigo == "ambiente_sem_processo_longo" else 400
        raise HTTPException(status_code=status, detail=envelope["erro"])
    return envelope

@router.get("/criativos/producoes/{trabalho_id}")
def producao(trabalho_id: str, tenant_id: str, destino: str = "ensaio"):
    envelope = servico.estado_da_producao(
        trabalho_id, tenant_id=tenant_id, destino=destino)
    if envelope is None:
        raise HTTPException(status_code=404, detail="trabalho não encontrado")
    return envelope
```

---

## 7. A ponte, para quem for ligar o caminho de Display no HTTP

As duas portas têm **assinatura idêntica** — um adaptador só serve aos dois:

```python
imagens_de_display   (lote, conteudo_por_identidade, *, exigencia=None, destino=Destino.PRODUCAO) -> Entrega
imagens_de_demand_gen(lote, conteudo_por_identidade, *, exigencia=None, destino=Destino.PRODUCAO) -> Entrega
```

O que **diverge por razão real** (não trate como defeito):

- **Papéis.** `ImagensDisplay` tem 4 (`marketing`, `marketing_quadrada`, `logo`
  4:1, `logo_quadrado`); `ImagensDemandGen` tem 5 (as duas primeiras + `retrato`
  4:5 + `retrato_alto` 9:16 + `logo_quadrado`, e **não tem** `logo` 4:1). Itere
  `entrega.imagens.PAPEIS`, nunca uma lista escrita à mão.
- **Entrega parcial.** Display entrega o que sobrou com as recusas ao lado;
  Demand Gen zera o payload se houver qualquer recusa.

O que **deixou de divergir** nesta rodada (commit `5efd756`):

- `ImagemParaSubir.recibo_aprovacao` agora vem preenchido **nos dois canais**.
  Falhar ao emitir vira recusa nomeada, nunca `recibo=None` silencioso.
- `imagens_de_display` passou a recusar lote de outro canal (`PonteIncompleta`),
  como Demand Gen já fazia. `SEARCH`/`TIKTOK` continuam morrendo antes, no
  `exigencia_binaria_de`, cuja mensagem nomeia o dono daquele canal.

---

## 8. Prova

| Afirmação | Teste | Contagem |
|---|---|---|
| envelope tem a forma de §3 e é JSON-nativo | `backend/tests/test_criativo_producao_local.py` | 25 |
| os desfechos de §4 se distinguem, e nenhum cria trabalho à toa | idem | |
| nenhum caminho de disco vaza para a tela | idem | |
| a ponte recusa `local` em destino produção | idem + `volc_ads/criativo/testes_producao.py` | |
| duas produções iguais ⇒ mesmo hash e mesma identidade | `volc_ads/criativo/testes_png_local.py` | 15 |
| asset carrega hash, MIME, dimensão, procedência e recibo | `volc_ads/criativo/testes_producao.py` | 21 |
| linhagem e recibo saem íntegros pela ponte | idem | |
