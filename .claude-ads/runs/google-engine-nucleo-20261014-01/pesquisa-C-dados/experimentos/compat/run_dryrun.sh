#!/bin/zsh
# Dry-run de resolução: cada candidato JUNTO com o freeze do backend/.venv como constraint (pinado).
cd "$(dirname $0)"
mkdir -p dryrun
for c in "google-ads-api-report-fetcher" "garf-core" "garf-io" "garf-executors" "garf-google-ads" "polars" "duckdb" "clickhouse-connect" "feast" "redis" "prefect" "dagster" "ray" "bytewax" "sentence-transformers" "litellm" "bertopic" "hdbscan" "qdrant-client" "fastembed" "crawlee" "playwright" "ipinfo" "geoip2" "schemathesis" "respx" "opentelemetry-sdk" "facebook-business" "pandas" "fastapi==0.143.1" "websockets==17.2" "pydantic==2.14.1"; do
  n=$(echo $c | tr '=' '_')
  /usr/bin/time -p ./venv-compat/bin/python -I -m pip install --dry-run --ignore-installed --quiet --report dryrun/$n.json -c backend_freeze.txt "$c" > dryrun/$n.log 2>&1
  echo "$c exit=$?" >> dryrun/_resumo.txt
done
