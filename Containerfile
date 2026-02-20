# ARGs and ENV
ARG FEDORA_VERSION="${FEDORA_VERSION:-43}"
ARG VARIANT=base
ENV FEDORA_VERSION=${FEDORA_VERSION}
ENV VARIANT=${VARIANT}

# Stage to hold build scripts
FROM scratch AS ctx
COPY build_files /

# -----------------------------
# Base variant stage
# -----------------------------
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION} AS base
RUN mv /usr/local /var/usr_local && ln -s -T /var/usr_local /usr/local
COPY system_files /
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh
RUN bootc container lint

# -----------------------------
# NVIDIA variant stage
# -----------------------------
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION} AS nvidia
RUN mv /usr/local /var/usr_local && ln -s -T /var/usr_local /usr/local
COPY system_files /
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh && /ctx/nvidia.sh
RUN bootc container lint
