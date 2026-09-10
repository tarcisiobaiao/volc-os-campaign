# PRENSA — o motor tipográfico da VOLC, envelopado.
#
# ## Por que Docker, e não um port
#
# A PRENSA resolve tipografia medindo no DOM de um navegador real antes do
# screenshot. Isso não é preferência de implementação: é o que dá kerning,
# ligadura, shaping de acento e quebra de linha corretos em português — e é o
# que um kit PIL de primitivas não entrega sozinho. Portar o motor significaria
# reescrever medição, fit e tratamentos tipográficos; envelopá-lo custa este
# arquivo.
#
# ## Chrome real, e não o chromium do Playwright
#
# `motor/render.py:777` lança com `channel="chrome"`. A diferença importa para
# um motor de tipografia: o Chrome estável traz os codecs e o stack de fontes
# completos, e o gate de pixel da PRENSA foi calibrado contra ELE. Trocar por
# chromium mudaria os bytes de saída e invalidaria os goldens por skin — que é
# justamente a prova de reprodutibilidade que o motor existe para dar.
#
# Por isso a imagem instala o Google Chrome stable pelo repositório oficial em
# vez de usar `playwright install chromium`.
# ⚠️ PLATAFORMA FIXA EM amd64, e isso não é descuido.
#
# O Google Chrome para Linux só é publicado em amd64 — não existe pacote arm64.
# O servidor de produção da VOLC é x86, então amd64 é o alvo real; num Mac
# Apple Silicon o build roda emulado (lento) e é para desenvolvimento apenas.
#
# A alternativa seria usar `chromium` (que tem arm64) e trocar o `channel`, mas
# isso mudaria os bytes de saída e invalidaria os goldens por skin do motor —
# a prova de reprodutibilidade que a PRENSA existe para dar. Preferimos build
# lento no laptop a recibo que mente.
FROM --platform=linux/amd64 python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # O Playwright não precisa baixar navegador: usamos o Chrome do sistema.
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Chrome stable pelo repositório oficial do Google, com a chave verificada.
# `--no-install-recommends` mantém a imagem enxuta; as fontes base entram
# explicitamente porque um container sem fontes renderiza tofu e o motor não
# tem como saber que renderizou errado.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg fonts-liberation fontconfig \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /prensa

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# O motor e as fontes que ele empacota. As fontes vêm ANTES do código porque
# mudam muito menos: assim uma alteração em render.py não invalida a camada.
COPY motor/fonts ./motor/fonts
COPY motor ./motor
COPY api.py ./

# ⚠️ O Chrome recusa rodar como root sem sandbox desabilitado, e desabilitar
# sandbox num serviço que recebe spec de fora é exatamente o que não se faz.
# Usuário sem privilégio + o sandbox do próprio Chrome ativo.
RUN useradd --create-home --shell /usr/sbin/nologin prensa \
    && chown -R prensa:prensa /prensa
USER prensa

EXPOSE 8020
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8020/saude').read()"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8020"]
