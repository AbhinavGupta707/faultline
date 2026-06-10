FROM python:3.12-slim
WORKDIR /app
COPY agents/requirements.txt agents/requirements.txt
RUN pip install --no-cache-dir -r agents/requirements.txt
COPY agents/ agents/
COPY contracts/ contracts/
ENV PORT=8080 CONTRACTS_DIR=/app/contracts
CMD exec uvicorn agents.main:app --host 0.0.0.0 --port ${PORT}
