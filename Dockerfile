FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config/config.example.toml ./config/config.toml
COPY examples ./examples

EXPOSE 4840/tcp
CMD ["koyo-opc-ua-server", "--config", "config/config.toml"]
