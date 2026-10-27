# Cantrip's app, ready to deploy. Needs CANTRIP_PASSWORD; see the README's "Deploy it".
FROM python:3.12-slim

WORKDIR /app
COPY cantrip ./cantrip
COPY spellbook ./spellbook
COPY examples ./examples

RUN useradd --create-home --uid 10001 cantrip && mkdir /data && chown cantrip /data
USER cantrip

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CANTRIP_HOST=0.0.0.0 \
    PORT=8765 \
    CANTRIP_PROFILE=/data/cantrip.toml
VOLUME /data
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=4)"

CMD ["python", "-m", "cantrip", "ui", "--no-browser"]
