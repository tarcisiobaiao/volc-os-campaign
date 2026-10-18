# Recibo de integração — Viability Kernel V2

Data: 17/10/2026  
Branch: `integration/data-foundation-viability-v2-20261017`

## Linhagem

- Fundação Data Intelligence recebida em `0f64e9b8`.
- Candidata Fable V2 fechada em `be81d4d0`.
- Correção final do contrato de câmbio em `127d9670`: taxa sem `de`/`para` nunca herda o par do ledger.
- Merge sem conflito sobre a fundação atual em `62854151`.
- Roadmap, curadoria e recibo reconciliados em `0b1a19ca`.
- Mapa Vivo reconstruído em `0c86303d`.

Nada foi mesclado no `main`, enviado ao remoto, implantado, aplicado no banco ou executado em produção.

## Provas reproduzidas na integração

- Suíte adversarial: **104 passed**.
- Viability Kernel: **332 passed**.
- Data Intelligence completa: **1287 passed, 3 skipped**.
- Replay: 18 fixtures, duas execuções com o mesmo hash
  `e76284c8e3293091119d16402009151b2e33ea713d71e889b9be87680f46590a`.
- Recibo do replay verificado pela CLI; `external_actions = 0`.
- `git diff --check`: limpo.
- Gitleaks no intervalo `0f64e9b8..HEAD`: nenhum segredo.
- Pacote de viabilidade sem imports de rede, banco ou SDK externo.

## Resultado da revisão final

R1, R2, R4, R5, R7 e R8 estão fechados por código e contraprovas. A revisão de integração encontrou e corrigiu um
caso que o relatório interrompido havia declarado verde indevidamente: câmbio com taxa, mas sem par explícito, ainda
era completado com as moedas observadas no ledger.

Continuam abertos por decisão consciente:

- **R3:** o hash da autorização prova integridade da referência, não autoria; a identidade precisa ser provada por
  assinatura ou ledger do lado VOLC.
- **R6:** receita projetada com gasto alto é limitada, não automaticamente interrompida; é política do owner.
- Premissas e limiares ainda são de laboratório, não calibração com operação madura.
- O kernel ainda não foi alimentado pelo snapshot real v21/JoinAds v2, não tem consumidor no cockpit/Bia e não roda
  em shadow agendado.

## Memória operacional

- `P14-T02` permanece **partial**: o kernel está provado offline, mas não existe shadow operacional nem autonomia.
- `P14-T09` permanece **todo**: existe cálculo marginal offline, mas não endpoint, cockpit ou modelo calibrado.
- `concept:data_intelligence_lab` permanece **inactive**.
- O Mapa Vivo foi reconstruído pelo pipeline oficial, sem `--refresh-live`; o gate final retornou `current: true`.

## Ambiente

O primeiro build do grafo bloqueou ao importar um `.pyc` `dataless` do ambiente Graphify guardado no Desktop/iCloud.
Ele foi interrompido sem efeito externo. O build foi repetido com Graphify 0.9.48 num venv temporário fora do iCloud e
concluiu normalmente, sem reutilizar a camada técnica.
