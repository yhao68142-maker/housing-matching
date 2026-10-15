FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py seed.json maintenance.py ./
RUN useradd --uid 10001 --create-home housing && mkdir /data && chown housing /data
USER housing
ENV DATA_DIR=/data
EXPOSE 8787
CMD ["gunicorn", "--bind", "0.0.0.0:8787", "--workers", "2", "--threads", "2", "--timeout", "180", "--access-logfile", "-", "app:create_app()"]
