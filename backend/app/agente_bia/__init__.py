"""Bia — conversa de consulta do VOLC O.S. sobre o Hermes privado.

Camadas, na regra da casa:

    dominio.py        estados, transições, limites, filtro de resposta (puro)
    portas.py         o que a aplicação precisa do mundo (ledger, motor)
    aplicacao.py      casos de uso: conversa, histórico, envio, reconciliação
    configuracao.py   leitura e validação da configuração (flag, Hermes, CORS)
    infra_ledger.py   ledger no Supabase oficial, só por RPC nomeada
    infra_hermes.py   API Server do profile `default` do Hermes (a mesma Bia do
                      Telegram), sessão web própria, superfície sem ferramenta
    cors.py           CORS exato, só para `/api/agent/*`
    rotas.py          HTTP `/api/agent/*`
    gateway/          VOLC Agent Gateway: capacidades tipadas, só leitura na V1

A Bia V1 consulta e explica. Não existe aqui caminho de mutação operacional:
o plano de execução (`gateway/execucao.py`) declara as portas da proposta →
aprovação → execução → read-back → recibo e recusa todas.
"""
