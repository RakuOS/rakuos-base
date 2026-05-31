# Global build arg — available to all FROM lines for image tag resolution.
# Must NOT have ENV here; ENV is a layer instruction and cannot precede FROM.
ARG FEDORA_VERSION="${FEDORA_VERSION:-43}"
ARG CHUNKAH_CONFIG_STR

# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /

# Base Image
FROM quay.io/fedora-ostree-desktops/base-atomic:${FEDORA_VERSION} AS builder
# Re-declare ARG inside this stage so it is in scope, then persist it as an
# environment variable for RUN scripts that read $FEDORA_VERSION at runtime.
ARG FEDORA_VERSION
ENV FEDORA_VERSION=${FEDORA_VERSION}

#RUN rm /opt && ln -s -T /var/opt /opt
RUN mkdir -vp /nix
COPY system_files /

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    --mount=type=secret,id=mok_key,target=/run/secrets/mok_key,required=false \
    /ctx/build.sh && /ctx/drivers.sh && /ctx/post-build.sh

RUN bootc container lint

FROM quay.io/coreos/chunkah AS chunkah
ARG CHUNKAH_CONFIG_STR
RUN --mount=from=builder,src=/,target=/chunkah,ro \
    --mount=type=bind,target=/run/src,rw \
        chunkah build --max-layers 128 --compressed --threads 16 \
          > /run/src/out.ociarchive

FROM oci-archive:out.ociarchive
LABEL containers.bootc=1
