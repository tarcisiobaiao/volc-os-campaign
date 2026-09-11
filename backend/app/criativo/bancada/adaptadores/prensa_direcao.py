"""Direção tipográfica v2. Papéis, não skins de clientes nem copy reescrita.

Escala de projeto: 16px de leitura a 540px de exibição -> apoio mínimo32px
no canvas1080. CTA18px ->36px. O título pode ceder antes desses dois papéis.
Esses são critérios de design declarados, não promessa de CTR.
"""
from copy import deepcopy


FONTES = [
    ('Archivo',700,'Archivo-Variable','0e094a7d3c7c4c25cf1310c4b30014f1dae9332220b1c2c88f4fa996f0b05053','100 900',None),
    ('Barlow Condensed',700,'BarlowCondensed-Bold','e476562ec9c1e16cf16475895b511f08c804f438cc9a9f80a44ea50a0eeb5b65',None,None),
    ('Barlow Condensed',500,'BarlowCondensed-Medium','262bd143292ce479ee0cd09a42b47ab173fca8e9c6eb5ed0b5c8a845bc371d17',None,None),
    ('Source Serif 4',500,'SourceSerif4-Variable','97b2d4da6e3cb494b5a1e66ae176914d852ccabef49e0c02c0df25f3e39aca0b','200 900',None),
    ('IBM Plex Mono',700,'IBMPlexMono-Bold','ac27abd6450a64dd94467580a02fe6235156d5b92f2926ebbc8e7489df64e0be',None,None),
    ('IBM Plex Mono',300,'IBMPlexMono-Light','780bcf65509d72a35ec114b57bcbe220dc6b77d8ea2e9b25e294be3c570c5025',None,None),
    ('Instrument Serif',400,'InstrumentSerif-Italic','08939b8bdf534afec24ae0ef5e03f948940cd9a8fe08e7fecbad040e62327385',None,'italic'),
    ('Bodoni Moda',500,'BodoniModa-Italic','dfff1619f8f6871c6372f8855b67211f9a73b4e93d45aca868cd8f46a48622de','400 900','italic'),
    ('Cormorant Garamond',700,'CormorantGaramond-Variable','b20b7d9626dd956b2c5e558692ad328b1f19e3275e2782db4fa07670d83f35e0','300 700',None),
]


def fonte(family, weight, line_height=1.12, **extras):
    # hhea (ascender-descender+lineGap)/unitsPerEm dos arquivos SHA acima.
    metrica={'Archivo':1.088,'Barlow Condensed':1.2,'Inter':1.21,
             'Source Serif 4':1.371,'IBM Plex Mono':1.3,'Instrument Serif':1.3,
             'Bodoni Moda':1.525,'Cormorant Garamond':1.211}[family]
    padding=round(max(0,(metrica-line_height)/2)+0.02,3)  # 0.02em tolerância de raster
    if family=='Inter': extras.setdefault('variacao',f"'opsz' 32, 'wght' {weight}")
    if family=='Source Serif 4': extras.setdefault('variacao',f"'opsz' 32, 'wght' {weight}")
    return dict(family=family,weight=weight,line_height=line_height,
                ink_padding=f'{padding}em 0.04em',tracking='-0.015em',wrap='balance',**extras)


REGISTROS = {
    'editorial': dict(display=fonte('Archivo',700),body=fonte('Source Serif 4',500,1.24),label=fonte('Inter',700)),
    'documento': dict(display=fonte('Archivo',800),body=fonte('Source Serif 4',500,1.24),label=fonte('IBM Plex Mono',700)),
    'foto_crua': dict(display=fonte('Barlow Condensed',700,1.02),body=fonte('Inter',600,1.20),label=fonte('Barlow Condensed',700)),
    'cartaz_beneficio': dict(display=fonte('Barlow Condensed',700,1.02),body=fonte('Inter',600,1.20),label=fonte('Barlow Condensed',700)),
    'grafico': dict(display=fonte('Archivo',800),body=fonte('Inter',500,1.24),label=fonte('IBM Plex Mono',700)),
}


def completar_skin(skin):
    for family,weight,file,sha,weight_range,style in FONTES:
        f=dict(role='registro',family=family,weight=weight,file=f'fonts/{file}.ttf',sha256=sha)
        if weight_range: f['weight_range']=weight_range
        if style: f['style']=style
        skin['fonts'].append(f)
    skin['type']['registros']=deepcopy(REGISTROS)
    skin['type']['registros']['editorial']['accent']=fonte('Instrument Serif',400,style='italic')
    skin['type']['registros']['documento']['serifa']=fonte('Cormorant Garamond',700)
    skin['type']['registros']['grafico']['accent']=fonte('Bodoni Moda',500,style='italic',variacao="'opsz' 72, 'wght' 500")
    skin['type']['registros']['grafico']['nota']=fonte('IBM Plex Mono',300)
    skin['type']['registros']['cartaz_beneficio']['nota']=fonte('Barlow Condensed',500)
    # A tinta pode ser neutra; a família de campanha continua nas superfícies.
    skin['color']['ink']={'dark':'#101C30','light':'#F7F7F5'}
    from .prensa_tradutor import contraste
    candidatos=['#101C30','#F7F7F5']
    fundo=skin['color']['accent']['text']
    tinta=max(candidatos,key=lambda c:contraste(c,fundo))
    if contraste(tinta,fundo)<4.5:
        tinta=max(['#000000','#FFFFFF'],key=lambda c:contraste(c,fundo))
    skin['color']['ink']['on_accent']=tinta
    return skin


def aplicar(post, spec):
    camadas=post.get('layers') or post['slides'][0]['layers']
    registro=str(spec.direcao_de_arte.get('registro') or 'editorial')
    if registro not in REGISTROS:
        raise ValueError(f'registro de direção desconhecido: {registro}')
    claro=(spec.plano_de_composicao or {}).get('nome')=='faixa_inferior_clara'
    tinta='$color.ink.dark' if claro else '$color.ink.light'
    w,h=post['artboard']['base']['w'],post['artboard']['base']['h']
    escala=min(w,h)/1080
    # Piso legível por menor eixo; o banner não herda corpos de um story.
    apoio=max(24,round(32*escala))
    cta=max(32,round(36*escala))
    frame=next(c for c in camadas if c['id']=='conteudo')
    if registro=='cartaz_beneficio' and h>=w:
        # Coluna de 68% (CTA ocupa64%): reduz a medição de pixels sem texto
        # à direita e deixa a outra coluna para a cena. Hipótese visual v2.
        frame['max_width']=min(frame['max_width'],round(w*.68))
    if not any(c['type']=='image' for c in camadas): tinta='$color.text.primary'
    botao=next((c for c in camadas if c['id']=='botao'),None)
    gap=max(12,round(apoio/2))
    frame['layout']['gap']=gap
    for c in frame['children']:
        papel={'headline':'display','complemento':'body','cta':'label'}[c['id']]
        c['style']['font']=f'$type.registros.{registro}.{papel}'
        c['style']['color']=tinta
        c.pop('efeitos',None)  # nenhuma névoa sobre a palavra; contraste vem da cena
        if c['id']=='headline':
            c['style']['accent_color']=tinta if claro else '$color.accent.text'
            protagonista=spec.direcao_de_arte.get('rota_de_texto')=='tipografia_protagonista'
            c['fit'].update(min=max(34,round(48*escala)),max=round(w*(0.155 if protagonista or registro in ('cartaz_beneficio','foto_crua') else 0.115)),shrink_priority=0)
            for run in c['runs']:
                if run.get('accent'): run['nowrap']=True
                # Chapa de anúncio só no cartaz; sem halo nem outras camadas de efeito.
                if registro!='cartaz_beneficio': run.pop('tratamento',None)
        elif c['id']=='complemento':
            c['fit'].update(min=apoio,max=round(apoio*1.25),shrink_priority=1)
        else:
            c['fit'].update(mode='fixed',size=cta)
    if botao:
        old=botao['children'][0]['fit']['size']
        botao['children'][0]['fit']['size']=cta
        botao['children'][0]['style']['font']=f'$type.registros.{registro}.label'
        botao['children'][0]['style']['color']='$color.ink.on_accent'
        # Nova altura do CTA é debitada do bloco, nunca da safe area.
        extra=round((cta-old)*1.44)
        frame['zona_h']-=extra
        if frame['pos']['anchor'].startswith('bottom'): frame['pos']['y']+=extra
        botao['style']['radius']=0 if registro=='documento' else round(cta*0.6)
        botao['width']=min(frame['max_width'],round(w*0.64)) if registro=='cartaz_beneficio' else frame['max_width']
        botao['layout']['justify']='center' if registro=='cartaz_beneficio' else 'flex-start'
    if frame['zona_h']<=0: raise ValueError('direção sem altura útil')
    # O retângulo medido segue exatamente o frame; nenhum fade global de rodapé.
    x=frame['pos']['x']; y=frame['pos']['y']
    if frame['pos']['anchor'].startswith('bottom'): y=h-y-frame['zona_h']
    selo=next((c for c in camadas if c['id']=='selo'),None)
    if selo:
        selo['box']={'x':x,'y':y,'w':frame['max_width'],'h':frame['zona_h']}
        cores=[tinta]
        if not claro and any(r.get('accent') and not r.get('tratamento') for r in frame['children'][0]['runs']):
            cores.append('$color.accent.text')
        selo['style']['gradient']={'auto_local':True,'cores_texto':cores,
            'cor_veu':'#FFFFFF' if claro else '#000000','contraste_alvo':7.0}
        selo['feather']=gap*4
        selo['borda']='dissolver'
    camadas[:]=[c for c in camadas if c['type'] not in ('vinheta','texture')]
    # O cartaz tem rubrica compacta, o documento mantém a linha de classificação.
    kicker=next((c for c in camadas if c['id']=='kicker_row'),None)
    if kicker:
        if registro in ('cartaz_beneficio','foto_crua'):
            kicker['children']=[c for c in kicker['children'] if c['id']=='kicker']
        k=next(c for c in kicker['children'] if c['id']=='kicker')
        k['style']['font']=f'$type.registros.{registro}.label'
    checklist=next((c for c in camadas if c['id']=='checklist'),None)
    if checklist:
        checklist.update(verificar=True,tam_titulo=apoio,tam_corpo=apoio,padding=gap)
        checklist['style'].update(fill='$color.surface.base',cor_titulo='$color.accent.text',
                                 cor_corpo='$color.text.primary',cor_fio='$color.linha.fio',
                                 font_titulo=f'$type.registros.{registro}.label',
                                 font_corpo=f'$type.registros.{registro}.body')
        if registro=='cartaz_beneficio':
            # Coluna lateral: 28% deixa os 72% restantes para o objeto central.
            # Hipótese compositiva, NÃO detecção automática de sujeito.
            checklist.update(orientacao='vertical',w=round(w*.28),gap=gap)
            checklist['style']['font_corpo']=f'$type.registros.{registro}.nota'
    post['direcao_resolvida']={'versao':'2','registro':registro,'tinta':'escura' if claro else 'clara',
        'apoio_min_px':apoio,'cta_px':cta,'escala_base':'16px em preview540; CTA18px; menor eixo/1080'}
    return post
