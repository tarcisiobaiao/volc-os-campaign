import json,sys,os,glob
for f in sorted(glob.glob(sys.argv[1]+'/*.json')):
    try: d=json.load(open(f))
    except Exception as e: print(os.path.basename(f),'ERR',e); continue
    if 'info' not in d: print(os.path.basename(f),'NOTFOUND'); continue
    i=d['info']; v=i['version']; files=d['releases'].get(v,[]) or d.get('urls',[])
    up=min((x['upload_time'] for x in files),default='?')
    tags=[x['filename'] for x in files if x['packagetype']=='bdist_wheel']
    cp314=any(('cp314' in t) or ('py3-none' in t) or ('abi3' in t) or ('py2.py3' in t) for t in tags)
    mac=[t for t in tags if 'macosx' in t and ('arm64' in t or 'universal2' in t) and ('cp314' in t or 'abi3' in t)]
    pure=any('none-any' in t for t in tags)
    lic=i.get('license_expression') or (i.get('license') or '')[:40].replace('\n',' ')
    print(f"{os.path.basename(f)[:-5]:32} v{v:14} {up[:10]} py{i.get('requires_python')} lic={lic} pure={pure} cp314mac={len(mac)>0} nwheels={len(tags)}")
