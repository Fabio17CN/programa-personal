# Imagem base enxuta com Python
FROM python:3.11-slim

# Dependências de sistema necessárias para Pillow, matplotlib, mediapipe e reportlab
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python primeiro (aproveita cache do Docker em rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# Garante que as pastas de dados existem dentro do container
RUN mkdir -p instance/models uploads

EXPOSE 5000

# Baixa o modelo de IA de postura automaticamente na primeira subida,
# caso ainda não exista (assim quem usar Docker não precisa rodar o
# script manualmente).
CMD ["sh", "-c", "python baixar_modelo_ia.py || true; gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app"]
