# Stage 1: install dependencies with the full Python image (has compilers/headers)
FROM python:3.12 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: run the app on the slim image as a non-root user
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /install /usr/local
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser app.py gunicorn.conf.py ./
COPY --chown=appuser:appuser templates/ ./templates/
USER appuser
EXPOSE 3000
# gunicorn reads gunicorn.conf.py from the working directory
CMD ["gunicorn", "app:app"]
