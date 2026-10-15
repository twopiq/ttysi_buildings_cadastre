# TTYSI kadastr sayti - server uchun obraz.
#   docker build -f web/Dockerfile -t ttysi-web .
#   docker run -d -p 8000:8000 -v "/srv/TTYSI Binolar:/data" --name ttysi-web ttysi-web
# Birinchi administrator: docker exec -it ttysi-web python -m web.auth --workspace /data add admin --role admin
FROM python:3.12-slim
WORKDIR /app
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY ttysi_cadastre ttysi_cadastre
COPY web web
ENV TTYSI_WORKSPACE=/data
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "web.server", "--host", "0.0.0.0", "--port", "8000"]
