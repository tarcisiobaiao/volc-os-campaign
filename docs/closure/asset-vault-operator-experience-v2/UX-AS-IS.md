# UX-AS-IS — Cofre de Ativos (antes do redesign operador v2)

**Lido em:** 2026-09-03  
**Árvore:** `/private/tmp/volc-asset-vault-operator-experience-v2`  
**SHA da auditoria (pós-merge, pré-redesign):** `caf4df9e350800e6a26ce236e8e4136b4f9a4a56`  
**Pais do merge:** `207e91f1da290130e8d02b78c3ba1c8e9a761111` (`origin/volc-os-v2`) + `5f54d25cf4375c4a43c6b8b5c819f8937106090d` (candidato orgânico)  
**Checkout principal (`main`) não foi usado.**  
**localhost:8080 (PID 38779) não foi alterado nem morto.**

Hallmark · pre-emit critique desta auditoria: P5 H4 E4 S5 R4 V4

## 1. Como a evidência visual foi (e não foi) obtida

Tentativa 1: Vite isolado na porta 4179, **sem** `.env`. O bundle não hidratou (`#root` vazio). Os PNG em `evidence/as-is/` (desktop 1440×900 = 5851 bytes; mobile 414 = 2901 bytes) são **capturas falhas de tela branca**, não um empty state real. Não devem ser lidos como “o Cofre está vazio”.

Tentativa 2: Vite na porta 4180 com `VITE_SUPABASE_*` placeholder e `VITE_PAUTADOR_API_URL=http://127.0.0.1:8010`. Sem sessão ADMIN o `ProtectedRoute` manda ao login ou o `AssetVaultPage` mostra “Acesso restrito”. Capturar o inventário real em 8010 **vazaria IDs e nomes operacionais** — proibido.

Fonte primária desta auditoria: **código em `caf4df9` + Vitest hermético** (já existiam os seis estados de API). Before/after visuais comparáveis usam um **double HTTP sanitizado fora do repositório** (`/tmp/volc-cofre-capture/`), nunca `fixtures.ts` no runtime de produção.

## 2. Caminho API real (provado no cliente)

Base: `VITE_PAUTADOR_API_URL` + prefixo `/api/cofre`. Sem base, `cofreConfigurado()` é falso e **não há fetch**.

| Método | Caminho | Tela | Mutação? |
|---|---|---|---|
| GET | `/ativos` | inventário | não |
| GET | `/ativos/{id}` | inspetor | não |
| GET | `/ativos/{id}/prontidao` | `ProntidaoDeOperacao` | não |
| GET | `/ativos/{id}/prontidao-visual` | `ProntidaoVisual` | não |
| POST | `/ativos` | cadastro | sim |
| PATCH | `/ativos/{id}` | revisão (delta) | sim |
| POST | `/ativos/{id}/credencial` | referência | sim |
| POST | `/ativos/{id}/relacoes` | relação | sim |
| POST | `/ativos/{id}/verificacoes` | verificação | sim |
| POST | `/ativos/{id}/aposentadoria` | aposentar | sim |
| POST | `/ativos/{id}/reativacao` | reativar | sim |

`fixtures.ts` **não é fallback**. Falha de API ≠ lista vazia ≠ fixture. Teste existente: 503 não mostra nomes de `INITIAL_ASSETS`.

O localizador `op://` **viaja só no POST** de referência. Leituras projetam provider, nome lógico, finalidade e estado. A tela as-is **pedia o endereço completo num input** (placeholder `op://VOLC/...`) — defeito de interação/privacidade, não de backend.

## 3. Inventário de fluxos, estados e ações (as-is)

### Cabeçalho e lentes
- H1 “Cofre de Ativos”, kicker, CTA “Cadastrar ativo”.
- Quatro lentes: Inventário / Revisões / Relações / Contrato (query `?view=`).
- Inspetor ao lado no desktop; detalhe via `?ativo=`.

### Visão operacional (Pulso)
Cinco células **idênticas** em `xl:grid-cols-5`: total, verificados, pedem conferência, custódias a provar, sem referência. Números vinham do inventário real.

**Defeito de modelo:** com amostra vazia, Pulso pintava `0 / 0 / 0 / 0 / 0`. Ausência virava zero saudável. Não havia “próximo ato”, frescor nomeado, nem distinção cofre bloqueado vs autorização negada vs verificação falha.

### Inventário
- Gavetas com contagem do servidor (funciona).
- Busca e filtros (funciona).
- **Lista de linhas**, não tabela comparável; owner, verificação, relações e revisão competiam em cards/linhas densas mas sem colunas alinhadas.
- Segundo botão “Cadastrar ativo” no cabeçalho da lista (duas primárias).
- Mobile: a mesma lista esmagada; nomes duplicavam na região “Ativos encontrados” quando havia variante estreita no DOM.

### Cadastro
Um **Painel/modal-grid** com todos os campos de uma vez. Gaveta derivada do tipo (correto, testado). Sem progressão, sem “por que este campo existe” por etapa, sem rascunho.

### Credencial
Input único de localizador com placeholder `op://...` e ajuda que **escrevia o esquema na UI**. Não havia campo de senha (bom). Havia aparência de “cole o endereço secreto”.

### Detalhe
Identidade, verificação, postura, `ProntidaoDeOperacao` **e** `ProntidaoVisual` (união do merge — ambos devem existir). Aposentar/reativar **mutavam no primeiro clique**, sem consequência explícita. Botões do inspetor abaixo de 40×40.

### Estados de API já honestos
Carregando (`role=status` “Carregando o inventário”), não configurado, 401, 403, 503 (“vazio e indisponível são fatos diferentes”), vazio com sete gavetas em 0, recorte sem correspondência. Estes **não eram aparência**.

## 4. Carga cognitiva e hierarquia

1. Cinco cartões de pulso iguais — grid de métricas, não um control plane.
2. Fronteira de segurança como faixa + pill de sucesso (“Zero segredo”) competindo com o pulso.
3. Cadastro monolítico: identidade, owner, destino, credencial e relações no mesmo fôlego.
4. Duas CTAs primárias de cadastro.
5. Inspetor longo (duas prontidões) sem um “próximo ato” na visão de página.
6. Empty state pedia cadastro, mas o pulso ao mesmo tempo dizia zero em tudo.

## 5. O que funcionava de verdade vs aparência

| Superfície | Veredito |
|---|---|
| GET inventário/detalhe/prontidões | real, contra `/api/cofre` |
| Filtros, busca, lentes, gavetas | real |
| Cadastro / revisão patch / relação / verificação / referência | real, com chave de idempotência derivada |
| Revisão só manda delta | real (teste) |
| Fixture como fallback | **ausente** (teste) |
| Placeholder `op://` | aparência de onboarding 1Password; empurra o esquema para o DOM |
| Pulso 0 em Cofre vazio | defeito de modelo (número real, significado falso) |
| Aposentar no primeiro clique | ação real, interação insegura |
| Grid de 5 células | defeito visual/IA: cartões idênticos |

## 6. Defeito visual vs interação vs lacuna de backend

- **Visual:** pulso em 5 células; lista sem tabela; hierarquia de duas CTAs; pill de sucesso na fronteira.
- **Interação:** formulário único; localizador cru; aposentar sem confirmação; hit area do fechar/inspetor.
- **Backend (não inventar endpoint):** o browser nunca recebe o valor nem o localizador nas GETs; “conectado” do broker ≠ credencial válida; AdsPower real e 1Password real **não** estão nesta tela. Resolver `op://` continua no host isolado. Grafo/Mapa Vivo continua fora. Nenhum inventário de produção cadastrado.

## 7. Merge do candidato (pré-condição do redesign)

`git merge-tree --write-tree` **não** foi limpo. Conflito material em cinco caminhos. Resolução **união**, não ours/theirs:

| Path | União |
|---|---|
| `backend/app/asset_vault/rotas.py` | `prontidao-visual` **e** `prontidao` |
| `cofreApi.ts` | `prontidaoVisual()` **e** `prontidao()` |
| `AssetVaultContent.tsx` | ambos os painéis |
| `prontidao.ts` | visual permanece; operacional em `prontidaoOperacao.ts` |
| testes | `prontidao.test.ts` visual; `prontidao-operacao.test.ts` operacional |

Broker e `prontidao.py` entraram limpos. Sem cherry-pick seletivo. Sem rebase. Sem force push.
