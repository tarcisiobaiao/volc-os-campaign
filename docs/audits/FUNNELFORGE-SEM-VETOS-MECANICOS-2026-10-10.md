# Motor canônico sem vetos mecânicos de copy

Data: 10/10/2026. Autoridade: diretriz explícita do operador neste chat.
Base: main @ fdb6488e. Alterações locais, sem commit/push/deploy nesta rodada.

## Decisão aplicada

A revisão contextual por LLM existente decide riscos editoriais e propõe
correções localizadas. Código não decide se uma palavra, frase, verbo ou
paráfrase é enganosa por lista, regex, quantidade de palavras ou similaridade.
Não foi criado perfil, serviço, agente ou chamada de revisão adicional.

O config.yaml distribuído passa a ligar editorial_v2 por padrão. O tipo legado
RunConfig mantém o default antigo para reproduzir configurações/runs arquivados;
V1 explicitamente desligado permanece intacto. Runs retomados usam seu snapshot,
portanto um snapshot antigo não muda silenciosamente com esta configuração.

## Saíram do veto da geração atual

- Scanners de medo, falsa oficialidade, verbos de CTA, idioma e identidade textual.
- Quotas de palavras, headings, introdução, blocos visuais e links oficiais.
- Similaridade de texto e congruência de CTA julgada por tokens.
- Match lexical de número/fonte/citação no corpo e nos widgets.
- Pré-voo de política sobre texto do plano e scanner de Ads sobre a LP gerada.
- Rejeição de CTA por começar com Entender, Conhecer ou Saiba, comprimento,
  número ou rótulo repetido. Orientação persuasiva continua no prompt.
- Retenção automática por lacuna/conflito factual antes de escrever: a pesquisa
  não promove o fato e a revisão recebe a lacuna; uma página sem dado pode ser
  útil sem inventá-lo. Não é autorização para afirmar dados contraditórios.

Esqueleto e revisão global determinísticos conservam avisos editoriais, não
vetos. Campos obrigatórios, destinos/IDs inexistentes e integridade do grafo
continuam contratos técnicos. Referência inexistente no briefing não vira fato.

## Proteções preservadas

JSON e slots necessários ao Elementor; blocos Gutenberg fechados; sanitização
de HTML/JS/CSS; links resolvidos; fórmulas e entradas das calculadoras;
posicionamento dos slots comprovados do Ad Inserter; hash dos pacotes/recibos;
aprovação contextual ou decisão humana explícita; segurança dos microajustes;
limites de chamadas/orçamento; autenticação; falha de stream/truncamento;
publicação em rascunho. Scanner de campanha Google Ads não foi alterado.

Bloqueio material da LLM continua retendo a página. Remover os vetos editoriais
não aprova páginas em nome do operador nem remove a revisão do motor.

## Prova local

Comando: `FF_VISUAL_BROWSER=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --tb=short`

- 1739 aprovados, zero falhas, zero pulados; um aviso herdado do google-genai.
- Oito contraprovas novas em test_editorial_sem_vetos_mecanicos.py.
- Scanners substituídos por funções que levantam erro se chamadas: fluxo integral
  cria cinco drafts no WordPress falso sem passar por qualquer um desses scanners.
- Revisor simulado recusa promessa falsa: só a página correspondente é retida;
  as outras quatro chegam ao publicador falso. Nenhuma publicação remota.
- HTML quebrado e script arbitrário ainda reprovam; ID de fato inexistente
  impede gastar na redação. Opinião semântica no briefing não gera retry.
- Uma fixture antiga de falha paralela não injetava erro: buscava a URL própria,
  ausente do prompt. Passou a injetar erro pelo headline exato; isolamento de
  falha serial/paralelo agora é efetivamente exercitado.
- Ouro V1 passou sem regenerar. git diff --check passou. Comparação de lint
  dos arquivos alterados com HEAD não mostrou achado novo.

São testes com provedores/publicador simulados e Chromium local. Nenhum canário
real novo, chamada paga, alteração de WordPress/Supabase/Ads ou deploy ocorreu.
Não há prova nova de qualidade editorial real, velocidade, CTR ou ROI.

## Estado operacional

P10-T22 continua partial; cap_funnel recebe a evidência sem promoção de estado.
Homologação real do funil, aceite do delta da p2, entregas pendentes e medição
de produção permanecem separados desta limpeza. Não invalidamos nem alteramos
artefatos, decisões humanas e runs anteriores. Snapshot antigo requer migração
explícita ou novo run para usar a nova configuração.
