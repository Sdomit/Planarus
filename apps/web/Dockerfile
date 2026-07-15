# Build the React app, then serve the static bundle via nginx.
# Build context is the repo ROOT (needs the pnpm workspace manifests).
FROM node:20-slim AS build
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web ./apps/web
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @approvo/web build

FROM nginx:alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
