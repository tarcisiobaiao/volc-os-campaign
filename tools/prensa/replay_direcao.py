"""Replay offline do lote pago, isolado no /tmp do MESMO container Chrome.

Não usa HTTP, .env, provider nem reinicia o serviço. Copia apenas motor/fontes
empacotadas e cenas explícitas; arquivos originais permanecem intocados.
"""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from app.criativo.agente.contrato import SaidaDoAgente
from app.criativo.studio.spec_visual import especificar
from app.criativo.bancada.adaptadores import prensa_tradutor as T


def run(cmd,**kw):
    return subprocess.run(cmd,check=True,capture_output=True,timeout=300,**kw)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--container',default='volc-prensa')
    parser.add_argument('--output',type=Path,help='Diretório novo; nunca sobrescreve um replay')
    args=parser.parse_args()
    output=args.output or Path(tempfile.mkdtemp(prefix='volc-prensa-direcao-'))
    if args.output: output.mkdir(parents=True, exist_ok=False)
    stage=output/'motor'; stage.mkdir(); (stage/'out').mkdir()
    for p in (ROOT/'services/prensa/motor').glob('*.py'): shutil.copy2(p,stage/p.name)
    shutil.copy2(ROOT/'tools/prensa/provar_chrome.py',stage/'provar_chrome.py')
    news=json.loads((ROOT/'services/prensa/motor/spec_news.json').read_text())
    (stage/'out'/f'spec_{news["spec_id"]}.json').write_text(json.dumps(news))
    shutil.copy2(ROOT/'services/prensa/motor/tokens_news.json',stage/'tokens_news.json')
    src=args.source
    saida=SaidaDoAgente.model_validate_json((src/'4-copy/saida_do_agente.json').read_text())
    catalog=json.loads((src/'4-copy/catalogo_do_lote.json').read_text())
    copies={c.ref:c for c in saida.copies_compartilhadas}
    pecas={p.ref:(i,p) for i,p in enumerate(saida.pecas)}
    familia=['azul royal','amarelo ouro','verde bandeira','branco']
    skin=T.skin_da_familia(familia,identificador='VOS:pedemeia-direcao-v2',versao_direcao='2')
    (stage/'out/tokens.json').write_text(json.dumps(skin,ensure_ascii=False))
    manifest=[]
    for item in catalog:
        if item['tipografia']!='codigo': continue
        i,p=pecas[item['peca']]
        spec=especificar(p,copies[p.shared_copy_ref],item['slot'],'sem_foto',
                        familia_cromatica=familia,semente_do_plano=i,tipografia_por_codigo=True)
        path=src/'3-cenas-limpas'/item['arquivo']
        from PIL import Image
        with Image.open(path) as im: w,h=im.size
        shutil.copy2(path,stage/'out'/path.name)
        nome=f"real_{p.ref.replace('creative_','')}_{item['slot'].replace('.','_')}"
        old=json.loads((src/'5-recibos'/f'spec_{nome}.json').read_text())
        post=T.traduzir(spec,artboard=(item['largura'],item['altura']),ancora='Pé-de-Meia',
            ancoras_aceitas=['Pé de Meia','poupança do ensino médio','a poupança'],
            asset={'id':'cena_ia','file':f'out/{path.name}','w':w,'h':h},
            botao=item['altura']>=700,
            kicker='CHECAGEM · CADÚNICO' if 'documento' in nome else 'ANTES DE ENTRAR EM PÂNICO',
            tokens_file='out/tokens.json',versao_direcao='2')
        assert T.textos_de(post)==T.textos_de(old),f'copy alterada: {nome}'
        assert post['gates']==old['gates'],f'gates alterados: {nome}'
        post['spec_id']=nome
        (stage/'out'/f'spec_{nome}.json').write_text(json.dumps(post,ensure_ascii=False,indent=2))
        manifest.append({'id':nome,'copy_preservada':True,'gates_preservados':True,
                         'scene_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as tar:
        for p in stage.rglob('*'):
            if p.is_file(): tar.add(p,arcname=str(p.relative_to(stage)))
    import uuid
    remote='/tmp/prensa-replay-'+uuid.uuid4().hex
    run(['docker','exec','-i',args.container,'python','-c',
         'import sys,tarfile,pathlib; p=pathlib.Path(sys.argv[1]); p.mkdir(); '
         'tarfile.open(fileobj=sys.stdin.buffer,mode="r|").extractall(p,filter="data"); '
         '(p/"fonts").symlink_to("/prensa/motor/fonts"); '
         '(p/"out/bg_news.png").symlink_to("/prensa/motor/out/bg_news.png")',remote],input=buf.getvalue())
    print(f'OUTPUT={output}',flush=True)
    try:
        qa=run(['docker','exec','-w',remote,args.container,'python','provar_chrome.py',
                '--motor',remote,'--output','out/prova_chrome.json'])
    except subprocess.CalledProcessError as exc:
        (output/'chrome.log').write_bytes(exc.stdout+exc.stderr)
        raise
    (output/'chrome.log').write_bytes(qa.stdout+qa.stderr)
    def render(entry):
        name=entry['id']
        code=('import subprocess,sys,pathlib; n=sys.argv[1]; '
              'subprocess.run([sys.executable,"resolve.py",f"out/spec_{n}.json"],check=True); '
              'p=next(pathlib.Path("out").glob(n+".*.resolvido.json")); '
              'subprocess.run([sys.executable,"render.py",str(p)],check=True)')
        r=subprocess.run(['docker','exec','-w',remote,args.container,'python','-c',code,name],capture_output=True,text=True,timeout=300)
        (output/f'{name}.log').write_text(r.stdout+r.stderr)
        entry['render_exit_code']=r.returncode
        print(name,r.returncode,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(render,manifest))
    stock={'id':news['spec_id'],'spec':'spec_news.json'}
    render(stock)
    (output/'acervo.json').write_text(json.dumps(stock,indent=2))
    data=run(['docker','exec',args.container,'python','-c',
        'import sys,tarfile,pathlib; p=pathlib.Path(sys.argv[1]); '
        't=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); '
        '[t.add(f,arcname=f.name) for f in p.iterdir() if f.is_file() and not f.is_symlink()]; t.close()',remote+'/out']).stdout
    rendered=output/'depois'; rendered.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar: tar.extractall(rendered,filter='data')
    for entry in manifest:
        resolved=next(rendered.glob(entry['id']+'.*.resolvido.json'),None)
        if resolved:
            fonts=json.loads(resolved.read_text())['fonts']
            entry['fontes_embutidas']=[{'family':f['family'],'file':f['file']} for f in fonts]
            entry['bytes_fontes']=sum((ROOT/'services/prensa/motor'/f['file']).stat().st_size for f in fonts)
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    before=output/'antes'; before.mkdir()
    for e in manifest: shutil.copy2(src/'1-prensa'/f'{e["id"]}.png',before/f'{e["id"]}.png')
    baseline=src/'6-direcao-v2/depois'
    has_baseline=all((baseline/f'{e["id"]}.png').is_file() for e in manifest)
    if has_baseline:
        (output/'anterior-v2').mkdir()
        for e in manifest: shutil.copy2(baseline/f'{e["id"]}.png',output/'anterior-v2'/f'{e["id"]}.png')
    rows=[]
    for e in manifest:
        columns=[('antes','Original v1')]
        if has_baseline: columns.append(('anterior-v2','v2 revisada pelo Claude'))
        columns.append(('depois','Refinamento atual'))
        cells=''.join(f'<figure><figcaption>{label}</figcaption><img loading="lazy" alt="{label}: {e["id"]}" src="{folder}/{e["id"]}.png"></figure>' for folder,label in columns)
        rows.append(f'<section><h2>{e["id"]}</h2><div>{cells}</div></section>')
    (output/'comparacao.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PRENSA · comparação controlada</title><style>body{background:#e9edf2;color:#152033;font:16px system-ui;margin:24px}section{max-width:1600px;margin:auto}section>div{display:grid;grid-auto-columns:1fr;grid-auto-flow:column;gap:24px}figure{margin:0}img{width:100%}h2{font-size:16px;margin-top:48px}figcaption{padding:12px} @media(max-width:650px){section>div{grid-auto-flow:row;gap:24px}}</style><h1>Mesma cena. Mesma copy. Outra direção.</h1><p>Prova local · sem nova geração paga · aceite visual pendente.</p>'+''.join(rows)+'</html>')
    return int(any(e['render_exit_code'] for e in manifest) or stock['render_exit_code'])


if __name__=='__main__': raise SystemExit(main())
