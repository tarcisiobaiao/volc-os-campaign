import json, sys
sys.path.insert(0, '.')
from guard_cfm import audita
CRM = "CRM 30986-PR"

def base(sid, i, kicker, runs, hy=186, hmax=104, hlines=3):
    return [
      {"id":"vinheta","type":"vinheta","cor":"$efeitos.vinheta.cor","raio":"$efeitos.vinheta.raio","centro":"$efeitos.vinheta.centro"},
      {"id":"kicker_row","type":"frame","pos":{"anchor":"top_left","x":102,"y":100},
       "layout":{"mode":"horizontal","gap":18,"align":"center"},
       "children":[{"id":"kicker_rule","type":"rect","w":48,"h":5,"fill":"$color.accent.graphic","radius":0,"verniz":"$efeitos.verniz"},
                   {"id":"kicker","type":"text","slot":"kicker","runs":[{"text":kicker}],
                    "style":{"font":"$type.kicker","color":"$color.accent.text"},
                    "fit":{"mode":"fixed","size":25,"max_lines":1,"overflow":"fail"}}]},
      {"id":"headline","type":"text","slot":"headline","pos":{"anchor":"top_left","x":102,"y":hy},
       "max_width":884,"runs":runs,
       "style":{"font":"$type.display","color":"$color.text.primary","accent_color":"$color.accent.text"},
       "efeitos":{"halacao":"$?efeitos.halacao_accent"},
       "fit":{"mode":"auto","min":50,"max":hmax,"max_lines":hlines,"hyphenate":False,"overflow":"fail"}},
      {"id":"handle","type":"text","slot":"label","pos":{"anchor":"bottom_left","x":102,"y":96},
       "runs":[{"text":f"@dr.andersonramos · {CRM}" if sid in ("capa","cta") else "@dr.andersonramos"}],
       "style":{"font":"$type.label","color":"$color.text.muted"},
       "fit":{"mode":"fixed","size":21,"max_lines":1}},
      {"id":"dots","type":"dots","total":6,"atual":i,"size":9,"gap":10,
       "cor_ativa":"$color.dots.ativa","cor_inativa":"$color.dots.inativa",
       "pos":{"anchor":"bottom_right","x":102,"y":100}},
      {"id":"grain","type":"texture","opacity":"$efeitos.grao.opacity","blend":"$efeitos.grao.blend",
       "escala":"$efeitos.grao.escala","piso":"$efeitos.grao.piso","amplitude":"$efeitos.grao.amplitude"}]

def nota(txt, y=200, x=108):
    return {"id":"nota","type":"text","slot":"serifa","pos":{"anchor":"bottom_left","x":x,"y":y},
            "max_width":850,"runs":[{"text":txt}],
            "style":{"font":"$type.serifa","color":"$color.text.nota"},
            "fit":{"mode":"fixed","size":29,"max_lines":2,"overflow":"fail"}}

EST_TAB = {"font_rotulo":"$type.kicker","font_valor":"$type.body",
           "cor_rotulo":"$color.text.secondary","cor_valor":"$color.text.primary",
           "cor_destaque":"$color.accent.text","cor_regua":"$color.linha.regua"}
EST_COL = {"font_titulo":"$type.kicker","font_corpo":"$type.body",
           "cor_titulo":"$color.text.secondary","cor_corpo":"$color.text.secondary",
           "cor_fio":"$color.linha.fio"}

S = []
# 1 · CAPA — tipografia dual (serifada itálica no acento) + halação
S.append({"id":"capa","background":"$color.surface.base","layers":
  base("capa",0,"LONGEVIDADE · BIOMARCADORES",
       [{"text":"Seu exame veio normal. Sua biologia, "},
        {"text":"não","fonte":"$type.accent_serif"},{"text":"."}], hy=470, hmax=118)
  + [nota("— faixa de referência é estatística de população doente.", 260)]})

# 2 · TABELA — o biomarker_ledger
S.append({"id":"ledger","background":"$color.surface.base","layers":
  base("ledger",1,"SINAL 01 · A TABELA",
       [{"text":"Normal e "},{"text":"ótimo","accent":True},{"text":" não são a mesma faixa"}])
  + [{"id":"tabela","type":"tabela","pos":{"anchor":"top_left","x":102,"y":486},"w":884,
      "tam_rotulo":24,"tam_valor":32,"style":EST_TAB,
      "linhas":[{"rotulo":"VITAMINA D","valor":"30 → 60 ng/mL","destaque":True},
                {"rotulo":"FERRITINA","valor":"15 → 100 ng/mL","destaque":True},
                {"rotulo":"TSH","valor":"4,5 → 2,0 mUI/L","destaque":True},
                {"rotulo":"HOMOCISTEÍNA","valor":"15 → 7 µmol/L","destaque":True},
                {"rotulo":"PCR ULTRA-SENSÍVEL","valor":"3,0 → 0,5 mg/L","destaque":True}]},
     nota("— à esquerda o laboratório libera; à direita a biologia agradece.", 210)]})

# 3 · COLUNAS — comparação com fio
S.append({"id":"colunas","background":"$color.surface.base","layers":
  base("colunas",2,"SINAL 02 · A COMPARAÇÃO",
       [{"text":"Mesmo número. Conduta "},{"text":"oposta.","accent":True}])
  + [{"id":"colunas_bloco","type":"colunas","pos":{"anchor":"top_left","x":102,"y":500},"w":884,"gap":40,
      "tam_titulo":24,"tam_corpo":27,"style":EST_COL,
      "colunas":[{"titulo":"LAUDO A","cor":"$color.text.muted",
                  "texto":"Ferritina 18. Dentro da referência. Cansaço atribuído à rotina. Sem conduta."},
                 {"titulo":"LAUDO B","cor":"$color.accent.text",
                  "texto":"Ferritina 18. Fora do ótimo. Investigação de perda oculta e reposição dirigida."}]},
     nota("— o exame não mudou. A leitura mudou.", 230)]})

# 4 · MEDIDOR — escala com faixa segura
S.append({"id":"medidor","background":"$color.surface.base","layers":
  base("medidor",3,"SINAL 03 · A ESCALA",
       [{"text":"Você vive no "},{"text":"piso","accent":True},{"text":" do aceitável"}])
  + [{"id":"medidor_barra","type":"medidor","pos":{"anchor":"top_left","x":102,"y":520},"w":884,"h":18,
      "valor_frac":0.17,"faixa_segura":[0.55,0.9],
      "style":{"cor_trilho":"$color.linha.trilho","cor_preenchido":"$color.accent.dim",
               "cor_faixa":"$color.accent.text","cor_marcador":"$color.accent.text"}},
     {"id":"legenda","type":"colunas","pos":{"anchor":"top_left","x":102,"y":578},"w":884,"gap":40,
      "tam_titulo":22,"tam_corpo":25,"style":EST_COL,
      "colunas":[{"titulo":"ONDE VOCÊ ESTÁ","texto":"Liberado pelo laudo. Sintomático na prática."},
                 {"titulo":"FAIXA ÓTIMA","cor":"$color.accent.text","texto":"Onde a performance celular deixa de ser gargalo."}]},
     nota("— a barra clara é onde a biologia trabalha sem esforço.", 220)]})

# 5 · CARIMBO — knockout, contorno e verniz na mesma lâmina
S.append({"id":"carimbo","background":"$color.surface.base","layers":
  base("carimbo",4,"SINAL 04 · A DECISÃO",
       [{"text":"Não é "},
        {"text":"sorte","tratamento":{"tipo":"contorno","cor":"#C9A84C","espessura":"3px"}},
        {"text":". É "},
        {"text":"método","accent":True,"tratamento":{"tipo":"verniz"}},
        {"text":"."}], hy=430, hmax=126)
  + [{"id":"selo","type":"text","slot":"headline","pos":{"anchor":"top_left","x":102,"y":700},
      "max_width":884,
      "runs":[{"text":"5 anos de","tratamento":{"tipo":"knockout","cor":"#C9A84C","cor_texto":"auto"}},
              {"text":" biomarcador não mente"}],
      "style":{"font":"$type.display","color":"$color.text.primary"},
      "fit":{"mode":"auto","min":40,"max":62,"max_lines":2,"overflow":"fail"}},
     nota("— o corpo registra a média, não a intenção.", 230)]})

# 6 · CTA
S.append({"id":"cta","background":"$color.surface.base","layers":
  base("cta",5,"PROTOCOLO INDIVIDUALIZADO",
       [{"text":"Ler o laudo é fácil. Ler a "},
        {"text":"biologia","fonte":"$type.accent_serif"},{"text":" é outra coisa."}], hy=430, hmax=112)
  + [{"id":"fecho","type":"text","slot":"body","pos":{"anchor":"bottom_left","x":102,"y":240},
      "max_width":860,"runs":[{"text":"Consulta de Performance · Curitiba · drandersonramos.com.br"}],
      "style":{"font":"$type.body","color":"$color.text.secondary"},
      "fit":{"mode":"auto","min":24,"max":31,"max_lines":2,"overflow":"fail"}},
     nota("— conteúdo educativo. Não substitui consulta médica.", 168)]})

txt = [CRM]
for sl in S:
    for c in sl["layers"]:
        if c.get("type")=="text": txt += [r["text"] for r in c["runs"]]
        if c.get("type")=="tabela": txt += [f"{l['rotulo']} {l['valor']}" for l in c["linhas"]]
        if c.get("type")=="colunas": txt += [f"{k['titulo']} {k['texto']}" for k in c["colunas"]]
        for f in c.get("children",[]):
            if f.get("type")=="text": txt += [r["text"] for r in f["runs"]]
v = audita(txt)
print(f"CFM: {v['regras_carregadas']} regras · vedados: {len(v['termos_bloqueados'])} · CRM: {v['crm_presente']}")
if not v["ok"]:
    print("REPROVADO:", v["termos_bloqueados"][:3]); raise SystemExit(1)

spec = {"schema_version":"post.spec/1.0.0-poc","spec_id":"anderson_vitrine","seed":11,
 "skin":{"id":"VOS:anderson-navy","versao":"1.0.0-poc","tokens_file":"tokens_anderson.json"},
 "brand":{"cliente":"dr-anderson","handle":"@dr.andersonramos","crm":CRM},
 "pauta":{"tema":"faixa de referência vs faixa ótima","nicho":"saude-longevidade","idioma":"pt-BR"},
 "compliance":{"perfil":"cfm_rules.yaml","auditado":True,"regras":v["regras_carregadas"]},
 "artboard":{"base":{"w":1088,"h":1360,"formato":"feed_4x5_ig","color_profile":"srgb"},
             "safe_area":{"top":88,"bottom":88,"left":88,"right":88}},
 "gates":{"accent_budget":{"max_palavras":2},"contrast_min":4.5,"contrast_min_large":3.0,
          "clearance_decorativo_px":16},
 "slides":S}
json.dump(spec, open("spec_anderson2.json","w"), ensure_ascii=False, indent=2)
print("✅ 6 lâminas · tabela + colunas + medidor + knockout/contorno/verniz + dual")
