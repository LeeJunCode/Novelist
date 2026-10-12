FROM python:3.12-slim

WORKDIR /app

# 安装依赖（先复制 requirements 利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY novelist/ ./novelist/
COPY samples/ ./samples/

# 创建数据目录
RUN mkdir -p output library chroma_db

# Streamlit 端口
EXPOSE 8501

# 启动 Streamlit
CMD ["streamlit", "run", "novelist/ui.py", "--server.address=0.0.0.0"]
