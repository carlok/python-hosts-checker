# Same instructions as Dockerfile; duplicate for Podman/Buildah (`podman build -f Containerfile`).
# When changing build steps, update both files (no symlink).

# Containerfile mirrors these steps for Podman; keep both in sync.
FROM python:3.14-slim

WORKDIR /app

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# App source and tests (build fails if tests or coverage gate fail)
COPY checker.py pytest.ini ./
COPY tests ./tests
RUN pytest
