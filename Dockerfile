FROM python:3.12-slim

LABEL maintainer="CEJO Project"
LABEL description="CEJO — Custom Enterprise IP/Network Orchestrator"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp && chmod 777 /tmp

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/tmp/cejo.db
ENV CEJO_API_KEY=cejo-api-2024
ENV PORT=5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "wsgi:application"]
