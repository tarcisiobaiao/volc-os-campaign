# AGPL-3.0 e a fronteira do VOLC-OS

> ⚠️ **Isto não é aconselhamento jurídico.** É a análise técnica que sustenta uma
> decisão de arquitetura, escrita por quem construiu a integração e a partir do
> texto público da licença. Não substitui a avaliação de um advogado, não vincula
> ninguém e não deve ser usada como parecer. Antes de distribuir software,
> oferecer o serviço a terceiros ou modificar o Postiz, consulte assessoria
> jurídica. As referências abaixo estão datadas justamente para que uma pessoa
> qualificada possa conferi-las.

---

## O fato

O Postiz é licenciado sob **GNU Affero General Public License v3.0**, copyright
(C) 2025 Nevo David.

Fonte primária: <https://github.com/gitroomhq/postiz-app/blob/main/LICENSE>,
consultada em **02/09/2026**.

---

## 1. O que a AGPL-3.0 exige

A AGPL é a GPLv3 **mais uma cláusula**. Vale a pena separar as duas coisas,
porque a confusão entre elas é a origem de quase todo mal-entendido sobre esta
licença.

### 1.1 O que ela herda da GPLv3

- **Copyleft sobre obra derivada** (§5). Quem distribui uma versão modificada, ou
  uma obra "baseada no Programa", tem de licenciar o todo sob a mesma AGPL e
  entregar a *Corresponding Source* (§1) — o código-fonte completo que permite
  regerar o binário, incluindo scripts de build e instalação.
- **A cláusula de agregado** (§5, parágrafo final). Reunir o Programa com outras
  obras **separadas e independentes**, num mesmo volume de armazenamento ou meio
  de distribuição, forma um *aggregate*; a licença do Programa **não** se estende
  às outras partes, desde que elas não sejam, por sua natureza, extensões do
  Programa.

### 1.2 O que ela acrescenta — §13, "Remote Network Interaction"

> *"Notwithstanding any other provision of this License, if you modify the
> Program, your modified version must prominently offer all users interacting
> with it remotely through a computer network […] an opportunity to receive the
> Corresponding Source of your version […]"*

É a cláusula que fecha a brecha do SaaS na GPL comum: sob GPLv3, quem roda
software modificado num servidor e nunca distribui o binário não distribui nada
e não deve nada; sob AGPL, **usar pela rede uma versão modificada equivale, para
efeito da obrigação de fonte, a distribuí-la**.

### 1.3 A condicional que quase todo mundo ignora

⚠️ **O §13 diz "if you modify the Program".** Rodar o Postiz **sem modificação**,
ainda que servindo terceiros pela rede, não faz nascer a obrigação do §13 sobre
o *nosso* código — e nem sobre o dele, que já é público. É por isso que a
primeira e mais forte linha de defesa deste pacote não é jurídica, é
operacional: **não modificamos o Postiz.**

O `docker-compose.yml` deste diretório usa a imagem publicada pelo upstream, com
tag pinada, sem `build:`, sem patch, sem overlay de código.

---

## 2. Por que rodar como serviço separado preserva a separação

Três características, e cada uma sustenta um pedaço do argumento.

### 2.1 Fronteira de processo

O Postiz roda no **próprio container**, com o **próprio Postgres**, o **próprio
Redis** e o **próprio Temporal**. Nada dele é carregado no espaço de endereçamento
do backend do VOLC. Não há import, não há link, não há plugin, não há vendoring.

A posição da FSF sobre onde fica a fronteira de obra derivada gira exatamente
nesse ponto: processos separados que se comunicam por mecanismos de troca de
mensagens *arm's length* — soquetes, pipes, chamadas de linha de comando —
tendem a ser programas separados; compartilhar espaço de endereçamento por
linkagem, estruturas de dados internas e fluxo de controle tende a formar um só
programa (GPL FAQ, *"What is the difference between an 'aggregate' and other
kinds of 'modified versions'?"*).

⚠️ **Honestidade sobre o peso disso:** essa é a interpretação do titular
histórico da licença e a prática corrente da indústria — **não é decisão
judicial**. Um tribunal poderia enxergar diferente, sobretudo se a comunicação
fosse tão íntima a ponto de os dois programas só fazerem sentido juntos. É mais
uma razão para a ressalva do topo desta página.

### 2.2 Interface pública e documentada, não interna

A comunicação usa a **API pública oficial** do Postiz (`/public/v1`), a mesma
publicada em <https://docs.postiz.com/public-api/introduction> e oferecida
igualmente à versão em nuvem do produto. Não usamos:

- o banco interno do Postiz (o Prisma dele é detalhe de implementação);
- nenhum endpoint não documentado;
- nenhuma estrutura interna dele.

⚠️ Este é um ponto **verificável, não retórico**, e o código o registra:
`backend/app/publicacao_organica/portas.py` documenta o mapa exato de cada
operação do VOLC para o endpoint oficial correspondente — e documenta as
**ausências**, com a data em que a documentação foi lida. Onde a API não tem
(`GET /posts/{id}`, chave de idempotência, health público, webhook de
confirmação), a implementação **não inventou** um caminho por dentro. Um
adaptador que fosse ao banco do Postiz para compensar essas ausências
atravessaria a fronteira que esta página descreve — e isso não aconteceu.

### 2.3 Substituibilidade

O VOLC fala com uma **porta** (`PortaDePublicacao`), não com o Postiz. Existe um
adaptador falso (`adaptadores/fake.py`) que a implementa por inteiro, e é ele que
os testes usam. Trocar o Postiz por outro control plane é escrever outro
adaptador.

Isso importa para a análise: um programa que **funciona sem** o Postiz, e cujos
testes rodam sem ele, dificilmente é "baseado no Postiz". O Postiz é uma
**escolha de fornecedor**, não um componente.

### 2.4 Fluxo de segredo, na direção que confirma a separação

O Postiz **nunca recebe a `service_role` do Supabase** (ADR de 28/08/2026). O
adaptador conhece **um** segredo, o `POSTIZ_API_TOKEN`, e há teste de contenção
(`test_publicacao_organica_segredos`) que falha se o módulo passar a referenciar
a chave do Supabase.

Isso não é exigência de licença — é higiene de segurança. Mas é evidência
corroborante de separação: os dois sistemas não compartilham nem credencial nem
banco.

---

## 3. O que é proibido, o que é permitido

| Situação | Sob esta análise | Por quê |
|---|---|---|
| Rodar o Postiz sem modificação, self-hosted | **Permitido** | §13 condiciona à modificação; nada é distribuído |
| Chamar a API pública a partir de código proprietário | **Permitido** | interface pública, processos separados |
| Automatizar o deploy dele (este diretório) | **Permitido** | configuração e agregação, não obra derivada |
| Copiar trecho de código do Postiz para o VOLC-OS | **Proibido** | torna o VOLC-OS obra derivada; §5 exige AGPL no todo |
| Fazer fork, modificar, e servir esse fork pela rede | **Exige publicar a fonte** | §13, e é a razão de existir da AGPL |
| Redistribuir imagem modificada | **Exige AGPL + Corresponding Source** | §5 e §6 |
| Biblioteca-ponte que faça link com código do Postiz no mesmo processo | **Proibido nesta arquitetura** | dissolve a fronteira de processo do §2.1 |
| Ir ao Postgres do Postiz por dentro, contornando a API | **Proibido nesta arquitetura** | acopla a estruturas internas; ver §2.2 |

⚠️ As duas últimas linhas **não são citação da licença** — são regra de
arquitetura desta casa, adotada para manter a análise acima verdadeira. Uma
regra que só existisse em prosa não valeria nada; por isso ela está codificada
na porta e no teste de contenção.

---

## 4. O que o pinning de versão tem a ver com licença

Parece detalhe de operação e não é.

Se um dia alguém tiver direito de pedir a *Corresponding Source* — porque a
instância passou a servir terceiros e alguém a modificou —, a primeira pergunta
é **"a fonte de qual versão?"**. Com `:latest`, como no compose oficial, essa
pergunta não tem resposta: `:latest` de ontem não é um endereço, e ninguém sabe
qual commit está rodando.

Com a tag `v2.23.0` — e melhor ainda com o digest `sha256:` — a resposta é uma
linha versionada no repositório, com data. **Pinning é rastreabilidade**, e
rastreabilidade é pré-requisito de qualquer conversa sobre conformidade.

---

## 5. Quando esta análise deixa de valer

Reabra a discussão — e agora com assessoria jurídica de verdade — se **qualquer**
destas mudar:

1. O Postiz passar a ser modificado (patch, fork, overlay de código, `build:` no
   compose no lugar da imagem oficial).
2. A integração deixar de ser por API pública (acesso ao banco dele, endpoint não
   documentado, biblioteca compartilhada).
3. A instância passar a ser oferecida **a terceiros** como serviço — clientes
   operando a interface do Postiz diretamente, não só o VOLC chamando a API.
4. Código do Postiz for copiado para dentro do VOLC-OS, em qualquer volume.
5. O upstream mudar a licença. A verificação de 02/09/2026 vale para o que estava
   publicado naquela data.

---

## 6. Verificação

O que sustenta esta página é conferível, e cada item tem onde ser conferido:

| Afirmação | Onde se confere |
|---|---|
| Não há código do Postiz no VOLC-OS | `git log`/`git grep` do repositório; não há vendoring nem submódulo |
| A integração é só HTTP | `backend/app/publicacao_organica/adaptadores/postiz.py` — só `httpx` |
| A imagem não é modificada | `deploy/postiz/docker-compose.yml` — sem `build:`, imagem do upstream |
| A porta é substituível | `adaptadores/fake.py` implementa a mesma `PortaDePublicacao` |
| O Postiz não recebe segredo do Supabase | `test_publicacao_organica_segredos` |
| A versão em uso é rastreável | tag pinada no compose, versionada com data |

---

## Fontes

- Texto da AGPL-3.0: <https://www.gnu.org/licenses/agpl-3.0.html>
- Licença do Postiz: <https://github.com/gitroomhq/postiz-app/blob/main/LICENSE>
  (consultada em 02/09/2026)
- FAQ da FSF sobre GPL (agregado × obra derivada):
  <https://www.gnu.org/licenses/gpl-faq.html>
- ADR interno: `docs/architecture/ADR-DISTRIBUICAO-ORGANICA-E-QA-VISUAL.md`
