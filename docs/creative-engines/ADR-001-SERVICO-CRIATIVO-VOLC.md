# ADR-001 — Extrair um serviço criativo VOLC, sem transformar o Positivo em núcleo

**Status:** aceita como direção arquitetural · implementação pendente  
**Data:** 26/08/2026

## Contexto

Aprova Ad Studio e Positivo Ad Studio já possuem uma fundação valiosa em comum: Vite/React, FastAPI, orquestração por agentes, provedores Gemini/OpenAI/mock, dimensões exatas, geração paralela e progresso por SSE.

O Positivo acrescenta composição de foto real. A PRENSA acrescenta tipografia, layers e gates determinísticos. O VOLC O.S. já criou `volc_ads/criativo`, sua porta interna para motores, procedência, requisitos e validação.

A dúvida é se o Positivo deve ser clonado e turbinado até virar o motor do VOLC O.S., se todo o código deve ser movido para o produto, ou se os recursos devem permanecer externos.

## Decisão

Criar um **serviço criativo VOLC dentro do monorepo, com runtime separável**, implementando a porta `MotorDeCriativo` já existente.

Não transformar o repositório Positivo no núcleo. Não importar seus frontends. Não acoplar o Hub a paths externos.

O serviço deve oferecer seis modos sob o mesmo contrato:

1. `typography_only` — PRENSA produz texto, formas, atmosfera e chrome sem provider de imagem.
2. `deterministic_graphics` — PRENSA combina texto com gráficos SVG/data-viz produzidos por código.
3. `full_llm` — a peça inteira é gerada pela LLM para a proporção e dimensão solicitadas, como Aprova e Positivo já fazem.
4. `photo_preserved` — uma foto real permanece como asset controlado e o anúncio é composto ao redor dela, reutilizando a engenharia do Positivo.
5. `prensa_hybrid` — IA produz cena/assets; PRENSA controla texto, fonte, layers, variantes e gates finais. Uma geração full-LLM aprovada também pode entrar como asset deste modo.
6. `full_llm_then_prensa` — uma peça full-LLM aprovada vira asset rastreado para acabamento, copy literal e variantes PRENSA.

`typography_only` e `deterministic_graphics` não são fallbacks degradados. São
rotas de produção próprias: zero custo de imagem generativa, copy literal,
reprodutibilidade e gates completos. O carrossel Método 90 e as famílias
Anderson provam ambos os caminhos no snapshot de 26/08/2026.

Estrutura-alvo, ainda não criada:

```text
services/creative-engine/
  app/                 API interna e workers
  core/                orquestração e contratos próprios do serviço
  adapters/
    aprova.py
    positivo_photo.py
    prensa.py
    providers/
  brand_packs/
    aprova/
    positivo/
    volc/
  tests/
```

O front chama apenas o backend autenticado do VOLC O.S. O backend cria um job, fala com o serviço e persiste estado. O navegador nunca recebe chave de provedor nem chama o motor diretamente.

## Por que não clonar o Positivo como produto-base

- branding, prompts, assets e UX estão especializados para um cliente;
- o repositório externo possui estado de trabalho e deploy próprios;
- futuras mudanças no Positivo poderiam alterar o núcleo do VOLC sem intenção;
- Meta, Google e orgânico precisam do mesmo motor, mas contratos de destino diferentes;
- PRENSA e Aprova trazem capacidades que não devem ser subordinadas ao modelo Positivo;
- um clone integral duplica frontend, autenticação, configurações e dívida.

Um fork temporário pode ser usado como bancada de extração, mas não vira autoridade permanente.

## O que será extraído

### Do Aprova

- orquestração agentic;
- pesquisa e blueprint;
- provedores de imagem;
- dimensões nativas e entrega no tamanho exato;
- SSE, erros tipados, retry e empacotamento.

### Do Positivo

- análise PHOTO-FIRST;
- seleção de zona pela geometria da foto;
- composição nativa, visão, chroma e híbrida;
- compositor que preserva o arquivo real.

### Da PRENSA

- contrato de brand pack e destino;
- fontes vendorizadas e tipografia real;
- resolve, compile e render;
- efeitos determinísticos;
- gates DOM/pixel e fail-closed;
- ledger de variantes.

### Do VOLC O.S.

- identidade, procedência e catálogo de assets;
- requisitos oficiais por canal;
- autenticação e autorização;
- jobs, recibos, aprovação humana e vínculos com campanha/anúncio;
- armazenamento e observabilidade.

## Dois caminhos de formato, ambos oficiais

### Full LLM

O request aceita dimensão exata. O provider calcula uma dimensão nativa aceita pelo modelo, preserva a proporção-alvo dentro do envelope suportado, orienta a LLM a compor para aquele canvas e entrega o arquivo final nas dimensões pedidas via processamento local sem distorção.

É a opção mais rápida e livre para explorar visual. Texto, fonte e microgeometria permanecem probabilísticos porque estão dentro da imagem gerada.

### PRENSA

Cada canvas recompila o layout. A cena pode vir da LLM, mas texto, fonte, layers e gates são controlados por código.

É a opção mais forte quando copy exata, identidade visual, legibilidade, compliance e repetibilidade são requisitos.

Os caminhos não competem: o job escolhe o modo conforme a finalidade e pode promover uma boa geração full-LLM para uma finalização PRENSA.

## Limite que precisa ficar explícito

“Qualquer formato” significa qualquer dimensão positiva aceita pelo contrato e processável pelo pipeline. Na versão observada, a composição nativa do `gpt-image-2` é ajustada ao envelope implementado pelo provider; proporções extremas fora dele podem usar tamanho padrão seguido de `cover` e crop.

Portanto:

- formato publicitário comum: composição full-LLM orientada para a proporção e saída exata;
- proporção extrema: saída exata continua possível, mas a fidelidade da composição pode depender de crop;
- zero crop e reposicionamento editorial garantido: usar PRENSA ou criar uma regra de composição específica.

## Contrato operacional mínimo

Cada job deve registrar:

- modo criativo;
- dimensão e proporção alvo;
- dimensão nativa realmente enviada ao provider;
- se houve resize, crop ou recomposição;
- provider, modelo e versão;
- brand pack e versão;
- hashes dos assets de entrada e saída;
- prompt/blueprint sanitizado;
- custo, duração, tentativas e erros;
- gates executados;
- aprovação humana;
- destino e vínculo com campanha/anúncio.

## Sequência de migração

1. Congelar hashes das fontes externas usadas na extração.
2. Criar `services/creative-engine` sem frontend e sem segredos versionados.
3. Portar primeiro `full_llm`, provando paridade com Aprova em três formatos.
4. Implementar o adapter `MotorDeCriativo` e persistir jobs/artefatos.
5. Portar `photo_preserved`, provando que o hash da foto original permanece rastreável.
6. Adaptar PRENSA e seus gates.
7. Converter Aprova, Positivo e VOLC em brand packs.
8. Ligar o primeiro pacote Display ao `validate_only` do Google Ads.
9. Só depois aposentar código duplicado nos produtos externos, se ainda fizer sentido.

## Critérios de aceite da primeira vertical

- mesmo briefing gera 1:1, 1.91:1 e 4:5 sem alterar o contrato;
- cada saída informa se foi full-LLM, crop ou PRENSA;
- procedência e hashes estão persistidos;
- uma falha de formato não derruba o lote;
- nenhuma chave chega ao browser;
- preview e provas aparecem no Hub;
- Google recebe primeiro `validate_only`;
- publicação exige confirmação explícita.

## Consequências

### Positivas

- preserva os produtos existentes;
- evita clone eterno e branding hardcoded;
- um runtime atende Google, Meta e orgânico;
- cada motor pode evoluir sem alterar o Hub;
- permite escolher velocidade criativa ou precisão determinística por job.

### Custos

- exige extração e testes de paridade;
- precisa storage e fila de jobs;
- brand packs terão de substituir literais de cliente;
- fotos reais exigem política de retenção e acesso;
- haverá período temporário com código duplicado até a migração fechar.

## Alternativas rejeitadas

### Clonar Positivo e evoluir diretamente

Rejeitada como arquitetura permanente. Aceitável apenas como bancada temporária de extração.

### Copiar todos os projetos para dentro do backend atual

Rejeitada. Mistura frontends, ambientes e responsabilidades e torna escala de geração concorrente dependente do processo principal da API.

### Manter tudo externo e chamar por path local

Rejeitada. Paths da máquina não são contrato de produção, impedem deploy reproduzível e escondem versões.
