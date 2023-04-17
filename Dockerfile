FROM python:3.9-slim-buster

LABEL "com.github.actions.name"="Restore RDS snapshot GitHub Action"
LABEL "com.github.actions.description"="This is a github actions to restore RDS snapshot."
LABEL "com.github.actions.icon"="airplay"
LABEL "com.github.actions.color"="green"

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt \
  && chmod +x entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
