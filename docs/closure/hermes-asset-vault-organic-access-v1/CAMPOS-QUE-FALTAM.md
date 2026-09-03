# O que falta para a Página existir no Cofre — lista mínima

**Missão:** `hermes-asset-vault-organic-access-v1` · **Data:** 02/09/2026
**Para:** quem tem acesso administrativo à Página e ao 1Password
**Tarefas travadas por esta lista:** P03-T02, P03-T07, P12-T02 (e, por
dependência, P03-T11 em modo real)

---

## Por que esta lista existe, e não um cadastro

A missão procurou fonte autorizada de leitura para a identidade real da Página e
**não encontrou nenhuma**: não há credencial Meta configurada nesta máquina, não
há AdsPower instalado, não há 1Password (app, CLI `op` ou MCP). Nenhum deles
poderia ser aberto sem sair do envelope autorizado — e nenhum dado foi inventado
para preencher o buraco.

> **Ferramenta pronta não é ativo cadastrado.** O caminho até o cadastro existe
> desde `033e1620` e continua funcionando; o que falta é o input humano.

## ⚠️ Nada de senha, token ou código

**Não envie senha, token, cookie, chave de API, código de recuperação nem código
de verificação — por nenhum canal.** O Cofre guarda o **endereço** do segredo
dentro do 1Password, nunca o valor. O script recusa a ficha inteira se encontrar
qualquer um deles, e a recusa **não repete o valor recusado**.

Segundo fator está fora **inclusive por referência**: uma referência terminada
em `?attribute=otp` aponta para o TOTP, e a gramática do Cofre não aceita query
string.

---

## As 30 pendências

Contadas sobre `docs/closure/asset-vault-onepassword-production-v1/FICHA-PAGINA-MODELO.json`,
aplicando a regra de `coletar_pendencias` (valor contendo `PREENCHER`,
`SUBSTITUIR`, `TODO`, `FIXME`, `XXXX`, `???`, `…`, ou casando `<template>`;
chaves `_*` e `*__onde_obter` são instrução para humano e não contam).

> ⚠️ **Procedência da contagem:** ela foi **derivada por leitura** do modelo
> versionado, e **não** medida rodando o script — `python3` não pôde ser
> executado nesta sessão (ver [`GATES.md`](GATES.md)). O número autoritativo sai
> do próprio script, e regenerá-lo é uma linha:
>
> ```bash
> python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json
> ```
>
> Enquanto sobrar campo, ele sai com código ≠ 0 e lista o caminho exato de cada
> pendência. Nenhum payload é emitido.

### `pagina` — 7 campos

| Caminho | O que é | Onde obter |
|---|---|---|
| `pagina.id_plataforma` | ID numérico da Página | Business Suite › Configurações › Informações da Página. **Só os 4 últimos dígitos** entram no Cofre (`•••-•••-1234`) |
| `pagina.nome` | nome público real | a própria Página — o repositório só tem o rótulo provisório "Página monetizada adquirida" |
| `pagina.business_portfolio_nome` | onde a Página mora | business.facebook.com › seletor de portfólio |
| `pagina.estado` | `declared` … `retired` | `declared` enquanto a propriedade não foi conferida com prova |
| `pagina.criticidade` | `low`\|`medium`\|`high`\|`critical` | sua avaliação |
| `pagina.dono_nome` | quem responde pela Página | você |
| `pagina.dono_custodia` | `declared`\|`verified`\|`unassigned` | `declared` = o dono afirmou; `verified` = alguém conferiu no painel |

Já preenchidos no modelo e **conferíveis**, não obrigatórios: `resumo`,
`capacidades`, `tags`, `proxima_acao` (vieram de `fixtures.ts`). Opcionais em
`null`: `url_publica`, `projeto`, `vertical`.

### `perfil_adspower` — 10 campos *(bloco opcional)*

`slug` · `id_referencia` · `nome` · `estado` · `criticidade` · `resumo` ·
`dono_nome` · `dono_custodia` · `capacidades[0]` · `proxima_acao`

> **Se não houver perfil AdsPower dedicado**, troque `perfil_adspower` **e**
> `credencial_perfil` por `null`. O script então emite **quatro** operações em
> vez de seis, e as pendências caem de **30 para 16**. Ele não inventa perfil.
>
> O `id_referencia` (o `user_id` da Local API) vai **inteiro** para `display_id`,
> e isso é intencional: P03-T07 exige ID de referência visível, e esse número é
> inútil sem a chave da Local API — que nunca entra no Cofre.

### `credencial_pagina` — 4 campos

`nome_logico` (ex.: `FACEBOOK_PAGE_ACESSO`) · `localizador` (`op://…`, forma 1Password sem query string) ·
`finalidade` · `owner_nome`

### `credencial_perfil` — 4 campos *(só se houver perfil)*

`nome_logico` (ex.: `ADSPOWER_API_KEY`) · `localizador` · `finalidade` · `owner_nome`

> Um perfil sem endereço de credencial é um ativo que ninguém consegue abrir, e
> o script recusa a combinação: perfil presente com `credencial_perfil: null`
> não passa.

### `verificacao` — 5 campos

`resultado` · `metodo` · `procedencia` · `evidencia` · `observado_em`

> `observado_em` é o instante ISO-8601 **com fuso** da OBSERVAÇÃO, não do
> preenchimento. Sem fuso, o instante seria lido no fuso do servidor; e o banco
> recusa data no futuro.
>
> Se a única base ainda é a sua palavra, **diga isso**: `unverified` +
> `owner_declaration` é uma resposta honesta e aceita pelo contrato. Ela é o que
> separa "achamos que a página é nossa" de "conferimos em tal dia, por tal
> método".

---

## Como entregar

```bash
# 1. gere sua cópia FORA do repositório (o ID completo não deve ser versionado)
python3 scripts/onboarding_pagina_facebook.py --modelo > ~/ficha-pagina.json

# 2. preencha tudo que estiver com PREENCHER ou <template>

# 3. valide — enquanto faltar campo, sai != 0 e lista o caminho de cada pendência
python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json

# 4. forma SQL, pronta para as funções governadas
python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json --sql
```

O script **não faz rede, não escreve no banco e não fala com a Meta nem com o
AdsPower**. Ele só transforma a ficha nos seis pedidos que o Cofre aceita — e
aplicá-los ainda depende da autorização de
[`CHECKPOINT-AUTORIZACAO.md`](CHECKPOINT-AUTORIZACAO.md).
