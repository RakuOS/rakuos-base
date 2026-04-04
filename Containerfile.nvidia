ARG FEDORA_VERSION="${FEDORA_VERSION:-43}"
ENV FEDORA_VERSION=${FEDORA_VERSION}
# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /

# Base Image
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION}

#RUN rm /opt && ln -s -T /var/opt /opt
RUN mkdir -p /var/nix && ln -s /var/nix /nix
COPY system_files /

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh && /ctx/drivers.sh && /ctx/nvidia.sh && /ctx/post-build.sh

### LINTING
## Verify final image and contents are correct.
RUN bootc container lint
