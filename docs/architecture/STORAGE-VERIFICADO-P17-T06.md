# Storage com verificação real de bytes — P17-T06

Data: 01/09/2026 · Branch: `sprint/creative-factory-production-spine-v1`
Arquivos: `backend/app/criativo/bancada/armazenamento_verificado.py` (novo),
`backend/app/criativo/armazenamento.py`,
`backend/tests/test_criativo_storage_verificado.py` (novo).

## 1. O achado

O roadmap dava a máquina de armazenamento como provada. Ela estava provada — em
SQL, e num SQL que ainda não foi aplicado. A sequência
`LOCAL -> UPLOADED_UNVERIFIED -> VERIFIED_OK | VERIFIED_MISMATCH` existia em
exatamente dois lugares:

- `supabase/migrations/v11_03_execucao_criativa.sql`, gatilho
  `criativo_render_artefato_imutavel` (bloco "A MAQUINA DE ESTADOS DO
  ARMAZENAMENTO", linhas ~496–546);
- `scripts/provas-v11_03.sql`.

Medido nesta worktree, em 01/09/2026:

```
rg -n "UPLOADED_UNVERIFIED|VERIFIED_MISMATCH" --glob '!node_modules'
→ .sql, .json e .md apenas. Nenhum .py. Nenhum .ts.
```

Três consequências, e nenhuma delas some por si:

1. **Regra escrita não é regra em vigor.** A migração não foi aplicada; o gatilho
   não roda em lugar nenhum hoje.
2. **Mesmo aplicado, o gatilho não confere bytes.** Ele recusa *escritas* de
   linha inconsistentes no Postgres. Ele nunca lê o objeto no object storage —
   não é trabalho dele, e não há como ser.
3. **O código que sobe arquivo não conhecia nenhum desses estados.**
   `armazenamento.py` fazia `guardar()` e voltava `None`; quem chamava lia
   "voltou sem exceção" como "está lá, íntegro".

Este trabalho põe a máquina em Python, e o passo que o SQL não tem: **a
releitura**.

## 2. A máquina, e por que os nomes são os mesmos do gatilho

| Estado | Colunas em `criativo_render_artefato` | Significado |
|---|---|---|
| `LOCAL` | chave nula, conferência nula | existe no disco do operário e em lugar nenhum além |
| `UPLOADED_UNVERIFIED` | chave preenchida, conferência nula | subiu; **ninguém leu de volta** |
| `VERIFIED_OK` | chave + carimbo + hash remoto igual ao local | conferido |
| `VERIFIED_MISMATCH` | chave + carimbo + hash diferente (ou nulo) | divergência, terminal e registrada |

Setas permitidas, e só estas — as mesmas do gatilho:

```
LOCAL ──▶ UPLOADED_UNVERIFIED ──▶ VERIFIED_OK
  │                          └──▶ VERIFIED_MISMATCH
  └──────────────────────────────▶ VERIFIED_*    (upload e conferência no mesmo passo)
```

Nunca volta, nunca reaponta, `VERIFIED_*` é final. Os nomes ficaram em inglês,
iguais aos do SQL, de propósito: traduzir aqui faria a mesma máquina existir com
dois vocabulários, e a próxima divergência entre banco e aplicação apareceria
como uma discussão de tradução.

`estado_de(...)` classifica uma **linha** — as três colunas que o gatilho olha —
na mesma máquina, e `Publicacao.para_registro()` produz exatamente essas três
colunas. O teste `test_o_registro_reclassifica_no_mesmo_estado` fecha o ciclo nos
quatro desfechos: o que a publicação grava, `estado_de` lê de volta igual. É essa
ida e volta que impede aplicação e banco de terem duas noções de "verificado" —
a dupla verdade que a fila de trabalhos (P17-T04) já pagou para eliminar.

## 3. `UPLOADED_UNVERIFIED` é o estado que importa

É o nome do intervalo em que o produto **não sabe**. Ele costuma ser apagado por
um booleano `ok=True` escrito logo depois do upload, e apagá-lo é o que permite
um job terminar verde apontando para um objeto truncado.

`publicar_artefato()` só sai desse estado depois de:

1. **política** (`conferir_upload`: vazio, teto, MIME) — antes de tocar em
   qualquer destino;
2. **preflight de bucket** — antes de enviar byte;
3. **upload**, que leva a máquina a `UPLOADED_UNVERIFIED` **e a nada mais**;
4. **releitura remota** — `loja.ler(chave)`, o único passo capaz de dizer algo
   sobre o objeto que está lá;
5. **comparação de bytes E sha256**, e então o veredito.

Divergência **não** levanta exceção: `VERIFIED_MISMATCH` é resultado que precisa
ser registrado, e exceção é fácil demais de engolir num `except`. Levantam, sim,
bucket ausente e recusa de política — aí não há o que registrar porque nada
aconteceu.

## 4. As três ausências, que continuam distintas

| Situação | Tipo | Estado resultante | Por quê |
|---|---|---|---|
| o armazenamento respondeu "não tenho" | `ObjetoNaoEncontrado` | `VERIFIED_MISMATCH` | é resposta: o upload foi aceito e o objeto não está lá |
| ninguém respondeu (rede, timeout, 5xx) | `ArmazenamentoIndisponivel` | **continua** `UPLOADED_UNVERIFIED` | `VERIFIED_MISMATCH` é terminal; carimbá-lo por um timeout condenaria um artefato possivelmente íntegro |
| o destino não existe | `BucketAusente` | nenhum — recusa antes do upload | publicar em outro lugar é pior que não publicar |

No caso do objeto ausente na releitura, `storage_hash_conferido` fica **nulo**
com o carimbo preenchido: a conferência aconteceu e não havia o que hashear.
Preencher com o hash de bytes vazios inventaria um conteúdo que ninguém leu.

## 5. Defeitos corrigidos, com contraprova vermelha

### 5.1 `ArmazenamentoSupabase.existe()` colapsava falha em ausência

Código de `HEAD`:

```python
except (ObjetoNaoEncontrado, Exception):  # noqa: BLE001
    return False
```

Contraprova vermelha, rodada offline contra o arquivo de `HEAD` (com
`httpx.get`/`httpx.request` levantando `ConnectError`):

```
VERMELHO: com a rede caida existe() devolveu False - ausencia inventada
```

Depois da correção, o mesmo roteiro:

```
VERDE: levantou FalhaDeTransporte - GET .../object/criativos/... falhou: ConnectError
```

A cláusula era, além de perigosa, **inerte**: `Exception` já cobre
`ObjetoNaoEncontrado`, então o primeiro nome do `except` só servia para fazer o
colapso parecer intencional e revisado. Hoje `existe()` devolve `False` apenas
quando o armazenamento **disse** que não tem (ou quando a própria política recusa
a chave, caso em que não há consulta a fazer). Falha sobe.

### 5.2 Os dois 404 do Storage eram lidos como um só

O Supabase responde 404 tanto para `{"error":"Bucket not found"}` quanto para
`{"error":"Object not found"}`. Ler o primeiro como ausência de objeto faz o
produto concluir "ainda não subiu" e tentar de novo, para sempre, contra um
bucket que não existe. `_erro_de_404` desempata pelo corpo e devolve
`BucketAusente` no primeiro caso.

### 5.3 5xx virava `ArquivoRecusado`

`if r.status_code >= 400: raise ArquivoRecusado(...)` transformava falha do
servidor em acusação ao arquivo do operador — e, na rota, em 400. Agora 5xx é
`ArmazenamentoIndisponivel` (retry faz sentido) e 4xx segue `ArquivoRecusado`
(retry não resolve).

### 5.4 `guardar()` não podia afirmar conferência, e agora não consegue

`guardar()` devolvia `None`. Passou a devolver `EscritaNaoConferida`, cujo
`conferido` é **propriedade `Literal[False]`, não campo**: não existe construtor
capaz de afirmar conferência, e o teste
`test_nao_existe_construtor_capaz_de_afirmar_conferencia` prova isso pelos campos
do dataclass, não pelo comentário.

## 6. Preflight de bucket — fail-closed nos dois adaptadores

`select * from storage.buckets` em `database.agenciavolc.com.br` devolveu **zero
linhas** em 27/08/2026. O preflight (`conferir_bucket()`) existe nos dois
adaptadores:

- **Supabase**: `GET /storage/v1/bucket/{bucket}`; 404 → `BucketAusente` com
  motivo legível; ≥400 → `ArmazenamentoIndisponivel`. Só o **sucesso** é
  memorizado — memorizar o fracasso recusaria para sempre um bucket criado um
  minuto depois; e um 404 de bucket no meio de uma operação derruba a memória.
- **Local**: o diretório raiz existe e aceita escrita. Existe para que o caminho
  realmente exercido hoje também tenha o teste da recusa, e não só o adaptador
  que ninguém executa.

O preflight está em `guardar()`, não só em `publicar_artefato()`, porque
`execucao.py` chama `guardar()` direto. Nunca há queda silenciosa para local.

## 7. O adaptador remoto: implementado e DESARMADO

`ArmazenamentoSupabase` ganhou uma porta de transporte (`TransporteHTTP`), com
`TransporteHttpx` como implementação real. Isso torna o adaptador **provável sem
rede**: os testes exercitam upload, releitura, objeto ausente, bucket ausente,
rede caída, 5xx e leitura corrompida contra um duplo em memória que responde com
os mesmos códigos e corpos do Storage.

**Fronteira declarada, sem eufemismo:**

- nenhum teste desta casa fala com `database.agenciavolc.com.br`, e portanto
  **nada aqui prova o comportamento do Supabase real**;
- o bucket `criativos` **não existe**, e criá-lo é mudança de infraestrutura em
  produção que precisa de autorização externa — esta missão não a tem;
- `armazenamento_padrao()` continua devolvendo `ArmazenamentoLocal`;
- a migração `v11_03` continua **não aplicada**; o gatilho não está em vigor.

"Provider indisponível" não é "provider reprovado", e "implementado" não é
"ativado". Quando o bucket existir, ativar é trocar a instância em
`armazenamento_padrao()` e rodar o preflight — que é a única coisa capaz de dizer
que o bucket passou a existir.

## 8. A chave canônica por tenant/job/slot

`chave_canonica(tenant_id, job_id, slot, sha256, extensao)` →
`criativos/<tenant>/<job>/<slot>_<hash32>.<ext>`.

Duas diferenças deliberadas em relação a `armazenamento.chave_de_asset`, que
**não foi alterada** (segue servindo `execucao.py`):

1. o primeiro nível é o **tenant**, não o projeto — é por tenant que o acesso é
   decidido, e uma chave que começa pelo projeto obriga qualquer política de
   prefixo a conhecer o mapa projeto→tenant;
2. identificador fora do alfabeto é **recusado**, não normalizado.
   `chave_de_asset` aplica `.lower()` na chave inteira, então os tenants
   `Cliente` e `cliente` produzem a MESMA chave — dois inquilinos no mesmo
   endereço. O teste
   `test_identificador_fora_do_alfabeto_e_recusado_e_nao_normalizado` **mede esse
   colapso na função antiga** e prova a recusa na nova. Trocar o comportamento de
   `chave_de_asset` mudaria o endereço de todo artefato já gravado e não cabe
   nesta lane.

## 9. Provas

Gate focal:

```
.venv-worker/bin/python -m pytest \
  backend/tests/test_criativo_storage_verificado.py \
  backend/tests/test_criativo_estudio.py -q -p no:cacheprovider
→ 159 passed
```

Regressão focal (`-k "armazenamento or storage or asset"`): 97 passed.
Consumidores de `armazenamento.py` (`test_criativo_execucao`, `_bancada`,
`_parque`, `_producao_local`, `_rotas_equivalentes`): 212 passed.

**Mata-mutantes.** Um teste que passa com o comportamento quebrado é tautologia.
Sete mutações foram aplicadas ao código e a suíte teve de cair em cada uma:

| Mutação | Resultado |
|---|---|
| releitura substituída pelos bytes locais (o mutante clássico: hash local duas vezes) | MORTO |
| `existe()` volta a engolir toda exceção | MORTO |
| 404 sempre tratado como objeto ausente | MORTO |
| `guardar()` sem preflight | MORTO |
| `publicar_artefato` sem preflight | MORTO |
| falha de rede tratada como divergência terminal | MORTO |
| política conferida depois da escrita | MORTO |

Nenhum sobrevivente.

## 10. O que ainda depende de terceiro

1. **Criar o bucket `criativos`** no Supabase self-hosted — autorização externa,
   fora do escopo desta missão. Enquanto não existir, o preflight recusa, e é
   assim que deve ser.
2. **Aplicar `v11_03_execucao_criativa.sql`** para que o gatilho passe a vigorar.
   Só então as duas metades da máquina (banco e aplicação) estarão as duas em
   vigor; hoje só a de Python está.
3. **Ligar `publicar_artefato` ao executor** (`execucao.py` e a coluna
   `storage_conferido_em`): está fora do ownership desta lane. Hoje `execucao.py`
   chama `guardar()` direto e, portanto, o artefato nasce
   `UPLOADED_UNVERIFIED` — que é o estado honesto, e não mais um "verificado"
   presumido.
