# PRENSA envelopada

O motor tipográfico da VOLC (`motor-imagem/compartilhado/prensa-poc`) rodando
como serviço HTTP, para que o Assistente Criativo possa compor tipografia real
sem depender de um Chrome instalado na máquina que hospeda o backend.

    docker compose up -d --build
    curl localhost:8020/saude

## O que está aqui e o que NÃO está

`motor/` é cópia do acervo, sem `out/`, `.venv` e `__pycache__`. O motor é a
autoridade: `api.py` só o envelopa e nunca interpreta a spec.

Não está aqui, e é a única razão pela qual isto foi envelopado em vez de
portado: a medição de tipografia acontece no DOM de um Chrome real, antes do
screenshot. É isso que dá kerning, ligadura e shaping de acento corretos em
português — e é o que um kit de primitivas PIL não entrega.

## O contrato

`POST /render` recebe `{"spec": <post.spec resolvido>, "sufixo": ""}` e devolve
os PNG em base64 com o `veredito` e o `pixelgate` de cada um.

A escada de gates da PRENSA é **fail-closed**: reprovou, nenhum PNG é escrito.
Nesse caso a resposta é 422 com o motivo nomeado — nunca um 200 com peça ruim.

## Chrome, e não chromium

`motor/render.py:777` lança com `channel="chrome"`. O gate de pixel foi
calibrado contra o Chrome estável; trocar pelo chromium do Playwright mudaria os
bytes e invalidaria os goldens por skin, que são a prova de reprodutibilidade do
motor. Por isso a imagem instala `google-chrome-stable` pelo repositório oficial.
