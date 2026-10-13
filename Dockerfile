# Sky e-paper – nasazení v Coolify (zdroj typu Dockerfile). Kód je součástí image.
#
# Efemerida de421.bsp (~17 MB) se stáhne při buildu do /app/cache-seed a při
# startu se zkopíruje do svazku SKY_CACHE_DIR, pokud tam ještě není. Do téhož
# svazku se ukládá cache TLE (ISS) a ICS (úkazy), aby přežily redeploy.
FROM python:3.12-slim

WORKDIR /app
ENV SKY_CACHE_DIR=/cache \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY sky ./sky
RUN pip install --no-cache-dir . \
 && mkdir -p /app/cache-seed \
 && SKY_CACHE_DIR=/app/cache-seed python -m sky warmup

EXPOSE 8080
CMD ["sh", "-c", "mkdir -p \"$SKY_CACHE_DIR\" && cp -n /app/cache-seed/*.bsp \"$SKY_CACHE_DIR\"/ 2>/dev/null; exec uvicorn sky.app:app --host 0.0.0.0 --port 8080 --no-access-log"]
