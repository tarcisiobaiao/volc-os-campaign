# Fechamento do funil Tarifa Social (10/10/2026)

Tarefa: P10-T22 (`partial`). Nó: `cap_funnel`. Sobre o run
`tarifa-social-energia-eletrica-20261010-revisao-localizada`, sem regenerar o
funil. Nada publicado.

## Correções

- **LP-ponte:** `validate_lp_content` reprova `lp_sem_entrega_propria` quando
  introdução e seções não têm ao menos 3 frases de conteúdo (8+ palavras). Vale
  na escrita, no gate final e no `step_publish`. Não é piso de palavras. A
  contraprova agora monta o artefato antes do portão; a LP curta que responde
  passa. O portão compartilhado com Ads (`landing_policy`) não foi alterado.
- **Fatos órfãos do brief:** fatos verificados presos a perguntas do PAA
  (`q_…`) chegam ao inventário de todas as páginas. O 80 kWh (MME/ANEEL) e as
  orientações oficiais de Cemig, Enel e EDP estavam verificados e inacessíveis.
- **Delta material do plano:** além dos slugs, entram papel, pergunta, tipos de
  entrega, ferramentas e destinos. Reescrita de texto não conta.
- **Calculadora:** título e rótulos com as palavras do leitor, aviso curto,
  fallback sem JavaScript oculto quando o script roda, resultado em destaque.
- **Visual:** o gate lê o plano vivo (rota oficial tardia) e mede a borda pelo
  contêiner de rolagem. No CSS do MU-plugin, tabela de 3+ colunas rola dentro
  do bloco no celular.
- **Revisão global:** aceita direção opcional do operador, como dado.

## Execução (reaproveitando o run; não mede geração do zero)

1 pesquisa seletiva da p4 (30 s), 2 redações da p4 (3 tentativas), 3 revisões
localizadas (137 s, 185 s, 103 s). Tudo `chatgpt/gpt-6*-sol`, pedido = servido,
sessão ChatGPT, sem fallback. Sem chamada faturada nesta rodada.

A 2ª revisão reteve a p4: meu script remontou o dossiê sem atualizar o
inventário do revisor. A 3ª, com o inventário coerente, aprovou.

- LP, p3, p4, p5, p6, p7 aprovadas e com gate OK; Chromium 390/1440 px sem
  bloqueio nas 7.
- p2: calculadora corrigida (sha256 do documento para decisão
  `21f760da…`, bloco `d495bb01…`). Aguarda `funnelforge decidir`; nenhuma
  decisão registrada.
- p4: pesquisa sem canal atual confirmado por distribuidora; a página entrega o
  mapa oficial da ANEEL (com print) e as orientações oficiais verificadas.

Lote de homologação, não aplicado:
`producao/recuperacao-motor-20261010/lote-homologacao/LOTE-HOMOLOGACAO.md`.
