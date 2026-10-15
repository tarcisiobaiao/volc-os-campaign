# Agenda do motor shadow da carteira (W13) — versionada, NÃO instalada

O motor (`tools/freedom-lab/src/volc_lab/sombra_carteira/`) gera um experimento
conferido por sha256 por campanha Google Ads da conta, no formato que a tela
`/trafego/sombra` e a seção da campanha (W7) já leem. Nada executa: a direção é
sombra, sem valor sugerido e sem botão.

## O que a agenda faz

`volc-sombra-carteira.timer` (08:00 em São Paulo, depois do D-1 às 06:30 e da
recoleta do W11 às 07:15) dispara `volc-sombra-carteira.service`, que roda
`run.sh`. Para cada conta de `VOLC_SOMBRA_CONTAS`:

1. lê `google_ads_campanha_dia` (custo, fato canônico v12_04: último valor por
   dia, recoleta incluída; nunca `daily_campaign_metrics`);
2. lê `receita_as_of(agora)` (receita datada na moeda de origem, v23_01/W12),
   paginada por `id`;
3. resolve o câmbio de cada dia NA LEITURA por `cambio_resolver(dia, par, max,
   agora)` (W12). O `receita_brl` gravado na ingestão não é usado: ele congela o
   câmbio daquele instante e não melhora quando a PTAX chega depois;
4. grava `gads-<campanha>-sombra-<as_of>/` e `_lotes/<lote>.json` em
   `VOLC_SOMBRA_DESTINO`.

O custo é paginado por `fato_id` (keyset): uma escrita concorrente não desloca
páginas, e página fora de ordem ou linha sem chave é recusada.

Só faz GET na tabela e POST nas RPCs `receita_as_of` e `cambio_resolver` (STABLE)
do Supabase oficial;
qualquer outro caminho é recusado no código antes da rede. Não lê o Google Ads.

## Travas

- **Não instalado.** Nenhuma unit está em `/etc/systemd/system`.
- **Desligado por configuração.** Mesmo instalado, `run.sh` sai 65 sem ler nada
  enquanto `VOLC_SOMBRA_HABILITADA` não for `sim` (`sombra.env.exemplo` vem `nao`).
- **Não reescreve experimento assinado.** O `as_of` é o INSTANTE da leitura
  (`gads-<campanha>-sombra-<aaaammdd>t<hhmmss>z`): uma segunda rodada no mesmo dia
  grava experimentos novos, mais recentes, que vencem na tela sem empate. Replay
  com os mesmos snapshots (mesmo `lido_em`) é idempotente; conteúdo diferente com
  o mesmo instante recusa o lote inteiro (saída 2) sem escrever nada.
- **Leitura vazia não é carteira vazia.** Fato de custo sem linha para a conta
  recusa o lote (saída 2): é coleta que não rodou.
- **Rodada interrompida** deixa os experimentos já gravados (cada um íntegro) e
  nenhum `_lotes/`; a tela mostra o mais recente de cada campanha e marca como
  "leitura velha" a linha mais de 2 dias atrás da mais nova.
- **flock**: uma execução por vez; a segunda sai 75.

## Configuração (sem segredo)

`/opt/volc-sombra-carteira/sombra.env`, a partir de `sombra.env.exemplo`:
contas, a trava e os parâmetros do laboratório (janela, dias imaturos, cliques
mínimos, fração máxima de custo sem receita, defasagem máxima do câmbio). O
horário muda por drop-in: `systemctl edit volc-sombra-carteira.timer` com outro
`OnCalendar=`.

## Segredo e isolamento

- **Usuário de serviço `volc-sombra`**, sem login, sem home e sem capacidade.
  `run.sh` recusa rodar como root (saída 64).
- **Só a service_role.** `/etc/volc-sombra-carteira/segredo.env` (root:root,
  0600, a partir de `segredo.env.exemplo`) tem uma linha: `SERVICE_ROLE_KEY=`.
  O systemd lê o arquivo como PID 1 antes de trocar de usuário, então o serviço
  não consegue reabri-lo. Nunca aponte o `EnvironmentFile` para
  `/root/supabase/docker/.env`: ele traz JWT_SECRET, a senha do Postgres e a do
  dashboard. Se alguma dessas chaves aparecer no ambiente, `run.sh` recusa
  (saída 64) sem ler nada.
- **Escrita só onde precisa.** `ProtectSystem=strict`; o destino é o
  `StateDirectory` (`/var/lib/volc-sombra-carteira`, dono `volc-sombra`) e a
  trava fica no `RuntimeDirectory` (`/run/volc-sombra-carteira`).
- **Hardening do systemd:** `NoNewPrivileges`, `PrivateTmp`, `PrivateDevices`,
  `ProtectHome`, proteções de kernel, cgroups, relógio e hostname, `ProtectProc`,
  namespaces e SUID bloqueados, só famílias IP/Unix, `SystemCallFilter=@system-service`.
  `systemd-analyze security --offline=true` dá **1,3 OK**; a unit anterior (root
  e o `.env` inteiro) dava 8,7 EXPOSED. O teste
  `tools/freedom-lab/tests/test_sombra_carteira_agenda.py` confere tudo isso.

## Pré-requisitos para ligar (decisão do dono)

1. v23_01 (W12) aplicada em produção: sem ela `receita_as_of` não existe e a
   leitura falha (contrato quebrado, saída 3 no motor, 1 no `run.sh`).
2. Coleta PTAX ligada: sem cotação recente, todo dia fica `cambio_defasado` ou
   `sem_cotacao` e toda campanha sai **sem dado** (é ausência, não zero). Como o
   câmbio é resolvido na leitura, a rodada seguinte à chegada da PTAX já converte
   os dias que ficaram para trás. Com `conhecido_ate`, a cotação legada sem
   `coletado_em` não aparece (regra do W12): vira `sem_cotacao`.
3. Coleta de custo (W11) ligada, para o fato ter a janela madura.
4. O backend que serve a tela precisa enxergar a pasta: `VOLC_EXPERIMENTOS_SHADOW_DIR`
   apontando para uma cópia de `VOLC_SOMBRA_DESTINO` (a Vercel não lê o disco do
   Hetzner; ver a decisão de deploy em `backend/app/trafego/recomendacao_shadow.py`).

## Instalar (quando autorizado)

```bash
useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin volc-sombra
install -d -o root -g root -m 0755 /opt/volc-sombra-carteira
install -d -o root -g root -m 0700 /etc/volc-sombra-carteira
install -o root -g root -m 0600 deploy/sombra-carteira/segredo.env.exemplo /etc/volc-sombra-carteira/segredo.env
# editar segredo.env: só o valor de SERVICE_ROLE_KEY do .env vivo, nada mais
# checkout do commit aprovado em /opt/volc-sombra-carteira/current
git -C /opt/volc-sombra-carteira/current rev-parse HEAD > /opt/volc-sombra-carteira/current/.base_ref
python3 -m venv /opt/volc-sombra-carteira/venv
/opt/volc-sombra-carteira/venv/bin/pip install 'jsonschema>=4.25,<5'
install -o root -g root -m 0755 deploy/sombra-carteira/run.sh /opt/volc-sombra-carteira/
install -o root -g root -m 0644 deploy/sombra-carteira/sombra.env.exemplo /opt/volc-sombra-carteira/sombra.env   # editar
cp deploy/sombra-carteira/volc-sombra-carteira.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemd-analyze security volc-sombra-carteira.service   # esperado: exposure ≤ 2
systemctl start volc-sombra-carteira.service       # uma rodada manual primeiro
systemctl enable --now volc-sombra-carteira.timer  # só depois de conferir o lote
```

Rollback: `systemctl disable --now volc-sombra-carteira.timer` e remover as
units. Os experimentos gravados não mudam nada fora da pasta.
