# Matriz: legado × schema × runtime × frontend

**Data:** 28/08/2026 · Produzida por cinco investigações de ownership disjunto.
Cada linha foi confirmada em pelo menos duas camadas. O que não foi confirmado
está marcado, não omitido.

## Como ler

- **Legado** = `motor-imagem`, `motor-video`, `volc-factory` (fora deste repositório)
- **Schema** = as 21 tabelas `criativo_*` **aplicadas em produção** em 28/08/2026
- **Runtime** = o backend Python que executa
- **Frontend** = as 9 páginas em `src/pages/criativos/`

## 1. Capacidades de imagem

| Capacidade | Legado | Schema | Runtime | Frontend |
|---|---|---|---|---|
| `full_llm` | Aprova/Positivo Ad Studio | `criativo_modo_de_producao` `implementado_no_volc` | **`gemini_imagem.py`** ✅ | oferecido |
| **LLM com referência** | **pronto** (`dace/image_providers/gemini.py:160`, `reference_images_b64`) | linha de catálogo | **não portado** | desabilitado com motivo |
| `typography_only` | **pronto** (`prensa/api.py::renderiza`) | `executado_externo`, 26 saídas | ausente | desabilitado |
| `deterministic_graphics` | **pronto** (`prensa-poc/graficos.py`, 5 tipos) | `executado_externo`, 13 saídas | ausente | desabilitado |
| `prensa_hybrid_llm_asset` | prova renderizada | `executado_externo` | ausente | desabilitado |
| `photo_preserved` | Positivo (`plan_split`, `PhotoAnalyzer`) | `componentes_observados` | ausente | desabilitado |
| adaptação responsiva | re-layout por variante na PRENSA | `criativo_formato` | **mais pobre**: `enquadramento.py` faz cover-crop de 1 imagem | — |

**Leitura:** o modo mais barato de destravar é **LLM com referência** — está pronto no
legado e não foi portado. Os quatro da PRENSA exigem trazer um motor de composição inteiro.

## 2. Capacidades de vídeo

| Eixo | Legado | Schema | Runtime | Frontend |
|---|---|---|---|---|
| composições | **15 registradas**, 17 formatos | — | — | — |
| narrativa (arco, beats, CTA) | contrato completo | `criativo_skin.arco` (15 skins) | leitura observada | `Direcao.tsx` mostra |
| gancho de 3 s / `retentionBeats` | existe e é medido no QA | **sem coluna** | **não lido** | não mostra |
| voz | 9 vozes, estilo, `atempo` 1.12 | `criativo_voz` (14) | leitura parcial | mostra id |
| **voz: pitch, apresentação, hash da geração** | **não existe no legado** | sem coluna | — | — |
| **voz: provider e modelo** | existe em runtime | sem coluna | **`None` por design** — a fábrica não grava a escolha no build | — |
| **legendas** | contrato rico: karaokê, stroke, safe area, `hideDuring`, destaque | **conceito inexistente** | — | — |
| áudio: LUFS −14, true peak −0,8 | número exato | **sem coluna numérica** | vira PASS/FAIL | selo |
| render: Remotion | **4.0.479** medido | sem coluna | — | — |
| custo | ~US$ 0,24–0,40 por vídeo | `criativo_job.custo_*` | **`None` por design** (não gastamos) | — |
| QA técnico | **35 checks** | `criativo_gate` (28) | agregado por pior severidade | `SeloDeGate` |
| QA visual (VLM) | 10 checks/quadro | idem | idem | idem |
| direitos/ledger | 7 fontes com licença | `criativo_master_direito` | **lido** ✅ | `Inspecao.tsx` |

**Leitura:** legenda e loudness numérico são as duas maiores lacunas de representação.
Voz tem lacuna **do lado do legado** (pitch e hash não existem lá) — não adianta criar
coluna para um dado que ninguém produz.

## 3. Gaps confirmados

| # | Gap | Evidência | Gravidade |
|---|---|---|---|
| G1 | **O parque não tem API.** 11 tabelas em produção, zero rotas HTTP | `criativosApi.ts` expõe 6 rotas, nenhuma de motor/modo/skin/voz/gate | **bloqueia o Laboratório** |
| G2 | **O executor lê `dominio.py`, não o banco.** 7 formatos no banco, 4 em memória | `criativos.py:202-218` itera `dominio.FORMATOS` | alta |
| G3 | **`motor_id`/`modo_id`/`finalidade_id` nunca escritos.** Zero referência em Python | `execucao.py:178-192` grava texto livre | alta |
| G4 | **Backend é serverless + execução fire-and-forget.** `asyncio.create_task` numa função Vercel | `backend/vercel.json`, `execucao.py:253-262` | **estrutural** |
| G5 | **Sem retomada de job.** A reconciliação de subida existe só para o "redator" | `main.py:72-116` | alta |
| G6 | **Replay curativo não dispara.** `if criado: disparar(...)` | `routers/criativos.py:359-364` | média |
| G7 | **Sem isolamento por dono.** `dono_id` é gravado e nunca lido como filtro | `persistencia.py:289-299` | **alta** |
| G8 | **Storage local em disco serverless.** `armazenamento_padrao()` fixo em `ArmazenamentoLocal` | `armazenamento.py:433-442` | alta |
| G9 | **13 de 23 FKs sem índice** | medido em produção hoje | média |
| G10 | **Teste de catálogo frouxo:** `assert "altura: 1350" in ts`, substring solta | `test_criativo_estudio.py` | média |
| G11 | **PRENSA e Estúdio usam canvas diferentes para o mesmo slot.** `4x5` = 1080×1350 aqui, 1088×1360 lá; `1x1` = 1080×1080 aqui, 1200×1200 no PMax real | manifesto vs `dominio.py` | média |
| G12 | **`volc_ads/criativo_ponte.py` sem consumidor HTTP** e `ProvarEntrada` sem campo de imagem | `routers/trafego.py:1216-1240` | média |
| G13 | **Display sem `validate_only` contra conta real** | `campanha/display.py:48-57` | média |
| G14 | **Quarto gate de pixel `text_present` fora do seed**, mais `gate_composicao`, `gate_traco`, `guard_cfm` | `dace/godmode_render/pixel_gates.py:119` | baixa |
| G15 | **SSE: falha de banco parece fim normal.** Backend distingue (`estado: "desconhecido"`); o front descarta o argumento | `JobPage.tsx:60` | média |

## 4. O que a missão pediu e não existe em lugar nenhum

- **Google Omni:** existe no vídeo (`SRC:omni`), **zero ocorrência** no `motor-imagem`.
- **Kie:** **zero ocorrência** em qualquer camada investigada. Não inventei entrada de catálogo.
- **Postiz e orgânico (TikTok, Pinterest, YouTube):** nenhuma integração, nenhuma tabela,
  nenhuma exigência de canal semeada. `criativo_finalidade` tem a classe que separa
  `paid` de `organic`, e é só isso que existe hoje.

## 5. Veredito sobre conflito estrutural

A Fase A **encontrou um conflito estrutural**, e ele é o G4: o modelo de execução
(fire-and-forget num processo serverless) é incompatível com produção durável de mídia.

**Isso não bloqueia a Fase B**, porque a fatia vertical pedida — catálogo → template →
compilação → validação → preview → render local → recibo — **não depende do caminho de
execução em produção**. A missão inclusive exige "render local/teste quando seguro" e
"nenhuma publicação".

O que o conflito **proíbe** é o contrário: prometer que o Laboratório produz em produção.
Ele não produz, e a fatia precisa dizer isso com dado do servidor, não com silêncio.
