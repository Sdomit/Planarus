# Build the React app, then serve the static bundle via nginx.
# Build context is the repo ROOT (needs the pnpm workspace manifests).
FROM node:20-slim AS build
WORKDIR /repo
# corepack reads the packageManager pin from package.json, so copy it first
# and let it activate the one version this repo is tested against.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
RUN corepack enable && corepack install
COPY apps/web ./apps/web
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @approvo/web build

FROM nginx:alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
