# Backlog do creative-runtime — dívida conhecida, com evidência

*Worker 1, missão "Fechamento operacional de tráfego + criativos". Nada aqui
bloqueia a fatia entregue; tudo aqui é verdadeiro hoje.*

Ordenado por quanto custa deixar como está.

---

## 1. `NAO_DECLARADA` ainda passa em destino de produção — e é a dívida central

**Onde:** `volc_ads/criativo_ponte.py`, `NATUREZAS_ACEITAS[Destino.PRODUCAO]`.

`Destino.PRODUCAO` aceita `PRODUCAO` **e** `NAO_DECLARADA`. A recusa efetiva
hoje cobre só `LOCAL` e `FIXTURE`. Está declarado no código como dívida, não
como descuido, e o motivo é que os produtores legados não declaram nada:

| Produtor | Declara natureza? |
|---|---|
| `criativo_ponte.lote_de_pasta` (pasta do operador) | não |
| `adaptadores/funnelforge_imagem.py` | não |
| `adaptadores/falso.MotorFalso` | não |
| `adaptadores/png_local.MotorLocalDePNG` | **sim** (`LOCAL`) |
| `bancada/adaptadores/png_local.MotorPngLocal` | **sim** (`LOCAL`) |
| `bancada/adaptadores/tipografico.MotorTipografico` | não |

Recusar `NAO_DECLARADA` hoje quebraria o único caminho que monta payload de
verdade (o do operador), para comprar uma garantia que a ausência não dá de
qualquer modo. O que ela ganhou foi visibilidade: cada asset sem natureza sai
nomeado em `Entrega.avisos`.

**Fechar quando:** os produtores acima declararem. Aí sai uma linha de
`NATUREZAS_ACEITAS` e o aviso vira recusa. **Risco de deixar:** um asset de
procedência desconhecida sobe sem que ninguém tenha afirmado que ele é de
produção.

---

## 2. `Linhagem` não carrega a natureza até o recibo da campanha

**Onde:** `volc_ads/campanha/brief.py::Linhagem` (fora do meu ownership).

A natureza viaja em `Entrega.naturezas` e no envelope do backend, mas **não**
dentro da `Linhagem` que entra no `ReciboAssetAprovado` e viaja até o recibo de
`subir.py`. Quem ler só o recibo da campanha, meses depois, não terá como
distinguir uma peça de ensaio de uma paga.

A recusa da ponte impede que uma peça de ensaio CHEGUE lá — então isto não é um
buraco de segurança hoje, é um buraco de arqueologia. **Fechar:** um campo
`natureza: str | None` em `Linhagem`, preenchido por `criativo_ponte.linhagem_de`.
Precisa do dono de `campanha/`.

---

## 3. Determinismo entre versões de `zlib` não é garantido, só declarado

**Onde:** `volc_ads/criativo/adaptadores/png_local.py::escrever_png_paletado`.

O deflate não é normativo sobre a saída. Duas máquinas com `zlib` diferente
podem comprimir os mesmos pixels em bytes diferentes, e o sha256 mudaria sem que
nada do pedido tivesse mudado. Mitigado — não resolvido — registrando
`zlib.ZLIB_VERSION` em `versoes()`, para que a divergência aponte para a causa.

É a mesma limitação que `MotorTipografico` tem com a versão do Pillow. Fechar de
verdade exigiria escrever deflate próprio (blocos *stored*), o que multiplicaria
o tamanho por ~700× e estouraria o teto de 150 KB do logo do Demand Gen.
**Aceito.** O teste de reprodutibilidade prova o que importa na prática: mesmo
processo, mesmo pedido, mesmos bytes.

---

## 4. `MotorTipografico` se registra numa máquina sem Pillow e falha no render

**Onde:** `backend/app/criativo/bancada/servico.py::montar` +
`bancada/adaptadores/tipografico.py`.

`montar()` protege o registro com `try/except FalhaDoMotor`, mas Pillow é
importado **dentro** de `produzir()` e de `versoes_congeladas()`. Numa máquina
sem Pillow — e ele não está em `backend/requirements.txt` — o motor entra no
registro e só falha no meio do trabalho, como `falha_inesperada`.

Não consertei: mudar a semântica de registro da bancada é mudança que merece
lote próprio, e o `png-local` já garante que a bancada produz em qualquer
máquina. **Fechar:** ou declarar Pillow em `requirements.txt`, ou fazer
`MotorTipografico.__init__` importar Pillow (falhando com `FalhaDoMotor`, que o
`montar()` já trata).

---

## 5. `MotorFalso` declara MIME e dimensão que os bytes não têm

**Onde:** `volc_ads/criativo/adaptadores/falso.py`.

Os bytes são `sha256(...) * 4`; o `ArquivoGerado` declara `mime="image/png"` e
`largura/altura`. `medir_imagem.medir()` lê `(None, None, None)` neles.

Isto é **contrato do motor falso**, não defeito: ele existe para injetar defeito
por encomenda, e declarar medida independentemente dos bytes é como ele
exercita `Defeito.SEM_MEDIDA`, `MIME_ERRADO` e `PROPORCAO_ERRADA`. O que faltava
era o registro de que ele NÃO serve ao caminho que confere bytes — e isso agora
está preso num teste
(`testes_png_local.py::test_o_motor_falso_nao_serve_para_este_caminho…`), que
falha se o falso um dia passar a produzir PNG de verdade. **Nada a fazer.**

---

## 6. Duas gramáticas de "o que produzir" convivem

`backend/app/criativo/dominio.FORMATOS` fala em slots (`1x1`, `4x5`, `9x16`,
`1.91x1`) com dimensões fixas; `volc_ads/criativo/producao.RECEITAS` fala em
canal + papel, com dimensão derivada da régua. As duas amarram no mesmo
`TipoDeAsset`, então não divergem no vocabulário — divergem no NÚMERO (o Display
mínimo sai 600×314 pela régua, e `1.91x1` é 1200×628 no `FORMATOS`).

Não unifiquei porque `FORMATOS` é comparado arquivo-contra-arquivo com
`src/types/criativos.ts` (`testes_criativo_dominio.py`), que não é meu
ownership. **Fechar:** decidir qual é a autoridade de dimensão e fazer a outra
derivar dela. Enquanto não: a produção local usa a régua, o Estúdio usa
`FORMATOS`, e as duas produzem arquivos válidos para o canal.

---

## 7. Não há rota HTTP nem rota de bytes

`produzir_local` / `estado_da_producao` existem e estão provados; **nenhuma rota
os chama** — `backend/app/routers/**` é do Worker 3, e o contrato para ele está
em `CONTRATO-CRIATIVO-PARA-UI.md`.

Separado disso, **não há como a tela exibir a peça**: `assets[]` deliberadamente
não carrega caminho de disco, e não existe rota que sirva os bytes por
`identidade`. A fatia entregue prova o caminho até o contrato de canal, não até
o olho do operador. **Fechar:** uma rota `GET /criativos/assets/{identidade}`
que leia do recibo e devolva os bytes com o `mime` medido — com a mesma checagem
de `tenant_id` que `estado_da_producao` já faz.

---

## 8. O render roda dentro do request

`DespachanteLocal` é síncrono e não durável, e `produzir_local` o usa. Isto está
guardado: a função consulta `despacho.escolher_despachante()` antes de qualquer
coisa, e em Vercel/Lambda/Cloudflare **recusa** com
`erro.codigo == "ambiente_sem_processo_longo"` sem criar trabalho.

Para o motor local (dezenas de milissegundos, stdlib, sem rede) isso é
aceitável. **Não estenda para motor pago** sem worker durável — é exatamente o
cenário que `despacho.py` documenta: teto de tempo da função, retry do cliente
virando segunda produção.

---

## 9. A paleta do `png_local` não passa por gate de contraste

`bancada/adaptadores/tipografico.py` roda `_conferir_paletas()` no import e
recusa paleta abaixo do piso AA — porque ele desenha TEXTO. O `png_local`
desenha blocos chapados e não compõe tipografia, então WCAG não se aplica à peça
que ele produz; as cinco paletas são as mesmas já conferidas do outro lado, mas
copiadas sem o gate.

**Risco:** se alguém acrescentar texto ao `png_local` sem trazer o gate junto, a
peça sairá sem contraste conferido e o gate do operário reportará `SKIPPED` —
que não é `PASS`, e é assim que se descobre. **Fechar:** só se o motor ganhar
tipografia.
