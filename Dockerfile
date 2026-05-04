# Dev image: install dev deps, copy app + tests; build fails if pytest fails.
FROM python:3.14-slim

WORKDIR /app

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# App source and tests (build fails if tests or coverage gate fail)
COPY checker.py pytest.ini ./
COPY tests ./tests
RUN pytest
