# Free web search for Cantrip, on your own computer

[SearXNG](https://github.com/searxng/searxng) is a free, open-source search engine that asks Google, Bing, DuckDuckGo and others for you and merges the results. Run it locally and Cantrip's web search needs no key, no account and has no monthly allowance.

## With Docker (easiest)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) if you don't have it, then from this folder:

```bash
python3 -c "import secrets; print('SEARXNG_SECRET=' + secrets.token_hex(32))" > .env
docker compose up -d
```

Point Cantrip at it and check it works:

```bash
export CANTRIP_SEARCH=searxng
export CANTRIP_SEARCH_URL=http://localhost:8888
cantrip search "head of developer relations at an AI startup"
```

It keeps running in the background and starts again with Docker. Stop it with `docker compose down`.

## Without Docker

```bash
git clone --depth 1 https://github.com/searxng/searxng.git && cd searxng
python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-server.txt && venv/bin/pip install --no-build-isolation -e .
SEARXNG_SETTINGS_PATH=/path/to/cantrip/searxng/config/settings.yml SEARXNG_SECRET=any-long-string SEARXNG_PORT=8888 venv/bin/searxng-run
```

## Good to know

- `config/settings.yml` is SearXNG's defaults plus one change Cantrip needs: JSON answers, which SearXNG turns off unless asked. If you use your own SearXNG and Cantrip says it refused JSON, add `json` under `search: formats:`.
- It listens on 127.0.0.1 only, so nobody else on your network can use it.
- The engines it asks can slow down or block a very busy instance. For a few dozen searches a run that's rarely a problem; if results thin out, wait a while or add `CANTRIP_TINYFISH_KEY` to read pages more reliably.
