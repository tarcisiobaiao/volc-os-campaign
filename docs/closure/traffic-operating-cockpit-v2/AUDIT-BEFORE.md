# AUDIT-BEFORE — o estado no SHA `207e91f1`

Levantado por 12 agentes de leitura em paralelo (775 fatos com `arquivo:linha`,
138 lacunas), reconciliados numa síntese única que **adjudicou pelo código** toda
divergência entre auditorias. Read-only: nenhuma escrita, nenhuma rede, nenhum
serviço externo tocado.

## A conclusão que mudou o plano da sprint

O domínio de tráfego **não é** um template genérico à espera de skin. Ele é
maduro, e em vários pontos mais honesto que o briefing supunha:

- O contrato de capacidade por canal **já existe** em Python
  (`backend/app/trafego/contrato_canais.py`, 1707 linhas): 4 portões ×
  4 estados, bloqueadores nomeados com `codigo`, `causa`, `origem`,
  `observado_em` e `revalidacao`.
- Ele **já é servido** em `GET /api/trafego/canais` e **já tem consumidor**:
  `PainelDeCanais`, montado no Hub (`HubDeTrafegoPage.tsx:655`).
- O design system é maduro: tokens semânticos (`verified` separado de `success`),
  razões WCAG medidas por token em comentário, tema escuro completo,
  `transition-volc` no lugar de `transition-all`.

⚠️ **Um handoff anterior afirmava que "a superfície visual dos quatro canais NÃO
foi construída".** É falso no SHA da base. Adjudicado pelo código, conforme a
ordem de fontes do AGENTS.md — contrato executável vence documento.

## O que estava de fato ausente ou errado

| # | Achado | Evidência |
|---|---|---|
| 1 | O manifesto de PMax dizia ao navegador "não há construtor — o engine levanta exceção", enquanto os portões do MESMO payload diziam que o canal planeja | `plataforma.py:442-446` contra `perfil.py:297-348` (`planejador=pmax.planejar`) |
| 2 | A aba **Criar** não lia `GET /canais`. Ela lia manifesto e vocabulário — nunca o veredito | `EstudioLigado.tsx` (antes): `useCapacidades`, `useVocabularioDoInventario`, `/trava`; sem `useCanais` |
| 3 | A máquina de 13 etapas — o único lugar do produto onde provar/aprovar/criar/ativar são quatro atos separados — estava construída, testada e **importada só por testes** | `criacao/conversa.ts` + `ConversaDeCriacao.tsx` |
| 4 | Duas declarações TypeScript do MESMO objeto do servidor, já divergentes em 3 campos | `types/trafego.ts:1094` vs `lib/trafego/canais.ts:95` |
| 5 | O ÚNICO caminho de entrada da página canônica era `<a href>` — recarga de documento inteiro, refazendo todas as leituras do Hub | `LinhaDeCampanha.tsx:683-685` |
| 6 | A etapa de ativação fechava por SEQUÊNCIA ("não há campanha criada para ligar") e reabriria ao responder a criação — prometendo um degrau que não existe em canal nenhum | `conversa.ts` `travaDaEtapa` |
| 7 | O CTA chamava Display de "Começar campanha" enquanto a porta monta Search | `jornada.ts:821` + `NovaCampanhaPage.tsx:414` (`canal: 'SEARCH'` fixo) |
| 8 | A gramática do frontend repetia a mentira do PMax | `jornada.ts:566` |

Os itens 6, 7 e 8 **não** vieram desta auditoria: apareceram depois, na revisão
adversarial e ao ver os componentes montados pela primeira vez. Ficam aqui
porque o "antes" honesto os inclui.

## O ANTES visual não pôde ser capturado nas rotas reais

As quatro rotas `/trafego*` estão sob `ProtectedRoute` e exigem sessão Supabase.
Sem credencial — e entrar senha é proibido — o navegador só alcança `/login`.

Foi por isso que a bancada de fixtures foi construída ANTES do redesenho, e não
depois: ela é o que torna o "antes" e o "depois" comparáveis sem conta de
produção. Ela também cobre estados que uma conta saudável **não produz sob
demanda** — leitura falhou, portão fechado sem causa, contrato truncado.

O que a auditoria mediu sem navegador, por leitura de código:

| Superfície | Defeito | Evidência |
|---|---|---|
| Hub | docblock diz "três abas"; o componente monta cinco | `HubDeTrafegoPage.tsx:2-6, :74` vs `:574-596` |
| Hub | uma QUINTA consulta de inventário monta em TODA aba | `:449` → `useAtencao.ts:83-87` |
| Hub | "Atualizar dados" não relê o inventário que alimenta o contador de atenção, nem `useCanais` | `:465-468` |
| Hub | o contador da aba Atenção é recalculado no cliente sobre uma lista que o servidor já totaliza em `totais.atencao` | `useAtencao.ts:151`, com o comentário de `:145-147` nomeando a fonte certa e não a usando |
| Cockpit | três verdades simultâneas para a etapa "copy": trilho marca pronta em `!!escrita`, cartão exige `status==='done'`, barra lista pendente em `status!=='done'` | `NovaCampanhaPage.tsx:442`, `:652`, `:335` |
| Cockpit | elegibilidade de lançamento (`pendencias`/`podeLancar`) montada no navegador; o `bloqueado` que o Python calcula nunca chega ao fio | `:332-343`; `projecao.py` `def cockpit` |
| Estúdio | a lista de etapas é um `<ol>` não interativo; o próprio cabeçalho declara "não monta pedido, não chama /provar e não chama /subir" | `EstudioMulticanal.tsx:14-18`, `:234-256` |
