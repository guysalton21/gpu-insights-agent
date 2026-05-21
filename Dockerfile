FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[server]"

USER 65532:65532

EXPOSE 8000

CMD ["uvicorn", "gpu_insights_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]

