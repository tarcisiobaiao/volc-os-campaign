# ADR — nomenclatura Meta e sugestões de copy

Estado: aceito para implementação local em 10/09/2026.

## Decisão

A numeração de campanha pertence à conta física Meta, não ao assunto, funil,
Business Manager ou usuário. O servidor lê o histórico acessível da conta e
reserva `max(histórico, reservas) + 1` em transação com advisory lock e chave
única por conta/número. O mesmo rascunho/conta recupera a mesma reserva.
Não reciclar ao excluir/arquivar evita colisões com objetos já publicados.

Conjuntos e anúncios usam suas chaves estáveis no rascunho, nunca a posição na
lista. Trocar de conjunto atribui a numeração do novo pai e preserva a antiga.
Nomes são intenção editável; não substituem IDs Meta, tracking ou aprovação.
Atualizações automáticas preservam nomes que o operador editou manualmente.

`LP_R` deriva do primeiro segmento `/r/` da URL WordPress. Quiz é informação
explícita; rewarded não é deduzido da rota. Tags de conversão vêm do evento
selecionado ou do catálogo de conversões, com rótulo editável. Não inventar
gênero, posicionamento ou dimensões ausentes do contrato atual.

O assistente de copy oferece propostas por conjunto, até cinco opções por tipo.
Usa o cliente de texto configurado, sem acessar LP, imagens, ferramentas ou Meta.
O operador autorizou assunto, textos, briefing e URL sem credenciais/parâmetros;
não autorizou enviar conta, públicos, IDs ou imagens nesse ato. O navegador
guarda essas identidades apenas para invalidar propostas obsoletas.
Gerar não aplica, salva, aprova ou publica: aplicar exige clique e nova revisão.

## Alternativas rejeitadas

- Contador no navegador: duas abas/operadores podem colidir.
- Contador por assunto: viola a sequência global da conta.
- Renumerar após exclusão: invalida rastreio e pode reutilizar nomes publicados.
- Aplicar resposta do modelo automaticamente: sobrescreve intenção e permite
  uma resposta atrasada atingir outro conjunto.
- Copiar configuração da campanha ao modelo: excede o contexto autorizado.

## Limites

A API só informa histórico acessível ao token; dados definitivamente removidos
não podem ser reconstruídos. Números criados manualmente fora do VOLC depois
da leitura não participam do lock local. Lacunas na sequência são esperadas.
Arquivos de vídeo sem tamanho conhecido usam `VIDEO`, sem dimensão fictícia.
Criativos recebem sufixo do conjunto para não colidir entre dois `An1`.
No flexível, o primeiro nome do grupo é o nome do anúncio emitido; as linhas
seguintes são imagens desse anúncio, não anúncios extras.

Um limite de 100 páginas/90s evita leitura infinita; histórico parcial não
reserva. Copy tem timeout60s, uma chamada concorrente por usuário/processo e
cooldown5s, não quota distribuída. Não há retry pago oculto após JSON inválido.

## Referências

- [SDK oficial Meta: campanhas da conta](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py)
- [Funções PostgreSQL no Supabase](https://supabase.com/docs/guides/database/functions)
- Evidências: `docs/closure/meta-copy-naming-20260910/HANDOFF.md`.
