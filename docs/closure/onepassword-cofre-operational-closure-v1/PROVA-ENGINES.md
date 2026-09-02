# Engines importados no Supabase oficial — Fase 4

**Medido em:** 2026-09-02 (UTC) · `database.agenciavolc.com.br`
**Caminho:** `scripts/importar_engines_no_cofre.py --sql` → `psql` → funções governadas
**Autoria:** `d267b400-7a08-42d6-a363-3f08e2ef7be5` / `tarcisio@agenciavolc.com.br`
— a identidade real da conta em `auth.users`, não um uuid inventado.

## Contagens

| Momento | ativos | engines | revisões `importacao_engine` | operações |
|---|---|---|---|---|
| antes | 0 | 0 | 0 | 0 |
| após a 1ª importação | 7 | 7 | 7 | 7 |
| **após reaplicar o mesmo SQL** | **7** | **7** | **7** | **7** |

Na segunda passada, os 7 statements devolveram `"idempotente": true`. Nada
duplicou: a chave de idempotência deriva do sha256 do manifesto.

## Os sete, com estado honesto

| ativo_id | estado | modalidade | estado operacional |
|---|---|---|---|
| `asset:engine:aprova-ad-studio-desktop-divergent` | inactive | imagem | `somente_referencia` |
| `asset:engine:aprova-ad-studio-official` | verified | imagem | `externo_parcial` |
| `asset:engine:motor-video-volc` | verified | video | `externo_parcial` |
| `asset:engine:positivo-ad-studio` | verified | imagem | `externo_parcial` |
| `asset:engine:prensa` | verified | imagem | `externo_parcial` |
| `asset:engine:volc-motor-imagem` | verified | imagem | `externo_parcial` |
| `asset:engine:volc-os-creative-port` | verified | misto | `catalogado` |

**Nenhum engine se declara integrado ao runtime.** Os três estados usados —
`somente_referencia`, `externo_parcial`, `catalogado` — são exatamente o que os
manifestos sustentam. O importador recusa afirmar mais que isso.

## Procedência preservada

Cada linha carrega `manifesto_fonte` e `manifesto_sha256`:

- `docs/creative-engines/motores-de-imagem.json` — sha `00dc0e95f2…` (6 engines)
- `docs/creative-engines/motores-de-video.json` — sha `b054b03b61…` (1 engine)

## Não-vazamento

O SQL emitido (553 linhas, 21.854 bytes) foi varrido antes de tocar o banco:
`op://` 0 · `/Users/` 0 · `password` 0 · `secret` 0 · `api_key` 0 · `cookie` 0 ·
`BEGIN RSA` 0 · `eyJ` 0. Nenhum caminho de disco local: `manifesto_fonte` é
relativo ao repositório.

A identidade do operador **não** está no artefato versionado — ela entra por
`psql -v autor_sub / autor_email`, porque identidade de operador não pertence a
arquivo em Git.
