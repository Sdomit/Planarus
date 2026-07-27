# Build the React app, then serve the static bundle via nginx.
# Build context is the repo ROOT (needs the pnpm workspace manifests).
FROM node:24-slim AS build
WORKDIR /repo
# corepack reads the packageManager pin from package.json, so copy it first
# and let it activate the one version this repo is tested against.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
RUN corepack enable && corepack install
COPY apps/web ./apps/web
# extension-contract.test.ts imports capture-url.js directly from apps/extension
# (outside the pnpm workspace on purpose - see apps/extension/README.md), so the
# build context needs that file even though it's not a workspace package.
COPY apps/extension ./apps/extension
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @planarus/web build

FROM nginx:alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
