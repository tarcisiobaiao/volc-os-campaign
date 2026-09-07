#!/usr/bin/env python3
"""Gera o workflow n8n de leitura diaria de insights Meta Ads (campanha-dia, D-1).

Este gerador e irmao de `n8n/gerar_flows_gads_ledger_v12.py` e copia o desenho
dele de proposito: mesmos nos de defesa, mesma ordem, mesmos ids deterministicos
por nome. O que muda e o PROVEDOR — e, com ele, tres coisas que o fluxo Google
nao precisava responder:

1. **o dia nao e o dia do servidor.** Uma conta Meta reporta no FUSO DA CONTA.
   Perguntar "ontem" com a data do host n8n devolve, por algumas horas todas as
   noites, uma serie de um dia que a conta ainda nao comecou — e um zero medido
   entra no painel como se fosse resultado. A janela sai de `Config.TZ`? Nao:
   sai de `trafego_meta_ad_account.timezone_name`, conta a conta. Este e o
   defeito que o lado Python acabou de corrigir (`dominio.hoje_na_conta`) e o
   fluxo repete a mesma regra, nao uma aproximacao dela.

2. **a pergunta viaja com o numero.** `time_increment`, `action_report_time`,
   `breakdown` e as janelas de atribuicao SOLICITADAS sao configuracao explicita,
   vao no pedido e voltam no recibo. Nunca se carimba uma janela que nao foi
   pedida: sem janela pedida, a etiqueta e `default` (a conta decidiu), como
   manda `dominio.PedidoDeInsights.janela_declarada`.

3. **`actions` e `action_values` sao medidas diferentes.** Uma conta eventos, a
   outra soma dinheiro. O fluxo pede as duas, normaliza as duas separadamente e
   NUNCA soma uma na outra. E `landing_page_views` sai SO de
   `action_type == 'landing_page_view'` — somar `ViewContent` ali foi o defeito
   T05, e a contraprova esta em backend/tests/test_meta_workflows_n8n.py.

O que este gerador NAO faz: nao fala com a rede, nao chama a API do n8n, nao
importa, nao executa, nao ativa nada, nao le nem escreve credencial. A saida e
um JSON com `active: false` e uma credencial que NAO resolve — de proposito.

Uso:
    python3 n8n/gerar_flows_meta_ledger.py
    python3 n8n/gerar_flows_meta_ledger.py --check   # falha se o JSON mudou
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent
SUPABASE = "https://database.agenciavolc.com.br"
GRAPH_BASE = "https://graph.facebook.com"
API_VERSION = "v26.0"
CONTRATO_VERSAO = "meta-insights-dia-v1"
RPC_PERSISTIR = "trafego_meta_persistir_snapshot"

# ───────────────────────────────────────────────────────── credencial ──
#
# ⚠️ O QUE MUDOU, E POR QUE A PROVA ANTIGA DEIXOU DE DESCREVER A VERDADE.
#
# A versao anterior declarava `nodeCredentialType: "metaGraphApiNaoProvisionada"`
# — um tipo INVENTADO. A intencao era honesta (nao fingir integracao), mas o
# efeito era pior do que parar: um `nodeCredentialType` que nao existe no catalogo
# da instancia nao e "credencial pendente", e workflow INVALIDO. O n8n nao tem
# onde pendurar o item do cofre, o editor nao oferece o seletor, e o operador nao
# consegue provisionar nada nem depois de ter o token na mao. A lacuna deixava de
# ser uma pendencia e virava um beco sem saida.
#
# A troca e para um mecanismo REAL e ja usado nesta base:
# `authentication: "genericCredentialType"` + `genericAuthType: "httpHeaderAuth"`,
# a forma literal de `n8n/joinads_report_day_before.json:144-146` (parametros) e
# `:190-194` (bloco `credentials`). O tipo `httpHeaderAuth` e nativo do n8n, nao
# exige node community instalado, e guarda NOME e VALOR do cabecalho DENTRO do
# item do cofre — por isso o workflow nao precisa (e nao pode) saber nem o nome do
# cabecalho. A Graph API aceita o token por cabecalho, e essa e a unica forma que
# mantem o segredo fora da URL: `httpQueryAuth` colocaria o token na query string,
# onde ele vaza para log de proxy e para o historico de execucao do n8n.
#
# ⚠️ ID DE ITEM DE COFRE E REFERENCIA, NAO SEGREDO — mas ele ainda NAO EXISTE.
# Nada nesta base prova que a instancia tenha um item `httpHeaderAuth` com o token
# Meta (o inventario sanitizado em `docs/volc-os-graph/inventario-n8n-sanitizado.json`
# recusa o campo `id` de proposito e nao lista credencial nenhuma). Entao o id sai
# como um MARCADOR NOMEADO, e o workflow declara `credencial_provisionada: false`
# no proprio `meta.volc`. Quem for provisionar preenche `CRED_META_ITEM_ID` com o
# id do item criado no cofre e regera: o marcador some, `credencial_provisionada`
# vira `true`, e so entao `scripts/publicar_workflows_n8n_meta.py --apply` deixa de
# recusar. O bloqueio e mecanico, nao um lembrete.
#
# O que NUNCA aparece aqui, provisionado ou nao: token, app secret, id de app, id
# de conta, cabecalho de autorizacao montado a mao, `$env`, endpoint local.
CRED_META_TIPO = "httpHeaderAuth"
#: Id do item no cofre do n8n. VAZIO = ainda nao provisionado. Preencher aqui
#: (e SO aqui) e regerar e o unico passo que libera a publicacao.
CRED_META_ITEM_ID = ""
#: Marcador que ocupa o lugar do id enquanto o item nao existe. Nomeado de
#: proposito: `REPLACE_ME` aparece em fluxo de tres provedores diferentes nesta
#: base (JoinAds inclusive), e um grep por ele nao diz QUAL credencial falta.
CRED_META_ITEM_MARCADOR = "PROVISIONAR__VOLC_META_ADS_HEADER_AUTH"
CRED_META_ITEM_NOME = "VOLC Meta Ads · cabecalho do sistema · A PROVISIONAR"
CRED_META_PROVISIONADA = bool(CRED_META_ITEM_ID.strip())
CRED_META = {CRED_META_TIPO: {
    "id": CRED_META_ITEM_ID.strip() if CRED_META_PROVISIONADA else CRED_META_ITEM_MARCADOR,
    "name": CRED_META_ITEM_NOME,
}}
# A credencial do Supabase e uma REFERENCIA (id + nome do item no cofre do n8n),
# a mesma ja versionada nos fluxos Google e JoinAds.
CRED_SUPABASE = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}

# ─────────────────────────────────────────────────── contrato do pedido ──
#
# Espelha `backend/app/trafego/meta/dominio.py`. O validador
# (scripts/validar_workflows_n8n_meta.py) compara estes valores com os do modulo
# Python quando ele esta importavel; divergencia derruba o gate.
NIVEL = "campaign"
TIME_INCREMENT = "1"
ACTION_REPORT_TIME = "impression"
BREAKDOWN = "none"
#: Vazio = "nao pedi janela nenhuma"; o fato carrega `default`. Preencher aqui
#: (ex.: "7d_click,1d_view") faz o pedido levar `action_attribution_windows` E o
#: fato carimbar `1d_view+7d_click`. Carimbar sem pedir e proibido.
JANELAS_DE_ATRIBUICAO = ""
#: `action_values` e irmao de `actions`, nao derivado dele. Copia literal de
#: `dominio.CAMPOS_DE_INSIGHT`.
CAMPOS_DE_INSIGHT = (
    "account_id,campaign_id,adset_id,ad_id,date_start,date_stop,"
    "spend,impressions,reach,frequency,clicks,inline_link_clicks,"
    "cpm,cpc,ctr,actions,action_values"
)
#: Teto LOCAL de dias por pedido. Copia de `dominio.MAX_DIAS_POR_PEDIDO`.
MAX_DIAS_POR_PEDIDO = {"1": 92, "7": 366, "28": 731, "monthly": 731, "all_days": 731}
#: O unico action_type que e visualizacao da pagina de destino.
ACTION_TYPE_LPV = "landing_page_view"

# ────────────────────────────────────────────── contrato do snapshot RPC ──
#
# ⚠️ FORMA ASSUMIDA, DECLARADA AQUI PARA NAO VIRAR ACORDO TACITO.
#
# O envelope abaixo e o que este fluxo ENVIA para `trafego_meta_persistir_snapshot`.
# Ele estende — sem quebrar — o envelope que `backend/app/trafego/meta/read_model.py`
# ja monta (`payload_rpc()`): mesmos nomes para provider, account_ref,
# account_asset_id, credential_asset_id, window, observed_at, idempotency_key,
# snapshot_hash, page_count, counts, rows.
#
# O que o fluxo ACRESCENTA — e que, ate a migration
# `20260908000000_meta_insights_escopo.sql`, a RPC nao sabia ler:
#   • `escopo`            — "insights_pagina" | "insights_fechamento".
#                            v15_01:238 punha CHECK (escopo = 'hierarchy') em
#                            `trafego_meta_sync_run` e a RPC gravava 'hierarchy'
#                            FIXO (20260907210000:1203-1205): os dois valores do
#                            fluxo eram IMPOSSIVEIS de gravar. A migration nova
#                            alarga o CHECK e faz a RPC ler o escopo do envelope,
#                            com DEFAULT 'hierarchy' para o produtor Python atual,
#                            que nao o envia.
#   • `hierarchy_complete` — booleano OBRIGATORIO no escopo 'hierarchy'
#                            (20260907210000:713 levanta META_LEITURA_SEM_COMPLETUDE
#                            sem ele). O fluxo nunca le hierarquia, entao emite
#                            `false`: e a declaracao de que esta leitura NAO
#                            autoriza marcar ausencia de campanha nenhuma.
#   • `stable_idempotency_key` — a chave que NAO carrega o instante, na forma que
#                            o comentario-contrato de 20260907210000:1260-1272
#                            pede. Sem ela a RPC cai para a volatil e carimba
#                            `chave_origem: "volatil"` no recibo.
#   • `partiality`         — a RPC ja faz coalesce(p_snapshot->'partiality'), so
#                            que nada o preenchia. O fluxo preenche.
#   • `pedido`             — o registro sanitizado do pedido (nivel, periodo,
#                            fuso da conta, time_increment, action_report_time,
#                            breakdown, janelas solicitadas, janela declarada).
#   • `completo` / `motivo_incompleto` — o equivalente de
#                            `dominio.ResultadoDeInsights`.
#   • `marca_dagua`        — data ate a qual a leitura pode avancar. `null`
#                            quando `completo` e falso. A RPC NAO pode avancar
#                            marca d'agua com snapshot incompleto.
#   • `rows.trafego_meta_insight_action[].medida` — "count" para `actions` e
#                            "value" para `action_values`, NA MESMA tabela, com
#                            `ordem` continua entre as duas. A coluna `medida`
#                            chega na migration candidata do read model, e o
#                            backend passou a emitir as duas medidas do mesmo
#                            jeito. Reiniciar a numeracao nos valores faria uma
#                            linha de dinheiro sobrescrever uma de contagem.
#   • fechamento           — o snapshot de `escopo: "insights_fechamento"` e da
#                            EXECUCAO, nao de uma conta: `account_asset_id` vem
#                            `null` e `contas[]` traz um sub-recibo por conta.
#                            20260907210000:699 recusava snapshot sem conta; a
#                            migration nova troca isso por um CHECK CONDICIONAL —
#                            conta continua obrigatoria em 'hierarchy' e em
#                            'insights_pagina', e so o fechamento pode vir sem.
#
# A releitura de saude procura o fechamento por `chave_de_idempotencia`.
CONTRATO_RPC = {
    "rpc": RPC_PERSISTIR,
    "escopos": ["insights_pagina", "insights_fechamento"],
    "chave_snapshot": "^meta_snapshot_[a-f0-9]{32}$",
    "chave_idempotencia": "^meta_sync_[a-f0-9]{32}$",
    "tabelas_de_linha": [
        "trafego_meta_insight_daily",
        "trafego_meta_insight_action",
    ],
    "releitura": "trafego_meta_sync_run",
    "migration_base": "supabase/migrations/v15_02_meta_ads_insights.sql",
    "migration_vigente": "supabase/migrations/20260907210000_meta_read_model_consistency.sql",
    "migration_escopo": "supabase/migrations/20260908000000_meta_insights_escopo.sql",
    # ⚠️ ESCRITA, NAO APLICADA. A revisao que destrava os tres campos existe como
    # arquivo neste repositorio; nada aqui prova que ela rodou no banco oficial.
    # Enquanto ela nao for aplicada, a RPC vigente RECUSA o snapshot de
    # fechamento (sem conta) e o de pagina (sem `hierarchy_complete`). Declarar
    # `revisao_necessaria: false` sem essa distincao seria trocar uma pendencia
    # por uma afirmacao falsa.
    "revisao": "ESCRITA_NAO_APLICADA",
}

# ────────────────────────────────────────────────────────── code: comuns ──

# ⚠️ TRES blocos, e nao um so. Cada Code node do n8n carrega uma COPIA do texto
# que recebe: prender o SHA-256 inteiro em seis nos dobraria o arquivo que um
# humano revisa e deixaria o editor do n8n lento sem que nenhum deles usasse a
# funcao. Cada no leva exatamente o que chama — a lista de quem usa o que esta
# em `construir()`.
#
# Sem `require`: o Code node do n8n bloqueia builtins por padrao
# (NODE_FUNCTION_ALLOW_BUILTIN nao esta armada). Sem luxon e sem `crypto`:
# `Intl` resolve fuso, e o SHA-256 e JS puro. Depender de um global que pode nao
# existir no sandbox seria trocar um defeito silencioso por outro.

JS_TEMPO = r"""
// ── ajudantes: TEMPO E FUSO ─────────────────────────────────────────────────

function dataNaZona(instante, tz) {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(instante);
  const v = {};
  for (const p of partes) v[p.type] = p.value;
  if (!v.year || !v.month || !v.day) {
    throw new Error(`FUSO_INVALIDO: nao consegui ler a data em ${tz}`);
  }
  return `${v.year}-${v.month}-${v.day}`;
}

function horaNaZona(instante, tz) {
  const partes = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(instante);
  const v = {};
  for (const p of partes) v[p.type] = p.value;
  return { hora: v.hour, minuto: v.minute };
}

// Um fuso que o runtime nao conhece NAO pode virar UTC calado: viraria um dia
// errado com cara de dia certo.
function fusoUtilizavel(tz) {
  if (typeof tz !== 'string' || tz.trim() === '') return false;
  try {
    dataNaZona(new Date(), tz);
    return true;
  } catch (e) {
    return false;
  }
}

// Aritmetica de CALENDARIO, nao de milissegundos: subtrair 86400000 de um
// instante erra no dia em que o fuso muda. Aqui o dia sai da data local ja
// resolvida.
function subtrairDias(iso, n) {
  const [a, m, d] = iso.split('-').map(Number);
  // Sem `|| 0`: o padrao de ausencia esta proibido em todo este arquivo, porque
  // e assim que uma metrica ausente vira zero medido. Aqui a intencao e a
  // mesma disciplina — declarar o caso, nao encobri-lo.
  const passos = Number.isFinite(Number(n)) ? Number(n) : 0;
  const x = new Date(Date.UTC(a, m - 1, d) - passos * 86400000);
  const p = (v) => String(v).padStart(2, '0');
  return `${x.getUTCFullYear()}-${p(x.getUTCMonth() + 1)}-${p(x.getUTCDate())}`;
}

function diasEntre(inicioIso, fimIso) {
  const [a1, m1, d1] = inicioIso.split('-').map(Number);
  const [a2, m2, d2] = fimIso.split('-').map(Number);
  const t1 = Date.UTC(a1, m1 - 1, d1);
  const t2 = Date.UTC(a2, m2 - 1, d2);
  return Math.round((t2 - t1) / 86400000) + 1;
}

"""

JS_HASH = r"""
// ── ajudantes: IDENTIDADE ESTAVEL ───────────────────────────────────────────
// JSON estavel: mesma forma que `read_model._stable_json` (chaves ordenadas,
// sem espaco). O hash so e util se dois produtores da mesma verdade chegarem no
// mesmo texto.
function jsonEstavel(valor) {
  if (valor === null || valor === undefined) return 'null';
  if (typeof valor === 'number') return Number.isFinite(valor) ? String(valor) : 'null';
  if (typeof valor === 'boolean') return valor ? 'true' : 'false';
  if (typeof valor === 'string') return JSON.stringify(valor);
  if (Array.isArray(valor)) return '[' + valor.map(jsonEstavel).join(',') + ']';
  const chaves = Object.keys(valor).sort();
  return '{' + chaves.map((k) => JSON.stringify(k) + ':' + jsonEstavel(valor[k])).join(',') + '}';
}

// UTF-8 sem TextEncoder: o sandbox do Code node nao garante o global.
function bytesUtf8(texto) {
  const saida = [];
  for (let i = 0; i < texto.length; i += 1) {
    let c = texto.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < texto.length) {
      const prox = texto.charCodeAt(i + 1);
      if (prox >= 0xdc00 && prox <= 0xdfff) {
        c = 0x10000 + ((c - 0xd800) << 10) + (prox - 0xdc00);
        i += 1;
      }
    }
    if (c < 0x80) saida.push(c);
    else if (c < 0x800) saida.push(0xc0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) saida.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else saida.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
  }
  return saida;
}

// SHA-256 em JS puro. Existe para que a IDENTIDADE do fato calculada aqui seja
// a MESMA que `persistencia.linhas_de_insights()` calcula em Python
// (`meta_insight_` + sha256 do grao) e para que `snapshot_hash` e
// `idempotency_key` respeitem os CHECKs de `trafego_meta_sync_run`
// (`^meta_snapshot_[a-f0-9]{32}$` e `^meta_sync_[a-f0-9]{32}$`).
const SHA256_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function sha256Hex(texto) {
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
             0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const msg = bytesUtf8(texto);
  const bits = msg.length * 8;
  msg.push(0x80);
  while (msg.length % 64 !== 56) msg.push(0);
  const alto = Math.floor(bits / 4294967296);
  const baixo = bits >>> 0;
  msg.push((alto >>> 24) & 255, (alto >>> 16) & 255, (alto >>> 8) & 255, alto & 255);
  msg.push((baixo >>> 24) & 255, (baixo >>> 16) & 255, (baixo >>> 8) & 255, baixo & 255);

  const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0;
  const w = new Array(64);
  for (let bloco = 0; bloco < msg.length; bloco += 64) {
    for (let i = 0; i < 16; i += 1) {
      w[i] = ((msg[bloco + i * 4] << 24) | (msg[bloco + i * 4 + 1] << 16)
        | (msg[bloco + i * 4 + 2] << 8) | msg[bloco + i * 4 + 3]) >>> 0;
    }
    for (let i = 16; i < 64; i += 1) {
      const s0 = (rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)) >>> 0;
      const s1 = (rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)) >>> 0;
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i += 1) {
      const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (hh + S1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (S0 + maj) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0;
    h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0;
    h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
  }
  return h.map((x) => ('00000000' + x.toString(16)).slice(-8)).join('');
}

"""

JS_VALORES = r"""
// ── ajudantes: VALORES E ETIQUETAS ──────────────────────────────────────────
// A etiqueta da janela NUNCA promete uma janela que nao foi pedida.
// Espelha `dominio.PedidoDeInsights.janela_declarada`.
function janelaDeclarada(janelas) {
  if (!Array.isArray(janelas) || janelas.length === 0) return 'default';
  return janelas.slice().sort().join('+');
}

// Ausencia e ausencia; '' nao e zero. `Number('')` devolveria 0 e fabricaria
// medida onde a Meta nao mediu nada.
function num(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function inteiro(v) {
  const n = num(v);
  return n === null ? null : Math.trunc(n);
}
function texto(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}
"""

JS_IDENTIDADE = JS_TEMPO + JS_VALORES + r"""
// ── IDENTIDADE DA EXECUCAO ──────────────────────────────────────────────────
//
// ⚠️ A chave da execucao NAO carrega a janela coletada, e isso e uma diferenca
// deliberada em relacao ao fluxo Google. La existe UM fuso; aqui cada conta tem
// o seu, e "ontem" pode ser dia 12 numa conta e dia 11 na conta ao lado. Uma
// chave com uma janela unica mentiria sobre metade das contas. Entao a chave da
// execucao carrega a DATA DO DISPARO (rotulo da rodada, no fuso do workflow) e
// a janela real viaja por conta, dentro do recibo.
const cfg = $('Config').first().json;
const tzDisparo = String(cfg.TZ_DO_DISPARO || 'America/Sao_Paulo');
if (!fusoUtilizavel(tzDisparo)) {
  throw new Error(`FUSO_DO_DISPARO_INVALIDO: ${tzDisparo}`);
}
const modo = String(cfg.JANELA_MODO || '').toUpperCase();
if (modo !== 'D-1') {
  throw new Error(`JANELA_MODO_INVALIDO: ${cfg.JANELA_MODO}`);
}

const nivel = String(cfg.NIVEL || '');
if (['account', 'campaign', 'adset', 'ad'].indexOf(nivel) === -1) {
  throw new Error(`NIVEL_DESCONHECIDO: ${nivel}`);
}
const timeIncrement = String(cfg.TIME_INCREMENT || '');
if (['1', '7', '28', 'monthly', 'all_days'].indexOf(timeIncrement) === -1) {
  throw new Error(`TIME_INCREMENT_DESCONHECIDO: ${timeIncrement}`);
}
const actionReportTime = String(cfg.ACTION_REPORT_TIME || '');
if (['impression', 'conversion', 'mixed'].indexOf(actionReportTime) === -1) {
  throw new Error(`ACTION_REPORT_TIME_DESCONHECIDO: ${actionReportTime}`);
}
const breakdown = String(cfg.BREAKDOWN || 'none');
const BREAKDOWNS = ['none', 'publisher_platform', 'platform_position',
  'impression_device', 'device_platform', 'country', 'region'];
if (BREAKDOWNS.indexOf(breakdown) === -1) {
  throw new Error(`BREAKDOWN_FORA_DA_ALLOWLIST: ${breakdown}`);
}
if (nivel === 'account' && (breakdown === 'region' || breakdown === 'platform_position')) {
  throw new Error(`COMBINACAO_RECUSADA: ${breakdown} nao e correlacionavel em ${nivel}`);
}

const JANELAS_VALIDAS = ['1d_click', '7d_click', '28d_click', '1d_view', '7d_view',
  '28d_view', '1d_ev', '7d_ev', '28d_ev'];
const janelas = String(cfg.JANELAS_DE_ATRIBUICAO || '')
  .split(',').map((s) => s.trim()).filter(Boolean);
for (const j of janelas) {
  if (JANELAS_VALIDAS.indexOf(j) === -1) {
    throw new Error(`JANELA_FORA_DA_ALLOWLIST: ${j}`);
  }
}
if (new Set(janelas).size !== janelas.length) {
  throw new Error('JANELA_REPETIDA_NO_PEDIDO');
}

const agora = new Date();
const dataDoDisparo = dataNaZona(agora, tzDisparo);
const relogio = horaNaZona(agora, tzDisparo);

// Disparo: `isExecuted` diz qual gatilho acordou o fluxo. Se o no nem existir na
// execucao, tratamos como manual — nunca como agenda, porque declarar "agenda"
// numa rodada manual mentiria para o deadman.
let porAgenda = false;
try { porAgenda = Boolean($('Agenda').isExecuted); } catch (e) { porAgenda = false; }
const disparo = porAgenda ? 'agenda' : 'manual';

const passosConfigurados = String(cfg.PASSOS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);
function passoDaAgenda(hora) {
  let escolhido = passosConfigurados[passosConfigurados.length - 1];
  for (const p of passosConfigurados) {
    if (p <= hora) escolhido = p;
  }
  return escolhido;
}
let passo;
if (String(cfg.PASSO_FORCADO || '').trim() !== '') {
  passo = String(cfg.PASSO_FORCADO).trim();
} else if (disparo === 'agenda') {
  passo = passoDaAgenda(relogio.hora);
} else {
  // Rodada manual ganha passo proprio: repetir o mesmo minuto e idempotente, e
  // um minuto depois e outra leitura, com outro recibo.
  passo = `m${relogio.hora}${relogio.minuto}`;
}
if (!passo) throw new Error('PASSO_INDETERMINADO: PASSOS vazio no Config');

const job = String(cfg.JOB || '');
if (!/^[a-z0-9_]{3,40}$/.test(job)) throw new Error(`JOB_INVALIDO: ${job}`);

const diasDeReprocesso = Math.max(0, Number(cfg.DIAS_DE_REPROCESSO) || 0);
const tetos = JSON.parse(String(cfg.MAX_DIAS_POR_PEDIDO || '{}'));
const teto = Number(tetos[timeIncrement] || tetos['1'] || 92);
if (diasDeReprocesso + 1 > teto) {
  throw new Error(`REPROCESSO_ACIMA_DO_TETO: ${diasDeReprocesso + 1} dias excede`
    + ` o teto local de ${teto} para time_increment=${timeIncrement}`);
}

const execucaoChave = `${job}:${modo}:${dataDoDisparo}:${passo}`;
const contasPermitidas = String(cfg.CONTAS_PERMITIDAS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);
for (const c of contasPermitidas) {
  if (!/^[0-9]{1,40}$/.test(c)) {
    throw new Error(`CONTA_PERMITIDA_INVALIDA: a allowlist so aceita id numerico`);
  }
}
const filtroConta = contasPermitidas.length
  ? `&account_external_id=in.(${contasPermitidas.join(',')})`
  : '';

const prontidoes = String(cfg.PRONTIDOES_ACEITAS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);
if (prontidoes.length === 0) throw new Error('PRONTIDOES_ACEITAS_VAZIO');

return [{
  json: {
    fonte: 'n8n',
    provider: 'META_ADS',
    job,
    disparo,
    origem_janela: modo,
    data_do_disparo: dataDoDisparo,
    dias_de_reprocesso: diasDeReprocesso,
    passo,
    execucao_chave: execucaoChave,
    api_versao: String(cfg.GRAPH_API_VERSION || ''),
    contrato_versao: String(cfg.CONTRATO_VERSAO || ''),
    contrato_sha256: String(cfg.CONTRATO_SHA256 || ''),
    nivel,
    time_increment: timeIncrement,
    action_report_time: actionReportTime,
    breakdown,
    janelas_solicitadas: janelas,
    janela_declarada: janelaDeclarada(janelas),
    campos_de_insight: String(cfg.CAMPOS_DE_INSIGHT || ''),
    limite_por_pagina: Math.min(500, Math.max(1, Number(cfg.LIMITE_POR_PAGINA) || 100)),
    tz_do_disparo: tzDisparo,
    workflow_id: $workflow.id,
    execucao_externa_id: String($execution.id),
    iniciada_em: agora.toISOString(),
    contas_permitidas: contasPermitidas,
    url_contas: `${cfg.SUPABASE_URL}/rest/v1/trafego_meta_ad_account`
      + '?select=cofre_ativo_id,account_external_id,timezone_name,moeda,'
      + 'account_status,readiness_state,credential_ativo_id'
      + `&readiness_state=in.(${prontidoes.join(',')})`
      + `&order=cofre_ativo_id.asc&limit=500${filtroConta}`,
  },
}];
"""

JS_SELECIONAR_CONTAS = JS_TEMPO + JS_VALORES + r"""
// ── CONTAS AUTORIZADAS E A JANELA DE CADA UMA ───────────────────────────────
//
// ⚠️ AQUI MORA A PROPRIEDADE MAIS IMPORTANTE DESTE FLUXO.
//
// A janela D-1 e calculada NO FUSO DA CONTA, lido de
// `trafego_meta_ad_account.timezone_name`. Nao no fuso do servidor n8n, nao no
// `TZ_DO_DISPARO`, nao num padrao. Uma conta em America/Sao_Paulo lida por um
// host em UTC recebe, durante tres horas toda noite, o pedido de um dia que a
// conta ainda nao comecou: a Meta devolve serie vazia, e o painel desenha um
// zero medido para um dia que nao existiu. Foi exatamente este defeito que o
// lado Python corrigiu em `dominio.hoje_na_conta`.
//
// Conta sem fuso, ou com fuso que este runtime nao conhece, NAO cai num padrao:
// ela e recusada, com motivo, e a execucao registra a recusa. Um fuso chutado e
// pior que uma conta a menos.
const ident = $('Identidade da execucao').first().json;
const cfg = $('Config').first().json;
const permitidas = ident.contas_permitidas || [];
const agora = new Date();

const vistas = new Set();
const contas = [];
const recusadas = [];
for (const item of $input.all()) {
  const linha = item.json;
  if (linha === null || linha === undefined) continue;
  const externo = texto(linha.account_external_id);
  const ativo = texto(linha.cofre_ativo_id);
  if (externo === null || ativo === null) continue;
  const conta = externo.replace(/^act_/, '');
  if (!/^[0-9]{1,40}$/.test(conta)) {
    recusadas.push({ conta_ativo_id: ativo, motivo: 'ID_EXTERNO_INVALIDO' });
    continue;
  }
  if (permitidas.length && permitidas.indexOf(conta) === -1) continue;
  if (vistas.has(ativo)) continue;
  vistas.add(ativo);

  const fuso = texto(linha.timezone_name);
  if (fuso === null) {
    recusadas.push({ conta_ativo_id: ativo, motivo: 'CONTA_SEM_FUSO' });
    continue;
  }
  if (!fusoUtilizavel(fuso)) {
    recusadas.push({ conta_ativo_id: ativo, motivo: 'FUSO_DESCONHECIDO' });
    continue;
  }

  // Hoje NA CONTA, e so entao o dia anterior — aritmetica de calendario.
  const hojeNaConta = dataNaZona(agora, fuso);
  const janelaFim = subtrairDias(hojeNaConta, 1);
  const janelaInicio = subtrairDias(janelaFim, ident.dias_de_reprocesso);
  contas.push({
    conta_ativo_id: ativo,
    // Referencia OPACA: e o sufixo estavel do ativo do cofre
    // (`meta_account_metaacct_…`), o mesmo handle que
    // `dominio.referencia_opaca_conta` produz. E ela que vai para recibo,
    // alerta e log — nunca o id numerico.
    conta_ref: ativo.replace(/^meta_account_/, ''),
    conta_externa: conta,
    id_mascarado: `••••${conta.slice(-4)}`,
    credencial_ativo_id: texto(linha.credential_ativo_id),
    fuso_da_conta: fuso,
    moeda: texto(linha.moeda),
    hoje_na_conta: hojeNaConta,
    janela_inicio: janelaInicio,
    janela_fim: janelaFim,
    dias_na_janela: diasEntre(janelaInicio, janelaFim),
  });
}
contas.sort((a, b) => (a.conta_ativo_id < b.conta_ativo_id ? -1 : 1));

// Falha fechada. Zero conta autorizada NAO e "nada a fazer": ou o read model
// nao respondeu, ou a allowlist esta errada, ou nenhuma conta tem fuso. Seguir
// daria um recibo verde de uma rodada que nao leu nada.
if (contas.length === 0) {
  throw new Error('SEM_CONTA_AUTORIZADA: o read model nao devolveu conta Meta'
    + ' com fuso utilizavel para esta execucao; nada foi lido e nada sera'
    + ' declarado como vazio'
    + (recusadas.length ? ` (${recusadas.length} recusada(s))` : ''));
}

const ativos = contas.map((c) => c.conta_ativo_id);
const url = `${cfg.SUPABASE_URL}/rest/v1/trafego_meta_campaign`
  + '?select=meta_campaign_id,ad_account_ativo_id,external_id&limit=20000'
  + `&ad_account_ativo_id=in.(${ativos.join(',')})`;

return [{
  json: {
    ...ident,
    contas,
    total_contas: contas.length,
    contas_recusadas_na_selecao: recusadas,
    url_objetos: url,
  },
}];
"""

JS_MAPA_IDENTIDADE = r"""
// ── IDENTIDADE VOLC POR CONTA ───────────────────────────────────────────────
//
// Cada conta leva SO o seu pedaco do mapa. Carregar o mapa inteiro em todo item
// engordaria o laco sem necessidade, e ler o mapa com `$('No').all()` dentro do
// laco seria o acumulador global que este contrato proibe.
const base = $('Selecionar contas').first().json;
const porConta = {};
for (const item of $input.all()) {
  const linha = item.json;
  if (!linha) continue;
  const ativo = linha.ad_account_ativo_id === null || linha.ad_account_ativo_id === undefined
    ? null : String(linha.ad_account_ativo_id);
  const externo = linha.external_id === null || linha.external_id === undefined
    ? null : String(linha.external_id);
  const volc = linha.meta_campaign_id === null || linha.meta_campaign_id === undefined
    ? null : String(linha.meta_campaign_id);
  if (!ativo || !externo || !volc) continue;
  if (!porConta[ativo]) porConta[ativo] = {};
  porConta[ativo][externo] = volc;
}

return base.contas.map((conta, i) => ({
  json: {
    fonte: base.fonte,
    provider: base.provider,
    job: base.job,
    disparo: base.disparo,
    origem_janela: base.origem_janela,
    data_do_disparo: base.data_do_disparo,
    execucao_chave: base.execucao_chave,
    api_versao: base.api_versao,
    contrato_versao: base.contrato_versao,
    contrato_sha256: base.contrato_sha256,
    nivel: base.nivel,
    time_increment: base.time_increment,
    action_report_time: base.action_report_time,
    breakdown: base.breakdown,
    janelas_solicitadas: base.janelas_solicitadas,
    janela_declarada: base.janela_declarada,
    campos_de_insight: base.campos_de_insight,
    limite_por_pagina: base.limite_por_pagina,
    workflow_id: base.workflow_id,
    execucao_externa_id: base.execucao_externa_id,
    iniciada_em: base.iniciada_em,
    contas_tentadas: base.contas.map((c) => c.conta_ref),
    total_contas: base.total_contas,
    contas_recusadas_na_selecao: base.contas_recusadas_na_selecao,
    conta_ativo_id: conta.conta_ativo_id,
    conta_ref: conta.conta_ref,
    conta_externa: conta.conta_externa,
    id_mascarado: conta.id_mascarado,
    credencial_ativo_id: conta.credencial_ativo_id,
    fuso_da_conta: conta.fuso_da_conta,
    moeda: conta.moeda,
    hoje_na_conta: conta.hoje_na_conta,
    janela_inicio: conta.janela_inicio,
    janela_fim: conta.janela_fim,
    dias_na_janela: conta.dias_na_janela,
    conta_ordinal: i + 1,
    mapa_conta: porConta[conta.conta_ativo_id] || {},
  },
}));
"""

JS_PREPARAR_PAGINA = JS_VALORES + r"""
// ── PEDIDO DE UMA PAGINA ────────────────────────────────────────────────────
//
// ⚠️ UMA CONTA POR ITERACAO, e isso e decisao, nao descuido. O edge de insights
// e `/act_<conta>/insights`: um lote com N contas exigiria abrir o lote de novo
// dentro do laco, e o retorno do laco passaria a disparar mais de uma vez por
// iteracao — que e exatamente como um `SplitInBatches` pula lote. O lote de
// VOLUME e a pagina (`limit` linhas por chamada e por RPC).
//
// ⚠️ O QUE VAI NO FIO E O QUE FICA NO RECIBO. `parametros_graph` e montado uma
// vez e viaja inteiro: `level`, `time_range`, `time_increment`,
// `action_report_time`, `fields`, `limit` e — SO SE PEDIDAS —
// `action_attribution_windows` e `breakdowns`. Espelha
// `dominio.PedidoDeInsights.parametros_graph()`.
const itens = $input.all();
if (itens.length === 0) {
  throw new Error('LOTE_VAZIO: o laco entregou zero item');
}
if (itens.length > 1) {
  throw new Error(`LOTE_CONTAS_MAIOR_QUE_UM: ${itens.length} contas na mesma iteracao;`
    + ' o batchSize do laco precisa continuar 1 enquanto a chamada for por conta');
}
const ctx = itens[0].json;
const cfg = $('Config').first().json;

if (!ctx || String(ctx.conta_externa || '') === '') {
  throw new Error('CONTEXTO_PERDIDO: a iteracao chegou sem a conta a ler');
}
if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(ctx.janela_inicio || ''))
    || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(ctx.janela_fim || ''))) {
  throw new Error('JANELA_INVALIDA: a conta chegou sem periodo resolvido no fuso dela');
}
if (String(ctx.fuso_da_conta || '').trim() === '') {
  throw new Error('FUSO_AUSENTE: nao existe "ontem" sem o fuso da conta');
}

const pagina = Number(ctx.pagina || 0) + 1;
const teto = Math.max(1, Number(cfg.MAX_PAGINAS) || 50);
// ⚠️ DIFERENCA DELIBERADA EM RELACAO AO FLUXO GOOGLE. La estourar o teto e erro
// duro. Aqui a janela truncada e um RESULTADO INCOMPLETO declarado: a leitura
// para, o que ja foi lido continua valendo, e a marca d'agua NAO avanca. E o
// equivalente de `dominio.ResultadoDeInsights(completo=False, motivo=…)`.
const estourouOTeto = pagina > teto;

const campos = String(ctx.campos_de_insight || '');
if (campos.trim() === '') throw new Error('CAMPOS_DE_INSIGHT_VAZIO');
if (campos.indexOf('action_values') === -1 || campos.indexOf('actions') === -1) {
  throw new Error('CAMPOS_SEM_ACTIONS_OU_ACTION_VALUES: `actions` conta eventos e'
    + ' `action_values` soma dinheiro; uma nao se deriva da outra');
}

const janelas = Array.isArray(ctx.janelas_solicitadas) ? ctx.janelas_solicitadas : [];
const parametros = {
  level: String(ctx.nivel),
  time_range: JSON.stringify({ since: ctx.janela_inicio, until: ctx.janela_fim }),
  time_increment: String(ctx.time_increment),
  action_report_time: String(ctx.action_report_time),
  fields: campos,
  limit: Number(ctx.limite_por_pagina),
};
if (String(ctx.breakdown) !== 'none') parametros.breakdowns = String(ctx.breakdown);
// NUNCA enviar `action_attribution_windows` vazio: enviar a chave sem janela
// pediria "nenhuma janela" em vez de "a janela da conta".
if (janelas.length) parametros.action_attribution_windows = JSON.stringify(janelas);

const cursor = String(ctx.proximo_cursor || '');
if (cursor !== '') parametros.after = cursor;

return [{
  json: {
    ...ctx,
    pagina,
    estourou_o_teto: estourouOTeto,
    parametros_graph: parametros,
    // O `registro_do_pedido` de `dominio.PedidoDeInsights`: e isto que da
    // significado ao numero, e e isto que o recibo guarda.
    pedido: {
      nivel: String(ctx.nivel),
      periodo_inicio: String(ctx.janela_inicio),
      periodo_fim: String(ctx.janela_fim),
      fuso_da_conta: String(ctx.fuso_da_conta),
      time_increment: String(ctx.time_increment),
      breakdown: String(ctx.breakdown),
      action_report_time: String(ctx.action_report_time),
      janelas_solicitadas: janelas,
      janela_declarada: janelaDeclarada(janelas),
    },
    url_graph: `${cfg.GRAPH_BASE}/${ctx.api_versao}/act_${ctx.conta_externa}/insights`,
    acumulado: ctx.acumulado || {
      linhas_lidas: 0, linhas_aceitas: 0, linhas_rejeitadas: 0,
      acoes: 0, valores_de_acao: 0, paginas: 0,
    },
  },
}];
"""

JS_NORMALIZAR = JS_VALORES + r"""
// ── NORMALIZACAO DA PAGINA ──────────────────────────────────────────────────
//
// ⚠️ O contexto CHEGA NO ITEM, vindo do Merge — nao de
// `$('Pagina: preparar pedido')`. `$()` resolve pelo INDICE DA RODADA do no que
// pergunta, e uma conta que falha faz o pedido rodar mais vezes que a
// normalizacao: da segunda conta em diante, o contexto lido seria o da
// PRIMEIRA, com a mesma cara. `combineByPosition` casa resposta e contexto da
// MESMA iteracao.
//
// ⚠️ AUSENCIA NAO VIRA ZERO. `null` significa "a Meta nao devolveu"; `0`
// significa "a Meta mediu zero". Os dois viajam ate o banco, onde a coluna nao
// tem DEFAULT.
//
// ⚠️ `actions` e `action_values` sao SEPARADOS ate o fim. Contar eventos e
// somar dinheiro sao unidades diferentes; misturar as duas inventa receita.
const ctx = $input.first().json;
const corpo = ctx;

if (!ctx || String(ctx.conta_externa || '') === '') {
  throw new Error('CONTEXTO_PERDIDO: a iteracao nao trouxe a conta pedida');
}

const dados = Array.isArray(corpo && corpo.data) ? corpo.data : [];
const paging = (corpo && corpo.paging) || {};
// A Meta devolve `paging.cursors.after` MESMO na ultima pagina. Quem decide se
// existe proxima pagina e `paging.next`; usar o cursor como sinal pagina para
// sempre. Espelha `adaptador.ClienteMetaGraph._cursor`.
const temProxima = Boolean(paging && paging.next);
const cursorApos = paging && paging.cursors && typeof paging.cursors.after === 'string'
  ? paging.cursors.after.trim() : '';

let incompleto = null;
if (temProxima && cursorApos === '') {
  incompleto = 'META_INVALID_PAGINATION: paging.next sem cursor after';
}
if (temProxima && cursorApos !== '' && cursorApos === String(ctx.proximo_cursor || '')) {
  incompleto = 'META_PAGINATION_LOOP: cursor de paginacao nao avancou';
}
if (ctx.estourou_o_teto) {
  incompleto = `PAGINACAO_ACIMA_DO_TETO: a janela ${ctx.janela_inicio}..${ctx.janela_fim}`
    + ' passou do teto de paginas e ficou truncada';
}

const janelas = Array.isArray(ctx.janelas_solicitadas) ? ctx.janelas_solicitadas : [];
const janelaDoFato = janelaDeclarada(janelas);
const colhidaEm = new Date().toISOString();

// Expande as actions SEM achatar janela de atribuicao. Com
// `action_attribution_windows` pedidas, a Graph nao repete a linha por janela:
// devolve uma linha por action_type com UMA CHAVE POR JANELA. Ler so `value`
// colapsaria as janelas num numero cujo significado ninguem recupera.
// Espelha `adaptador.ClienteMetaGraph._acoes`.
function expandirAcoes(bruto, medida, inicio, fim) {
  if (bruto === null || bruto === undefined) return [];
  if (!Array.isArray(bruto)) {
    throw new Error(`META_INVALID_RESPONSE: ${medida} de insight nao e lista`);
  }
  const saida = [];
  for (const item of bruto) {
    if (!item || typeof item !== 'object') continue;
    const tipo = texto(item.action_type) || 'unknown';
    const presentes = janelas.filter((j) => Object.prototype.hasOwnProperty.call(item, j));
    if (presentes.length) {
      for (const janela of presentes) {
        saida.push({
          action_type: tipo,
          value: num(item[janela]),
          attribution_window: janela,
          object_level: String(ctx.nivel),
          date_start: inicio,
          date_stop: fim,
          medida,
        });
      }
      continue;
    }
    saida.push({
      action_type: tipo,
      value: num(item.value),
      attribution_window: janelaDoFato,
      object_level: String(ctx.nivel),
      date_start: inicio,
      date_stop: fim,
      medida,
    });
  }
  return saida;
}

// Landing page views e SO `landing_page_view`. Somar
// `offsite_conversion.fb_pixel_view_content` ali foi o defeito T05: LPV e medido
// pela Meta quando a pagina carrega; ViewContent e evento do pixel do site, com
// outra definicao e outro dono. LPV=4 + ViewContent=7 devolvia 11, um numero que
// nao e nenhuma das duas medidas. E action presente sem valor medido devolve
// null, nunca zero. Espelha `adaptador._landing_page_views`.
function landingPageViews(acoes) {
  const relevantes = acoes.filter(
    (a) => a.medida === 'count' && a.action_type === 'landing_page_view');
  if (relevantes.length === 0) return null;
  if (relevantes.some((a) => a.value === null)) return null;
  let total = 0;
  for (const a of relevantes) total += Math.trunc(a.value);
  return total;
}

const fatos = [];
for (const linha of dados) {
  if (!linha || typeof linha !== 'object') {
    throw new Error('META_INVALID_RESPONSE: insight nao e objeto');
  }
  const contaDevolvida = texto(linha.account_id);
  if (contaDevolvida !== null
      && contaDevolvida.replace(/^act_/, '') !== String(ctx.conta_externa)) {
    throw new Error('IDENTIDADE_DIVERGENTE: a resposta trouxe outra conta Meta');
  }

  const inicio = texto(linha.date_start) || String(ctx.janela_inicio);
  const fim = texto(linha.date_stop) || String(ctx.janela_fim);
  let objeto;
  if (ctx.nivel === 'account') objeto = String(ctx.conta_externa);
  else if (ctx.nivel === 'campaign') objeto = texto(linha.campaign_id);
  else if (ctx.nivel === 'adset') objeto = texto(linha.adset_id);
  else objeto = texto(linha.ad_id);

  const acoes = expandirAcoes(linha.actions, 'count', inicio, fim);
  const valores = expandirAcoes(linha.action_values, 'value', inicio, fim);

  fatos.push({
    provider: 'META_ADS',
    conta_externa: String(ctx.conta_externa),
    conta_ativo_id: String(ctx.conta_ativo_id),
    nivel: String(ctx.nivel),
    objeto_externo: objeto,
    volc_objeto_id: (ctx.mapa_conta || {})[objeto] || null,
    periodo_inicio: inicio,
    periodo_fim: fim,
    janela_atribuicao: janelaDoFato,
    breakdown: String(ctx.breakdown),
    observado_em: colhidaEm,
    time_increment: String(ctx.time_increment),
    action_report_time: String(ctx.action_report_time),
    fuso_da_conta: String(ctx.fuso_da_conta),
    janelas_solicitadas: janelas,

    spend: num(linha.spend),
    impressions: inteiro(linha.impressions),
    reach: inteiro(linha.reach),
    frequency: num(linha.frequency),
    clicks: inteiro(linha.clicks),
    inline_link_clicks: inteiro(linha.inline_link_clicks),
    landing_page_views: landingPageViews(acoes),
    cpm: num(linha.cpm),
    cpc: num(linha.cpc),
    ctr: num(linha.ctr),

    actions: acoes,
    action_values: valores,
  });
}

// O ordinal do lote e o indice da rodada DESTE no, que so executa quando a
// chamada a Meta deu certo. Assim a sequencia de lotes fica contigua e o
// fechamento consegue acusar lote perdido.
const loteOrdinal = Number($runIndex) + 1;
if (!Number.isInteger(loteOrdinal) || loteOrdinal < 1) {
  throw new Error(`LOTE_ORDINAL_INVALIDO: ${loteOrdinal}`);
}

return [{
  json: {
    ...ctx,
    lote_ordinal: loteOrdinal,
    fatos,
    linhas_lidas_na_pagina: fatos.length,
    proximo_cursor: incompleto === null && temProxima ? cursorApos : '',
    tem_proxima_pagina: incompleto === null && temProxima,
    motivo_incompleto: incompleto,
    pagina_lida_em: colhidaEm,
  },
}];
"""

JS_VALIDAR = JS_HASH + r"""
// ── VALIDACAO SEMANTICA E MONTAGEM DO SNAPSHOT ──────────────────────────────
//
// O banco valida de novo, e isso e de proposito: aqui a recusa vira motivo
// legivel no recibo, la ela vira constraint. Duas redes, a mesma regra.
//
// ⚠️ METRICAS NAO ADITIVAS. `reach`, `frequency`, `cpm`, `cpc` e `ctr` NAO
// podem ser somadas entre dias, objetos ou breakdowns — somar alcance de sete
// dias produz um numero maior que as pessoas alcancadas. O fluxo nao soma
// nenhuma delas em lugar nenhum; guarda linha a linha e deixa a soma para quem
// sabe recalcular pelos denominadores.
const ctx = $input.first().json;
const fatos = Array.isArray(ctx.fatos) ? ctx.fatos : [];

const TAXAS = ['ctr'];
const NAO_NEGATIVAS = ['spend', 'impressions', 'reach', 'frequency', 'clicks',
  'inline_link_clicks', 'landing_page_views', 'cpm', 'cpc'];

const boas = [];
const recusadas = [];
const chaves = new Set();

for (let i = 0; i < fatos.length; i += 1) {
  const f = fatos[i];
  let motivo = null;

  if (!/^[0-9]{1,40}$/.test(String(f.conta_externa || ''))) motivo = 'CONTA_INVALIDA';
  else if (f.nivel !== 'account' && !/^[0-9]{1,40}$/.test(String(f.objeto_externo || ''))) motivo = 'OBJETO_INVALIDO';
  else if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(f.periodo_inicio || ''))) motivo = 'PERIODO_INICIO_AUSENTE';
  else if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(f.periodo_fim || ''))) motivo = 'PERIODO_FIM_AUSENTE';
  else if (f.periodo_fim < f.periodo_inicio) motivo = 'PERIODO_INVERTIDO';
  else if (f.periodo_inicio < ctx.janela_inicio || f.periodo_fim > ctx.janela_fim) motivo = 'DATA_FORA_DA_JANELA';
  else if (String(f.janela_atribuicao || '') !== String(ctx.janela_declarada)) motivo = 'JANELA_CARIMBADA_SEM_PEDIDO';

  if (motivo === null) {
    for (const campo of TAXAS) {
      const v = f[campo];
      if (v !== null && (typeof v !== 'number' || v < 0 || v > 1)) {
        motivo = `TAXA_FORA_DE_0_1:${campo}`;
        break;
      }
    }
  }
  if (motivo === null) {
    for (const campo of NAO_NEGATIVAS) {
      const v = f[campo];
      if (v !== null && (typeof v !== 'number' || v < 0)) {
        motivo = `VALOR_NEGATIVO_OU_NAO_NUMERICO:${campo}`;
        break;
      }
    }
  }
  if (motivo === null) {
    const chave = `${f.nivel}|${f.objeto_externo}|${f.periodo_inicio}|${f.periodo_fim}`
      + `|${f.janela_atribuicao}|${f.breakdown}`;
    if (chaves.has(chave)) motivo = 'LINHA_DUPLICADA_NA_PAGINA';
    else chaves.add(chave);
  }

  if (motivo === null) boas.push(f);
  else recusadas.push({ ordinal: i + 1, motivo });
}

// ── linhas, na forma exata de `persistencia.linhas_de_insights()` ───────────
//
// A identidade do fato inclui `observado_em`: reler um dia passado NAO duplica
// gasto, produz uma REVISAO nova do mesmo grao. Quem le resolve pela projecao
// mais recente. Por isso o id e o mesmo que o Python calcularia — sha256 do
// grao com o instante da observacao.
// A completude da JANELA e decidida antes do laco porque ela entra em cada
// linha do fato: uma janela truncada precisa marcar TODAS as linhas que ela
// produziu, e nao so o recibo. Declarar depois do laco deixava a linha lendo a
// constante antes da inicializacao.
const completo = ctx.motivo_incompleto === null || ctx.motivo_incompleto === undefined;
const insightDaily = [];
const insightAction = [];
for (const f of boas) {
  // ⚠️ ESTA LISTA E A MESMA, NA MESMA ORDEM, de
  // `backend/app/trafego/meta/persistencia.py::linhas_de_insights`. Os dois
  // produtores precisam gerar o MESMO `meta_insight_daily_id` para o mesmo
  // fato: se divergirem, o mesmo dia entra duas vezes com duas chaves e a
  // projecao `latest` passa a expor duas "revisoes correntes" do mesmo grao.
  // Mexeu num lado, mexa no outro na mesma mudanca.
  const identidade = [
    f.provider, f.conta_externa, f.nivel, f.objeto_externo,
    f.periodo_inicio, f.periodo_fim, f.janela_atribuicao, f.breakdown,
    f.time_increment, f.action_report_time, f.fuso_da_conta || '',
    f.observado_em,
  ].join('|');
  const fatoId = 'meta_insight_' + sha256Hex(identidade);
  insightDaily.push({
    meta_insight_daily_id: fatoId,
    ad_account_ativo_id: f.conta_ativo_id,
    provider: f.provider,
    conta_externa: f.conta_externa,
    nivel: f.nivel,
    objeto_externo: f.objeto_externo,
    periodo_inicio: f.periodo_inicio,
    periodo_fim: f.periodo_fim,
    janela_atribuicao: f.janela_atribuicao,
    breakdown: f.breakdown,
    // O grao inteiro chega a linha. Sem estes campos uma serie diaria e uma
    // linha agregada do mesmo periodo ficam indistinguiveis — e somaveis.
    time_increment: f.time_increment,
    action_report_time: f.action_report_time,
    account_timezone: f.fuso_da_conta,
    currency: ctx.moeda || null,
    completo: completo,
    observado_em: f.observado_em,
    spend: f.spend,
    impressions: f.impressions,
    reach: f.reach,
    frequency: f.frequency,
    clicks: f.clicks,
    inline_link_clicks: f.inline_link_clicks,
    landing_page_views: f.landing_page_views,
    cpm: f.cpm,
    cpc: f.cpc,
    ctr: f.ctr,
  });
  // `actions` (contagem) e `action_values` (dinheiro) vao para a MESMA tabela,
  // separadas pela coluna `medida`, com `ordem` CONTINUA entre as duas. A chave
  // e (fato, ordem): reiniciar a numeracao nos valores faria cada linha de
  // dinheiro sobrescrever uma linha de contagem, e o total de eventos viraria o
  // total em reais sem nada reclamar. A RPC recusa a colisao
  // (`META_ACTION_ORDEM_COLIDE`), mas o produtor nao pode depender disso.
  let ordemDaAction = 0;
  for (const a of f.actions.concat(f.action_values)) {
    insightAction.push({
      meta_insight_daily_id: fatoId,
      ordem: ordemDaAction,
      action_type: a.action_type,
      value: a.value,
      attribution_window: a.attribution_window,
      object_level: a.object_level,
      date_start: a.date_start,
      date_stop: a.date_stop,
      medida: a.medida === 'value' ? 'value' : 'count',
    });
    ordemDaAction += 1;
  }
}

const houveRecusa = recusadas.length > 0;
const parcialidade = [];
if (!completo) parcialidade.push(String(ctx.motivo_incompleto));
if (houveRecusa) {
  parcialidade.push(`${recusadas.length} de ${fatos.length} linhas recusadas na validacao local`);
}
// A lacuna anterior fechou: a migration candidata do read model adicionou a
// coluna `medida` a `trafego_meta_insight_action`, e o backend passou a emitir
// as linhas de `action_values` na mesma tabela. Nao ha mais valor monetario
// viajando sem destino, entao nada a declarar como parcialidade aqui.

const rows = {
  trafego_meta_insight_daily: insightDaily,
  trafego_meta_insight_action: insightAction,
};
const janela = `${ctx.janela_inicio}..${ctx.janela_fim}`;
// ⚠️ A IMPRESSAO DIGITAL E DO CONTEUDO, E SO DELE — igual ao lado Python
// (`read_model._COLUNAS_DE_INSTANTE`). `observado_em` e `ultima_vez_visto_em`
// dizem QUANDO olhamos, nao O QUE vimos. Se entrassem no hash, duas leituras
// identicas da mesma janela pareceriam conteudos diferentes, a RPC nunca
// reconheceria um replay, e uma reexecucao manual gravaria uma revisao que nao
// revisa nada. Com eles fora, o hash responde a pergunta util: "mudou?".
const SEM_INSTANTE = new Set(['observado_em', 'ultima_vez_visto_em']);
const semInstante = (lista) => lista.map((linha) => {
  const copia = {};
  for (const chave of Object.keys(linha)) {
    if (!SEM_INSTANTE.has(chave)) copia[chave] = linha[chave];
  }
  return copia;
});
const paraHash = {
  provider: 'META_ADS',
  conta: String(ctx.conta_externa),
  janela,
  pedido: ctx.pedido,
  pagina: Number(ctx.pagina),
  linhas: {
    trafego_meta_insight_daily: semInstante(rows.trafego_meta_insight_daily),
    trafego_meta_insight_action: semInstante(rows.trafego_meta_insight_action),
  },
};
const snapshotHash = 'meta_snapshot_' + sha256Hex(jsonEstavel(paraHash)).slice(0, 32);
const idempotencia = 'meta_sync_' + sha256Hex(
  `META_ADS|${ctx.execucao_chave}|${ctx.conta_ref}|${janela}|${ctx.pagina}|${snapshotHash}`
).slice(0, 32);

// ── CHAVE ESTAVEL: SO O QUE FOI PEDIDO, NADA DO QUANDO ──────────────────────
//
// ⚠️ A chave acima e VOLATIL por construcao, e o comentario-contrato de
// `20260907210000_meta_read_model_consistency.sql:1272-1276` nomeia o defeito:
// ela deriva de `execucao_chave` (que numa rodada manual carrega `m<HH><MM>`, um
// relogio) e de `snapshotHash` (que deriva das linhas, que carregam
// `observado_em`). Dois cliques com um segundo de diferenca produzem duas chaves
// e DOIS runs da mesma leitura — e a RPC carimba `chave_origem: "volatil"` no
// recibo justamente para deixar essa degradacao visivel.
//
// A chave estavel responde outra pergunta: QUAL UNIDADE LOGICA DE TRABALHO e
// esta? Ela nao pode conter instante nenhum — nem `execucao_chave`, nem `passo`,
// nem `iniciada_em`, nem o hash do conteudo. Ela carrega exatamente o que
// DESCREVE O PEDIDO: conta, janela, grao (nivel, incremento, instante de
// relatorio, breakdown, janela de atribuicao declarada), a lista de campos, e a
// versao do contrato.
//
// ⚠️ E A PAGINA ENTRA. Nao por gosto: sem ela, as paginas 2..N da mesma janela
// nasceriam com a MESMA chave da pagina 1, a RPC as reconheceria como replay
// (20260907210000:746-757 devolve `repetido: true` e NAO escreve linha nenhuma) e
// tudo depois da primeira pagina seria descartado em silencio. A pagina e "que
// pedaco do pedido", nao "quando a resposta chegou": duas leituras da mesma
// janela paginam igual.
const pedidoEstavel = [
  'META_ADS',
  String(ctx.conta_externa),
  janela,
  String(ctx.nivel),
  String(ctx.time_increment),
  String(ctx.action_report_time),
  String(ctx.breakdown),
  String(ctx.janela_declarada),
  String(ctx.campos_de_insight),
  String(ctx.contrato_sha256),
  `pagina=${Number(ctx.pagina)}`,
].join('|');
const idempotenciaEstavel = 'meta_sync_' + sha256Hex(pedidoEstavel).slice(0, 32);

const agora = new Date().toISOString();
const snapshot = {
  provider: 'META_ADS',
  escopo: 'insights_pagina',
  account_ref: String(ctx.conta_ref),
  account_asset_id: String(ctx.conta_ativo_id),
  credential_asset_id: ctx.credencial_ativo_id || null,
  window: janela,
  observed_at: ctx.iniciada_em,
  idempotency_key: idempotencia,
  // A chave que a RPC prefere. Quando ela chega, o recibo carimba
  // `chave_origem: "estavel"`; a volatil continua viajando ao lado porque a RPC
  // a guarda em `cursor_final.chave_volatil` para forense.
  stable_idempotency_key: idempotenciaEstavel,
  // ⚠️ FALSE, E ISSO E UMA AFIRMACAO, NAO UM PADRAO. `hierarchy_complete` e a
  // UNICA declaracao que autoriza a RPC a marcar ausencia de campanha/adset/ad
  // (20260907210000:713 e 7.7). Este fluxo le INSIGHTS: ele nunca percorre a
  // hierarquia da conta, entao nao tem como saber o que sumiu. Mandar `true`
  // aqui autorizaria apagar inventario a partir de uma leitura que nem olhou
  // para ele. Mandar `false` diz a verdade: esta leitura nao marca ausencia
  // nenhuma. (Depois da migration de escopo, a RPC so EXIGE o campo no escopo
  // 'hierarchy'; o fluxo o envia mesmo assim, para que o envelope siga valido
  // por qualquer caminho e para que a resposta fique escrita em vez de omitida.)
  hierarchy_complete: false,
  snapshot_hash: snapshotHash,
  page_count: Number(ctx.pagina),
  counts: {
    insight: insightDaily.length,
    action: insightAction.filter((a) => a.medida === 'count').length,
    action_value: insightAction.filter((a) => a.medida === 'value').length,
    recusadas: recusadas.length,
  },
  partiality: parcialidade,
  completo: completo && !houveRecusa,
  motivo_incompleto: parcialidade.length ? parcialidade.join(' | ') : null,
  // Marca d'agua so avanca sobre janela lida inteira. Incompleta nao avanca —
  // e por isso ela vem `null`, e nao "a data que quase deu certo".
  marca_dagua: completo && !houveRecusa ? String(ctx.janela_fim) : null,
  pedido: ctx.pedido,
  execucao: {
    fonte: ctx.fonte,
    job: ctx.job,
    disparo: ctx.disparo,
    execucao_chave: ctx.execucao_chave,
    workflow_id: ctx.workflow_id,
    execucao_externa_id: ctx.execucao_externa_id,
    api_versao: ctx.api_versao,
    contrato_versao: ctx.contrato_versao,
    contrato_sha256: ctx.contrato_sha256,
    lote_ordinal: ctx.lote_ordinal,
    iniciada_em: ctx.iniciada_em,
    encerrada_em: agora,
  },
  rows,
};

return [{
  json: {
    ...ctx,
    snapshot,
    linhas_enviadas: insightDaily.length,
    acoes_enviadas: insightAction.filter((a) => a.medida === 'count').length,
    valores_enviados: insightAction.filter((a) => a.medida === 'value').length,
    linhas_recusadas_localmente: recusadas.length,
    recusas_locais: recusadas,
  },
}];
"""

JS_RECONCILIAR = r"""
// ── RECONCILIACAO DO LOTE ───────────────────────────────────────────────────
//
// O recibo do banco tem de bater com o que o fluxo enviou. Nao bater e defeito,
// nao ruido — e o fluxo para em vez de fechar uma execucao que mente.
const recibo = $input.first().json;
const ctx = $('Validar semanticamente').first().json;

if (!recibo || typeof recibo !== 'object') {
  throw new Error('RPC_SEM_RECIBO: a persistencia nao devolveu documento');
}
if (recibo.ok !== true) {
  throw new Error('RPC_RECUSOU_O_SNAPSHOT: a persistencia nao confirmou a escrita');
}
const repetido = Boolean(recibo.repetido);
const runId = recibo.run_id === null || recibo.run_id === undefined ? null : String(recibo.run_id);
if (runId === null || runId === '') {
  throw new Error('RPC_SEM_RUN_ID: sem identidade da gravacao nao ha o que reconciliar');
}

const antes = ctx.acumulado || {};
const acumulado = {
  linhas_lidas: Number(antes.linhas_lidas || 0) + Number(ctx.linhas_lidas_na_pagina || 0),
  linhas_aceitas: Number(antes.linhas_aceitas || 0) + Number(ctx.linhas_enviadas || 0),
  linhas_rejeitadas: Number(antes.linhas_rejeitadas || 0) + Number(ctx.linhas_recusadas_localmente || 0),
  acoes: Number(antes.acoes || 0) + Number(ctx.acoes_enviadas || 0),
  valores_de_acao: Number(antes.valores_de_acao || 0) + Number(ctx.valores_enviados || 0),
  paginas: Number(antes.paginas || 0) + 1,
};
const parcialidades = (antes.parcialidades || []).concat(ctx.snapshot.partiality || []);
const persistencias = (antes.persistencias || []).concat([repetido ? 'repetido' : 'gravado']);

return [{
  json: {
    fonte: ctx.fonte,
    provider: ctx.provider,
    job: ctx.job,
    disparo: ctx.disparo,
    origem_janela: ctx.origem_janela,
    data_do_disparo: ctx.data_do_disparo,
    execucao_chave: ctx.execucao_chave,
    api_versao: ctx.api_versao,
    contrato_versao: ctx.contrato_versao,
    contrato_sha256: ctx.contrato_sha256,
    nivel: ctx.nivel,
    time_increment: ctx.time_increment,
    action_report_time: ctx.action_report_time,
    breakdown: ctx.breakdown,
    janelas_solicitadas: ctx.janelas_solicitadas,
    janela_declarada: ctx.janela_declarada,
    campos_de_insight: ctx.campos_de_insight,
    limite_por_pagina: ctx.limite_por_pagina,
    workflow_id: ctx.workflow_id,
    execucao_externa_id: ctx.execucao_externa_id,
    iniciada_em: ctx.iniciada_em,
    contas_tentadas: ctx.contas_tentadas,
    total_contas: ctx.total_contas,
    contas_recusadas_na_selecao: ctx.contas_recusadas_na_selecao,
    conta_ativo_id: ctx.conta_ativo_id,
    conta_ref: ctx.conta_ref,
    conta_externa: ctx.conta_externa,
    id_mascarado: ctx.id_mascarado,
    credencial_ativo_id: ctx.credencial_ativo_id,
    fuso_da_conta: ctx.fuso_da_conta,
    moeda: ctx.moeda,
    hoje_na_conta: ctx.hoje_na_conta,
    janela_inicio: ctx.janela_inicio,
    janela_fim: ctx.janela_fim,
    dias_na_janela: ctx.dias_na_janela,
    conta_ordinal: ctx.conta_ordinal,
    mapa_conta: ctx.mapa_conta,
    pedido: ctx.pedido,
    pagina: ctx.pagina,
    proximo_cursor: ctx.proximo_cursor,
    tem_proxima_pagina: Boolean(ctx.tem_proxima_pagina),
    motivo_incompleto: ctx.motivo_incompleto,
    acumulado: { ...acumulado, parcialidades, persistencias },
    estado_conta: 'lida',
    persistencia_confirmada: true,
    ultimo_run_id: runId,
    // A chave sob a qual o banco gravou este lote e a ESTAVEL (a RPC so cai para
    // a volatil quando a estavel falta). Guardar a volatil aqui faria o traco
    // apontar para uma chave que nao esta em `trafego_meta_sync_run`.
    ultima_idempotencia: ctx.snapshot.stable_idempotency_key,
    ultima_idempotencia_volatil: ctx.snapshot.idempotency_key,
    // A RPC diz de qual chave ela partiu; guardar a resposta DELA e melhor que
    // supor. `volatil` aqui significaria que a chave estavel nao chegou.
    chave_origem: recibo.chave_origem === undefined ? null : String(recibo.chave_origem),
  },
}];
"""

JS_CLASSIFICAR_ERRO = r"""
// ── CLASSIFICACAO DO ERRO DA META ───────────────────────────────────────────
//
// ⚠️ A saida de erro NUNCA volta para o no de requisicao. Ela segue para a
// frente e reentra no laco de contas, que so anda — por isso 401/403 nao tem
// como girar. A repeticao limitada de 429/5xx e o `maxTries` do proprio no
// (backoff fixo, tres tentativas). O n8n nao sabe repetir condicionalmente por
// codigo; a defesa contra "repetir para sempre" e topologica, nao configuravel.
//
// AUTENTICACAO PARA E EXIGE ACAO: a conta e encerrada como incompleta, a marca
// d'agua nao avanca, e o batimento vira alerta. Nao existe caminho que tente de
// novo dentro da mesma execucao.
//
// Rotulo desconhecido vira DESCONHECIDA, nunca "ok". A mensagem publica nao
// interpola o texto bruto do erro: ele pode carregar token e cabecalho.
// Mesma razao da normalizacao: contexto pelo Merge, nunca por `$()` no laco.
const ctx = $input.first().json || {};
const bruto = ctx;

const alvo = bruto.error && typeof bruto.error === 'object' ? bruto.error : bruto;
let codigo = null;
for (const chave of ['httpCode', 'status', 'statusCode', 'code']) {
  const v = alvo[chave];
  if (v !== null && v !== undefined && /^[0-9]{3}$/.test(String(v))) {
    codigo = Number(v);
    break;
  }
}
if (codigo === null) {
  const m = String(alvo.message || '').match(/\b(4[0-9]{2}|5[0-9]{2})\b/);
  if (m) codigo = Number(m[1]);
}

// Codigos proprios da Graph, quando o HTTP nao conta a historia inteira.
const grafo = (alvo.error && typeof alvo.error === 'object') ? alvo.error : {};
const codigoGraph = Number(grafo.code);
const subcodigo = Number(grafo.error_subcode);

if (String(ctx.conta_ref || '') === '') {
  throw new Error('CONTEXTO_PERDIDO: a falha chegou sem a conta que a produziu');
}

let classe;
if (codigo === 401 || codigo === 403 || codigoGraph === 190 || codigoGraph === 200
    || codigoGraph === 10) {
  classe = 'AUTENTICACAO';
} else if (codigo === 429 || codigoGraph === 4 || codigoGraph === 17 || codigoGraph === 613
           || codigoGraph === 80004) {
  classe = 'COTA';
} else if (codigo !== null && codigo >= 500) {
  classe = 'INDISPONIVEL';
} else if (codigoGraph === 1 || codigoGraph === 2) {
  classe = 'INDISPONIVEL';
} else if (codigo !== null && codigo >= 400) {
  classe = 'PEDIDO_INVALIDO';
} else {
  classe = 'DESCONHECIDA';
}

const exigeAcaoHumana = classe === 'AUTENTICACAO';
// Repetir vale na PROXIMA rodada agendada, nao dentro desta: a janela ficou
// incompleta e a marca d'agua nao avancou, entao a proxima leitura cobre o
// mesmo periodo sem duplicar gasto (produz outra revisao do mesmo grao).
const retryNaProximaRodada = classe === 'COTA' || classe === 'INDISPONIVEL';

const antes = ctx.acumulado || {};
const motivo = `META_${classe}`
  + (codigo === null ? '' : `_HTTP_${codigo}`)
  + (Number.isFinite(codigoGraph) && codigoGraph ? `_GRAPH_${codigoGraph}` : '')
  + (Number.isFinite(subcodigo) && subcodigo ? `_SUB_${subcodigo}` : '');

return [{
  json: {
    fonte: ctx.fonte,
    provider: ctx.provider,
    job: ctx.job,
    disparo: ctx.disparo,
    origem_janela: ctx.origem_janela,
    data_do_disparo: ctx.data_do_disparo,
    execucao_chave: ctx.execucao_chave,
    api_versao: ctx.api_versao,
    contrato_versao: ctx.contrato_versao,
    contrato_sha256: ctx.contrato_sha256,
    nivel: ctx.nivel,
    time_increment: ctx.time_increment,
    action_report_time: ctx.action_report_time,
    breakdown: ctx.breakdown,
    janelas_solicitadas: ctx.janelas_solicitadas,
    janela_declarada: ctx.janela_declarada,
    workflow_id: ctx.workflow_id,
    execucao_externa_id: ctx.execucao_externa_id,
    iniciada_em: ctx.iniciada_em,
    contas_tentadas: ctx.contas_tentadas,
    total_contas: ctx.total_contas,
    contas_recusadas_na_selecao: ctx.contas_recusadas_na_selecao,
    conta_ativo_id: ctx.conta_ativo_id,
    conta_ref: ctx.conta_ref,
    id_mascarado: ctx.id_mascarado,
    fuso_da_conta: ctx.fuso_da_conta,
    janela_inicio: ctx.janela_inicio,
    janela_fim: ctx.janela_fim,
    dias_na_janela: ctx.dias_na_janela,
    conta_ordinal: ctx.conta_ordinal,
    pedido: ctx.pedido,
    pagina: ctx.pagina,
    acumulado: { ...antes, parcialidades: (antes.parcialidades || []).concat([motivo]) },
    estado_conta: 'falhou',
    persistencia_confirmada: false,
    erro_classe: classe,
    erro_codigo: codigo === null ? null : String(codigo),
    erro_codigo_graph: Number.isFinite(codigoGraph) && codigoGraph ? String(codigoGraph) : null,
    // Mensagem SANITIZADA: rotulo, nunca o corpo bruto do erro.
    erro_mensagem: motivo,
    exige_acao_humana: exigeAcaoHumana,
    retry_na_proxima_rodada: retryNaProximaRodada,
    motivo_incompleto: motivo,
    tem_proxima_pagina: false,
    proximo_cursor: '',
  },
}];
"""

JS_FECHAR = JS_HASH + r"""
// ── FECHAMENTO DA EXECUCAO ──────────────────────────────────────────────────
//
// ⚠️ O acumulado vem de `$input.all()` — a saida `done` do laco, que traz TODOS
// os itens que reentraram nele. Nao de `$('No dentro do laco').all()`, que
// devolveria so a ultima rodada e faria o recibo declarar o ultimo lote como se
// fosse a execucao inteira.
const itens = $input.all().map((i) => i.json);
if (itens.length === 0) {
  throw new Error('FECHAMENTO_SEM_ITEM: o laco terminou sem devolver conta nenhuma');
}
const base = itens[0];

let lidas = 0; let aceitas = 0; let rejeitadas = 0;
let acoes = 0; let valores = 0; let paginas = 0;
const contas = [];
const contasAceitas = [];
const contasRecusadas = [];
const parcialidades = [];
let exigeAcaoHumana = false;

for (const it of itens) {
  const a = it.acumulado || {};
  lidas += Number(a.linhas_lidas || 0);
  aceitas += Number(a.linhas_aceitas || 0);
  rejeitadas += Number(a.linhas_rejeitadas || 0);
  acoes += Number(a.acoes || 0);
  valores += Number(a.valores_de_acao || 0);
  paginas += Number(a.paginas || 0);
  for (const p of (a.parcialidades || [])) parcialidades.push(p);

  const falhou = it.estado_conta === 'falhou';
  const completo = !falhou && (it.motivo_incompleto === null || it.motivo_incompleto === undefined);
  if (falhou && it.exige_acao_humana) exigeAcaoHumana = true;

  // ⚠️ SUB-RECIBO POR CONTA, COM O SUFICIENTE PARA REPROCESSAR: referencia
  // opaca (nunca id cru), periodo NO FUSO DA CONTA, versao da API, os parametros
  // efetivamente pedidos, paginas, contagens, completude, se a persistencia foi
  // confirmada e o erro ja sanitizado.
  contas.push({
    conta_ref: String(it.conta_ref),
    id_mascarado: it.id_mascarado || null,
    fuso_da_conta: it.fuso_da_conta || null,
    moeda: it.moeda || null,
    periodo_inicio: it.janela_inicio || null,
    periodo_fim: it.janela_fim || null,
    dias_na_janela: it.dias_na_janela === undefined ? null : it.dias_na_janela,
    api_versao: it.api_versao || null,
    pedido: it.pedido || null,
    paginas: Number(a.paginas || 0),
    linhas_lidas: Number(a.linhas_lidas || 0),
    linhas_aceitas: Number(a.linhas_aceitas || 0),
    linhas_rejeitadas: Number(a.linhas_rejeitadas || 0),
    acoes: Number(a.acoes || 0),
    valores_de_acao: Number(a.valores_de_acao || 0),
    completo,
    motivo_incompleto: it.motivo_incompleto === undefined ? null : it.motivo_incompleto,
    persistencia_confirmada: Boolean(it.persistencia_confirmada),
    // A marca d'agua so avanca sobre janela lida INTEIRA e persistida.
    marca_dagua: completo && it.persistencia_confirmada ? (it.janela_fim || null) : null,
    erro_classe: falhou ? (it.erro_classe || 'DESCONHECIDA') : null,
    erro_codigo: falhou ? (it.erro_codigo === undefined ? null : it.erro_codigo) : null,
    erro_mensagem: falhou ? (it.erro_mensagem || null) : null,
    exige_acao_humana: Boolean(falhou && it.exige_acao_humana),
    retry_na_proxima_rodada: Boolean(falhou && it.retry_na_proxima_rodada),
    ultimo_run_id: it.ultimo_run_id || null,
  });

  if (falhou) {
    contasRecusadas.push({ conta_ref: String(it.conta_ref),
                           classe: it.erro_classe || 'DESCONHECIDA' });
  } else {
    contasAceitas.push(String(it.conta_ref));
  }
}

const incompletas = contas.filter((c) => !c.completo).length;

// Uma falha de conta nao pode virar vazio nem sumir. Ela decide o desfecho.
let resultado;
let motivo = null;
if (contasRecusadas.length === 0 && rejeitadas === 0 && incompletas === 0) {
  resultado = 'ok';
} else if (contasRecusadas.length === 0 && incompletas === 0) {
  resultado = aceitas > 0 ? 'parcial' : 'falhou';
  motivo = `${rejeitadas} linhas rejeitadas semanticamente; nenhuma recusa pode virar ok`;
} else if (contasAceitas.length > 0 || aceitas > 0) {
  resultado = 'parcial';
  motivo = `${contasRecusadas.length} de ${itens.length} contas falharam,`
    + ` ${incompletas} janela(s) incompleta(s), ${rejeitadas} linhas rejeitadas`;
} else {
  resultado = 'falhou';
  motivo = `todas as ${contasRecusadas.length} contas falharam;`
    + ` ${rejeitadas} linhas rejeitadas`;
}
// `falhou` significa "nada aproveitavel". Se linha verde existe, o desfecho
// honesto e parcial.
if (resultado === 'falhou' && aceitas > 0) {
  resultado = 'parcial';
  motivo = `linhas aceitas apesar de contas falhas: ${motivo}`;
}
if (exigeAcaoHumana) {
  motivo = `AUTORIZACAO_META_EXIGE_ACAO — ${motivo || 'leitura interrompida'}`;
}

const agora = new Date().toISOString();
const janela = `${base.data_do_disparo}:${base.origem_janela}`;
const paraHash = {
  provider: 'META_ADS',
  execucao: String(base.execucao_chave),
  contas,
  resultado,
};
const snapshotHash = 'meta_snapshot_' + sha256Hex(jsonEstavel(paraHash)).slice(0, 32);
const idempotencia = 'meta_sync_' + sha256Hex(
  `META_ADS|fechamento|${base.execucao_chave}|${snapshotHash}`).slice(0, 32);

// ── CHAVE ESTAVEL DO FECHAMENTO ─────────────────────────────────────────────
//
// ⚠️ NEM `execucao_chave` NEM `snapshotHash` PODEM ENTRAR AQUI, e cada um por um
// motivo proprio:
//   • `execucao_chave` termina em `passo`, que numa rodada manual e
//     `m<HH><MM>` — um relogio (ver JS da "Identidade da execucao").
//   • `snapshotHash` do fechamento cobre `contas[]`, e cada sub-recibo carrega
//     `ultimo_run_id`, um uuid sorteado pela RPC a cada gravacao. Duas execucoes
//     identicas jamais produziriam o mesmo hash.
// Qualquer um dos dois faria a chave "estavel" ser tao volatil quanto a outra —
// o defeito que `20260907210000:1272-1276` chama de `chave_origem: volatil`.
//
// O que IDENTIFICA esta unidade de trabalho: o job, o modo da janela, o DIA de
// calendario do disparo (rotulo, nao instante), a versao do contrato, e o
// conjunto ordenado de (conta, periodo lido). O `resultado` fica de fora de
// proposito: desfecho e consequencia, nao pedido.
//
// ⚠️ CONSEQUENCIA ACEITA E DECLARADA: rerodar o MESMO job, no MESMO dia, sobre as
// MESMAS janelas produz a mesma chave, e a RPC devolve `repetido: true` sem
// gravar um segundo fechamento. Isso e o comportamento pedido — duas leituras
// identicas sao uma unidade de trabalho, nao duas. Quando a segunda rodada le um
// numero de paginas diferente da primeira, "Batimento e saude" acusa
// INDETERMINADO ("releitura diverge"), que e exatamente o sinal que o operador
// precisa ver. O que nao acontece e a segunda rodada passar por execucao nova.
const contasParaChave = contas
  .map((c) => `${c.conta_ref}@${c.periodo_inicio}..${c.periodo_fim}`)
  .sort();
const fechamentoEstavel = [
  'META_ADS',
  'fechamento',
  String(base.job),
  String(base.origem_janela),
  String(base.data_do_disparo),
  String(base.contrato_sha256),
  contasParaChave.join(','),
].join('|');
const idempotenciaEstavel = 'meta_sync_' + sha256Hex(fechamentoEstavel).slice(0, 32);

// ⚠️ FECHAMENTO DA EXECUCAO, NAO DE UMA CONTA: `account_asset_id` vem `null` de
// proposito e `contas[]` traz um sub-recibo por conta. Ver CONTRATO_RPC no
// gerador — a v15_02 exigiria uma conta; a revisao da RPC precisa aceitar o
// escopo de execucao.
const snapshot = {
  provider: 'META_ADS',
  escopo: 'insights_fechamento',
  account_ref: null,
  account_asset_id: null,
  credential_asset_id: null,
  window: janela,
  observed_at: base.iniciada_em,
  idempotency_key: idempotencia,
  stable_idempotency_key: idempotenciaEstavel,
  // Mesma afirmacao do snapshot de pagina: o fechamento resume leituras de
  // INSIGHTS, nunca uma varredura de hierarquia. `false` nega, explicitamente,
  // autorizacao para marcar ausencia de qualquer objeto da conta.
  hierarchy_complete: false,
  snapshot_hash: snapshotHash,
  page_count: paginas,
  counts: {
    contas: itens.length,
    contas_aceitas: contasAceitas.length,
    contas_recusadas: contasRecusadas.length,
    insight: aceitas,
    action: acoes,
    action_value: valores,
    recusadas: rejeitadas,
  },
  partiality: parcialidades,
  completo: resultado === 'ok',
  motivo_incompleto: resultado === 'ok' ? null : motivo,
  marca_dagua: null,
  contas,
  execucao: {
    fonte: base.fonte,
    job: base.job,
    disparo: base.disparo,
    execucao_chave: base.execucao_chave,
    workflow_id: base.workflow_id,
    execucao_externa_id: base.execucao_externa_id,
    api_versao: base.api_versao,
    contrato_versao: base.contrato_versao,
    contrato_sha256: base.contrato_sha256,
    origem_janela: base.origem_janela,
    data_do_disparo: base.data_do_disparo,
    iniciada_em: base.iniciada_em,
    encerrada_em: agora,
    duracao_ms: Math.max(0, Date.parse(agora) - Date.parse(base.iniciada_em)),
    resultado,
    motivo,
  },
  rows: {},
};

return [{
  json: {
    snapshot,
    resumo: {
      job: base.job,
      execucao_chave: base.execucao_chave,
      // ⚠️ A RELEITURA PROCURA A CHAVE QUE O BANCO GRAVOU, e o banco grava a
      // ESTAVEL quando ela chega: `20260907210000:727-742` faz
      // `v_chave := v_chave_estavel` e so cai para a volatil quando o campo
      // falta. Apontar "Releitura do recibo" para a volatil daria
      // `chave_de_idempotencia=eq.<chave que nao existe>`, zero linha de volta e
      // "Batimento e saude" carimbando INDETERMINADO em TODA rodada — um alerta
      // permanente que ensina o operador a ignorar alerta.
      idempotencia_fechamento: idempotenciaEstavel,
      // A volatil continua no recibo, mas como TRACO, nao como endereco: e ela
      // que a RPC guarda em `cursor_final.chave_volatil` para forense.
      idempotencia_volatil: idempotencia,
      data_do_disparo: base.data_do_disparo,
      contas_lidas: contasAceitas.length,
      contas_recusadas: contasRecusadas.length,
      contas_incompletas: incompletas,
      paginas,
      linhas_lidas: lidas,
      linhas_aceitas: aceitas,
      linhas_rejeitadas: rejeitadas,
      acoes: acoes,
      valores_de_acao: valores,
      exige_acao_humana: exigeAcaoHumana,
      resultado,
      motivo,
      contas,
    },
  },
}];
"""

JS_BATIMENTO = r"""
// ── BATIMENTO E SAUDE ───────────────────────────────────────────────────────
//
// A leitura de volta prova que o recibo POUSOU. Sem ela, o fluxo declararia
// sucesso com base na propria memoria — o autoatestado que o contrato de saude
// proibe.
//
// ⚠️ SAUDAVEL nunca sai so de tentativa ou de batimento. Ausencia de leitura de
// volta e INDETERMINADO, nao sucesso.
const fechamento = $('Fechar execucao').first().json;
const resumo = fechamento.resumo;

const linhas = $input.all().map((i) => i.json)
  .filter((l) => l && l.chave_de_idempotencia);
const lido = linhas.find(
  (l) => String(l.chave_de_idempotencia) === String(resumo.idempotencia_fechamento)) || null;

let estado;
let alerta = false;
let motivoAlerta = null;

if (resumo.exige_acao_humana) {
  // Autorizacao quebrada nao e "parcial que melhora sozinho": alguem precisa
  // agir. Ela ganha estado proprio e nunca e silenciada por uma releitura boa.
  estado = 'BLOQUEADO_AUTORIZACAO';
  alerta = true;
  motivoAlerta = 'a Meta recusou a autorizacao; a leitura parou e exige acao humana';
} else if (lido === null) {
  estado = 'INDETERMINADO';
  alerta = true;
  motivoAlerta = 'o recibo de fechamento nao foi encontrado na releitura';
} else if (String(lido.resultado) === 'falhou') {
  estado = 'FALHOU';
  alerta = true;
  motivoAlerta = String(lido.erro_mensagem || 'falha sem motivo declarado');
} else if (Number(lido.paginas_lidas) !== Number(resumo.paginas)) {
  estado = 'INDETERMINADO';
  alerta = true;
  motivoAlerta = `releitura diverge: banco ${lido.paginas_lidas} paginas,`
    + ` fluxo ${resumo.paginas}`;
} else if (String(resumo.resultado) === 'parcial' || Number(resumo.contas_incompletas) > 0) {
  estado = 'PARCIAL';
  alerta = true;
  motivoAlerta = String(resumo.motivo || 'parcial sem motivo declarado');
} else {
  // Vazio confirmado NAO e alerta: a leitura foi boa e nao havia linha.
  estado = 'SAUDAVEL';
  alerta = false;
}

// O que sai daqui vai para alerta e log: referencia opaca, contagens e rotulos.
// Nunca id de conta cru, nunca token, nunca valor financeiro.
const contasSanitizadas = (resumo.contas || []).map((c) => ({
  conta_ref: c.conta_ref,
  periodo_inicio: c.periodo_inicio,
  periodo_fim: c.periodo_fim,
  fuso_da_conta: c.fuso_da_conta,
  paginas: c.paginas,
  linhas_aceitas: c.linhas_aceitas,
  completo: c.completo,
  persistencia_confirmada: c.persistencia_confirmada,
  marca_dagua: c.marca_dagua,
  erro_classe: c.erro_classe,
}));

return [{
  json: {
    job: resumo.job,
    execucao_chave: resumo.execucao_chave,
    data_do_disparo: resumo.data_do_disparo,
    contas_lidas: resumo.contas_lidas,
    contas_recusadas: resumo.contas_recusadas,
    contas_incompletas: resumo.contas_incompletas,
    paginas: resumo.paginas,
    linhas_lidas: resumo.linhas_lidas,
    linhas_aceitas: resumo.linhas_aceitas,
    linhas_rejeitadas: resumo.linhas_rejeitadas,
    resultado: resumo.resultado,
    motivo: resumo.motivo,
    estado_saude: estado,
    alerta,
    motivo_alerta: motivoAlerta,
    exige_acao_humana: Boolean(resumo.exige_acao_humana),
    releitura_encontrada: lido !== null,
    persistencia_confirmada: lido !== null && String(lido.resultado) === 'ok',
    vazio_confirmado: Number(resumo.linhas_lidas) === 0 && String(resumo.resultado) === 'ok',
    contas: contasSanitizadas,
  },
}];
"""

# ────────────────────────────────────────────────────────────── construcao ──


def _id(nome: str) -> str:
    """Id estavel do no: o mesmo nome gera sempre o mesmo id, sem sorteio.

    ⚠️ O NAMESPACE e `meta-insights-dia`, diferente do `gads-dia` do gerador
    Google. Dois workflows com o mesmo id de no colidem no import do n8n e um
    sobrescreve o outro em silencio.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"volc:n8n:meta-insights-dia:{nome}"))


def _no(nome: str, tipo: str, tv: Any, pos: list[int], parametros: dict, **extra) -> dict:
    no: dict[str, Any] = {
        "parameters": parametros,
        "id": _id(nome),
        "name": nome,
        "type": tipo,
        "typeVersion": tv,
        "position": pos,
    }
    no.update(extra)
    return no


def _code(nome: str, pos: list[int], js: str) -> dict:
    return _no(nome, "n8n-nodes-base.code", 2, pos,
               {"mode": "runOnceForAllItems", "jsCode": js.strip() + "\n"})


def _se_booleano(nome: str, pos: list[int], expressao: str) -> dict:
    return _no(nome, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose", "version": 2},
            "conditions": [{
                "id": _id(nome + ":cond"),
                "leftValue": expressao,
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "looseTypeValidation": True,
        "options": {},
    })


def construir(papel: str, contrato_sha: str) -> dict:
    if papel != "d1":
        raise ValueError(f"papel desconhecido: {papel!r}")
    job = "meta_insights_dia_d1"
    modo = "D-1"
    # 07:00 e nao 06:00: o fluxo Google D-1 ja ocupa as 06h, e duas leituras
    # pesadas no mesmo minuto competem por recurso do mesmo host.
    cron = "0 7 * * *"
    passos = "07"
    nome = "VOLC · Meta Ads insights campanha-dia · D-1 (fuso da conta)"

    config = [
        ("SUPABASE_URL", SUPABASE),
        ("GRAPH_BASE", GRAPH_BASE),
        ("GRAPH_API_VERSION", API_VERSION),
        ("RPC_PERSISTIR", RPC_PERSISTIR),
        ("JOB", job),
        ("JANELA_MODO", modo),
        ("PASSOS", passos),
        ("PASSO_FORCADO", ""),
        # ⚠️ ESTE FUSO E SO O DO ROTULO DA RODADA E DA AGENDA. A JANELA
        # COLETADA SAI DO FUSO DA CONTA, lido de
        # `trafego_meta_ad_account.timezone_name`, conta a conta.
        ("TZ_DO_DISPARO", "America/Sao_Paulo"),
        ("NIVEL", NIVEL),
        ("TIME_INCREMENT", TIME_INCREMENT),
        ("ACTION_REPORT_TIME", ACTION_REPORT_TIME),
        ("BREAKDOWN", BREAKDOWN),
        # Vazio = "nao pedi janela"; o fato carimba `default`.
        ("JANELAS_DE_ATRIBUICAO", JANELAS_DE_ATRIBUICAO),
        ("CAMPOS_DE_INSIGHT", CAMPOS_DE_INSIGHT),
        ("LIMITE_POR_PAGINA", "100"),
        ("MAX_PAGINAS", "50"),
        ("MAX_DIAS_POR_PEDIDO", json.dumps(MAX_DIAS_POR_PEDIDO, sort_keys=True,
                                           separators=(",", ":"))),
        # Janela de reprocesso para revisao tardia: 0 = so D-1. Subir para N faz
        # o pedido cobrir D-1-N..D-1 numa unica leitura com `time_increment=1`
        # (uma linha por dia). Reler nao duplica gasto: gera outra REVISAO do
        # mesmo grao, resolvida pela projecao mais recente.
        ("DIAS_DE_REPROCESSO", "0"),
        ("PRONTIDOES_ACEITAS",
         "READY_FOR_READ,READY_FOR_VALIDATION,READY_FOR_CREATE_PAUSED,READY_FOR_ACTIVATION"),
        # Vazio = todas as contas prontas do read model. O canario preenche com UMA.
        ("CONTAS_PERMITIDAS", ""),
        ("CONTRATO_VERSAO", CONTRATO_VERSAO),
        ("CONTRATO_SHA256", contrato_sha),
    ]

    nos = [
        _no("Agenda", "n8n-nodes-base.scheduleTrigger", 1.2, [-660, -120],
            {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}),
        _no("Executar manualmente", "n8n-nodes-base.manualTrigger", 1, [-660, 60], {}),
        _no("Config", "n8n-nodes-base.set", 3.4, [-440, -20], {
            "assignments": {"assignments": [
                {"id": f"c{i}", "name": k, "type": "string", "value": v}
                for i, (k, v) in enumerate(config, start=1)
            ]},
            "options": {},
        }),
        _code("Identidade da execucao", [-220, -20], JS_IDENTIDADE),
        _no("Contas autorizadas", "n8n-nodes-base.httpRequest", 4.2, [0, -20], {
            "url": "={{ $json.url_contas }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 30000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000,
            alwaysOutputData=True),
        _code("Selecionar contas", [220, -20], JS_SELECIONAR_CONTAS),
        _no("Objetos conhecidos", "n8n-nodes-base.httpRequest", 4.2, [440, -20], {
            "url": "={{ $json.url_objetos }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 60000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000,
            alwaysOutputData=True),
        _code("Identidade VOLC por conta", [660, -20], JS_MAPA_IDENTIDADE),
        # ⚠️ batchSize 1: ver o comentario de "Pagina: preparar pedido".
        _no("Lote de contas", "n8n-nodes-base.splitInBatches", 3, [880, -20],
            {"batchSize": 1, "options": {}}),
        _code("Pagina: preparar pedido", [1100, 120], JS_PREPARAR_PAGINA),
        _no("Meta Graph: insights", "n8n-nodes-base.httpRequest", 4.2, [1320, 120], {
            "method": "GET",
            "url": "={{ $json.url_graph }}",
            # ⚠️ A AUTORIZACAO E DA CREDENCIAL, NAO DO WORKFLOW. Nao existe
            # cabecalho de autorizacao montado aqui, nem `access_token` em query,
            # nem `$env`. A forma abaixo e copia literal do precedente vivo desta
            # base — `n8n/joinads_report_day_before.json:144-146` — e e a unica
            # que mantem NOME e VALOR do cabecalho dentro do item do cofre. Por
            # isso o workflow nao declara (nem precisa saber) qual e o cabecalho.
            # `httpQueryAuth` seria a alternativa obvia e esta PROIBIDA: ela
            # poria o token na query string, onde ele vaza para log de proxy e
            # para o historico de execucao do n8n.
            "authentication": "genericCredentialType",
            "genericAuthType": CRED_META_TIPO,
            "sendQuery": True,
            "specifyQuery": "json",
            "jsonQuery": "={{ JSON.stringify($json.parametros_graph) }}",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 120000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_META,
            # Backoff limitado: tres tentativas, cinco segundos entre elas. O
            # n8n nao repete por codigo; a defesa contra "repetir para sempre" em
            # 401/403 e topologica — a saida de erro segue para a frente e
            # reentra no laco, que so anda.
            retryOnFail=True, maxTries=3, waitBetweenTries=5000,
            onError="continueErrorOutput"),
        # ⚠️ OS DOIS MERGES EXISTEM POR UM DEFEITO MEDIDO NO FLUXO IRMAO, nao por
        # gosto. Ler o contexto com `$('Pagina: preparar pedido')` dentro do laco
        # resolve pelo INDICE DA RODADA do no que pergunta: uma conta que falha
        # faz o pedido rodar mais vezes que a normalizacao, e a partir dali cada
        # iteracao le o contexto de OUTRA conta, em silencio. `combineByPosition`
        # casa resposta e contexto da MESMA iteracao, sem depender de indice.
        _no("Juntar contexto e resposta", "n8n-nodes-base.merge", 3.2, [1450, 40],
            {"mode": "combine", "combineBy": "combineByPosition", "options": {}}),
        _no("Juntar contexto e erro", "n8n-nodes-base.merge", 3.2, [1450, 320],
            {"mode": "combine", "combineBy": "combineByPosition", "options": {}}),
        _code("Pagina: normalizar", [1650, 40], JS_NORMALIZAR),
        _code("Validar semanticamente", [1850, 40], JS_VALIDAR),
        _no("RPC: ingerir lote", "n8n-nodes-base.httpRequest", 4.2, [2050, 40], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/rpc/{RPC_PERSISTIR}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ p_snapshot: $json.snapshot }) }}",
            "options": {"timeout": 120000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _code("Reconciliar lote", [2250, 40], JS_RECONCILIAR),
        _se_booleano("Tem proxima pagina?", [2450, 40], "={{ $json.tem_proxima_pagina }}"),
        _code("Classificar erro da Meta", [1650, 320], JS_CLASSIFICAR_ERRO),
        _code("Fechar execucao", [1100, -220], JS_FECHAR),
        _no("Limite do fechamento", "n8n-nodes-base.limit", 1, [1320, -220],
            {"maxItems": 1}),
        _no("RPC: fechar recibo", "n8n-nodes-base.httpRequest", 4.2, [1540, -220], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/rpc/{RPC_PERSISTIR}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ p_snapshot: $json.snapshot }) }}",
            "options": {"timeout": 60000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _no("Releitura do recibo", "n8n-nodes-base.httpRequest", 4.2, [1760, -220], {
            "url": "={{ $node[\"Config\"].json[\"SUPABASE_URL\"] "
                   "+ '/rest/v1/trafego_meta_sync_run?select=run_id,chave_de_idempotencia,"
                   "escopo,resultado,paginas_lidas,contagens,parcialidade,snapshot_hash,"
                   "escrita_executada,erro_codigo,erro_mensagem&chave_de_idempotencia=eq.' "
                   "+ $node[\"Fechar execucao\"].json[\"resumo\"][\"idempotencia_fechamento\"] }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 30000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _code("Batimento e saude", [1980, -220], JS_BATIMENTO),
        _se_booleano("Falha real?", [2200, -220], "={{ $json.alerta }}"),
        _no("Alerta de rotina parada", "n8n-nodes-base.httpRequest", 4.2, [2420, -220], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/system_settings",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "on_conflict", "value": "key"}]},
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            # Alerta sanitizado: chave do job, chave da execucao, estado e
            # motivo. Nenhuma conta crua, nenhum valor financeiro, nenhum token.
            "jsonBody": "={{ JSON.stringify({ key: 'meta_insights_' + $json.job"
                        " + '_ultimo_alerta',"
                        " value: $json.execucao_chave + ' | ' + $json.estado_saude + ' | '"
                        " + ($json.motivo_alerta || 'sem motivo declarado'),"
                        " updated_at: new Date().toISOString() }) }}",
            "options": {"timeout": 30000},
        }, credentials=CRED_SUPABASE),
        _no("Sticky Note", "n8n-nodes-base.stickyNote", 1, [-660, -520], {
            "width": 980, "height": 380,
            "content": (
                f"## {nome}\n\n"
                "**INATIVO por contrato E SEM CREDENCIAL.** Este JSON nao foi importado, "
                "nao foi executado e nao foi ativado. A agenda so pode ser ligada depois "
                "do pacote de autorizacao.\n\n"
                + ("**A credencial Meta NAO EXISTE ainda.** O no `Meta Graph: insights` "
                   f"autentica por `{CRED_META_TIPO}` — um tipo REAL do n8n — mas o id do "
                   f"item do cofre esta como o marcador `{CRED_META_ITEM_MARCADOR}`, que "
                   "nao resolve. Para provisionar: crie no cofre do n8n um item **Header "
                   f"Auth** chamado `{CRED_META_ITEM_NOME}` com o cabecalho de autorizacao "
                   "do token de sistema Meta, preencha `CRED_META_ITEM_ID` em "
                   "`n8n/gerar_flows_meta_ledger.py` com o id desse item e REGERE. Ate la "
                   "`meta.volc.credencial.provisionada` fica `false` e o publicador recusa "
                   "`--apply`.\n\n"
                   if not CRED_META_PROVISIONADA else
                   "**Credencial Meta PROVISIONADA.** O no `Meta Graph: insights` autentica "
                   f"por `{CRED_META_TIPO}`, referenciando pelo id o item "
                   f"`{CRED_META_ITEM_NOME}` do cofre do n8n. O nome e o valor do cabecalho "
                   "vivem no item, nunca neste arquivo.\n\n")
                + "Nenhum token, id de app ou id de conta vive neste arquivo — nem antes "
                "nem depois do provisionamento: o que viaja e uma REFERENCIA (id + nome do "
                "item do cofre), como ja acontece com `supabaseApi`.\n\n"
                "Gerado por `n8n/gerar_flows_meta_ledger.py`. **Nao edite este JSON a mao** — "
                "edite o gerador e regere.\n\n"
                "**A janela e D-1 NO FUSO DA CONTA** (`trafego_meta_ad_account.timezone_name`), "
                "nunca no fuso do servidor n8n. `TZ_DO_DISPARO` so rotula a rodada.\n\n"
                "`action_report_time`, `time_increment`, `breakdown` e as janelas de atribuicao "
                "sao pedidos explicitos e voltam no recibo. Sem janela pedida, o fato carimba "
                "`default` — nunca uma janela nominal que ninguem solicitou.\n\n"
                "Destino unico: `database.agenciavolc.com.br`. Somente leitura na Meta "
                "(nenhum POST/DELETE em objeto de anuncio). Ausencia permanece NULL; zero "
                "medido permanece zero. Janela truncada vira INCOMPLETA e nao avanca marca "
                "d'agua.\n\n"
                "Antes de ativar: provisionar a credencial Meta, APLICAR "
                "`supabase/migrations/20260908000000_meta_insights_escopo.sql` (sem ela "
                f"`{RPC_PERSISTIR}` recusa os escopos `insights_pagina`/`insights_fechamento`), "
                "e rodar o canario com `CONTAS_PERMITIDAS` = uma conta."
            ),
        }),
    ]

    conexoes = {
        "Agenda": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Executar manualmente": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Config": {"main": [[{"node": "Identidade da execucao", "type": "main", "index": 0}]]},
        "Identidade da execucao": {
            "main": [[{"node": "Contas autorizadas", "type": "main", "index": 0}]]},
        "Contas autorizadas": {
            "main": [[{"node": "Selecionar contas", "type": "main", "index": 0}]]},
        "Selecionar contas": {
            "main": [[{"node": "Objetos conhecidos", "type": "main", "index": 0}]]},
        "Objetos conhecidos": {
            "main": [[{"node": "Identidade VOLC por conta", "type": "main", "index": 0}]]},
        "Identidade VOLC por conta": {
            "main": [[{"node": "Lote de contas", "type": "main", "index": 0}]]},
        # main[0] = done (fim do laco) · main[1] = lote atual
        "Lote de contas": {"main": [
            [{"node": "Fechar execucao", "type": "main", "index": 0}],
            [{"node": "Pagina: preparar pedido", "type": "main", "index": 0}],
        ]},
        # O contexto da iteracao segue para o pedido E para os dois merges; a
        # resposta (ou o erro) casa com ele por posicao, na mesma iteracao.
        "Pagina: preparar pedido": {"main": [[
            {"node": "Meta Graph: insights", "type": "main", "index": 0},
            {"node": "Juntar contexto e resposta", "type": "main", "index": 1},
            {"node": "Juntar contexto e erro", "type": "main", "index": 1},
        ]]},
        # main[0] = sucesso · main[1] = saida de erro (continueErrorOutput)
        "Meta Graph: insights": {"main": [
            [{"node": "Juntar contexto e resposta", "type": "main", "index": 0}],
            [{"node": "Juntar contexto e erro", "type": "main", "index": 0}],
        ]},
        "Juntar contexto e resposta": {
            "main": [[{"node": "Pagina: normalizar", "type": "main", "index": 0}]]},
        "Juntar contexto e erro": {
            "main": [[{"node": "Classificar erro da Meta", "type": "main", "index": 0}]]},
        "Pagina: normalizar": {
            "main": [[{"node": "Validar semanticamente", "type": "main", "index": 0}]]},
        "Validar semanticamente": {
            "main": [[{"node": "RPC: ingerir lote", "type": "main", "index": 0}]]},
        "RPC: ingerir lote": {
            "main": [[{"node": "Reconciliar lote", "type": "main", "index": 0}]]},
        "Reconciliar lote": {
            "main": [[{"node": "Tem proxima pagina?", "type": "main", "index": 0}]]},
        # true = mais uma pagina da MESMA conta · false = conta encerrada
        "Tem proxima pagina?": {"main": [
            [{"node": "Pagina: preparar pedido", "type": "main", "index": 0}],
            [{"node": "Lote de contas", "type": "main", "index": 0}],
        ]},
        "Classificar erro da Meta": {
            "main": [[{"node": "Lote de contas", "type": "main", "index": 0}]]},
        "Fechar execucao": {
            "main": [[{"node": "Limite do fechamento", "type": "main", "index": 0}]]},
        "Limite do fechamento": {
            "main": [[{"node": "RPC: fechar recibo", "type": "main", "index": 0}]]},
        "RPC: fechar recibo": {
            "main": [[{"node": "Releitura do recibo", "type": "main", "index": 0}]]},
        "Releitura do recibo": {
            "main": [[{"node": "Batimento e saude", "type": "main", "index": 0}]]},
        "Batimento e saude": {
            "main": [[{"node": "Falha real?", "type": "main", "index": 0}]]},
        "Falha real?": {"main": [
            [{"node": "Alerta de rotina parada", "type": "main", "index": 0}],
            [],
        ]},
    }

    return {
        "name": nome,
        "nodes": nos,
        "connections": conexoes,
        "active": False,
        "settings": {
            "executionOrder": "v1",
            "timezone": "America/Sao_Paulo",
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
            "saveExecutionProgress": True,
            "saveManualExecutions": True,
            "executionTimeout": 3600,
        },
        "pinData": {},
        "meta": {
            "volc": {
                "gerador": "n8n/gerar_flows_meta_ledger.py",
                # ⚠️ IDENTIDADE PARA REENCONTRAR ESTE WORKFLOW NA INSTANCIA, e o
                # motivo dela existir: a instancia tem 396 workflows e ja carrega
                # nomes vizinhos ("Meta Insights", "VOLC - Meta Ads"). Procurar
                # por NOME casaria com um workflow de outra pessoa e o
                # sobrescreveria. `scripts/publicar_workflows_n8n_meta.py` procura
                # por (gerador, dono, contrato_sha256) — origem, dono e hash —, e
                # so trata como "o mesmo artefato" quem bate nos tres.
                "dono": "volc-os/trafego-meta",
                "artefato": "n8n/volc_meta_insights_dia_d1.json",
                "contrato": CONTRATO_VERSAO,
                "contrato_sha256": contrato_sha,
                "provider": "META_ADS",
                "rpc": RPC_PERSISTIR,
                "rpc_contrato": CONTRATO_RPC,
                "migration": CONTRATO_RPC["migration_base"],
                "papel": modo,
                "fuso_da_janela": "trafego_meta_ad_account.timezone_name",
                "credencial": {
                    # O TIPO agora e real (`httpHeaderAuth`, nativo do n8n); o que
                    # continua faltando e o ITEM no cofre. Os dois fatos sao
                    # diferentes e por isso viajam em campos diferentes: declarar
                    # so "NAO_PROVISIONADA" escondia que o tipo tambem era falso,
                    # e declarar so o tipo esconderia que nada resolve ainda.
                    "tipo": CRED_META_TIPO,
                    "mecanismo": "genericCredentialType",
                    "provisionada": CRED_META_PROVISIONADA,
                    "estado": ("PROVISIONADA" if CRED_META_PROVISIONADA
                               else "NAO_PROVISIONADA"),
                    "item_nome": CRED_META_ITEM_NOME,
                    # O id do item e REFERENCIA, nao segredo — mas enquanto o item
                    # nao existe o que viaja e o marcador, e ele fica declarado
                    # aqui para que um gate possa provar a COERENCIA entre o que o
                    # workflow diz e o que ele carrega no no.
                    "item_id_marcador": (None if CRED_META_PROVISIONADA
                                         else CRED_META_ITEM_MARCADOR),
                    "observacao": (
                        "o item do cofre ainda nao existe; o no aponta para um marcador "
                        "nomeado e nao resolve. Provisionar = criar o item Header Auth no "
                        "cofre do n8n, preencher CRED_META_ITEM_ID no gerador e regerar."
                        if not CRED_META_PROVISIONADA else
                        "referencia por id ao item do cofre do n8n; nome e valor do "
                        "cabecalho vivem no item, nunca neste arquivo."
                    ),
                },
                # ⚠️ ESTE E O BLOQUEIO, e ele e mecanico: enquanto for `false`,
                # `scripts/publicar_workflows_n8n_meta.py` recusa `--apply`. Nao
                # e um lembrete para alguem ler.
                "pronto_para_publicar": CRED_META_PROVISIONADA,
                "estado": (
                    "INATIVO — depende do pacote de autorizacao E do provisionamento "
                    "da credencial Meta"
                    if not CRED_META_PROVISIONADA else
                    "INATIVO — credencial provisionada; depende do pacote de autorizacao"
                ),
            }
        },
    }


def contrato_sha256() -> str:
    """Impressao do CONTRATO, e nao do arquivo.

    Ela viaja em todo recibo. Mudar o nivel, o incremento, o instante de
    relatorio, a janela pedida ou a lista de campos muda o hash — e o ledger
    passa a distinguir leituras de contratos diferentes sem depender de memoria
    de ninguem. Um numero coletado sob outro contrato nunca mais se soma
    calado com este.
    """
    corpo = json.dumps({
        "versao": CONTRATO_VERSAO,
        "api": API_VERSION,
        "provider": "META_ADS",
        "nivel": NIVEL,
        "time_increment": TIME_INCREMENT,
        "action_report_time": ACTION_REPORT_TIME,
        "breakdown": BREAKDOWN,
        "janelas_de_atribuicao": JANELAS_DE_ATRIBUICAO,
        "campos": CAMPOS_DE_INSIGHT,
        "rpc": RPC_PERSISTIR,
        "destino": SUPABASE,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


ALVOS = {
    "d1": "volc_meta_insights_dia_d1.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="não escreve; falha se o arquivo em disco divergir")
    args = parser.parse_args()

    sha = contrato_sha256()
    divergiu = []
    for papel, arquivo in ALVOS.items():
        destino = RAIZ / arquivo
        texto = json.dumps(construir(papel, sha), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
            if atual != texto:
                divergiu.append(arquivo)
        else:
            destino.write_text(texto, encoding="utf-8")
            print(f"gerado {destino.relative_to(RAIZ.parent)}")

    if args.check:
        if divergiu:
            print("FALHOU · o JSON em disco não é o que o gerador produz: "
                  + ", ".join(divergiu), file=sys.stderr)
            return 1
        print(f"ok · {len(ALVOS)} workflow(s) Meta em disco batem com o gerador "
              f"(contrato {sha[:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
