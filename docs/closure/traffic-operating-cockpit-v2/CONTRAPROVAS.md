# CONTRAPROVAS — o que cada prova impede de voltar

Escritas contra defeitos MEDIDOS, não contra a implementação. Onde uma prova
poderia passar de forma vacuamente verdadeira, isso está dito e corrigido.

## Backend — `backend/tests/test_trafego_plataforma.py`

| Prova | Impede |
|---|---|
| `test_o_manifesto_nao_nega_construtor_de_canal_que_planeja` | Lê por **AST** quais canais têm `planejador` em `volc_ads/campanha/perfil.py` e falha se o manifesto desses canais afirmar ausência de código ("não há construtor", "levanta exceção"). AST e não `import`, porque `test_o_manifesto_nao_importa_o_engine` proíbe o manifesto de importar `volc_ads` — uma prova que precisasse do import afrouxaria o limite que deveria defender. |
| `test_pmax_declara_a_retencao_como_decisao_e_nao_como_falta` | Trocar um texto falso por um vago. Exige que a frase nomeie o **executor** e separe *criar* de *provar por validate_only*. |

⚠️ `test_recusa_de_canal_sem_construtor_diz_o_que_existe` exigia a palavra
"exceção" na recusa de PMax — **fixava a afirmação falsa**. Um teste que fixa a
redação de um erro passa a defender o erro. Passa a exigir que a recusa nomeie o
impedimento, que é a propriedade que sua própria docstring dizia testar.

## Frontend — `src/lib/trafego/__tests__/contrato-unico.test.ts` (7 casos)

Leem a **fonte**, não o tipo: uma prova de atribuição passaria mesmo com duas
declarações divergentes, porque provaria que UMA delas aceita o objeto.

- `canais.ts` não redeclara `ManifestoDoCanal` como interface; ele é alias.
- `canais.ts` importa o tipo canônico.
- `sabe_provar` não voltou a ser opcional (o Python o emite em toda resposta).
- Os dois vocabulários de portão continuam separados: 4 estados de canal,
  5 de mensuração, e `PRONTO` não é `PERMITIDO`.
- Nenhum `<a href>` em `src/components/trafego` ou `src/pages/trafego` aponta
  para `/trafego/campanhas/`, `/dashboard/campaign/`, `/trafego/nova/` ou
  `/trafego?aba=` — rota interna atrás de âncora recarrega o documento.
- A linha do inventário navega com `<Link to=…>` nas duas rotas.

## Frontend — `jornada-do-canal.test.tsx` (19 casos)

| Prova | Impede |
|---|---|
| INDETERMINADO é âmbar, nunca vermelho | Pintar ignorância de recusa. As duas pedem atos opostos. |
| Portão **ausente** não vira portão fechado | Afirmar um veredito que ninguém deu quando o contrato vem truncado. |
| BLOQUEADO **sem** bloqueador declara a lacuna | Ler lista vazia como permissão. |
| A causa aparece como o servidor a escreveu | A tela reescrever a regra do servidor. |
| **A ativação fecha pela causa do servidor** | O achado que bloqueava o aceite: a etapa fechava por sequência e reabriria ao responder a criação. |
| **Nem respondendo a criação a ativação abre** | Prova direta na máquina, com `respostas.criacao` preenchido. |
| **Sem portão lido, a regra local não abre a ativação** | Ausência de leitura virar permissão. |
| A criação fecha pela causa do servidor sob `trava = null | false | true` | A tela antecipar um motivo local diferente do que a escada mostra. |
| Falha COM leitura anterior preserva o veredito | "Conhecido, porém velho" colapsar em "não sei nada". |
| O aviso de releitura não muda nenhum estado | O aviso virar veredito novo. Compara os quatro estados com e sem falha. |
| Causa repetida é dita uma vez; causas diferentes voltam linha a linha | 13 parágrafos idênticos empurrando o nome da etapa para fora da tela. |

### Duas provas que passavam de forma vacuamente verdadeira

Apontadas pela revisão adversarial e **confirmadas**: os dois casos de "nenhum
ato falso" percorriam `screen.queryAllByRole('button')` sobre uma coleção
**vazia**. O laço não executava uma única asserção, e um botão "Confirmar" que
disparasse `/subir` passaria pela regex de texto.

Agora afirmam o estado da coleção primeiro (`expect(interativos.length).toBe(0)`,
incluindo `link`, `input`, `select`, `textarea` e `[onclick]`) e provam por
**estrutura**: o módulo não importa `pautadorApi`, não chama `fetch(` e não usa
`useMutation`. Um botão renomeado passa por qualquer regex de texto; um `import`
não passa.

## Frontend — `bancada.test.tsx`

| Prova | Impede |
|---|---|
| Display diz "Preparar por Search", nunca "Começar campanha" | O convite a atravessar uma porta que monta OUTRO canal. |
| Só Search é convidado a "Começar campanha" | O mesmo, canal a canal. |

⚠️ O caso anterior fixava `'Começar campanha'` para Display — **fixava a promessa
falsa**.

## Frontend — `bancada-fora-de-producao.test.ts` (4 casos)

Rápidas (rodam sempre): a rota só existe sob `import.meta.env.DEV`; a entrada é
preguiçosa; nada fora de `src/pages/qa` importa a bancada.

Cara (sob `VOLC_PROVA_DE_BUNDLE=1`): roda `vite build` de verdade e varre a saída
inteira procurando o marcador.

⚠️ **A prova cara achou o que a barata não achava.** A de fonte passava; o build
emitia `assets/BancadaVisual-*.js` com as fixtures dentro. O Rollup monta o grafo
a partir de cada `import()` **antes** da eliminação de código morto: guardar a
rota elimina o ramo, guardar o `React.lazy` elimina a chamada, e nenhum dos dois
elimina o chunk.

⚠️ **E ela ficava skipped.** `describe.runIf` sem ninguém ligando a variável deixa
a suíte verde com a prova crítica pulada.
`scripts/gate_bancada_fora_do_bundle.py` liga a variável, exige que o caso tenha
RODADO (skipped é falha) e falha se o nome sumir.

**O gate foi provado ao contrário**: com o alias de produção desligado ele acusa
`assets/BancadaVisual-*.js` e sai 1; religado, sai 0.

## Cobertura contra a lista de 26 contraprovas exigidas

| # | Exigência | Estado |
|---|---|---|
| 1 | frontend não inventa zero para dado ausente | herdado (11 estados de inventário) + os casos de "não veio" |
| 4 | canal sem criação não exibe lançamento funcional | **coberto** (CTA por canal) |
| 5 | Demand Gen não promete criação | **coberto** (portão + manifesto) |
| 7 | manifest não diverge entre backend e frontend | **coberto** (AST + fonte) |
| 8 | bloqueio traz razão e próximo ato | **coberto** (causa + origem→a quem pedir + revalidação) |
| 10 | ação bloqueada faz zero rede | **coberto** (prova estrutural, sem `pautadorApi`/`fetch`/`useMutation`) |
| 19 | botão final diferencia provar de executar | **coberto** (5 portões da conversa, separados) |
| 23 | ativação não é oferecida | **coberto**, três provas |
| 24 | layouts em 375/768/1440/1920 | **coberto**, 104 capturas, 0 overflow |
| 25 | nenhuma credencial no bundle | **coberto** (varredura + `seguranca-bundle` herdado) |
| 26 | nenhuma chamada Google real | **coberto** (ambiente fail-closed, `engine=mock`) |

**Não cobertas nesta sprint** — declaradas em `REMAINING-RISKS.md`, não
silenciadas: 2, 3, 6, 9, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22. Elas
dependem do cockpit de lançamento e da tela canônica, que esta sprint não
reescreveu.
