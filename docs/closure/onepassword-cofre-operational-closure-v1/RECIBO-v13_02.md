# Recibo sanitizado — aplicação da v13_02 no Supabase oficial

**Momento:** 2026-09-02T01:50Z · **Autoridade:** `database.agenciavolc.com.br`
(verificada imediatamente antes) · **PostgreSQL:** 15.8 · **Papel:** `postgres`

## Artefato

| Campo | Valor |
|---|---|
| Migration | `supabase/migrations/v13_02_cofre_recusa_sem_vazar_linha.sql` |
| sha256 | `06c7b804119d1d66a25b01f622d3bc166db201935ada6601f2ac04291fd4aea7` |
| Bytes | 5.283 |
| Checksum confere com o commitado | sim (`git show HEAD:…` idêntico) |

## Backup, antes de qualquer escrita

| Campo | Valor |
|---|---|
| Caminho | `/root/backups/pre-v13_02-20260902T015026Z.dump` |
| Formato | custom (`pg_dump -Fc`) |
| Bytes | 2.514.218 (2.4M) |
| sha256 | `fb779be445a81963064cf8797c34e31d5c4e509ae4950a801bad928afee72ec1` |
| `pg_dump` exit | 0 |
| `pg_restore -l` exit | 0 · **2.422 itens** (TOC 2.429) · stderr vazio |
| Entradas `cofre_` no archive | 165 |
| Origem | `Dumped from database version: 15.8` |

Nenhuma connection string foi impressa.

## Estado antes

- v13_01 íntegra: 9 tabelas · RLS forçada em 9 · 0 policies · 28 funções
- v13_02 **ausente**, não parcial: gatilho 0, função 0
- 7 ativos · 7 engines · 0 credenciais · 7 operações · 7 revisões

## Aplicação

`psql -v ON_ERROR_STOP=1`, somente esta migration. Saída literal:

```
NOTICE:  v13_02: guardas ok (papel=postgres, versao=15.8)
NOTICE:  trigger "cofre_credencial_obrigatorios" ... does not exist, skipping
NOTICE:  v13_02 OK: gatilho instalado; a recusa por campo obrigatorio nao anexa mais a linha
```

## Contraprovas transacionais (BEGIN … ROLLBACK)

| # | Prova | Resultado |
|---|---|---|
| P1 | referência incompleta é recusada | **`23502`** (not_null_violation) |
| P2 | a recusa nomeia apenas o campo ausente | cita `owner_nome` |
| P3 | a recusa não contém o valor nem a referência | sem `op://`, sem `Failing row` |
| P4 | referência completa passa pelo contrato | 1 linha |
| P5 | escrita direta continua governada | `42501` para `service_role` |
| P6 | `UPDATE` que apaga campo obrigatório é recusado | recusado, sem eco |
| P7 | nenhuma leitura devolve o localizador | 20.624 bytes inspecionados, 0 `op://` |
| P8 | os 7 engines permanecem intactos | 7 |
| P9 | zero fixture após o rollback | estado idêntico ao de antes |

O localizador usado nas provas é sintético (`op://CofreSintetico/…`). Nenhuma
referência real, nenhum dado de Página, nenhum valor de segredo.

## Estado depois

| Medida | Antes | Depois |
|---|---|---|
| tabelas `cofre_*` | 9 | **9** |
| RLS forçada | 9 | **9** |
| policies | 0 | **0** |
| funções `cofre_*` | 28 | **29** (+ a função do gatilho) |
| gatilhos | 8 | **9** (+ `cofre_credencial_obrigatorios`) |
| grants a `PUBLIC`/`anon`/`authenticated`/`service_role` | 0 | **0** |
| ativos / engines / credenciais | 7 / 7 / 0 | **7 / 7 / 0** |

`v13_01` permanece íntegra. `v13_99` **não** foi executada.

## Estados do 1Password (só estados, sem identificadores)

| Condição | CLI | MCP |
|---|---|---|
| destrancado, aprovado | `ok` | `ok` |
| **trancado** | `blocked/sem_sessao` | `blocked/aprovacao_negada` |
| reautorizado | `ok` | `ok` |

Cache de metadados **desabilitado** na prova (`--cache=false`). **Nenhum valor
observado**, em nenhum momento. Não há aqui account id, user id, environment id,
referência `op://` completa, nem conteúdo de item real.
