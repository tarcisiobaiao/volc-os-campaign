# Replay do kernel de viabilidade

kernel `viability-kernel@1.0.0` · código `0056d0b1c786…` · replay_hash `9b9de21b16b7…`

| fixture | veredito | recomendação | confiança | manter | não lançar | igual | CPC médio | RPC médio | kernel marginal | invariantes |
|---|---|---|---|---|---|---|---|---|---|---|
| cambio_ausente | insufficient_evidence | coletar_evidencia | insufficient | continuar | parar | continuar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| campanha_favoravel | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| campanha_nova_sem_historico | test_with_cap | preparar_campanha_pausada | low | inconclusivo | nao_lancar | lancar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| curva_ultimos_20pct_destroem | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | expandir | continuar | expandir_ate_100000 | ok |
| custo_ausente | insufficient_evidence | coletar_evidencia | insufficient | inconclusivo | nao_lancar | lancar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| dados_imaturos | insufficient_evidence | aguardar_maturacao | insufficient | continuar | parar | continuar_igual | parar | parar | sem_curva | ok |
| limite_financeiro_ausente | insufficient_evidence | coletar_evidencia | insufficient | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| moeda_apenas_atestada | test_with_cap | propor_teste_limitado | medium | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| moeda_desconhecida | insufficient_evidence | coletar_evidencia | insufficient | continuar | parar | continuar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| proximo_do_equilibrio | test_with_cap | propor_teste_limitado | medium | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| receita_atrasada | insufficient_evidence | coletar_evidencia | insufficient | continuar | parar | continuar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| receita_ausente | insufficient_evidence | coletar_evidencia | insufficient | continuar | parar | continuar_igual | inconclusivo | inconclusivo | sem_curva | ok |
| receita_zero_observada | structurally_unviable | rejeitar_tese_economica | high | continuar | parar | continuar_igual | parar | parar | sem_curva | ok |
| roas_medio_bom_marginal_destroi | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | expandir | continuar | expandir_ate_100000 | ok |
| senac_sanitizada | structurally_unviable | rejeitar_tese_economica | medium | continuar | parar | continuar_igual | parar | parar | sem_curva | ok |
| simulacao_inexistente | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| simulacao_nao_monotonica | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |
| simulacao_pontos_duplicados | already_profitable | continuar_campanha_existente | high | continuar | parar | continuar_igual | continuar | continuar | sem_curva | ok |

Nenhuma superioridade é declarada: não há resultado maduro contra o qual medir. A tabela mostra onde regras ingênuas e o kernel divergem e por quê.
