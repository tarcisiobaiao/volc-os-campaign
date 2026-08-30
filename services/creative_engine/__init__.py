"""Serviço criativo VOLC — runtime separável (ADR-001).

Hoje roda no processo do backend; a fronteira, porém, é um contrato de job e
não uma chamada de função, para que a extração para serviço próprio não exija
reescrever quem chama.

    enquadramento.py   envelope nativo do provider e normalização até a medida
    motores/           implementações de `volc_ads.criativo.porta.MotorDeCriativo`

⚠️ O diretório usa `creative_engine` com sublinhado, e o ADR-001 escreve
`services/creative-engine/` com hífen. A diferença é importabilidade: um hífen
impede `import`, e um pacote que só é alcançável por manipulação de `sys.path`
convida exatamente o tipo de global de caminho que o próprio ADR marca como
risco. O nome do diretório mudou; a fronteira que o ADR decidiu, não.
"""
