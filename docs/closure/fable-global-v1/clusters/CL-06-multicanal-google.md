# CL-06 · Multicanal Google Ads (Display, Demand Gen, PMax)

**Horizonte**: A tardio / B · **Resultado**: um segundo canal nasce reutilizando
identidade, assets, prova, criação pausada e recibo do chassi Search.

## Estado factual (F005, F031, F010)

- Display: construtor completo na main (62 testes próprios; volc_ads 458),
  validate_only provado com cliente falso; falta SÓ a prova contra conta real (**D5**).
- Demand Gen: builder + 11 testes dentro da autonomous-closure (não na main);
  na main o canal falha por design (sem construtor no registry).
- PMax: candidato read-only de observabilidade `5eb6b38` nunca revisado
  (reviewers crasharam); aceite de P04-T07 já escrito no roadmap (delta
  não-commitado).
- Ponte criativa provada por dentro; caminho HTTP e UI sem linhagem (F031).

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W1-03 | (compartilhada) FF autonomous-closure traz o Demand Gen | 1 | — |
| M-W1-04 | (compartilhada) Revisão substituta + integração PMax obs 5eb6b38 | 1 | — |
| M-W2-07 | Demand Gen pós-merge: registrar canal, rodar gates na main, atualizar testes_subir | 2 | após M-W1-03 |
| M-W2-06 | (compartilhada) Colheita das worktrees dos fix-writers (demand-gen/orakul) | 2 | read-only |
| M-W3-11 | Elo HTTP+UI da linhagem de imagem (ProvarEntrada ganha campo; front renderiza Preparo.linhagem) | 3 | nenhum |
| M-W3-12 | validate_only real de Display na conta-laboratório | 3 | **D5** |
| M-W4+ | Radar Adios/Copycat/Vigenair (P04-T08); PMax coleta | 4 | — |

## Regra dura

Display AVISA (não recusa) quando falta linhagem — decisão deliberada mantida;
nenhum canal novo sem `EstruturaDoCanal` distinguindo as três ausências.
