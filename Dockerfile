FROM python:3.12-slim

WORKDIR app/

COPY requirements.txt .

RUN pip install --no-cache-dir protobuf==5.27.2 && \
    pip install --no-cache-dir -r requirements.txt --no-deps
COPY .. .
