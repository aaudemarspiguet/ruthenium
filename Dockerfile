# ─── Base Image ───────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm

# ─── Install FFmpeg (which includes ffprobe on Bookworm) ──────────────
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# ─── App Directory & Python Dependencies ─────────────────────────────
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ─── Copy Your Code ──────────────────────────────────────────────────
COPY . .

# ─── Environment ─────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
# ─── Sanity Check (optional; you can remove this after confirming) ────
RUN which ffmpeg && ffmpeg -version && which ffprobe && ffprobe -version

# ─── Run with Gunicorn ────────────────────────────────────────────────
CMD ["gunicorn", "index:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120"]