# VOLC OS

Contrato de produto. Fonte humana de verdade para quem constrói e opera.
Se este arquivo divergir de uma página de marketing ou de um deck, este arquivo vence.
`design.md` governa a receita visual. Este arquivo governa o que o produto é, o que ele recusa ser e como um estado deve ser lido.

## 1. Visão e proposta operacional

VOLC OS é uma bancada operacional para profissionais de mídia paga e criação.
O operador precisa observar, decidir, preparar, aprovar e agir com confiança.

O produto reúne pauta, produção, publicação e tráfego num único sistema confiável.
Ele não promete automação de gasto. Ele prova o que foi lido, declara o que faltou e deixa a decisão humana explícita antes de qualquer escrita que possa gastar, publicar ou alterar entrega.

A linguagem é de um control room editorial e energético: denso, nítido, acionável.
Não é apresentação institucional. Não é clone do Meta Ads Manager. Não é dashboard cenográfico.

Cena de referência: um operador às 14h, monitor de 27 polegadas, luz de janela, conferindo mídia antes de autorizar gasto. O tema claro é o padrão dessa cena. O tema escuro é interpretação completa, não inversão.

## 2. Perfis e trabalhos críticos

### Administrador

Opera o ciclo inteiro: portfólio, projetos, relatórios, incubadora, pauta, redação, criativos, tráfego e configuração.
Trabalhos críticos: ler o estado econômico real, preparar ou lançar campanha, aprovar peça, resolver exceção, configurar custo, usuário e integração.

### Operador

Enxerga o recorte que lhe foi atribuído, em geral campanhas.
Trabalhos críticos: conferir entrega, pausar ou ativar o que lhe cabe, abrir a campanha canônica e não atravessar salas que a autorização recusou.

### Trabalho compartilhado

Todo perfil precisa distinguir, sem treino extra:

- o que foi medido agora;
- o que é demonstração;
- o que está parcial;
- o que está bloqueado;
- o que falhou;
- o que é zero real;
- o que é desconhecido.

## 3. Fluxos principais

1. **Descobrir.** Pautador Pro e salas de oportunidade: achar entidade, dor e recorte sem inventar volume.
2. **Preparar.** Hub de Tráfego, bancada e briefings: juntar prova, destino, orçamento e peça antes de qualquer mutate.
3. **Criar.** Estúdio, Laboratório, Assistente Criativo e cockpits de canal: produzir ou montar o que será publicado ou anunciado.
4. **Aprovar.** Filas humanas de peça, campanha e política. Aprovação não limpa evidência velha.
5. **Publicar.** WordPress, registro de mídia ou nascimento de campanha. Sempre com recibo e consequência nomeada.
6. **Monitorar.** Dashboard, campanha canônica, relatórios e atenção: leitura datada, não hero de KPI falso.
7. **Resolver exceção.** Fila de atenção, erro recuperável, bloqueio de segurança e falha que exige operador.

A hierarquia de uma tela é sempre: contexto, tarefa, filtros, workspace, detalhe.
O primeiro bloco operacional precisa caber no viewport inicial do desktop.

## 4. Contrato de verdade dos dados

Estes estados são distintos. Nenhum pode ser pintado como outro.

| Estado | Significa | Pode virar número zero? | Pode parecer botão disponível? |
|---|---|---|---|
| **Real** | Fonte observada, com horário e procedência | Só se a fonte mediu zero | Sim, se a ação estiver autorizada |
| **Demonstração** | Fixture, recorte explorável ou dado de ensaio | Não. Demo não prova operação | Só como ação de ensaio, rotulada |
| **Parcial** | Parte da leitura chegou, parte não | Não. Soma incompleta não vira total | Só para o recorte que ainda é seguro |
| **Bloqueado** | Segurança, política ou aprovação impedem o ato | Não | Não |
| **Indisponível** | Fonte ou integração não respondeu ou não está configurada | Não | Não. Explica o pré-requisito |
| **Erro** | A leitura ou a escrita falhou | Não. Último bom dado, se existir, fica datado | Retry visível quando for recuperável |
| **Desconhecido** | Ainda não houve leitura, ou o servidor omitiu o campo | Não | Não |
| **Zero real** | A fonte mediu zero | Sim, e o rótulo diz que foi medido | Depende da ação, não do zero |
| **Vazio** | A coleção existe e não tem itens | Não é métrica | CTA de povoar, se couber |
| **Vazio após filtro** | O universo tem itens; o recorte atual não alcança nenhum | Não | Limpar filtro |

Regras fechadas:

- Ausência não vira zero.
- Demo não vira dado real.
- Bloqueado não vira controle aparentemente disponível.
- "Não configurado" não vira "offline" nem "saudável".
- Um ponto verde fixo não afirma integração.
- Um número sem frescor não é número operacional.
- Stack trace, SQL, GAQL, PostgREST e nome de tabela não aparecem na interface do operador.

## 5. Taxonomia de ações

Cada região tem no máximo uma ação primária. O rótulo usa verbo e nomeia o resultado.

| Tipo | Exemplos | Tratamento |
|---|---|---|
| **Informativa** | Abrir detalhe, expandir linha, copiar ID | Secundária ou terciária. Sem confirmação. |
| **Reversível** | Limpar filtro, trocar aba, recolher menu | Imediata. Estado anterior recuperável. |
| **Preparatória** | Validar, gerar rascunho, montar receita | Primária da bancada. Não gasta. Explica o que ainda falta. |
| **Confirmatória** | Pausar, ativar, publicar, lançar, gravar custo | Explica escopo, consequência, reversibilidade e aprovação. |
| **Destrutiva** | Excluir execução, rejeitar peça, remover vínculo | Isolada, nunca primária da região, sempre confirma o que se perde. |
| **Externa** | Abrir conta no Google ou na Meta, ir ao WordPress | Deixa claro que sai do VOLC OS. |

Ação de gasto, publicação ou mudança de entrega nunca parece clique trivial.
Se a ação estiver indisponível, o controle explica o pré-requisito. Não some em silêncio, salvo quando a própria autorização da rota já desviou o operador por contrato existente de segurança.

## 6. Segurança e aprovação

- Identidade e papel vêm do servidor. A interface não inventa permissão.
- OPERATOR permanece no recorte que o roteador já autoriza. Esta revisão não altera esse contrato.
- Mutação de mídia, schema oficial, Storage, n8n remoto e geração paga ficam fora de qualquer redesign visual.
- Aprovação humana não apaga recibo velho. Um recibo novo é que limpa estado.
- Confirmação descreve o objeto, o efeito e se há desfazer.
- Modo demonstração, se existir na rota, declara-se no cabeçalho e em cada bloco de dado.

## 7. Hierarquia de atenção

1. Bloqueio de segurança ou ação ainda não autorizada.
2. Erro que impede a tarefa atual.
3. Atenção operacional com prova e próximo passo.
4. Dado parcial ou fonte indisponível.
5. Demonstração, para ninguém confundir com produção.
6. Contexto e navegação.

Um único sinal dominante por linha, painel ou etapa.
Cor nunca é o único portador: glifo + palavra +, quando necessário, uma frase.

## 8. Navegação

- Shell persistente: identidade, seções, busca, tema, alertas.
- Sidebar em desktop. Drawer em mobile, com Escape, foco e `inert` quando fechado.
- Skip link para o conteúdo em toda página com shell.
- Item ativo sobrevive a rota filha por segmento, não por prefixo cego.
- Breadcrumb quando a profundidade passa de dois níveis operacionais.
- Voltar restaura filtro, aba e posição de scroll.
- Command palette (`⌘K`) busca destinos e ações. Não substitui a navegação visível.
- URL é a fonte do recorte: `rede`, `nivel`, ids e query existentes não mudam de nome.

## 9. Densidade por tipo de tela

| Tipo | Densidade | Regra |
|---|---|---|
| Dashboard econômico | Alta, comparável | Números alinhados, frescor visível, sem grade de cartões idênticos para o mesmo tipo de fato. |
| Inventário e tabelas | Alta | Tabela, não cards. Grupo de conta é faixa, não segundo cartão. |
| Campanha canônica | Média-alta | Identidade, evidência, diagnóstico, linhagem, rail de ação. |
| Criativos e aprovações | Média | Objeto + estado + próxima decisão. Sem KPI decorativo. |
| Wizards e bancadas | Média | Um passo dominante, pedido ao lado, progresso real. |
| Configuração | Média | Formulário com label visível e erro no campo. |
| Identidade (login, senha) | Baixa | Marca pode aparecer. Workspace não copia essa atmosfera. |

Cards existem quando representam um objeto, uma elevação temporária ou um agrupamento real.
Não embrulhar tabela, filtro ou métrica comparável em cartão só para parecer acabado.

## 10. Copy e feedback

- Português direto, sentença, voz ativa.
- Sem "oops", sem ponto de exclamação em sucesso, sem metáfora vaga, sem jargão de modelo.
- Erro diz a causa e o caminho: tentar de novo, corrigir campo, pedir autorização.
- Loading acima de 300ms usa esqueleto do layout final, não spinner solto no vazio.
- Toast é transitório. Não é o único lugar de um erro de formulário.
- `aria-live` anuncia leitura assíncrona sem roubar foco.
- Disabled é opaco e não recebe clique. Read-only continua legível e focável.

## 11. Acessibilidade, performance e temas

- WCAG 2.2 AA: 4,5:1 texto normal, 3:1 texto grande e controle.
- Foco visível, ordem de tab igual à ordem visual, alvo de toque 44×44px no mobile.
- Label real acima do campo. Placeholder não substitui label.
- `prefers-reduced-motion` desliga motion não essencial. Troca de tema não anima.
- Breakpoints de prova: 375, 768, 1024, 1440.
- Sem overflow horizontal no mobile.
- Light e dark são pares, medidos os dois.
- Tipografia e cor vêm de tokens. Componente não carrega hexadecimal solto.

## 12. O que o produto deliberadamente não faz ainda

Esta lista não é roadmap disfarçado de feature. É recusa operacional.

- Não lança, valida nem altera campanha Meta ou Google a partir de um redesign visual.
- Não gera imagem ou texto pago só porque a tela ficou mais clara.
- Não trata n8n remoto, WordPress ou Supabase oficial como detalhe de interface.
- Não inventa saúde de integração no sidebar.
- Não oferece um segundo Ads Manager.
- Não automatiza gasto sem decisão humana.
- Não esconde dívida de dado atrás de zero, skeleton eterno ou cartão verde.

Anti-referências: dashboard genérico sem fonte; interface promocional em etapa de conferência; alerta só por cor; clique trivial em escrita ou gasto; hero de landing em rota operacional.
