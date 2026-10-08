# Perfil emocional do funil com JEV

## Objetivo

Transformar perguntas reais de busca, PAA e autocomplete em um **avatar comportamental do momento**, antes de o arquiteto desenhar as páginas. Ele descreve a tensão visível na demanda — não inventa idade, renda, personalidade ou história de vida.

O JEV é consultivo. Uma única chamada classifica todas as perguntas do funil. Se estiver desligado, sem chave, indisponível ou fora do contrato, o FunnelForge usa o fallback determinístico e continua. O perfil nunca prova fatos, nunca escreve a copy e nunca bloqueia uma página.

```text
PAA/termos reais
      ↓
JEV: família + força + entrega + momento (1 chamada)
      ↓
brief_pre_arquitetura.json (SHA-256)
      ↓
arquiteto: ordem, clímax, entregas e direção dos CTAs
      ↓
dossiê factual → redação paralela → revisão global
```

## As seis famílias

| Família | O que aparece na linguagem | Entrega que costuma reduzir a tensão | Clímax legítimo | Direção do CTA | Limite obrigatório |
|---|---|---|---|---|---|
| Oportunidade | “tenho direito?”, “é grátis?”, “quanto recebo?” | critérios, possibilidades e exemplos | revelar a possibilidade concreta e suas condições | nomear o ganho informacional da próxima página | possibilidade não é promessa de ganho ou aprovação |
| Incerteza | “quem pode?”, “qual regra?”, “isso vale para mim?” | explicação, confirmação e comparação | esclarecer o critério que muda a decisão | prometer a resposta específica que será esclarecida | não simular elegibilidade, saldo ou resultado pessoal |
| Medo de perder | “até quando?”, “ainda dá tempo?”, “vou perder?” | calendário, condição e alerta factual | mostrar a janela ou condição verificável | dizer o que conferir para não perder um próximo passo real | nunca criar escassez, prazo ou “última chance” |
| Desejo de controle | “como calcular?”, “como acompanhar?”, “quanto dá?” | cálculo, tabela, comparação ou acompanhamento | devolver um critério que o leitor consegue usar | levar ao cálculo, conferência ou comparação concreta | não prometer acesso a dados individuais inexistentes |
| Prevenção de erro | “quais documentos?”, “é golpe?”, “por que foi negado?” | checklist, correção e sinais de alerta | evitar o erro de maior consequência sustentado pelas fontes | mostrar o preparo ou erro evitável da próxima etapa | medo genérico e risco sem evidência são proibidos |
| Necessidade de ação | “como pedir?”, “onde sacar?”, “como me inscrever?” | passo a passo, localização e canal oficial | permitir que o leitor execute o próximo passo correto | usar verbo concreto e nomear o resultado informacional | não dizer que o site executa uma ação que apenas explica |

`ambigua` é uma saída válida quando a linguagem não sustenta nenhuma família. É melhor não forçar emoção do que construir um funil em cima de uma ficção.

## Checkpoints do contrato

### 1. Correspondência

Cada pergunta recebe uma distribuição entre as famílias. A família vencedora orienta o desenho, mas a distribuição preserva ambiguidades úteis. Não se converte confiança do modelo em “verdade sobre o usuário”.
Sinais, correlações e clímax também carregam o `duvida_id` estável do brief; índices existem apenas para inspeção humana e não devem governar links.

### 2. Quatro notas, de 0 a 100

- **Intensidade:** força explícita da tensão na frase.
- **Autorrelevância:** consequência pessoal sugerida pela pergunta.
- **Potencial de continuação:** chance de a resposta abrir outra dúvida útil, sem circular.
- **Urgência de ação:** necessidade aparente de executar um próximo passo.

Leitura operacional: 0–39 é sinal fraco; 40–69 é hipótese útil; 70–100 é candidato forte. A medição real pode contrariar qualquer faixa.

### 3. Entrega e momento

O JEV escolhe a forma de valor esperada — por exemplo critérios, cálculo, calendário ou passo a passo — e o momento provável: reconhecimento, qualificação, decisão, preparação, ação ou confirmação. O arquiteto decide se isso vira página, seção, FAQ ou ferramenta.

### 4. Correlação

- **Progressão:** tensões compatíveis em momentos adjacentes; candidata a ligação principal.
- **Complementar:** mesma tensão com entregas distintas; candidata a ligação secundária.
- **Possível redundância:** mesma família, entrega e momento; o arquiteto deve tentar fundir.

Correlação não é causalidade e não autoriza uma rota que contradiga a jornada factual.

### 5. Clímax

É a pergunta com maior combinação ponderada de intensidade, autorrelevância, continuação e ação. O clímax entrega o maior ganho de compreensão ou capacidade de decidir. Não é o ponto de maior ansiedade artificial.

### 6. CTA

O motor entrega uma direção, não um texto pronto. O arquiteto deve escrever o CTA com esta fórmula:

```text
verbo concreto + resposta/entrega específica + contexto necessário
```

Exemplos:

- “Ver quem pode receber e quais critérios contam”
- “Conferir o calendário e a próxima data”
- “Calcular a estimativa com a regra atual”
- “Separar os documentos antes de solicitar”

O CTA precisa corresponder à página de destino. Curiosidade sem entrega, urgência fabricada, falsa oficialidade e promessa individual são falhas.

## Validação que importa

O perfil só merece promoção depois de comparar, por país e idioma:

- CTR de continuação entre páginas;
- abandono depois da resposta imediata;
- páginas úteis por sessão;
- chegada ao canal oficial quando a tarefa estiver resolvida;
- receita por sessão e por mil entradas;
- taxa de revisão humana e falsos positivos por família.

Confiança do JEV é telemetria, não KPI de negócio. Idiomas e países devem ser calibrados separadamente.

## Canário real, sem publicar

O endpoint e o modelo seguem o contrato oficial do TypeSafe System One. A chave fica apenas na sessão do processo:

```bash
export TYPESAFE_API_KEY='sua-chave'
cd funnelforge-migracao/engine
.venv/bin/python scripts/canario_jev_emocoes.py \
  --tema 'Gás do Povo' --pais BR --idioma pt-BR \
  --pergunta 'Quem tem direito ao Gás do Povo?' \
  --pergunta 'Quando começa e até quando posso usar?' \
  --pergunta 'Como consultar se fui incluído?' \
  --pergunta 'O que fazer se o benefício não aparecer?' \
  --saida /tmp/canario-jev-gas-do-povo.json
```

O comando faz no máximo uma chamada, não lê `.env`, não publica e retorna código diferente de zero se o JEV cair no fallback. O recibo não contém a chave.

### Primeiro canário real

Em 08/10/2026, “Gás do Povo” foi avaliado em uma chamada: 688 ms, 4.446 tokens de entrada, 1.588 de saída, `jev-latest` servido como `jev-1.13.0` e nenhum fallback. A leitura apontou incerteza como família dominante, seguida de necessidade de ação e medo de perder; o clímax foi a dúvida sobre o que fazer quando o benefício não aparece. O provedor não informou custo. O resultado prova a integração, não a superioridade da jornada: isso depende do comparativo com/sem JEV e de sinal comportamental real.

## Critério de adoção

Começar com `jev_enabled=false`. Ativar só no canário e promover gradualmente se houver ganho de jornada/CTA ou redução de retrabalho sem piora de compliance, tempo e receita. Falha do fornecedor sempre continua fail-soft; o JEV não pode virar dependência crítica do nascimento do funil.
