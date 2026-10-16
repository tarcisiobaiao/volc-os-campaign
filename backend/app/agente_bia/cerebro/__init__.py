"""Cérebro VOLC pela web: rascunho pela Bia (sem ferramenta) + gravação tipada pelo servidor.

A Bia web não tem ferramentas e continua sem ter. `/salve` e `/cerebro` do
Telegram escrevem e fazem git com ferramentas do agente; aqui o desenho é outro:

1. **Rascunho** — um turno comum da conversa, com o pedido montado pelo
   SERVIDOR: a Bia devolve JSON com decisões, aprendizados, pendências e
   hipóteses. Nada é gravado.
2. **Gravação** — depois do "confirmar" do operador, o backend chama um
   executor determinístico no VPS (comando forçado de SSH, usuário próprio)
   que só sabe criar UM arquivo novo na estação `inbox/bia-web/` do cérebro
   escolhido, e ler o status git dos três. Sem commit, sem push, sem pull,
   sem editar arquivo existente.
"""
