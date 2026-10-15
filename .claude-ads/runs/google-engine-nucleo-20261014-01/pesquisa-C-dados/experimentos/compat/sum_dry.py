import json,glob,os,sys
base=set(l.split('==')[0].lower().replace('_','-') for l in open(sys.argv[1]) if '==' in l)
for f in sorted(glob.glob(sys.argv[2]+'/*.json')):
    d=json.load(open(f)); inst=d.get('install',[])
    novos=[i['metadata']['name']+'=='+i['metadata']['version'] for i in inst if i['metadata']['name'].lower().replace('_','-') not in base]
    sdists=[i['metadata']['name'] for i in inst if not i['download_info']['url'].endswith('.whl')]
    tot=sum((i['download_info'].get('archive_info',{}) or {}).get('size',0) or 0 for i in inst)
    print(f"{os.path.basename(f)[:-5]:32} total={len(inst):3} novos={len(novos):3} sdist={sdists} ", ' '.join(sorted(novos))[:900])
