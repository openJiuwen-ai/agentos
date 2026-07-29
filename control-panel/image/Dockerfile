# =============================================================================
# AgentOS Control Panel — Multi-stage Docker Build
# Base: openEuler 24.03 LTS
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build frontend (Node.js)
# ---------------------------------------------------------------------------
FROM node:24-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npx vite build

# ---------------------------------------------------------------------------
# Stage 2: Runtime — openEuler 24.03 LTS
# ---------------------------------------------------------------------------
FROM openeuler/openeuler:24.03-lts

RUN yum install -y \
        python3 \
        python3-pip \
        nginx \
        && yum clean all

WORKDIR /opt/agentos/backend

# Create venv and install dependencies
COPY backend/pyproject.toml ./
RUN python3 -m venv .venv && \
    .venv/bin/pip install --no-cache-dir aiosqlite

COPY backend/ ./
RUN .venv/bin/pip install --no-cache-dir -e .

# Copy frontend dist
COPY --from=frontend-builder /build/frontend/dist /usr/share/nginx/html

# Nginx config — mounted at runtime via docker-compose
RUN rm -f /etc/nginx/conf.d/default.conf

# Startup script
COPY image/entrypoint.sh /opt/agentos/entrypoint.sh
RUN chmod +x /opt/agentos/entrypoint.sh

EXPOSE 80 8000

ENTRYPOINT ["/opt/agentos/entrypoint.sh"]
