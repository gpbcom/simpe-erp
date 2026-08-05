# rt-erp front-end.
#
# Two targets from one file. `development` runs the Vite dev server with the
# source bind-mounted over it; `production` builds the static bundle and serves
# it from nginx, which also proxies /api so the browser sees a single origin.

FROM node:20-alpine AS base
WORKDIR /app
# Copied on their own first, so a change to a component does not invalidate the
# dependency layer and reinstall the world.
COPY package.json package-lock.json* ./
RUN npm ci


FROM base AS development
# The source is bind-mounted over this by the compose overlay; copying it here
# too means the image still runs standalone, which is what `docker run` and CI
# both expect.
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


FROM base AS build
COPY . .
# Vite inlines every VITE_* variable at build time, so the API address is baked
# into the bundle rather than read at boot. That is why it is a build argument
# here and not an environment variable on the running container — setting it at
# run time would silently do nothing.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:1.27-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
