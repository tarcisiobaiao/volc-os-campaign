# Congruência do assunto no Assistente Criativo

Data: 2026-09-09. Estado: implementação local, validação hermética; qualidade de
novas imagens e desempenho de mídia ainda não medidos. Tarefa P11-T17, partial.

## Decisão

A peça pode mudar de ângulo, não desaparecer com o assunto. Separar o nome curto
do programa/produto/tema da descrição da operação, do aplicativo auxiliar e do
objetivo de mídia. A referência visual complementa a âncora, não a substitui.
Não basta instruir o modelo: validar texto interno antes de qualquer render.
Não inserir um título novo depois de aprovado: isso alteraria a peça autorizada.

## Contrato e experiência

- A leitura da LP retorna `assunto_principal` (até 160 caracteres) e
  `referencias_visuais_sugeridas` (até 1500). Nome sugerido requer menção no
  conteúdo visível e classificação explícita sem ambiguidade. Em dúvida,
  preencher manualmente. A menção não prova a centralidade: a pessoa revisa.
- No novo briefing, o assunto é obrigatório na interface e editável. Use nome
  curto, como “Pé-de-Meia”, não uma frase descrevendo toda a campanha.
- `EntradaNovaOperacao` e `PedidoDoAgente` recebem `assunto_principal` e
  `referencias_visuais`. São opcionais na API para compatibilidade histórica;
  entradas novas com assunto vazio/só sinais são recusadas. Campos seguem o
  input JSON existente e a reconstrução da próxima run; não há migration.
- O prompt distingue o tema principal dos meios auxiliares (app, consulta,
  login ou pagamento). Cada peça nova precisa nomear a âncora na headline ou
  complemento interno. Só citar na copy externa, CTA ou direção não basta.
- Checagem determinística normaliza acentos, caixa e hífens, exige a frase
  completa com limites de palavra e usa o retry já existente do briefador.
  Duas respostas inválidas não despacham uma imagem genérica.
- O texto validado entra na spec e no prompt de imagem sem reescrita tardia.
  A validação não é OCR nem prova de texto legível no raster gerado.
- Referências de cores/cenas são sugestões editoriais, não paletas oficiais
  verificadas. Não inferir logo autorizado, endosso, identidade governamental,
  benefício concedido ou resultado a partir dessas sugestões.
- Peças congeladas e contratos históricos permanecem preservados. Para aplicar
  a nova âncora a um projeto antigo sem esse campo, iniciar novo briefing.

## Evidência e limites

Resultado integrado: 194 testes backend e 69 frontend passaram; build aprovado.
TypeScript global: 76 erros herdados, nenhum no domínio criativo. Scanner de
segredos e diff check limpos. Sem QA visual autenticado nesta rodada.

Testes cobrem assunto ausente, app secundário, variações ortográficas, nome só
na copy externa, congelamento, duas tentativas inválidas, transporte até prompt
de imagem e criação/continuação pelo repositório dublê. Testes de LP mantêm
SSRF, vínculo URL e proveniência; testes de interface cobrem preenchimento e
preservação de edições humanas.

Sem geração paga, nova prova contra banco vivo, alteração Meta, alteração de
modelo/quality ou mudança no Webgo. CTR só pode ser avaliado com experimento.
Documentação complementa `meta-parallel-creative-20260909/HANDOFF.md`.
