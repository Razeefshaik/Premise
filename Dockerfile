FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml README.md ./
COPY premise ./premise
COPY premise_v2 ./premise_v2
RUN pip install --no-cache-dir --no-deps .
COPY sandbox ./sandbox
COPY scenarios ./scenarios
COPY bench ./bench
COPY redteam ./redteam
COPY scripts ./scripts
COPY docs ./docs
COPY tests ./tests
RUN useradd --create-home premise && chown -R premise:premise /app
USER premise
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["python", "-m", "premise.bootstrap"]
