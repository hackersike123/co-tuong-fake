FROM node:22-alpine AS build

WORKDIR /workspace
RUN npm install --global pnpm@10.34.3

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm build

FROM nginx:1.30-alpine AS runtime
COPY nginx/templates/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/snippets/proxy-headers.conf /etc/nginx/snippets/proxy-headers.conf
COPY nginx/snippets/proxy-routes.conf /etc/nginx/snippets/proxy-routes.conf
COPY --from=build /workspace/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
