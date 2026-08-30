# SPEC — Laboratório de Templates do Estúdio Criativo VOLC

**Data:** 28/08/2026 · **Estado:** especificação; a fatia vertical implementa o nível 1.
Complementa `SPEC-ESTUDIO-CRIATIVO-VOLC.md`, que não menciona template — o Laboratório
é capacidade **nova**, não peça faltando de algo já desenhado.

## 1. O que o Laboratório é, e o que ele não é

O Estúdio de hoje produz **peça avulsa**: um briefing vira um job vira um master. O
Laboratório produz **receita reutilizável**: uma configuração de motor, formato, skin,
voz e parâmetros que sobrevive ao pedido que a originou e pode ser versionada, comparada
e aprovada como padrão da casa.

`/criativos/novo` abre o seletor de briefing. `/criativos/laboratorio` abre o workspace
de receita. **As duas rotas não podem ser confundidas na navegação** — se o operador
achar que está criando peça quando está editando receita, ele publica a receita errada.

## 2. Os três níveis

Não é um formulário com todas as variáveis. São três recortes do **mesmo** rascunho —
trocar de nível não perde estado, só muda quantos campos aparecem.

| Nível | Quem usa | O que vê |
|---|---|---|
| **Guiado** | operador de mídia | finalidade, canal, formato, skin com nome em português. Nada técnico. |
| **Avançado** | direção criativa | + gancho, duração, elementos de retenção, brand pack, voz (estilo e velocidade), legenda (idioma e densidade) |
| **Especialista** | quem depura | + contrato tipado campo a campo, diagnóstico de compatibilidade, override de gate com motivo obrigatório |

⚠️ **Especialista não é `<textarea>` de JSON cru.** É editor estruturado, rotulado, campo
a campo. JSON cru transfere para o operador o trabalho de validar, e é a forma mais rápida
de gravar receita sintaticamente válida e semanticamente errada.

## 3. Todo parâmetro declara

Regra dura, aplicada a cada campo de cada contrato abaixo:

`tipo` · `unidade` · `padrão` · `opções ou intervalo` · `compatibilidade` · `origem` ·
`proveniência` · `versão` · `custo estimado quando aplicável` · `impacto na renderização` ·
`dependências` · `validações` · `fallback` · `pode mudar depois de aprovado?`

O último é o que separa contrato de formulário. Um campo que **pode** mudar após
aprovação torna a aprovação uma opinião sobre um alvo móvel.

## 4. Contratos tipados

Persistência, resolução e execução de cada um. **Onde não há consumidor, o contrato não
existe** — a missão proíbe abstração sem consumidor, e cumpro isso marcando o que fica
de fora desta rodada.

| Contrato | Persiste em | Resolvido por | Executado por | Nesta fatia? |
|---|---|---|---|---|
| `TemplateDefinition` | `criativo_template` (v11_03) | Laboratório | — | **contrato + fixture** |
| `TemplateVersion` | `criativo_template_versao` (v11_03) | Laboratório | — | **contrato + fixture** |
| `TemplatePreset` | `criativo_template_preset` (v11_03) | Laboratório | — | contrato |
| `RenderRecipe` | derivado, não persistido até haver render | compilador | motor | **compilado e validado** |
| `Composition` | `criativo_formato` (existe) + Remotion | resolvedor | fábrica | referenciado |
| `Scene` / `Timeline` / `Layer` | `criativo_template_versao.corpo` (jsonb) | Laboratório | fábrica | contrato |
| `Hook` | idem | Laboratório | fábrica | contrato |
| `NarrativeArc` | **`criativo_skin.arco` (já existe, 15 linhas em produção)** | banco | — | **lido do banco** |
| `VoiceProfile` | **`criativo_voz` (já existe, 14 linhas)** | banco | fábrica | **lido do banco** |
| `CaptionProfile` | `criativo_perfil_de_legenda` (v11_03) | — | fábrica | **contrato apenas** |
| `AudioProfile` | `criativo_perfil_de_audio` (v11_03) | — | fábrica | contrato apenas |
| `AssetSource` | **`criativo_master_direito` (já existe)** | ledger | — | lido |
| `RightsRecord` | idem | ledger | — | lido |
| `ChannelProfile` | **`criativo_exigencia_de_canal` + `criativo_teto_combinado` (18+3 linhas)** | banco | validador | **lido do banco** |
| `QAProfile` | **`criativo_gate` (28 linhas)** | banco | gate runner | **lido do banco** |
| `ExperimentVariant` | `criativo_template_variante` (v11_03) | — | — | contrato apenas |
| `DistributionPackage` | **`criativo_pacote` (existe, vazia)** | empacotador | — | contrato apenas |

**Sete dos dezoito já têm tabela em produção.** O Laboratório não precisa de migration
para ler o parque — precisa de rota HTTP, que é o G1.

## 5. Paid e Organic: mesmo núcleo, saídas separadas

`criativo_finalidade.classe` já separa `paid` de `organic` no banco (9 finalidades
semeadas). A regra de produto:

- **O núcleo criativo é o mesmo.** Um master serve os dois.
- **Exigência, direito, aprovação e pacote são separados.** Um `criativo_pacote` é de
  uma finalidade só. Uma aprovação vale para a finalidade em que foi dada.
- ⚠️ **Entregar peça orgânica como anúncio (ou o inverso) é o defeito de negócio mais
  caro desta área** — muda obrigação de disclosure, de direito de uso e de política de
  plataforma. O gatilho `criativo_entrega_autorizada` já exige aprovação vigente, positiva
  e **do próprio pacote**; falta a trava de que a finalidade da aprovação seja a do pacote.
  **Isso vai para a v11_03 e está listado como gap, não como resolvido.**

## 6. Estados que a tela precisa distinguir sem mentir

Herdados de `Estados.tsx` e `Selo.tsx`, que já resolvem a maioria:

carregando · vazio · vazio-após-filtro · erro · **parcial** · **incompatível** (com motivo
nomeado, nunca um "✗" mudo) · **sem runtime** · **ausência ≠ zero**.

**"Sem runtime" tem lastro em dado**, não em constante do bundle:
`criativo_modo_de_producao.estado_de_prova` mapeia 1:1 em três graus —
`planejado` (nada existe), `componentes_observados` (peças provadas, sem integração),
`executado_externo` (só a fábrica roda; o VOLC O.S. lê depois).

⚠️ **Proibido mockar o catálogo no bundle para a tela não ficar vazia.** Isso criaria a
**quinta cópia** do catálogo — exatamente o defeito que a v11_02 existe para matar. Se a
rota não responder, a tela mostra erro honesto.

## 7. Acessibilidade — o que já está resolvido e o que é novo

Resolvido e a copiar, não redesenhar:
- storyboard **sem arrasto** (`Direcao.tsx`): cenas como botões, Enter/Espaço,
  `aria-expanded`/`aria-controls`. É a alternativa de ponteiro único do critério 2.5.7.
- progresso em `aria-live="polite"` (`Acompanhamento.tsx`).
- três zonas → abas em 1024px (`LeituraDeVideo.tsx`).
- `prefers-reduced-motion` já respeitado nas transições existentes.

Novo e a vigiar:
- alvos ≥24px nos controles densos (seletor de nível, chips de compatibilidade);
- se a barra de ações for fixa, `scroll-margin-bottom` no conteúdo rolável (critério
  2.4.11) — nenhuma tela do Estúdio tem barra fixa hoje, então não há precedente;
- comparação A/B **sem divisor arrastável**: seletor por botões (50/50, foco em A, foco em B).
