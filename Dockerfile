FROM nikolaik/python-nodejs:python3.11-nodejs20

RUN apt-get update && apt-get install -y \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt* ./

RUN pip install --no-cache-dir browser-use playwright

COPY . .

RUN pip install -e .

CMD ["python", "-m", "gateway.run"]
