ARG FEDORA_VERSION="${FEDORA_VERSION:-43}"
ARG VARIANT=base

ENV FEDORA_VERSION=${FEDORA_VERSION}
ENV VARIANT=${VARIANT}

# Allow build scripts to be referenced without copying into final image
FROM scratch AS ctx
COPY build_files /

# Base Image
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION}

# Persist /usr/local to /var
RUN mv /usr/local /var/usr_local && ln -s -T /var/usr_local /usr/local

# Copy system files
COPY system_files /

# Run build + optional NVIDIA setup
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    bash -euxo pipefail -c '\
        VARIANT="${VARIANT:-base}"; \
        /ctx/build.sh; \
        if [ "$VARIANT" = "nvidia" ]; then \
            echo "Installing NVIDIA variant"; \
            /ctx/nvidia.sh; \
        fi \
    '

### LINTING
RUN bootc container lint
