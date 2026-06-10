FROM python:3.12-slim
WORKDIR /app
COPY agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ .
COPY contracts/ /contracts/
ENV PORT=8080 CONTRACTS_DIR=/contracts
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
