# Future local/production container image. NOT runtime-tested in this
# environment (no Docker Desktop available) — see docs/docker-setup.md.
FROM node:24-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
