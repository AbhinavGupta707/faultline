FROM python:3.12-slim
WORKDIR /app
COPY services/po_generator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/po_generator/ .
ENV PORT=8080
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
