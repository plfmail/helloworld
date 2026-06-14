# ========================
# helloworld - Flask 示例应用
# ========================
FROM docker.m.daocloud.io/python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app.py .
COPY templates ./templates

EXPOSE 5008

CMD ["python", "app.py"]
