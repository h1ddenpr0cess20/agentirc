FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY ircbot/ ircbot/
COPY agentirc/ agentirc/

RUN pip install --no-cache-dir '.[crypto]'

CMD ["agentirc"]
