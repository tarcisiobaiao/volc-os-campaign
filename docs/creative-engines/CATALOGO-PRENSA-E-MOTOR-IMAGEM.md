# Catálogo vivo — Motor de Imagem VOLC e PRENSA

Atualizado em 26/08/2026 a partir de leitura somente do parque externo.

## O que fica blindado aqui

O `motor-imagem` não é apenas um gerador conectado a uma LLM. Ele contém um
sistema editorial capaz de produzir imagem, texto, gráficos, atmosferas e
variações de formato por caminhos independentes. A fotografia atual é gerada
por `scripts/inventariar_motor_imagem.py` e fica em
`snapshots/motor-imagem-2026-08-26.json`.

Essa fotografia registra 856 arquivos, 443 arquivos de código/contrato
hasheados, 18 specs PRENSA, 7 skins e 94 imagens no diretório `out` canônico.
Das 64 saídas finais ou experimentais renderizadas:

- 26 usam somente tipografia, formas e atmosfera produzidas por código;
- 12 combinam tipografia com gráficos determinísticos;
- 26 usam um asset de imagem gerado por IA e acabamento PRENSA;
- 47 têm pixel gate aprovado e 65 possuem veredito DOM `ok` — as contagens não
  são iguais porque algumas provas antigas não materializaram ambos os sidecars.

Também existem 71 imagens em `out_antes_costura`; 64 são byte a byte idênticas
às atuais. Esse diretório é evidência de evolução, não autoridade de publicação.

## A distinção que não pode mais se perder

**Imagem generativa é opcional.** O serviço criativo tem seis modos legítimos;
quatro deles usam PRENSA diretamente:

| Modo | O que a IA faz | O que o código faz | Exemplo |
|---|---|---|---|
| `typography_only` | nada nos pixels | texto, hierarquia, formas, textura, vinheta, luz e paginação | `carrossel_produtividade_metodo90_s02.png` |
| `deterministic_graphics` | nada nos pixels | texto + gráficos SVG + composição + gates | `anderson_grafico_s01.png` |
| `full_llm` | gera toda a peça | entrega e rastreabilidade; PRENSA não é obrigatória | Aprova e Positivo |
| `existing_asset_plus_prensa` | pode apenas ajudar no briefing | preserva foto/asset existente e recompõe ao redor | integração futura com o Positivo |
| `prensa_hybrid_llm_asset` | gera a cena sem texto | tipografia real, layers, formatos e gates | `kintsugi_planejado.png` |
| `full_llm_then_prensa` | gera uma peça ou asset exploratório | promove a geração aprovada a matéria-prima e cria variantes controladas | caminho previsto no ADR-001 |

O modo `typography_only` é especialmente valioso: é barato, rápido,
reproduzível, não depende de provider de imagem e mantém a copy literal. Ele é
adequado para carrossel educativo, dado, lista, explicador, card de notícia,
CTA, capa editorial e peças de remarketing orientadas por texto.

## A prova citada pelo dono: Método 90

`carrossel_produtividade_metodo90` possui quatro lâminas e foi materializado em
cinco tratamentos, totalizando 20 PNGs:

- base — pele carbon, acento laranja, grain e hierarquia editorial;
- `fx` — atmosfera e halation mais presentes;
- `fxd` — variação de tratamento determinístico;
- `titanium` — aplicação explícita da skin Titanium;
- `dossier` — a mesma estrutura editorial em papel creme, serifas e dourado.

O exemplo `carrossel_produtividade_metodo90_s02.png` não possui `assets[]` no
spec. Seus pixels vêm de texto, frames, retângulos, dots, texture, vazamento e
vinheta. Isso comprova que o conteúdo pode ser retematizado por tokens sem
regenerar uma imagem e sem transformar texto em pixel probabilístico.

## Famílias executadas no `out` canônico

| Família | Saídas | Modo predominante | O que prova |
|---|---:|---|---|
| Método 90 | 20 | tipografia pura | carrossel e troca de skin sem imagem |
| Anderson Sono | 5 | tipografia pura | sequência editorial sem foto |
| Anderson Gráfico | 6 | gráfico determinístico | curva, mostrador, trajetória, small multiples e radar |
| Anderson Vitrine | 6 | gráfico determinístico | cards de dado, colunas, tabela e medidor |
| Capas de referência | 6 | híbrido | imagem + estrutura de carrossel |
| Layoffs | 6 | híbrido | variação serial de uma pauta visual |
| Kintsugi | 5 | híbrido | cenas com espaço semântico para texto |
| VOLC News | 6 | híbrido e multidestino | base, PMax e Demand Gen recompostos |
| INSS 13º | 2 | híbrido | card editorial de notícia |
| Food | 1 | híbrido | aplicação de uma skin por nicho |
| Amostrário | 1 | tipografia pura | prova de fontes e hierarquia; não é peça publicável |

Os números vêm do snapshot, não de uma lista escrita à mão.

## As sete skins observadas

| Brand pack | Fontes vendorizadas | Efeitos declarados |
|---|---|---|
| Anderson | Barlow Condensed, Instrument Serif, Inter | grain, halation, light leak, varnish, vignette |
| Dossier | Cormorant Garamond, Instrument Serif, Inter, Source Serif | grain, ink bleed, varnish, vignette |
| Food | Archivo | grain, vignette |
| Kintsugi | Instrument Serif, Inter | grain, halation, vignette |
| News | Inter | grain, light leak, vignette |
| Titanium | Barlow Condensed, Instrument Serif, Inter | grain, halation, light leak, varnish, vignette |
| VOLC News | Archivo, Bodoni Moda, IBM Plex Mono | grain, vignette |

Cada arquivo de fonte é declarado no token pack e validado por SHA-256. Marca é
dado; o renderer não deve carregar hex, handle ou fonte de um cliente.

## Inteligência reaproveitável

### Contrato e resolução

- `post.spec` separa pauta, skin, artboard, safe area, assets, layers e gates;
- `$tokens` viram valores literais antes do render;
- spec resolvido recebe hash canônico;
- fonte ausente, hash divergente, accent budget e zona de foto inviável recusam
  o job antes de promover saída.

### Tipografia e composição

- fonts reais vendorizadas;
- runs permitem acento sem procurar palavras por substring;
- fit por nó com mínimo, máximo, número de linhas e `overflow: fail`;
- duas passadas estabilizam o layout antes da avaliação;
- PRENSA mede tinta, baseline, cap-height, clearance, costuras e elasticidade;
- gráficos são SVG determinísticos gerados de dados, não imagens “desenhadas”
  por uma LLM.

### Atmosfera por código

- grain com seed;
- halation em múltiplos passes restrita aos runs de acento;
- light leak/vazamento;
- vignette;
- ink bleed/sangria;
- varnish;
- scrim calculado pela luminância da zona de texto;
- máscaras, gradientes e tratamentos declarados em layer/token.

### Gates e evidência

- verify no DOM antes do screenshot;
- PNG reaberto para contraste, bbox de tinta, clipping e box fit;
- portão de traço para elementos não textuais;
- clearance entre conteúdo, gráficos e mobília;
- caso adversarial obrigatório para provar que o gate sabe reprovar;
- promoção transacional: carrossel reprovado não publica lâminas parciais;
- `Resultado` devolve hash do spec, SHA-256 do PNG e evidência serializável.

### Operação

- API Python única `renderiza(spec, saida, tokens, raiz, trabalho)`;
- erros tipados: `SpecInvalido`, `AssetAusente`, `GateReprovou` e
  `MotorIndisponivel`;
- zero rede e zero segredo no renderer;
- escala atual por processos, não threads;
- um browser por chamada e ausência de batch são limites conhecidos.

## Como empacotar no VOLC O.S.

Não copiar a pasta inteira para dentro do backend. O pacote deve preservar a
inteligência por camadas:

```text
volc_ads/criativo/                 contrato de asset, procedência e porta
services/creative-engine/         runtime separável e fila de jobs
  core/                            CreativeJob, aprovação e ledger
  adapters/prensa.py              chama o renderer offline
  adapters/positivo_photo.py      preserva foto real
  adapters/providers/             gera assets quando o modo pedir
  brand_packs/                     tokens, fontes, compliance e versões
  workers/                         escala por processo
```

O PRENSA deve receber o asset já resolvido. Assim, um job tipográfico não
precisa de provider, um job com foto real não altera o original, e um job
híbrido pode trocar OpenAI/Gemini/banco de imagem sem alterar o renderer.

## Checklist de incorporação

### Patrimônio — concluído nesta rodada

- [x] Inventário reproduzível e somente leitura.
- [x] Hash de 443 arquivos de código/contrato.
- [x] Catálogo das 18 specs e sete skins.
- [x] Catálogo das famílias e modos de produção.
- [x] Registro explícito do modo sem LLM de imagem.
- [x] Preservação da evidência `out_antes_costura` sem tratá-la como atual.

### Próxima vertical segura

- [ ] Congelar uma versão extraível do pacote `prensa/` e da POC que ele envolve.
- [ ] Criar `CreativeJob.mode` com os seis modos deste catálogo.
- [ ] Criar adapter PRENSA atrás de `MotorDeCriativo`.
- [ ] Persistir spec hash, PNG hash, sidecars e decisão humana.
- [ ] Executar paridade com Método 90, Anderson Gráfico, Kintsugi e VOLC News.
- [ ] Criar worker por processo e `renderiza_lote()`.
- [ ] Ligar primeiro a preview; publicar continua exigindo aprovação.

## Como atualizar

```bash
python3 scripts/inventariar_motor_imagem.py \
  --output docs/creative-engines/snapshots/motor-imagem-2026-08-26.json
```

O script só lê o projeto externo. Alterações materiais devem atualizar este
catálogo, `motores-de-imagem.json`, a curadoria operacional e então o grafo.
