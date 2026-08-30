#!/usr/bin/env python3
"""Aplica as correções nos flows Join Ads vivos, preservando auth e JOIN_DOMAIN."""
import json, os, sys, urllib.request, datetime

BASE = os.environ['N8N_BASE_URL']
KEY = os.environ['N8N_API_KEY']
REPO = '/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/n8n'
BACKUP = os.environ['BACKUP_DIR']

# LOOKBACK_DAYS mantém a expressão de override pelo corpo do webhook — é ela que
# faz o botão "atualizar agora" poder pedir uma janela maior sem editar o flow.
ALVOS = {
    'RpxB9ppefxZWujEV': ('joinads_report_day_before.json',
                         {'OFFSET_DAYS': '1',
                          'LOOKBACK_DAYS': '={{ $json.body?.lookback_days ?? 2 }}'}),
    'U0jEfGt30HqbUq1o': ('joinads_report_intraday.json',
                         {'OFFSET_DAYS': '0',
                          'LOOKBACK_DAYS': '={{ $json.body?.lookback_days ?? 0 }}'}),
}
CODE_NODES = ['Monta janelas', 'Normaliza earnings', 'Normaliza key-value', 'Resumo']
DRY = '--apply' not in sys.argv


def api(metodo, caminho, corpo=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{caminho}", method=metodo,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"},
        data=json.dumps(corpo).encode() if corpo else None)
    return json.load(urllib.request.urlopen(req))


os.makedirs(BACKUP, exist_ok=True)

for wid, (arquivo, janela) in ALVOS.items():
    vivo = api('GET', f'/workflows/{wid}')
    novo = json.load(open(os.path.join(REPO, arquivo)))
    novos_code = {n['name']: n['parameters']['jsCode']
                  for n in novo['nodes'] if n['type'].endswith('.code')}

    # backup ANTES de qualquer coisa
    bkp = os.path.join(BACKUP, f"{wid}-{vivo['name'].replace(' ', '_')}.json")
    with open(bkp, 'w', encoding='utf-8') as fh:
        json.dump(vivo, fh, indent=2, ensure_ascii=False)

    mudancas = []
    for n in vivo['nodes']:
        # 1. Code nodes: troca só o jsCode
        if n['name'] in CODE_NODES and n['name'] in novos_code:
            if n['parameters'].get('jsCode') != novos_code[n['name']]:
                n['parameters']['jsCode'] = novos_code[n['name']]
                mudancas.append(f"jsCode: {n['name']}")

        # 2. Config: preserva JOIN_DOMAIN, ajusta janela, troca chaves
        if n['name'] == 'Config':
            asg = n['parameters']['assignments']['assignments']
            porNome = {a['name']: a for a in asg}
            for k, v in janela.items():
                if k in porNome and porNome[k]['value'] != v:
                    mudancas.append(f"Config.{k}: {porNome[k]['value']!r} -> {v!r}")
                    porNome[k]['value'] = v
            if 'MAX_RANGE_DAYS' in porNome:
                porNome['MAX_RANGE_DAYS']['name'] = 'MAX_DIAS_POR_RUN'
                porNome['MAX_RANGE_DAYS']['value'] = '62'
                mudancas.append('Config: MAX_RANGE_DAYS -> MAX_DIAS_POR_RUN=62')
            if 'CUSTOM_KEY' not in porNome:
                asg.append({'id': 'c10', 'name': 'CUSTOM_KEY',
                            'type': 'string', 'value': 'utm_campaign'})
                mudancas.append('Config: + CUSTOM_KEY=utm_campaign')
            dom = porNome.get('JOIN_DOMAIN', {}).get('value')
            print(f"    (JOIN_DOMAIN preservado: {dom!r})")

        # 3. custom_key do key-value passa a ler do Config
        if n['name'] == 'Join - GET /key-value':
            for p in n['parameters'].get('queryParameters', {}).get('parameters', []):
                if p['name'] == 'custom_key' and not str(p['value']).startswith('='):
                    p['value'] = "={{ $('Config').first().json.CUSTOM_KEY }}"
                    mudancas.append('key-value: custom_key -> lê do Config')

    print(f"\n■ {vivo['name']}  ({wid})  ativo={vivo.get('active')}")
    print(f"  backup: {bkp}")
    for m in mudancas:
        print(f"  · {m}")
    if not mudancas:
        print("  (nada a mudar)")
        continue

    if DRY:
        print("  → DRY RUN, nada enviado")
        continue

    # PUT só aceita estes campos
    payload = {k: vivo[k] for k in ('name', 'nodes', 'connections', 'settings')}
    api('PUT', f'/workflows/{wid}', payload)
    print("  → aplicado")

print("\nDRY RUN — rode com --apply para valer" if DRY else "\nconcluído")
