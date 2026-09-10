# Direção cromática e presença visual do briefador

Data: 2026-09-09. P11-T17 permanece partial.

## Causa observada

O briefing fornecido pelo operador pedia explicitamente cinza-claro/off-white,
CTA discreto e acentos acinzentados, justificando isso por evitar identidade
governamental. O render seguiu a direção fraca. No contexto, uma menção a paleta
oficial ainda podia apagar toda a sugestão cromática. Mudar só o renderizador
depois da aprovação alteraria o que foi autorizado, sem resolver o brief.

## Ajuste

- Contexto da LP propõe dominante, apoio e acento com papéis visíveis e elementos
  reconhecíveis do tema. Referência cromática deixa de ser confundida com endosso.
- Menções a identidade oficial não apagam automaticamente as cores. Conteúdo
  permanece como sugestão editorial não verificada e recebe aviso para revisão.
  Não é um classificador de política nem uma autorização de copiar logos.
- O briefador define dominante/apoio/acento/tinta e onde aparecem, gesto espacial,
  foco, hierarquia, luz e um ou dois elementos narrativos relacionados ao tema.
- Novas peças sem direção explícita priorizam presença cromática e contraste;
  neutralidade factual não impõe estética pastel. Evitar repetição de topo branco,
  foto escolar e pílula discreta. Estilo suave explicitamente pedido é preservado.
- Ousadia vem de composição, cor, escala e curiosidade sustentada pela LP, não
  aumento da promessa, falso saldo/urgência/endosso ou atributo do observador.
- O assunto principal continua obrigatório no texto interno quando confirmado.
  Não foi adicionada paleta fixa do Pé-de-Meia ou do VOLC para todos os temas.

## Compatibilidade e teste operacional

Nenhuma alteração de schema, migration, modelo (`gpt-image-2`), quality (`medium`),
compilador de imagem, versão de spec ou direção congelada. Mudam instruções para
novas propostas; specs aprovadas seguem reproduzíveis.

Para avaliar: criar novo briefing e analisar a LP novamente, revisar as referências
visuais sugeridas, gerar estratégia, conferir paleta/composição e só depois aprovar
e gerar imagens. Alternativamente, desfazer aprovação das peças a alterar e refinar
com referência explícita. Repetir imagem de spec antiga repete direção antiga.

O leitor de LP é textual: não amostra CSS, imagens nem HEX oficiais. A tentativa
de consultar `https://www.gov.br/mec/pt-br/pe-de-meia` encontrou desafio de acesso;
não há evidência nesta rodada de paleta oficial medida ou verificada. Cores devem
ser revisadas como proposta editorial; referência cromática exata requer material
de origem acessível. Não incorporamos referências visuais externas não verificadas.

## Verificação

201 testes backend passaram (contexto, assunto, estratégia, spec, transporte ao
provider dublê, JSON/replay e legado). Novos testes provam transporte intacto de
paleta expressiva e de monocromático explicitamente aprovado, isolamento de dados
e contrato de instruções. Não provam que um LLM obedecerá sempre nem que o raster
terá qualidade ou CTR superior. Diff check limpo.

Sem chamada paga, imagens novas, mutação Meta, banco ou Webgo. Revisão visual das
novas peças e experimento de mídia permanecem com o operador. Para rollback,
reverter apenas a revisão de instruções/contexto desta rodada; nunca reescrever
specs históricas para reproduzir outra estética.
