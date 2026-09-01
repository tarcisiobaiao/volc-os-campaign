"""Cofre de Ativos — o control plane do patrimonio digital da VOLC.

Camadas, na direcao que o CLAUDE.md pede:

    dominio.py         regras e modelos. Sem FastAPI, sem httpx, sem I/O.
    aplicacao.py       casos de uso e a PORTA do repositorio.
    infraestrutura.py  o adapter Supabase que implementa a porta.
    rotas.py           HTTP: adapta entrada e saida, decide status code.

A regra que atravessa as quatro: **segredo nao passa por aqui**. Este modulo
manipula REFERENCIA, postura, evidencia e proximo ato. O valor de qualquer
credencial vive no 1Password, e o endereco dele vive numa coluna que nenhuma
funcao de leitura do banco projeta (ver `supabase/migrations/v13_01`, secao 16).
"""
