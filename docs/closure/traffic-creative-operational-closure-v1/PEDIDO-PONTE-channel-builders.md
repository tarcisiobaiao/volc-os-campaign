# Pedido à ponte criativa — Performance Max

*Worker 2 (channel-builders) → Worker 1 (creative-runtime), dono de
`volc_ads/criativo_ponte.py`. 01/09/2026.*

> Não editei nada em `volc_ads/criativo/**` nem em `criativo_ponte.py`. Este é o
> pedido; o que dava para fazer sem ele já está feito e provado.

---

## 1. O que falta, em uma frase

`criativo_ponte` sabe emitir asset aprovado para **Display** e **Demand Gen**.
Performance Max exige um recibo com `canal="PERFORMANCE_MAX"` e com os papéis
DELE — e essa função não existe.

## 2. Por que não dá para reaproveitar o recibo de Demand Gen

Não é preciosismo de nome: os dois canais têm tabelas de asset **diferentes**.

| Papel (`AssetFieldType`) | Display | Demand Gen | **PMax** |
|---|:--:|:--:|:--:|
| `MARKETING_IMAGE` (1.91:1) | ✅ | ✅ | ✅ |
| `SQUARE_MARKETING_IMAGE` (1:1) | ✅ | ✅ | ✅ |
| `PORTRAIT_MARKETING_IMAGE` (4:5) | — | ✅ | ✅ |
| `TALL_PORTRAIT_MARKETING_IMAGE` (9:16) | — | ✅ | **não existe** |
| `LOGO` (1:1) | ✅ | — | ✅ |
| `LANDSCAPE_LOGO` (4:1) | — | — | ✅ **só aqui** |
| `SQUARE_LOGO` | ✅ | ✅ (`logo_quadrado`) | — |

Um recibo de Demand Gen carimbando um `LANDSCAPE_LOGO` estaria aprovando uma
geometria que a régua dele nunca julgou. `campanha/brief.
conferir_asset_aprovado()` já recusa isso — o `canal` virou parâmetro nesta
entrega, e há teste
(`testes_pmax.py::test_recibo_de_outro_canal_nao_vale_em_pmax`). O bloqueio é
`ASSET_RECIBO_DIVERGENTE`.

## 3. O que peço

```python
def imagens_de_pmax(entrega: Entrega, *, customer_id: str) -> ImagensPMax
```

Mesma forma de `imagens_de_demand_gen()`, com três diferenças:

1. **`canal="PERFORMANCE_MAX"`** ao emitir `_emitir_recibo_asset_aprovado`;
2. os papéis do tipo `volc_ads.campanha.brief.ImagensPMax` —
   `marketing`, `marketing_quadrada`, `marketing_retrato`, `logo`,
   `logo_paisagem` (a ordem canônica está em `brief.PAPEIS_DE_ASSET_PMAX`);
3. `videos_youtube` é `list[str]` de resource name — vídeo do YouTube não tem
   bytes para reconferir, e é a única exceção declarada do canal.

`ImagensPMax` **não aceita `str` solto** nos papéis de imagem, diferente de
Display: PMax é o único canal com tabela oficial completa de proporção, dimensão
mínima e peso (5120 KB) por papel, e sem os bytes nada disso é reconferível
antes do `validate_only`. O builder recusa com `ASSET_SEM_RECIBO`.

## 4. A régua de geometria — o que peço que NÃO seja inventado aqui

Os mínimos por papel já existem, medidos e testados, em
`volc_ads/observabilidade_pmax/coverage.py::PMAX_FIELD_REQUIREMENTS`, e
`campanha/pmax.py` os importa em vez de redeclarar. Se `criativo/requisitos.yaml`
precisar de uma entrada de PMax, ela deve **apontar para a mesma fonte**, não
copiar os números. Duas tabelas dos mesmos mínimos divergem no primeiro ajuste,
e a divergência aparece como "o Estúdio aprovou o que o builder recusa".

Proporções e dimensões mínimas oficiais estão em
`docs/growth-engine/matriz-api/performance-max.md` §4 (`[alta]`, ref `[X8]`):

| Papel | Proporção | Recomendada | Mínima |
|---|---|---|---|
| `MARKETING_IMAGE` | 1.91:1 | 1200×628 | 600×314 |
| `SQUARE_MARKETING_IMAGE` | 1:1 | 1200×1200 | 300×300 |
| `PORTRAIT_MARKETING_IMAGE` | 4:5 | 960×1200 | 480×600 |
| `LOGO` | 1:1 | 1200×1200 | 128×128 |
| `LANDSCAPE_LOGO` | 4:1 | 1200×300 | 512×128 |

Peso máximo: **5120 KB** para todos.

## 5. Uma regra que a API me ensinou hoje, e que vale para a ponte inteira

`validate_only` real na conta 547-809-6539 recusou o mutate de Display com

```
asset_error.DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE
  @mutate_operations[7].asset_operation.create.name
  "Duplicate assets across mutates cannot have different asset level fields."
```

porque dois assets tinham os **mesmos bytes** em papéis diferentes e `name`
distinto. O Google identifica asset pelo CONTEÚDO.

Se a ponte puder emitir o mesmo arquivo em dois papéis (a mesma arte servindo de
quadrada e de logo, por exemplo), o payload é recusado inteiro. Display agora
barra isso localmente (`2b6392f`), mas seria melhor a ponte não produzir o lote.
Detalhes em `verificacao/VALIDATE-ONLY-CANAIS.md` §1.1.

## 6. Enquanto isso

Nada está bloqueado do meu lado. `campanha/pmax.py` está completo e provado
offline com recibos emitidos pela mesma fábrica privada que a ponte usa
(`brief._emitir_recibo_asset_aprovado`), e PMax não está no executor nesta
rodada de qualquer forma. O pedido é sobre o **caminho de produção**, para
quando o canal for habilitado.
