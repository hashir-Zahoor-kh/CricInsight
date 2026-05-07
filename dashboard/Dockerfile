# CricInsight dashboard — React + TypeScript dev container
# This image targets local development (CRA's `npm start`). Production builds
# would use a multi-stage build with nginx, but for a portfolio project the
# dashboard is screenshotted from local — no need to deploy it.

FROM node:20-slim

WORKDIR /app

# Install deps first to keep the Docker cache warm across source edits.
# package*.json may not exist yet during early phases — the wildcard avoids
# blowing up before Phase 5.1 scaffolds the React app. After Phase 5.1 these
# files will exist and the layer caches normally.
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; \
    elif [ -f package.json ]; then npm install; \
    else echo "package.json not yet present — Phase 5.1 will populate this"; fi

COPY . .

ENV PORT=3000 \
    HOST=0.0.0.0 \
    BROWSER=none \
    CI=true

EXPOSE 3000

CMD ["npm", "start"]
