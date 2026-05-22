# Global build arg — available to all FROM lines for image tag resolution.
# Must NOT have ENV here; ENV is a layer instruction and cannot precede FROM.
ARG FEDORA_VERSION="${FEDORA_VERSION:-43}"

# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /

# Base Image
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION}
# Re-declare ARG inside this stage so it is in scope, then persist it as an
# environment variable for RUN scripts that read $FEDORA_VERSION at runtime.
ARG FEDORA_VERSION
ENV FEDORA_VERSION=${FEDORA_VERSION}

#RUN rm /opt && ln -s -T /var/opt /opt
RUN mkdir -p /var/nix && ln -s /var/nix /nix
COPY system_files /

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    --mount=type=secret,id=mok_key,target=/run/secrets/mok_key,required=false \
    /ctx/build.sh && /ctx/drivers.sh && /ctx/post-build.sh

### LINTING
## Verify final image and contents are correct.
RUN bootc container lint
