# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes -r requirements.txt
ARG INSTALAR_DEV=false
RUN if [ "$INSTALAR_DEV" = "true" ]; then pip install --require-hashes -r requirements.txt -r requirements-dev.txt; fi

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" PYTHONPATH=/app/src
# OCR (Etapa 4C.6): versoes fixadas do Debian trixie; o hash do modelo portugues e conferido.
ARG TESSERACT_VERSAO=5.5.0-1+b1
ARG TESSDATA_VERSAO=1:4.1.0-2
ARG POR_TRAINEDDATA_SHA256=c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb
RUN apt-get update  && apt-get install -y --no-install-recommends       tesseract-ocr=${TESSERACT_VERSAO}       tesseract-ocr-por=${TESSDATA_VERSAO}       tesseract-ocr-osd=${TESSDATA_VERSAO}       tesseract-ocr-eng=${TESSDATA_VERSAO}  && rm -rf /var/lib/apt/lists/*  && echo "${POR_TRAINEDDATA_SHA256}  /usr/share/tesseract-ocr/5/tessdata/por.traineddata" | sha256sum -c -
RUN groupadd --system --gid 10001 lupa && useradd --system --uid 10001 --gid lupa --no-create-home lupa
WORKDIR /app
RUN chown lupa:lupa /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=lupa:lupa pyproject.toml ./
COPY --chown=lupa:lupa src ./src
COPY --chown=lupa:lupa tests ./tests
COPY --chown=lupa:lupa scripts ./scripts
USER lupa
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "lupa.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
