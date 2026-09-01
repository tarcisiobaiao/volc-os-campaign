# Pedido ao operador — dados da página Facebook monetizada

**Para:** quem tem acesso administrativo à Página e ao 1Password
**Por quê:** o VOLC O.S. não sabe nada sobre essa Página. A única linha que fala
dela (`src/features/asset-vault/fixtures.ts:11-44`) traz `external: {}` — sem ID,
sem URL, sem Business Portfolio, sem o nome verdadeiro — e a única evidência é a
declaração do dono de **26/08/2026**. Enquanto esses campos não vierem de você,
não há como cadastrar a Página (P03-T02 / P12-T02) sem inventar dado, e dado
inventado no Cofre é pior do que Cofre vazio.

## ⚠️ Nada de senha, token ou código

**Não envie senha, token, cookie, chave de API, código de recuperação nem código
de verificação — por nenhum canal.** O Cofre guarda o **endereço** do segredo
dentro do 1Password, nunca o valor. O script recusa a ficha inteira se encontrar
qualquer um deles, e a recusa não repete o valor recusado.

Segundo fator também está fora, **inclusive por referência**: uma referência do
1Password terminada em `?attribute=otp` aponta para o TOTP, e a gramática do
Cofre não aceita query string.

## O que precisamos

| O que | Por que | Onde obter | Obrigatório |
|---|---|---|---|
| **ID numérico da Página** | Identifica a linha certa. Só os **4 últimos dígitos** entram no Cofre, na forma `•••-•••-1234`; o número inteiro não vai para payload nenhum. | Meta Business Suite › Configurações › Informações da Página › ID da Página. Ou: Página › Sobre › Transparência da Página | Sim |
| **Nome público da Página** | Hoje o repositório tem só o rótulo provisório "Página monetizada adquirida". | A própria Página | Sim |
| **Nome do Business Portfolio** | É onde a Página operacionalmente mora; vira o rótulo de localização do ativo. | business.facebook.com › seletor de portfólio no topo, ou Configurações do Negócio › Informações do Negócio | Sim |
| **Quem responde pela Página** | O Cofre não aceita ativo sem dono nomeado, e distingue "o dono afirmou" de "alguém conferiu". | Você | Sim |
| **Estado e criticidade** | `declared` enquanto a propriedade não foi conferida com prova; `verified` só com recibo. | Sua avaliação | Sim |
| **O que a Página faz hoje** | Lista de capacidades e a próxima ação. Já há rascunho vindo da fixture; corrija se estiver errado. | Você | Sim |
| **URL pública da Página** | Deixa a linha clicável. Use o endereço de **nome de usuário**; `profile.php?id=<número>` é recusado porque carrega o ID inteiro. | Barra de endereços da Página | Não |
| **Referência 1Password do acesso à Página** | O Cofre registra **onde** a credencial mora, para que ninguém precise perguntar "quem tem a senha?". | No 1Password: botão direito no **campo** › "Copiar referência de segredo". Forma: `op://<cofre>/<item>/<campo>` | Sim |
| **Nome lógico dessa credencial** | Rótulo do item, em MAIÚSCULA_COM_UNDERSCORE (ex.: `FACEBOOK_PAGE_ACESSO`). | Você escolhe | Sim |
| **Como e quando você conferiu** | Método, procedência, evidência em palavras e o **instante da observação com fuso**. Se a base ainda é só a sua palavra, diga isso: `unverified` + `owner_declaration` é resposta aceita. | Você | Sim |
| **ID do perfil AdsPower dedicado** | O ADR manda o perfil entrar no Cofre como referência operacional; P03-T07 exige ID, dono e finalidade visíveis. Esse número é inútil sem a API key da Local API, que nunca entra aqui. | Cliente AdsPower › lista de perfis › coluna "No." / ID do perfil | Não (se não houver perfil, informe e o bloco sai da ficha) |
| **Referência 1Password do acesso ao AdsPower** | Mesma regra: endereço, nunca valor. | 1Password, igual acima | Só se houver perfil |
| **Rótulo do proxy do perfil** | Rótulo curto e não sensível (ex.: "Proxy residencial BR-SP"). **Nunca** host, porta, usuário ou senha. | Você | Não |

Os caminhos de menu acima são referência de navegação, não contrato — telas de
plataforma mudam. O que não muda é o **valor** pedido em cada linha.

## Como entregar

1. Gere sua cópia da ficha, **fora do repositório** (o ID completo não deve ser versionado):

   ```bash
   python3 scripts/onboarding_pagina_facebook.py --modelo > ~/ficha-pagina.json
   ```

   Ou parta de `docs/closure/asset-vault-onepassword-production-v1/FICHA-PAGINA-MODELO.json`,
   que é o mesmo conteúdo. Cada campo tem ao lado um irmão `__onde_obter`
   dizendo exatamente onde achar o dado.

2. Preencha tudo que estiver com `PREENCHER` ou `<template>`. Campos opcionais
   ficam em `null`. Se não houver perfil AdsPower, troque o objeto
   `perfil_adspower` **e** `credencial_perfil` por `null`.

3. Rode o comando abaixo. Enquanto faltar campo, ele sai com código diferente de
   zero e lista o caminho exato de cada pendência — nenhum payload é emitido:

   ```bash
   python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json
   ```

   Para a forma SQL, pronta para as funções governadas do Cofre:

   ```bash
   python3 scripts/onboarding_pagina_facebook.py --ficha ~/ficha-pagina.json --sql
   ```

O script não faz rede, não escreve no banco e não fala com a Meta nem com o
AdsPower. Ele só transforma a sua ficha nos seis pedidos que o Cofre aceita.
