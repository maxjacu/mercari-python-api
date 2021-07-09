FROM python:3.7-slim
MAINTAINER Max Jacubowsky <maxjacu@gmail.com>

ARG DEBIAN_FRONTEND=noninteractive

COPY . /app/

WORKDIR /app

RUN pip3 install --upgrade pip
RUN pip3 install -e .

WORKDIR /app/examples

ENTRYPOINT [ "python3", "monitor.py" ]
