FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

RUN groupadd -r agent && useradd -r -g agent agent

WORKDIR /app

COPY --from=builder /root/.local /home/agent/.local
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

RUN chown -R agent:agent /app /home/agent/.local

ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app/src
ENV AGENT_CONFIG_PATH=/app/config/prod.yaml

USER agent

CMD ["python3", "-m", "agent_core.memory.agent_main"]
