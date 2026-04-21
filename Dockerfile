FROM python:3.11-slim

# TA-Lib C library
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget && \
    wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs/daily

EXPOSE 8501

ENV PORT=8501

CMD streamlit run dashboard.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true
