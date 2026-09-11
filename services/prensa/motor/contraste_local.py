"""Mede a zona visível, simulando a composição sRGB que o CSS pinta.

Percentil5 é uma garantia estatística da área, NÃO gate de pixel dos glifos.
O recibo declara essa limitação. Dependência ausente ou zona inválida é erro.
"""
import numpy as np
from PIL import Image, ImageOps


def rgb(hexadecimal):
    return np.array([int(hexadecimal[i:i+2],16) for i in (1,3,5)],dtype=float)/255


def lum(c):
    linear=np.where(c<=0.04045,c/12.92,((c+0.055)/1.055)**2.4)
    return linear @ np.array([0.2126,0.7152,0.0722])


def medir(arquivo, artboard, box, object_position, cores, cor_veu, alvo):
    w,h=artboard
    x,y,bw,bh=(int(box[k]) for k in ('x','y','w','h'))
    if w<=0 or h<=0 or bw<=0 or bh<=0 or x<0 or y<0 or x+bw>w or y+bh>h:
        raise ValueError('zona local inválida')
    if not cores or not 1<alvo<=21: raise ValueError('contraste local inválido')
    horizontal,vertical=object_position.split()
    centros={'left':0,'top':0,'center':0.5,'right':1,'bottom':1}
    with Image.open(arquivo) as origem:
        cena=ImageOps.fit(origem.convert('RGB'),(w,h),method=Image.Resampling.LANCZOS,
                         centering=(centros[horizontal],centros[vertical]))
    pixels=np.asarray(cena.crop((x,y,x+bw,y+bh)),dtype=float)/255
    # Uma malha regular de até ~16k amostras; não muda o enquadramento medido.
    pixels=pixels[::max(1,bh//128),::max(1,bw//128)]
    tinta=[float(lum(rgb(c))) for c in cores]; veu=rgb(cor_veu)
    for passo in range(101):
        alpha=passo/100
        fundo=lum(pixels*(1-alpha)+veu*alpha)
        ratios=[float(np.percentile((np.maximum(fundo,t)+0.05)/(np.minimum(fundo,t)+0.05),5)) for t in tinta]
        if min(ratios)>=alvo:
            return dict(alpha=alpha,contraste_p05=round(min(ratios),4),alvo=alvo,
                        box=box,espaco='sRGB CSS',garantia='percentil5 da zona; não gate de glifos')
    raise ValueError('contraste local impossível para as tintas declaradas')
