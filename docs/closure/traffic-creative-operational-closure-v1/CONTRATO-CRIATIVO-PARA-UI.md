# Contrato do motor criativo para a UI — o que o Worker 3 chama

*Worker 1 (creative-runtime) → Worker 3 (UI `/criativos`). Branch
`sprint/traffic-creative-operational-closure-v1`.*

> **Estado deste documento.** Escrito no início da rodada como contrato de
> integração e mantido em sincronia com o código à medida que ele foi ficando de
> pé. A seção final ("Prova") diz quais testes cobrem cada afirmação. Se algo
> aqui divergir do código, **o código é a autoridade** — abra defeito e me
> avise, não contorne.

---

## 1. Onde o caminho mora

Um só módulo, e ele é a **extensão da bancada que já existia** — não um segundo
caminho:

```
backend/app/criativo/bancada/servico.py
```

O Worker 3 **não** deve importar `volc_ads.criativo.*` nem
`volc_ads.criativo_ponte` a partir da camada HTTP. Tudo que a tela precisa sai
das quatro funções abaixo, já em tipos JSON-nativos (`str`, `int`, `float`,
`bool`, `None`, `list`, `dict`). Não há `datetime`, `Enum`, `bytes` nem
`dataclass` no retorno.

```python
from app.criativo.bancada import servico

servico.receitas_locais()
servico.produzir_local(...)
servico.estado_da_producao(...)
servico.motores_disponiveis()      # já existia; inalterado
```

---

## 2. As quatro assinaturas

### 2.1 `receitas_locais()`

```python
def receitas_locais() -> list[dict[str, Any]]
```

Sem argumentos. Nunca levanta. Devolve as receitas que **esta máquina** consegue
produzir agora, offline, sem crédito e sem rede.

```jsonc
[
  {
    "receita_id": "display-minimo",
    "canal": "DISPLAY",
    "rotulo": "Display — o mínimo que o canal aceita",
    "motor_slug": "png-local",
    "natureza": "local",          // "producao" | "local" | "fixture" | "nao_declarada"
    "publicavel": false,          // ⚠️ ver §5
    "exigencia_fonte": "matriz-api/display.md §3 (proto ResponsiveDisplayAdInfo)",
    "exigencia_provisoria": false,
    "saidas": [
      { "slot": "imagem_marketing",          "papel": "marketing",
        "tipo": "imagem_marketing",          "largura": 1200, "altura": 628 },
      { "slot": "imagem_marketing_quadrada", "papel": "marketing_quadrada",
        "tipo": "imagem_marketing_quadrada", "largura": 1080, "altura": 1080 }
    ]
  },
  { "receita_id": "demand-gen-minimo", "canal": "DEMAND_GEN", ... }
]
```

`saidas` é derivado da régua do canal (`volc_ads/criativo/requisitos.yaml`), não
de uma lista escrita à mão na UI. Se o YAML mudar, esta lista muda junto.

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
) -> dict[str, Any]
```

Enfileira **e executa** o trabalho na bancada (despachante local, síncrono) e
devolve o **mesmo envelope** de `estado_da_producao` (§2.3).

| Parâmetro | Obrigatório | O quê |
|---|---|---|
| `receita_id` | sim | um `receita_id` de `receitas_locais()` |
| `tenant_id` | sim | dono do trabalho; entra na chave de idempotência |
| `insumo` | sim | o briefing/prompt. String vazia é recusada |
| `intencao` | não | a que campanha/tema o lote serve; default `receita_id` |
| `seed` | não | semente do motor. Mesma semente ⇒ mesmos bytes |

**Idempotência.** Duas chamadas com os mesmos cinco argumentos convergem para o
**mesmo `trabalho_id`** e não produzem de novo. Isso é da bancada
(`Encomenda.chave_de_idempotencia`), não desta camada.

**Nunca levanta por erro de entrada.** Receita desconhecida, `insumo` vazio,
motor ausente na máquina — tudo volta como envelope com `erro` preenchido e
`trabalho_id: null` (§4). Levantar obrigaria a rota a adivinhar o status HTTP a
partir do texto da exceção.

Erro de programação (assinatura errada) continua sendo `TypeError`, como deve
ser.

---

### 2.3 `estado_da_producao(...)`

```python
def estado_da_producao(trabalho_id: str, *, tenant_id: str) -> dict[str, Any] | None
```

`None` quando não existe trabalho com esse id **para esse inquilino**. `None`
significa "não existe/não é seu" — a rota traduz para 404. Não é "existe e está
vazio".

---

### 2.4 `motores_disponiveis()` (já existia)

Inalterada, exceto que `png-local` agora aparece na lista. Cada item ganhou dois
campos: `"natureza"` e `"publicavel"`.

---

## 3. O envelope — campo a campo

```jsonc
{
  "trabalho_id": "0f3c…",           // string | null (null só com "erro")
  "tenant_id": "volc",
  "receita_id": "display-minimo",
  "canal": "DISPLAY",
  "intencao": "display-minimo",
  "insumo": "banner do FGTS de setembro",
  "seed": 0,
  "chave_de_idempotencia": "9a1b…", // string | null

  "estado": "rendered",             // queued|claimed|running|validating|rendered|failed|cancelled
  "terminal": true,                 // estado ∈ {rendered, failed, cancelled}
  "tentativa": 1,
  "max_tentativas": 3,
  "criado_em": "2026-09-01T12:00:00+00:00",

  "motor": {
    "slug": "png-local",
    "versao": "1.0.0",
    "natureza": "local",
    "publicavel": false,
    "versoes": { "adaptador": "1.0.0", "zlib": "1.2.12", "algoritmo": "…" }
  },

  "falha": null,                    // ou { "codigo", "mensagem", "permanente" }
  "erro":  null,                    // ver §4

  "recibo": { … } | null,           // o Recibo da bancada, já em JSON
  "assinatura_determinista": "…" | null,

  "assets": [ … ],                  // §3.1 — [] quando nada foi produzido
  "entrega": { … } | null           // §3.2 — null quando NÃO foi tentada
}
```

### 3.1 `assets[]`

Uma entrada por artefato produzido **e medido a partir dos bytes** (não do que o
motor declarou). Ordem: a das saídas da receita.

```jsonc
{
  "identidade": "cri_9f2c1a…",      // id interno, derivado do conteúdo
  "conteudo_hash": "sha256:9f2c…",  // com o algoritmo declarado no prefixo
  "slot": "imagem_marketing",
  "papel": "marketing",             // string | null (null = tipo sem papel neste canal)
  "tipo": "imagem_marketing",
  "mime": "image/png",              // string | null
  "largura": 1200,                  // int | null  ⚠️ null = não medido, nunca 0
  "altura": 628,                    // int | null
  "bytes_totais": 4127,             // int | null
  "natureza": "local",
  "publicavel": false,
  "origem": "gerado",
  "procedencia": {
    "motor": "png-local",
    "versao_do_motor": "1.0.0",
    "insumo": "banner do FGTS de setembro",
    "insumo_hash": "3a91…",
    "pedido": "png-local-…",
    "quando": "2026-09-01T12:00:00+00:00",
    "custo_usd": null,              // ⚠️ null, nunca 0.0 — ver §5
    "nota": "…"
  },
  "recibo_asset": { … } | null      // recibo tipado do asset, quando emitido
}
```

**Sem caminho de disco.** Nenhum campo carrega `/var/folders/...` nem
`~/.volc-os/...`. Se a tela precisar exibir a peça, isso é outra fatia (rota de
bytes) e ainda não existe — não invente um caminho a partir daqui.

### 3.2 `entrega`

O resultado de atravessar a **ponte canônica**
(`volc_ads/criativo_ponte.imagens_de_display` / `imagens_de_demand_gen`) até o
contrato de canal.

```jsonc
{
  "tentada": true,
  "destino": "ensaio",              // "producao" | "ensaio"
  "ok": false,                      // há payload montável?
  "canal": "DISPLAY",
  "veredito": {
    "ok": true,                     // o lote é bom?  ⚠️ ≠ entrega.ok
    "aprovados": 2,
    "reprovados": 0,
    "provisorio": false,
    "fonte": "matriz-api/display.md §3 (proto ResponsiveDisplayAdInfo)",
    "violacoes": [
      "[aviso/gerar_mais] Q3.abaixo_do_recomendado @logo_quadrado: 0 de 1 recomendados"
    ]
  },
  "linhagem": [ { "nome", "papel", "identidade", "conteudo_hash", "motor",
                  "versao_do_motor", "insumo", "insumo_hash", "pedido",
                  "quando", "origem", "mime", "largura", "altura",
                  "bytes_totais", "custo_usd", "confirmada", … } ],
  "recusas": [ "cri_…: procedência de natureza 'local' não pode ser apresentada como produção…" ],
  "avisos":  [ "cri_…: natureza da procedência não declarada…" ],
  "naturezas": { "cri_9f2c1a…": "local" }
}
```

⚠️ **`veredito.ok` e `entrega.ok` são perguntas diferentes.** A primeira é "os
arquivos são bons"; a segunda é "há payload montável". Um lote aprovado cujos
bytes foram recusados pela ponte tem `veredito.ok = true` e `ok = false`, e o
motivo está em `recusas`. A UI tem de mostrar `recusas` — sem elas a tela diz
"aprovado" sobre uma entrega que não saiu.

---

## 4. Como a tela distingue os quatro desfechos

`ausente ≠ zero ≠ falha ≠ não aplicável`. Leia nesta ordem:

| # | Condição | O que aconteceu | O que a tela mostra |
|---|---|---|---|
| 1 | `erro != null` | O pedido nem virou trabalho (receita desconhecida, insumo vazio, motor ausente). `trabalho_id` é `null`. | O texto de `erro.mensagem`. **Não** é falha de render. |
| 2 | `estado == "failed"` | O trabalho existiu e terminou mal. `falha.codigo` diz por quê; `falha.permanente` diz se retentar adianta. | Causa explícita + botão de retomar **só se** `permanente == false`. |
| 3 | `terminal == false` | Ainda em andamento (`queued`/`claimed`/`running`/`validating`). `assets` pode estar vazio, e isso é **pendência**, não zero. | Estado em andamento. Nunca "nenhum criativo". |
| 4 | `estado == "rendered"` | Produziu. `assets` tem ao menos um item e `recibo != null`. | As peças + a etiqueta de natureza (§5). |

E dentro do desfecho 4, sobre a entrega:

| Condição | Significado |
|---|---|
| `entrega == null` | A entrega **não foi tentada** — o trabalho não chegou a `rendered`. Não é "zero imagens". |
| `entrega.ok == false` e `veredito.ok == false` | O lote não serve. Mostre `veredito.violacoes`. |
| `entrega.ok == false` e `veredito.ok == true` | O lote é bom, a ponte descartou os arquivos. Mostre `recusas` — é aqui que cai a recusa de promover fixture/local a produção. |
| `entrega.ok == true` | Há payload montável. `linhagem` tem uma entrada por imagem. |

Códigos de falha que esta fatia emite, todos com causa explícita:

| `falha.codigo` | Quando | `permanente` |
|---|---|---|
| `motor_desconhecido` | o slug pedido não está registrado nesta máquina | `true` |
| `motor_recusou` | o motor olhou o pedido e disse não (tipo não suportado, saída sem sentido) | conforme o motor |
| `gate_reprovou` | o arquivo saiu, o gate bloqueante reprovou (hash, bytes, dimensão, slot) | `true` |
| `falha_inesperada` | defeito nosso | `false` |

E os códigos que aparecem em `erro.codigo` (desfecho 1):

`receita_desconhecida` · `insumo_vazio` · `motor_indisponivel` · `tenant_vazio`

---

## 5. A regra que a UI **não pode** quebrar

> **Peça local/fixture nunca é apresentada como produção.**

Três coisas garantem isso do meu lado, e a quarta é sua:

1. `Procedencia.natureza` viaja em todo asset — `producao` | `local` | `fixture`
   | `nao_declarada`. O motor desta fatia declara `local`, sempre.
2. A ponte **recusa** asset de natureza `local`/`fixture` quando o destino é
   produção. A recusa é nomeada e aparece em `entrega.recusas`.
3. `publicavel` é derivado (`natureza == "producao"`), nunca um booleano
   gravado que pode ficar velho.
4. **Sua parte:** onde `publicavel == false`, a tela rotula a peça como ensaio.
   Nada de badge verde de "pronto para subir", nada de botão de publicar
   habilitado. O envelope te dá o dado; esconder é escolha da tela.

Corolário: **`custo_usd` é `null`, não `0.0`.** O motor local não custa dinheiro,
mas `0.0` é uma afirmação de custo apurado, e um relatório de COGS que soma esses
zeros fecha bonito e está errado. Renderize ausência como "—", não como "US$ 0,00".

---

## 6. Exemplo de rota (referência, não obrigação)

```python
@router.get("/criativos/receitas")
def receitas():
    return {"receitas": servico.receitas_locais()}

@router.post("/criativos/produzir")
def produzir(corpo: PedidoDeProducao):
    envelope = servico.produzir_local(
        receita_id=corpo.receita_id, tenant_id=corpo.tenant_id,
        insumo=corpo.insumo, intencao=corpo.intencao or "", seed=corpo.seed or 0,
    )
    if envelope["erro"] is not None:
        raise HTTPException(status_code=400, detail=envelope["erro"])
    return envelope

@router.get("/criativos/producoes/{trabalho_id}")
def producao(trabalho_id: str, tenant_id: str):
    envelope = servico.estado_da_producao(trabalho_id, tenant_id=tenant_id)
    if envelope is None:
        raise HTTPException(status_code=404, detail="trabalho não encontrado")
    return envelope
```

⚠️ `produzir_local` roda o render **no processo do request** (despachante local,
síncrono). Para as receitas desta fatia isso é da ordem de dezenas de
milissegundos — o motor é stdlib e não fala com ninguém. Não estenda esse padrão
para motor pago.

---

## 7. Prova

| Afirmação deste documento | Teste |
|---|---|
| envelope tem a forma de §3, JSON-nativo | `backend/tests/test_criativo_producao_local.py` |
| os quatro desfechos de §4 se distinguem | `backend/tests/test_criativo_producao_local.py` |
| duas produções iguais ⇒ mesmo hash e mesma identidade | `volc_ads/criativo/testes_png_local.py` |
| asset carrega hash, MIME, dimensão, procedência e recibo | `volc_ads/criativo/testes_producao.py` |
| a ponte recusa `local`/`fixture` em destino produção | `volc_ads/testes_criativo_ponte.py` |
| linhagem e recibo saem íntegros pela ponte | `volc_ads/criativo/testes_producao.py` |
