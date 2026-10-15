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
2. lê `receita_as_of(agora)` (receita datada com câmbio versionado, v23_01/W12);
3. grava `gads-<campanha>-sombra-<as_of>/` e `_lotes/<lote>.json` em
   `VOLC_SOMBRA_DESTINO`.

Só faz GET na tabela e POST na RPC `receita_as_of` (STABLE) do Supabase oficial;
qualquer outro caminho é recusado no código antes da rede. Não lê o Google Ads.

## Travas

- **Não instalado.** Nenhuma unit está em `/etc/systemd/system`.
- **Desligado por configuração.** Mesmo instalado, `run.sh` sai 65 sem ler nada
  enquanto `VOLC_SOMBRA_HABILITADA` não for `sim` (`sombra.env.exemplo` vem `nao`).
- **Não reescreve experimento assinado.** Rodada repetida com o mesmo dado é
  idempotente; dado diferente no mesmo `as_of` recusa o lote inteiro (saída 2)
  sem escrever nada.
- **flock**: uma execução por vez; a segunda sai 75.

## Configuração (sem segredo)

`/opt/volc-sombra-carteira/sombra.env`, a partir de `sombra.env.exemplo`:
contas, destino e os quatro parâmetros do laboratório (janela, dias imaturos,
cliques mínimos, fração máxima de custo sem receita). O horário muda por
drop-in: `systemctl edit volc-sombra-carteira.timer` com outro `OnCalendar=`.
A service_role vem de `/root/supabase/docker/.env` (`SERVICE_ROLE_KEY`), como na
coleta.

## Pré-requisitos para ligar (decisão do dono)

1. v23_01 (W12) aplicada em produção: sem ela `receita_as_of` não existe e a
   leitura falha (contrato quebrado, saída 3 no motor, 1 no `run.sh`).
2. Coleta PTAX ligada: sem cotação recente, todo dia fica `cambio_defasado` e
   toda campanha sai **sem dado** (é ausência, não zero).
3. Coleta de custo (W11) ligada, para o fato ter a janela madura.
4. O backend que serve a tela precisa enxergar a pasta: `VOLC_EXPERIMENTOS_SHADOW_DIR`
   apontando para uma cópia de `VOLC_SOMBRA_DESTINO` (a Vercel não lê o disco do
   Hetzner; ver a decisão de deploy em `backend/app/trafego/recomendacao_shadow.py`).

## Instalar (quando autorizado)

```bash
install -d /opt/volc-sombra-carteira /var/lib/volc-sombra-carteira
# checkout do commit aprovado em /opt/volc-sombra-carteira/current
git -C /opt/volc-sombra-carteira/current rev-parse HEAD > /opt/volc-sombra-carteira/current/.base_ref
python3 -m venv /opt/volc-sombra-carteira/venv
/opt/volc-sombra-carteira/venv/bin/pip install 'jsonschema>=4.25,<5'
cp deploy/sombra-carteira/run.sh /opt/volc-sombra-carteira/
cp deploy/sombra-carteira/sombra.env.exemplo /opt/volc-sombra-carteira/sombra.env   # editar
cp deploy/sombra-carteira/volc-sombra-carteira.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl start volc-sombra-carteira.service       # uma rodada manual primeiro
systemctl enable --now volc-sombra-carteira.timer  # só depois de conferir o lote
```

Rollback: `systemctl disable --now volc-sombra-carteira.timer` e remover as
units. Os experimentos gravados não mudam nada fora da pasta.
