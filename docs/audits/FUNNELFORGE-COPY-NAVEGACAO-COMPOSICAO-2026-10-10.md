# FunnelForge: copy, navegação e composição (rodada de 10/10)

Base: `main` @ 73583489. Escritor único. Nada foi publicado: nenhum WordPress,
Supabase, Ads, deploy ou push. A mensagem do operador chegou cortada no item 7;
para o restante, seguimos as regras da rodada anterior.

## 1. Referências observadas

Navegação no Chromium a 390 px, só leitura, sem formulários. Seis LPs e as
internas seguidas pelo primeiro caminho, com capturas em
`producao/funil-canario-copy-20261010/referencias/`.

**O que funciona nas referências:**
- **Topo das internas.** A ordem é H1, anúncio, uma frase de orientação e
  depois uma pilha de 2 a 5 botões, todos visíveis já na primeira dobra.
- **Rótulos.** Eles dão a situação ou a pergunta do leitor: "Quem tem direito
  / Como solicitar", "Ya soy beneficiaria y quiero saber cuándo me pagan",
  "¿Cómo activar la Cédula Digital?".
- **H2 das soluções.** Cada um é uma situação do leitor: "¿Ya la tienes?…",
  "O que fazer se você ainda não foi contemplado".
- **Negrito e recirculação.** O negrito é intenso, com 13 a 157 por página, e
  os botões se repetem no fim.

**O que não serve:**
- contador inventado ("946 pessoas acessaram hoje") e selos ("100% SEGURO");
- interstitial "Escolha uma opção";
- promessa de função que o site não tem ("Consultar pelo CPF", "Quiero mi préstamo");
- todos os botões com o mesmo peso visual.

**n8n:** a sessão expirou e o editor pede login, que não fiz. Usei os trechos
lidos na rodada anterior: micro-gancho antes do botão, rótulo partindo da
dúvida do leitor e estrutura de leitura rápida.

## 2. Diagnóstico do preview anterior (390 px)

- **Navegação:** nas internas, 0 ou 1 botão perto do topo. A p4 não tinha
  nenhum, e a p7 só a saída oficial.
- **Rótulos:** comandos editoriais ("Saiba como…", "Ache o contato…",
  "Descubra…").
- **Composição:** de 2 a 6 `<strong>` por página e de 11 a 22 parágrafos para
  1 ou 2 listas; termos técnicos sem explicação.
- **p4:** o título prometia Cemig, Enel e outras distribuidoras, mas a página
  entregava só a Neoenergia e terminava sem saída.

## 3. Mudanças duráveis no motor

| Mudança | Onde | Prova |
|---|---|---|
| Navegação do topo nas internas: um único `wp:buttons` sem `<p>` (para o Ad Inserter), logo depois do 1º parágrafo. O próximo passo principal fica na cor do tema; as alternativas, em botão sólido claro (6,28:1, sem *outline*). Botões do redator antes do 1º H2 saem. A operação é idempotente e entra antes da revisão, portanto no recibo. | `steps.navegacao_do_topo`, no `step_write` V2 | `test_navegacao_*` |
| O sniper escreve a próxima pergunta ou situação do leitor que o destino resolve, com a aresta principal marcada. Comando genérico é descrito como problema, mas nenhum verbo é proibido. Palavras de função só valem quando o destino executa a função. | `ctas_do_funil.jinja`, `ctas._arestas` | `test_sniper_marca_o_passo_principal…` |
| Leitura rápida: subtítulo como pergunta ou situação do leitor; 1ª frase da seção responde, com o que decide em negrito; formato pela função; termo técnico e sigla explicados. | `reader_contract_v2.jinja`, `escrita_natural.jinja`, LP V2 | `test_redator_das_internas_sabe…` |
| Revisor com padrões `titulo_sem_resposta` e `termo_sem_explicacao`, que viram patch de naturalidade na mesma chamada | `revisao.PADROES_DE_ESCRITA`, `revisor.jinja` | `test_revisor_corrige…` |
| LP e pré-sell recebem os fatos verificados dos destinos diretos, marcados `do_destino`. Redator e revisor leem a mesma projeção, e o revisor deixa de cortar da LP uma frase verdadeira que só o destino provava. | `dossie.projecao_para_o_prompt` | `test_hub_recebe_os_fatos…` |
| **Canário:** um bloqueante corrigido por patch que embrulha o trecho em `<strong>` contava como "não resolvido" e mandava a p6 a humano | `revisao.executar_revisao` | `test_bloqueante_resolvido…` |
| **Canário:** negrito aberto num parágrafo e fechado em outro é fechado no próprio parágrafo, só no markup | `steps.fechar_inline_por_paragrafo` | `test_negrito_aberto…` |
| **Canário:** 1º parágrafo que só repete o H1 sai, salvo se isso quebrar os slots | `steps.sem_eco_do_titulo` | `test_paragrafo_que_so_repete…` |

Não foram criados vetos de palavra, pisos de tamanho nem quotas de botões ou
blocos.

## 4. Aplicação no canário

O run `runs-canario/tarifa-social-energia-eletrica-20261010-canario-copy` é uma
cópia do canário editorial; o run anterior fica intacto para comparação. O teto
de 14 chamadas foi registrado antes da primeira chamada.

1. **p4, sem chamada.** Três hints (URL e afirmação) foram conferidos na página
   da ANEEL "Fale com a sua distribuidora", já baixada no bucket e atualizada
   em 11/08/2026:
   - o caminho distribuidora → ouvidoria → ANEEL;
   - a fatura traz os telefones da distribuidora;
   - a Enel aparece separada por estado (CE, RJ, SP).

   Resultado: cobertura `ready` e a lista da ANEEL como canal oficial
   verificado. Os telefones da lista **não** viraram fatos, porque a lista
   ainda mostra "Enel Distribuição Goiás".
2. **p4, continuidade.** A próxima dúvida passou a ser a da p5 ("onde vejo o
   desconto na fatura"), com link editorial e tensão residual. O delta ficou
   registrado em `delta_de_esqueleto`.
3. **Retomada pelo pipeline.** Pelo `run_pipeline` canônico: sniper (1 chamada),
   7 redações em paralelo, revisão em lote (1) e acabamento.
4. **Retomadas localizadas:**
   - p6: mesma resposta do revisor, com o critério corrigido (0 chamadas);
   - p2: eco do H1 removido pela função do motor e 1 revisão.

| | Canário anterior | Esta rodada |
|---|---|---|
| Chamadas | 14 no run + 4 em retomadas | **10** (1 sniper + 7 redações + 2 revisões), 0 retentativas |
| Parede | 630 s | 350 s na rodada, mais uns 40 s da retomada da p2 |
| Tokens | n/d | 218 mil de entrada / 22 mil de saída |
| Faturado | US$ 0 | US$ 0 (`chatgpt_plan`, sem fallback) |
| Concorrência | 3 workers | 3 workers, pico de 3 em voo |
| Revisão | 7/7 aprovadas | 7/7 aprovadas, gate final OK |

## 5. Resultado por página (390 px)

| Pág. | Topo | Botão principal → destino | Problema restante |
|---|---|---|---|
| LP | Imagem, título curto, subtítulo com critério, valor e limite; 2 caminhos na dobra | "Quem tem direito à Tarifa Social?" → pré-sell | A introdução descreve o guia e repete o limite do portal, frase que vem da `resposta_imediata` do esqueleto |
| p2 pré-sell | Três hipóteses de acesso com os limites, depois 3 caminhos | "Como o desconto entra na conta de luz?" → p3 | Entrega ajustada pelo motor (renda por pessoa e salário-mínimo em reais sem fonte), espera aceite |
| p3 | Situação reconhecível, depois 2 caminhos | "Onde falar com a distribuidora da minha conta?" → p4 | — |
| p4 | Resposta em negrito, depois o próximo passo | "Onde vejo o desconto na fatura?" → p5 | A lista da ANEEL está em prosa no passo de ação; o canal oficial "principal" do estado ficou na ordem antiga (sem botão visível); tabela de 3 colunas rola dentro do bloco no celular |
| p5 | Resposta, depois o caminho | "O que ainda pode ser cobrado com a Tarifa Social?" → p6 | Instrução restrita à Neoenergia, que é o que está comprovado |
| p6 | Resposta, depois o caminho | "Desconto Social e Tarifa Social mudam a mesma cobrança?" → p7 | — |
| p7 | 3 parágrafos, depois a saída oficial | "Ministério de Minas e Energia: regras do Desconto Social >>>" | Terminal, sem caminho interno no topo |

O caminho principal clicado no preview vai da LP à p7 sem interrupção. O
`<strong>` passou de 2–6 para 8–16 por página. Os H2 já eram perguntas e
mudaram pouco. As ressalvas não caíram.

## 6. Validação

- **Motor:** 1756 testes passaram, 0 falharam e 0 foram pulados, com
  `FF_VISUAL_BROWSER=1`; 10 testes são novos.
- **Preview local:** auditoria visual do motor aprovada em 390 e 1440 px.
- **Chromium funcional:**
  - sem erro JS, sem rolagem lateral da página e sem link interno quebrado;
  - LP e pré-sell sem link externo;
  - calculadora com 7 casos iguais a `widgets.calculos.calcular`;
  - widgets de escolha (p3, p4, p5) e de botões (p6, p7) trocam a resposta;
  - navegação visível na primeira dobra de p2 a p6.

Não provado: tema, plugins, anúncios reais, CLS com anúncio, tráfego, CTR,
receita e ROI.

## 7. Pendências

1. **LP:** tirar da `resposta_imediata` do esqueleto a frase "não confirma
   direito individual, não cadastra pessoas e não consulta contas". O aviso do
   portal já existe uma vez no template. A decisão é do operador.
2. **Entrega ajustada da p2:** espera aceite.
3. **Delta `continuidade_p4`:** p4 → p5 entra no esqueleto aprovado, e também
   espera aceite.
4. **Ordem dos canais da p4 no roteiro:** faltou a segunda passada de
   consolidação. O motor faz as duas; o efeito visível é nulo.
5. **Ressalvas e H2:** a orientação nova não reduziu ressalvas, e os H2
   continuam presos à estrutura do esqueleto.
