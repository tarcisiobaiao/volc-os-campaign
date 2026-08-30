# SPEC — P14-T10 v5: fronteira positiva de confiança

> ## ⛔ ESTA SPEC FOI REJEITADA NA REVISÃO ADVERSARIAL
>
> *Revisão de 2026-08-30, run `20260830-174525-230856`. Codex gpt-5.6-sol: **REJEITAR**;
> Gemini 3.7 Flash: aprovou. Prevalece a contraprova, conforme a regra de adjudicação
> do projeto.*
>
> **O defeito da v4 não foi eliminado — foi mudado de arquivo.** A SPEC propunha que
> `atestacao.py` recebesse um `DocumentoColeta` já construído e o selasse, mantendo
> `coletor.py` read-only. Mas:
>
> - `DocumentoColeta` é um `@dataclass` **público** (`modelo.py:101`) exportado em
>   `inteligencia_google/__init__.py:3-12`. Qualquer caller constrói um e pede o selo.
> - A emissão **não nasce na coleta**: `coletor.py:91-106` cria o documento, chama
>   `persistencia.registrar()` e devolve apenas `(coleta_id, estado)` — o documento fica
>   solto e nunca é selado. Selá-lo no nascimento **exige editar `coletor.py`**, que a
>   SPEC proibia.
> - O HMAC provaria apenas que **o assinador foi chamado**, não que o coletor obteve os
>   valores da API.
>
> E um achado que eu tinha perdido inteiramente: **não existe sequer ponte semântica.**
> O coletor produz `COM_DADOS`, `VAZIO_CONFIRMADO`, `INELEGIVEL`, `FALHOU` e documentos
> de recomendação/forecast, e **não modela receita diária** — que `ObservacaoDiaria`
> exige. Antes da fronteira de confiança falta o mapeamento de dados.
>
> A seção "Risco que registro" no fim deste documento também era **contraditória** com
> as afirmações absolutas nas seções 5 e 6, que prometiam autoridade que Python e um
> HMAC de processo não entregam.
>
> ### Redesenho exigido antes de qualquer v6
>
> 1. **Nenhuma função pública, em nenhum módulo importável, pode assinar um
>    `DocumentoColeta` solto.** A emissão entra em `ColetorGoogleInteligencia._persistir_familia`,
>    logo após `produzir()` e antes de persistir. Se `coletor.py` tiver de continuar
>    read-only, a missão vira **protótipo inelegível para contagens reais** — e diz isso.
> 2. **Agregado atômico** contendo documento, observações normalizadas e envelope, com
>    conversão determinística para `ObservacaoDiaria`. Enquanto o coletor não tiver
>    receita diária, **todo documento permanece `indeterminado`**.
> 3. **Separar emissor e verificador.** O Core verifica, nunca importa o emissor —
>    com regra AST em `isolamento.py` e teste. `origem`, `dataset_kind` e a flag real
>    passam a ser **resultado do verificador**, jamais campo do caller.
> 4. **Canonicalização versionada e ciclo de vida do selo**: campos cobertos, tipo
>    exato, UTC com microssegundos, `Decimal`, rejeição de `NaN`/`Infinity`, ordem de
>    coleções, identidade determinística. Declarar que o HMAC de processo é
>    *in-process* e **não sobrevive a restart**.
> 5. **Whitelist de `tipo_sinal`/`estado`** apta a contagens reais. Hoje não existe.
>
> P14-T10 **permanece BLOQUEADO**. Nada abaixo foi implementado. O texto original é
> preservado como registro da investigação, não como plano aprovado.

---


*Investigação read-only em `51b4e2e` · 2026-08-30 · nenhum código escrito*

## O achado que muda o desenho

O grafo sugeria `coletor.py`, `modelo.py` e `persistencia.py` como fronteiras. Os
três existem. Mas a investigação por construtores e chamadas reais mostra algo
que o grafo não dizia:

> **A ponte entre a coleta real e o ORAKUL Predictive não existe.**

- `ObservacaoDiaria` é construída em **dois lugares apenas**:
  `services/orakul_predictive/fixtures_sinteticas.py:40` (fixture sintética) e
  `backend/tests/orakul_predictive/test_mutantes.py:93` (teste). **Zero call
  sites de dado real.**
- **Nada fora do Core importa `orakul_predictive`** — ele não tem consumidor de
  produção.
- **Nada converte `DocumentoColeta` → `ObservacaoDiaria`.** Os únicos
  consumidores de `DocumentoColeta` fora do próprio módulo são dois testes.
- `services/orakul_predictive/isolamento.py:10-26` bane por AST imports de rede,
  Supabase e dotenv, e leitura de `.env*`. O Core é offline puro **por contrato**.

Isso reformula a missão: v5 não conserta uma fronteira defeituosa — **ela cria a
primeira**. E explica por que v3 e v4 falharam: sem uma fronteira real, qualquer
barreira dentro do Core é o Core autorizando a própria entrada.

## 1. Call sites que criam `ObservacaoDiaria`

| Arquivo | Linha | Natureza |
|---|---|---|
| `services/orakul_predictive/fixtures_sinteticas.py` | 40 | fixture sintética, `dataset_kind=DATASET_SINTETICO` fixo (`:52`) |
| `backend/tests/orakul_predictive/test_mutantes.py` | 93 | teste |

## 2. Quem decide hoje se uma observação é real

Ninguém atesta. `SourceReceipt.__post_init__` (`contratos.py:59-67`) valida
**forma**, não origem: `recibo_id`, `origem` e `hash_fonte` são strings livres do
caller e `entra_em_contagens_reais` é um bool que o caller escolhe. A única regra
material é `contratos.py:83-88`: se `dataset_kind == SINTETICO`, força
`entra_em_contagens_reais is False`. Todo o resto é declaração.

`avaliacao.py:129-132` confia nessa declaração para decidir contagens reais.

**É por isso que a fábrica pública `recibo_real_autorizado` do candidato
`7ee202e` era forjável: ela apenas formalizou o que já era livre.**

## 3. Onde dados Google Ads / n8n / Supabase entram no Predictive

Em lugar nenhum. Grep de imports em `services/orakul_predictive/*.py` por
`supabase|google|n8n|httpx|requests` retorna vazio, e `isolamento.py` proíbe por
AST. A entrada real hoje termina em `persistencia.py:84 registrar(documento)`,
que grava o `DocumentoColeta` no Supabase — e para por aí.

## 4. Primeiro dono confiável da origem

`ColetorGoogleInteligencia` (`volc_ads/inteligencia_google/coletor.py:59`, 528
linhas), cujo ponto de entrada é `executar_coleta(...)` (`:527`). Ele é quem fala
com a API, conhece `customer_id`, janela e modo, e produz `DocumentoColeta`
(`modelo.py:101`) com `Item`, `Metrica`, `EstadoValor` e `EstadoColeta`.

**Ele é o único componente que sabe, por construção, que o dado é real.**
Qualquer atestação criada depois dele é inferência.

## 5. Menor conjunto de arquivos para construção atômica

```
volc_ads/inteligencia_google/atestacao.py     (NOVO)  emite o envelope opaco
services/orakul_predictive/contratos.py       (EDITA) aceita envelope, perde a mintagem livre
services/orakul_predictive/features.py        (EDITA) exige envelope para contagens reais
backend/tests/orakul_predictive/              (EDITA) provas negativas
backend/tests/test_google_inteligencia_atestacao.py (NOVO) provas da emissão
```

**Desenho.** `atestacao.py` recebe o `DocumentoColeta` de quem o coletou, deriva
`hash_fonte` **internamente** dos bytes canônicos do documento, e devolve um
`EnvelopeAtestado` opaco — sem construtor público de campos livres. O Core passa
a aceitar **só** esse envelope como fonte de `entra_em_contagens_reais=True`.

Inversão essencial: hoje o Core decide se confia; depois, o Core **não tem como**
fabricar confiança — ela só chega de fora, já atestada.

## 6. Como impedir cada vetor que o Sol provou

| Vetor | Defesa |
|---|---|
| caller fornece `recibo_id`, `origem`, `hash_fonte` | remover o construtor público; `SourceReceipt` só nasce de `EnvelopeAtestado`, e `hash_fonte` é derivado internamente dos bytes do documento |
| `dataclasses.replace` promove procedência | envelope carrega HMAC sobre `(conteúdo, chave de processo)`; `replace` altera o conteúdo e invalida o selo |
| `deepcopy` transforma fixture em real | selo vincula-se ao **conteúdo da observação**, não à identidade do objeto; copiar preserva o selo mas também o conteúdo — e o conteúdo da fixture nunca teve selo válido |
| timestamp alterado promove dado | `lido_em` entra no conteúdo selado; +1 µs quebra o HMAC |
| recibos distintos com mesmo `hash_fonte` | comparar **identidade completa do envelope**, não só `hash_fonte` — corrige `proveniencia.py:61-80` |

Nada disso é criptografia inventada: um HMAC de processo sobre bytes canônicos,
com a chave nascendo e morrendo no processo de ingestão. Sem serviço externo,
sem rede — compatível com `isolamento.py`.

## 7. Preservar o que já está fechado

D1 (cutoff), D3 (hash completo) e D4 (semântica de alvos) e o quinto caminho
(representação canônica) estão fechados em `7ee202e` e confirmados por
contraprova. A v5 **parte de `7ee202e`** como base material — não como commit
integrado — e só substitui a camada de procedência. Gate obrigatório: as
contraprovas de D1/D3/D4 e do quinto caminho continuam verdes.

## 8. Testes negativos necessários

1. reconstruir fixture como `ObservacaoDiaria` base → inelegível;
2. `+1 µs` em `lido_em` sobre observação selada → selo inválido;
3. `dataclasses.replace` alterando valor, conta ou campanha → selo inválido;
4. `copy.copy` e `copy.deepcopy` do envelope → não promove fixture;
5. dois envelopes com mesmo `hash_fonte` e identidades diferentes → série recusada;
6. tentar construir `SourceReceipt` diretamente → impossível pela API pública;
7. envelope emitido para o documento A anexado a observações do documento B → recusado;
8. ausência de envelope → `indeterminada`, nunca `real`.

## 9. Ownership mínimo proposto

```
writable_paths:
  - volc_ads/inteligencia_google/atestacao.py
  - services/orakul_predictive/contratos.py
  - services/orakul_predictive/features.py
  - services/orakul_predictive/proveniencia.py
  - backend/tests/orakul_predictive
  - backend/tests/test_google_inteligencia_atestacao.py
  - docs/architecture/ORAKUL-PREDICTIVE-CORE-V1.md
```

`coletor.py` e `persistencia.py` ficam **read-only**: a v5 não muda a coleta, só
adiciona a emissão do envelope ao lado dela.

## 10. Colisões

- `services/orakul_predictive` e `backend/tests/orakul_predictive`: tocados só
  pela linhagem P14 (`75b1400`, `c2216cb`, `7ee202e`), toda ela fora da
  integração. **Sem colisão com os três commits convergidos.**
- `volc_ads/inteligencia_google`: mexido por `5c25e2e` e `94c4682`
  (health/deadman), já em HEAD. `atestacao.py` é arquivo novo — sem colisão.
- 11 worktrees citam ORAKUL ou inteligência no nome; nenhuma com processo vivo.
- **Sem interseção** com os ownerships de P04-T09 e P17-T09.

## Risco que registro

O envelope com HMAC de processo protege contra forja **dentro do processo**. Ele
não protege contra um atacante que já execute código arbitrário no processo de
ingestão — nesse cenário nada no Python protegeria. A garantia honesta é:
*"nenhum caller pode declarar dado real sem passar pela ingestão"*, não
*"impossível forjar"*. A documentação deve dizer exatamente isso.
