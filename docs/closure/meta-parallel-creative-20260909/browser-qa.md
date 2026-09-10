# QA hermético da galeria — 2026-09-09

Escopo: componente real `GaleriaDeGeracoes`, seus componentes filhos e CSS real,
renderizados em fixture temporária com `BrowserRouter`. Não é evidência da jornada
autenticada, da API real, do motor de imagem nem do provider. O método
`criativosApi.job` foi substituído em memória apenas na fixture, sem alterar código
de produção. Imagem SVG claramente identificada como fictícia, sem geração paga.
HTML e script temporários removidos após o teste; apenas este registro permanece.

Execução: Playwright com Google Chrome headless instalado; viewport 375×1000 e
1440×1000, temas claro e escuro, `reducedMotion: reduce`. Interceptador impediu
requests fora do servidor Vite localhost:8080. Nenhum request externo/API foi
tentado; nenhum segredo, autenticação, sessão ou objeto real foi utilizado.

## Cenário e resultado

1. Pedido com dois slots, sem jobs registrados: dois placeholders visíveis e
   progresso `0 de 2 prontas · 2 aguardando`.
2. Job registrado e primeira leitura: uma imagem pronta e uma em produção.
   Selecionada a imagem pronta e colocado foco em `Ampliar Retrato QA`.
3. Próximo polling: job terminal parcial, uma imagem pronta e outra com falha
   simulada. Cabeçalho informa pendências, sem apresentar sucesso integral.

Nas quatro combinações:

- Zero `pageerror`; zero overflow horizontal.
- Dois reads locais de job e exatamente um callback terminal.
- Checkbox da imagem pronta permaneceu marcado.
- Foco permaneceu em `Ampliar Retrato QA` durante a atualização assíncrona.
- Checkbox da imagem com falha permaneceu desabilitado.
- Nenhuma animação computada com reduced-motion ativado.
- Ordem dos slots preservada. Em desktop ambos permaneceram nas mesmas posições.

## Achados comunicados ao integrador

- Pequeno deslocamento vertical em mobile: o rodapé de placeholder é cerca de
  48 px menor que o rodapé de rendition com controles. A ordem permanece; o
  segundo cartão desloca-se para baixo quando o primeiro fica pronto.
- Na captura inicial, o cabeçalho secundário mostrava `0 de 0 arquivos` enquanto
  o progresso principal mostrava `0 de 2`. O integrador já estava ajustando essa
  contagem; estas capturas registram o estado anterior e não provam o ajuste.

## Capturas

Doze PNGs locais, todos inspecionados visualmente:

`/private/tmp/gallery-{375,1440}-{light,dark}-{loading,running,partial}.png`

Não foi realizado teste de download, exclusão, persistência de packs, retomada de
sessão nem submit real de geração. As fontes tipográficas e o shell autenticado
completo não foram objeto desta fixture. Nenhum arquivo de produção foi alterado
por este trabalho de QA.
