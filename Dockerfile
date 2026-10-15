FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY premise ./premise
RUN pip install --no-cache-dir '.[dev]'
COPY sandbox ./sandbox
COPY scenarios ./scenarios
COPY tests ./tests
RUN useradd --create-home premise && chown -R premise:premise /app
USER premise
EXPOSE 8000
CMD ["python", "-m", "premise.bootstrap"]
