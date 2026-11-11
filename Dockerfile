FROM python:3.12.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt constraints.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --no-create-home app
COPY rag_core /app/rag_core
COPY worker.py inspect_db.py /app/
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "worker.py"]
