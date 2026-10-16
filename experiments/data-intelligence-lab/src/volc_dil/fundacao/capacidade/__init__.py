"""Frente B da Fundação Data Intelligence: cadência, capacidade e coletor seguro.

- `cron`: execuções/dia e intervalos de agendas cron diárias;
- `volume`: modelo puro de linhas, versões (dedup), bytes e acumulados por horizonte;
- `cenarios`: jobs de coleta (atuais e propostos), escalas e cadências avaliadas;
- `quotas`: limites conhecidos de API com fonte/estado de confirmação e chamadas/dia;
- `coletor`: contrato `run_coleta` com trava de somente leitura e modo padrão `dry_run`.

Nada aqui faz I/O de rede ou banco. Números de bytes vêm de medição externa (script
`fundacao_capacidade_pg.py`) injetada como `PerfilBytes`.
"""
