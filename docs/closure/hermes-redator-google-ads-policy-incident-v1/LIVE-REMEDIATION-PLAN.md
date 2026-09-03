# PLANO DE REMEDIAÇÃO AO VIVO — o que precisa mudar no site

> **Nada abaixo foi executado.** Este pacote não escreveu no WordPress, não
> alterou destino ao vivo, não republicou nada. Toda ação aqui exige autorização
> explícita do operador — ver `AUTORIZACAO-EXTERNA.md`.
>
> **Ordem obrigatória:** a evidência já está preservada (`evidence-public/`, com
> hashes em `GATE-RECEIPTS.json`), então corrigir o site agora **não** destrói
> prova. Mas a apelação deve citar o estado corrigido; por isso a remediação vem
> ANTES do envio da apelação, e nunca antes da preservação.

---

## Fase A — bloqueios, por página (o que impede `paid_destination_ready`)

### A1 · `/r/antecipacao-saque-aniversario-fgts/` — a página em pior estado

Sete bloqueios. É a única das quatro amostradas **sem nenhum bloco de identidade**.

| # | correção | código que fecha |
|---|---|---|
| 1 | Renderizar o rodapé de identidade que as outras três páginas já têm: razão social, CNPJ `42.724.548/0001-24`, links Sobre / Contato / Política de Privacidade | `IDENTIDADE_OPERADOR_AUSENTE`, `IDENTIDADE_CONTATO_AUSENTE` |
| 2 | Incluir o aviso de não-vínculo **na primeira tela**, não só no rodapé | `AVISO_NAO_OFICIAL_AUSENTE`, `AFILIACAO_GOVERNAMENTAL_IMPLICITA` |
| 3 | Remover "autorizar um banco parceiro, como o **Banco Bmg** ou o **Santander**" e "fintechs 100% digitais como a **meutudo**, ou bancos tradicionais como o **Nubank**, Banco Bmg e Santander". Reescrever sem apresentar marca de terceiro como canal | `MARCA_TERCEIRA_SEM_LASTRO` |
| 4 | Reescrever "as instituições financeiras **não realizam consultas** aos órgãos de proteção ao crédito como SPC e Serasa" e "a liberação do dinheiro costuma ocorrer **em poucos minutos**" | `ALEGACAO_DE_RESULTADO_IMPROVAVEL` |
| 5 | Acrescentar bloco de divulgação junto às cifras: valores ilustrativos, sujeitos às regras vigentes, consultar o canal oficial | `ALEGACAO_FINANCEIRA_SEM_DIVULGACAO` |
| 6 | Acrescentar a divulgação de monetização por anúncios | `DIVULGACAO_DE_MONETIZACAO_AUSENTE` (risco) |

### A2 · `/r/fgts-saque-aniversario/` — o destino da conta suspensa

| # | correção | código que fecha |
|---|---|---|
| 1 | **Desfazer os sete links `caixa.gov.br` de âncora numérica.** Citar a fonte em prosa, com âncora descritiva ("regras do FGTS no site da Caixa"), **uma vez**, e nunca envolvendo um número | `LINK_GOVERNO_COM_ANCORA_DE_VALOR` |
| 2 | Corrigir `2900.00 R$` → `R$ 2.900,00`; corrigir `40 %`/`5 %`/`50 %` → `40%`/`5%`/`50%` | `VALOR_MONETARIO_MALFORMADO` |
| 3 | Declarar ou remover `www.fabiolobo.com.br` (link de autoria) | `LINK_EXTERNO_NAO_CLASSIFICADO` |

### A3 · `/r/nova-carteira-identidade-nacional-2026/` — categoria restrita

| # | correção | código que fecha |
|---|---|---|
| 1 | Retirar todo verbo de aquisição dirigido ao leitor ("emitir a sua carteira…"). A página fica **estritamente explicativa**, encaminhando ao canal oficial sem prometer executar o serviço | `SERVICO_GOVERNAMENTAL_RESTRITO` |
| 2 | Declarar ou remover o host de terceiro | `LINK_EXTERNO_NAO_CLASSIFICADO` |

> ⚠️ **Restrição com data.** A política *Government documents and services* foi
> atualizada com efeito em **05/10/2026**: provedor autorizado passa a exigir
> que o domínio seja **linkado a partir de site oficial de governo**, e contrato
> comercial / licença / registro empresarial **não** contam como autorização.
> Enquanto não houver esse link, a decisão honesta para as rotas de documento de
> governo (`nova-carteira-identidade-nacional-2026`, `guia-pis-pasep-2026`) é
> **não anunciá-las**.

### A4 · Todas as quatro — host de adtech

Declarar `script.joinads.me` no inventário de adtech do site **e** fazer a
divulgação na página bater com o que é carregado de fato: hoje o rodapé diz
"Google Adsense" e o carregador é o JoinAds.
Fecha `SCRIPT_TERCEIRO_NAO_DECLARADO`.

---

## Fase B — superfície de experiência

| item | evidência | ação |
|---|---|---|
| Prompt de push na chegada | `ai-web-push` + Firebase, `AI_WEB_PUSH_MODAL_DELAY = 0` | atrasar o modal (ou desligá-lo nos destinos pagos) para o revisor e o visitante pago encontrarem o conteúdo primeiro |
| `AI_WEB_PUSH_WEBVIEW_META_EXIT` | observado no HTML | revisar o comportamento de saída em webview |
| Cabeçalhos de segurança | há `x-content-type-options` e `referrer-policy`; **não** há HSTS nem CSP | endurecimento recomendado, não exigido por política |

**Não** mexer em: TLS (válido, Let's Encrypt, SAN correta), conteúdo misto
(inexistente), `atob`/`fromCharCode` (atribuídos ao plugin de rotação de anúncio).

---

## Fase C — a carteira `/r/` inteira

`ROUTE-R-INVENTORY.json`: 14 destinos pagos em dois domínios.

1. **`portalmundomais.com` responde HTTP 410** (raiz e `sitemap_index.xml`), e há
   4 rotas `/r/` que só existem na evidência da conta. Enquanto o domínio estiver
   fora do ar, qualquer campanha apontando para lá é destino que não funciona.
   Ação: manter pausado; decidir entre restaurar o domínio ou remover as
   campanhas — sem criar conta nova, sem recriar variação do mesmo conteúdo.
2. **Slugs repetidos entre domínios** (`pe-de-meia-2026-guia`,
   `senai-cursos-gratuitos-2026`, `nova-carteira-identidade-nacional-2026`).
   A igualdade de conteúdo **não foi verificada** (o outro domínio está 410).
   Ação: escolher um domínio por conjunto temático. Republicar rota reprovada em
   segundo domínio é exatamente o que a política de *circumventing systems*
   descreve.
3. **Rodar o portão nos 10 destinos `/r/` de `creditoup.com.br`** antes de
   qualquer campanha voltar: `python3 scripts/auditar_landing_policy.py --ao-vivo <url>`.

---

## Fase D — no motor, para não repetir

| # | mudança | onde | fecha |
|---|---|---|---|
| 1 | Rodar o portão no **plano**, não só no corpo escrito | `funnelforge...pipeline/steps.py`, etapa de plano | a alegação que entrou pelo H1 |
| 2 | Trocar o `OU` de `checks.compliance` por exigência dos dois âncoras (`utilidade pública` **e** divulgação de monetização) | `funnelforge...validators/checks.py` | página que passa só por ter "Adsense" |
| 3 | Ligar o ponto de portão 2 | `backend/app/routers/publicacao.py` | ver `HANDOFF-PATCH-PUBLICACAO.md` |
| 4 | Ligar o ponto de portão 3 na criação/retomada de campanha | rota de tráfego (reservada) | destino pago sem recibo |
| 5 | **Gravar o hash aprovado na publicação** | recibo do portão 2 | `DERIVA_AO_VIVO`, hoje immensurável |
| 6 | Formatar moeda pt-BR na geração e barrar a forma malformada | `funnelforge...enhancers/gutenberg.py` | `VALOR_MONETARIO_MALFORMADO` |
| 7 | Gerar a âncora do CTA a partir do H1 do destino | `funnelforge...pipeline/routing.py` | `ANCORA_INCONGRUENTE_COM_DESTINO` |

Itens 1, 2, 6 e 7 tocam `funnelforge-migracao/engine/**`, que **não foi alterado
nesta entrega** — o contrato novo consome artefato do motor, e misturar
reorganização de contrato com mudança funcional ampla no mesmo lote destruiria a
capacidade de provar equivalência. São o lote seguinte.

---

## Ordem de execução recomendada

```
1. (feito) preservar evidência com hash            → evidence-public/, GATE-RECEIPTS.json
2. obter a notificação literal de suspensão        → operador, ACCOUNT-EVIDENCE.md
3. Fase A (bloqueios) + Fase B (experiência)       → WordPress, com autorização
4. reauditar: scripts/auditar_landing_policy.py --ao-vivo <url> por destino
5. gravar o hash aprovado de cada destino corrigido
6. só então: revisar e enviar a apelação           → APPEAL-DRAFT.md
7. Fase C (carteira) e Fase D (motor)
```

O passo 2 vem antes do 6 porque uma apelação que não sabe qual política foi
citada é um chute; e o passo 4 vem antes do 6 porque a apelação só pode listar
mudanças que já estão de pé.
