# Smoke ADK + DeepSeek do runtime de recuperação

Prova isolada do candidato `deepseek-v4-flash` dentro do Google ADK. Este diretório não integra o modelo ao backend e não possui ferramenta de escrita externa.

## 1. Preflight sem rede

O ambiente isolado pode ser preparado com:

```bash
.venv-adk/bin/python -m pip install \
  -r tools/agentic-recovery-smoke/requirements.txt
```

```bash
.venv-adk/bin/python tools/agentic-recovery-smoke/run.py --preflight
```

O preflight exige:

- `google-adk==2.8.0`;
- `litellm>=1.84` e diferente das versões comprometidas `1.82.7` e `1.82.8`;
- contrato JSON válido;
- zero ferramenta proibida entre as permitidas.

## 2. Prova real, ainda sem ferramenta

Injete `DEEPSEEK_API_KEY` somente na sessão/ambiente aprovado. Não coloque a chave no comando, no Roadmap ou em arquivo versionado.

```bash
.venv-adk/bin/python tools/agentic-recovery-smoke/run.py \
  --live \
  --scenario redator-invalid-json-loop \
  --repeat 10
```

Segundo cenário:

```bash
.venv-adk/bin/python tools/agentic-recovery-smoke/run.py \
  --live \
  --scenario search-low-delivery-readonly \
  --repeat 10
```

Os relatórios sanitizados ficam em `/private/tmp/volc-agentic-recovery-smoke/`. A chave nunca é serializada.

## O que isto prova — e o que não prova

Prova: conectividade ADK→LiteLLM→DeepSeek, saída estruturada, repetibilidade, latência e respeito ao contrato sem escrita externa.

Não prova: uso de ferramentas, correção de uma run real, segurança de deploy, qualidade com dados vivos ou autorização de mutação. Esses gates vêm depois e continuam separados.

## 3. Prova cirúrgica (“sniper”)

Esta prova usa o endpoint oficial com thinking ligado e `reasoning_effort=low`,
mas lê e registra somente `message.content`. O raciocínio nunca entra no log.
O modelo propõe apenas um span; uma guarda local determinística decide se a
substituição é aplicável. Código gerado livremente nunca é executado.

```bash
.venv-adk/bin/python tools/agentic-recovery-smoke/sniper.py --scenario all
```

Os dois casos são: remoção local de uma promessa absoluta em copy e correção de
um único identificador Python com allowlist, AST e prova funcional em sandbox.
