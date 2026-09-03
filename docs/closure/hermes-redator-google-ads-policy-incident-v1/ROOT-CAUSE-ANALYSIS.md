# ROOT CAUSE ANALYSIS — suspensão Google Ads e os destinos `/r/*`

Data da análise: **2026-09-03**
Fontes: evidência preservada em `evidence-public/`, `account-evidence-sanitized.json`,
`ROUTE-R-INVENTORY.json`, `GATE-RECEIPTS.json`, `GOOGLE-POLICY-MATRIX.json`,
artefatos históricos em `funnelforge-migracao/referencia/**`.

> **Limite desta análise, dito antes de qualquer conclusão.**
> O texto literal da notificação de suspensão (in-account + e-mail) **não foi lido**.
> Nada aqui afirma a causa confirmada da suspensão. O que está abaixo é o que a
> evidência disponível sustenta, e o que ela explicitamente não sustenta.

---

## 1 · O que está provado sobre a conta

Da leitura read-only sanitizada (`account-evidence-sanitized.json`), sem ID cru:

| fato | valor |
|---|---|
| contas acessíveis | 13 |
| contas com permissão de leitura | 3 (`CUST_006`, `CUST_010`, `CUST_013`) |
| **`CUST_013` — `customer.status`** | **`SUSPENDED`** |
| `CUST_010` — `customer.status` | `ENABLED` |
| `CUST_005` | `CUSTOMER_NOT_ENABLED_OR_DEACTIVATED` |
| anúncios de Busca apontando para `creditoup.com.br` ou `/r/` | 14 |
| status de política no nível do ANÚNCIO | 11 `APPROVED/REVIEWED`, 2 `APPROVED_LIMITED`, 1 `UNKNOWN/REVIEW_IN_PROGRESS` |

Duas leituras importam mais que as outras:

1. **A suspensão é de CONTA, não de anúncio.** `CUST_013` está `SUSPENDED` enquanto
   todos os seus anúncios estão `APPROVED`/`REVIEWED`. Isso **refuta** a hipótese
   de que o texto dos anúncios foi reprovado; o gatilho está no nível da conta
   ou do destino.
2. **`CUST_013` é exatamente a conta que anunciava `/r/fgts-saque-aniversario/`** —
   a URL preservada nesta apuração.

E o único sinal literal de política que a API entrega: os anúncios que apontam
para `portalmundomais.com/r/nova-carteira-identidade-nacional-2026` estão
`APPROVED_LIMITED`. Documento de identidade nacional está na lista de escopo da
política *Government documents and services*.

**O que NÃO foi obtido:** a classificação literal ("phishing", "misrepresentation",
"circumventing systems" ou outra). A API do Google Ads não expõe o motivo da
suspensão em `customer.status`; ele vive na notificação in-account e no e-mail.
Ver `ACCOUNT-EVIDENCE.md` para o pedido de evidência ao operador.

---

## 2 · O que está provado sobre o destino

Quatro destinos `/r/` foram preservados e passados pelo portão
(`GATE-RECEIPTS.json`, versão de política `df252bc25e636d78`). **Os cinco recibos
saíram `blocked`; nenhum `paid_destination_ready`.**

### 2.1 O achado mais forte — `/r/fgts-saque-aniversario/`

Sete links inline para `https://www.caixa.gov.br/` cuja **âncora é só um valor**:

```html
multa rescisória de <a href="https://www.caixa.gov.br/"><strong>40 %</strong></a>
prazo padrão ... é de <a href="https://www.caixa.gov.br/"><strong>90 dias</strong></a>
alíquota de <a href="https://www.caixa.gov.br/"><strong>5 %</strong></a>
             a <a href="https://www.caixa.gov.br/"><strong>50 %</strong></a>
parcela fixa de até <a href="https://www.caixa.gov.br/"><strong>2900.00 R$</strong></a>
contratação de até <a href="https://www.caixa.gov.br/"><strong>5 saques anuais</strong></a>
```

Para quem lê, cada número parece vir da Caixa. A página não é da Caixa. É a
forma ESTRUTURAL — não verbal — de sugerir vínculo, e é o que a política de
*Unacceptable business practices* descreve literalmente: *"Make it seem like
you're affiliated with another brand, organization or government entity when
you're not."*

O `2900.00 R$` agrava: valor fora do formato pt-BR, vazamento de máquina,
apresentado como cifra oficial dentro de um link para o banco público.

### 2.2 O destino em pior estado — `/r/antecipacao-saque-aniversario-fgts/`

Ainda no ar em 2026-09-03, com sete bloqueios:

- **19 menções** a órgão público (Caixa, Caixa Econômica Federal, Receita Federal, FGTS)
  e **nenhum aviso de não-vínculo**;
- **nenhuma identidade de operador**: sem CNPJ, sem "sobre", sem contato, sem privacidade
  — as outras três páginas amostradas têm todos;
- **"autorizar um banco parceiro, como o Banco Bmg ou o Santander"** — marcas de
  terceiros apresentadas como canal, sem lastro;
- **"as instituições financeiras não realizam consultas aos órgãos de proteção ao
  crédito como SPC e Serasa"** e **"a liberação do dinheiro costuma ocorrer em
  poucos minutos"** — promessa de resultado que a página não controla;
- 32 ocorrências de alegação financeira sem bloco de divulgação.

### 2.3 A carteira `/r/` inteira

`ROUTE-R-INVENTORY.json`: 14 rotas de destino pago em dois domínios. O tema é
concentrado em **benefício público + crédito regulado**: FGTS, PIS/PASEP,
Pé-de-Meia, SENAI, Carteira de Identidade Nacional, consignado INSS, Serasa
limpa nome, empréstimo para negativado. É a interseção exata de duas áreas de
política sensível do Google.

---

## 3 · O que a evidência REFUTA

Nenhum destes é suposição: cada linha foi medida.

| tese | veredito | evidência |
|---|---|---|
| Cloaking (conteúdo diferente para o Google) | **refutado** | Googlebot e usuário devolveram HTML **byte a byte idêntico** (`sha256 7c674d1d7daf…`, 174 243 bytes), em duas leituras separadas em 2026-09-03 |
| Redirecionamento / abuso de click tracker | **refutado** | zero saltos de redirecionamento na leitura ao vivo |
| Conteúdo misto / destino inseguro | **refutado** | as 12 ocorrências de `http://` são todas o namespace SVG do w3.org; TLS 1.3 válido (Let's Encrypt, SAN correta) |
| Script ofuscado / malicioso | **refutado como malícia** | `String.fromCharCode` e 8 `atob(` pertencem ao plugin de rotação de anúncio (namespace `ai_*`), decodificando os próprios `data-info`/`data-shares`/`data-time`. Nenhuma exfiltração observada |
| Phishing no sentido literal da política | **não sustentado pelo destino** | **nenhum campo de dado pessoal** em nenhum dos quatro destinos; o único formulário é a busca do WordPress (`<input name="s">`). Sem senha, sem cartão, sem CPF, sem login |
| Texto do anúncio reprovado | **refutado** | 11 de 14 anúncios `APPROVED/REVIEWED`; a suspensão é de conta |

---

## 4 · A hipótese Caixa, analisada separadamente

**Enunciado avaliado:** *a suspensão foi causada pelos destinos `/r/` se
apresentarem de forma que implica vínculo com a Caixa Econômica Federal / o
governo brasileiro, acionando enforcement sob Misrepresentation / Unacceptable
business practices.*

**A favor**
1. Sete links `caixa.gov.br` com âncora de valor na URL exata que a conta
   suspensa anunciava.
2. `/r/antecipacao-saque-aniversario-fgts/` com 19 menções a órgão público e zero
   aviso de não-vínculo.
3. Carteira `/r/` concentrada em benefício público e documento de governo.
4. `APPROVED_LIMITED` nos anúncios de documento de identidade — sinal literal de
   restrição do Google nessa categoria.
5. Artefato histórico com H1 **"Saque-Aniversário FGTS Liberado pelo Governo"** e
   corpo "com base nas **instruções oficiais** da Caixa Econômica Federal (CAIXA)".
6. Correspondência textual direta com a cláusula publicada de afiliação
   governamental.

**Contra**
1. A assinatura de phishing que a própria FAQ do Google descreve — coletar dado
   pessoal fingindo ser entidade confiável — **não existe** no destino.
2. A URL da conta suspensa **carrega** CNPJ, aviso de não-vínculo e divulgação de
   AdSense no rodapé.
3. Sem cloaking, sem redirecionamento, sem conteúdo misto.

**Não obtido**
1. A classificação literal da suspensão.
2. Qual snapshot o Google revisou (nenhum hash aprovado foi gravado na
   publicação — `DERIVA_AO_VIVO` é hoje **immensurável**, e essa lacuna é ela
   própria um achado).
3. Histórico de enforcement anterior da conta.

### Veredito

```
HYPOTHESIS_PARTIALLY_SUPPORTED
```

O padrão de vínculo governamental implícito **existe, é verificável e mapeia
para uma cláusula nomeada da política** — nas páginas exatas que a conta
suspensa anunciava. Mas a assinatura literal de phishing **não está no destino**,
e sem a notificação de suspensão não há como afirmar qual política foi citada.
A hipótese explica um risco real e presente; ela **não** está provada como a
causa.

---

## 5 · A causa raiz de ENGENHARIA (esta, sim, está provada)

Independente de qual política o Google citou, o motor tinha um buraco de
contrato, e ele é demonstrável:

> **O motor nunca soube a diferença entre uma página editorial e um destino que
> recebe clique comprado.**

Os papéis do motor (`LP`/`PRESELL`/`SOLUTION` em `funnelforge.domain.models`)
descrevem **posição no funil**, não **exposição a política de anúncio**. Disso
decorrem quatro defeitos concretos, cada um medido:

1. **A alegação entrou pelo PLANO, antes do portão de conteúdo.**
   `calm_utility` bane "liberado pelo governo" no CORPO; o H1 do plano histórico
   é literalmente *"Saque-Aniversário FGTS Liberado pelo Governo"*. O portão
   olhava depois do ponto em que o defeito nasceu.
   Prova: `backend/tests/test_landing_policy_regressao_fgts.py::test_o_plano_historico_real_carrega_a_alegacao_que_o_portao_barra`.

2. **O portão de compliance aceitava um de dois âncoras, por OU.**
   `checks.compliance` aprova se o texto contém `"adsense"` **ou**
   `"utilidade pública"`. Uma página com "Adsense" no rodapé passa sem nenhum
   aviso de não-vínculo — que é exatamente o estado de
   `/r/antecipacao-saque-aniversario-fgts/`.

3. **Nada media o destino DEPOIS de publicado.** Sem hash aprovado gravado, sem
   comparação rastreador/usuário, sem cadeia de redirecionamento. O sistema não
   tinha como saber se a página no ar ainda era a aprovada.

4. **Nada ligava a URL do anúncio ao estado da página.** Uma campanha podia
   apontar para qualquer `/r/`, em qualquer estado, sem portão nenhum.

O que este pacote entrega corrige (1), (3) e (4) e cria o caminho para (2) — ver
`ENGINE-CHANGES.md` e `GATES.md`.
