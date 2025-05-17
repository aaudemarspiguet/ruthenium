# ─── Base Image ───────────────────────────────────────────────────────
FROM python:3.12.10-slim-bookworm

# Upgrade pip and system packages to minimize vulnerabilities
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# ─── App Directory & Python Dependencies ─────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Copy Your Code ──────────────────────────────────────────────────
COPY . .

# ─── Environment ─────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# ─── Run with Gunicorn ────────────────────────────────────────────────
CMD ["gunicorn", "api.index:app", "--bind", "0.0.0.0:8080", "--workers", "2"]