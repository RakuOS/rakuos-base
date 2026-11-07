# One Containerfile for every rakuos-base image. CI picks the image with
# build args instead of a separate Containerfile per image:
#
#   BASE_IMAGE_REPO / BASE_IMAGE_TAG  what to build FROM: Fedora's bootc image
#                       for the base and minimal images, or the base/minimal
#                       image just built for this branch for the NVIDIA ones
#   RAKUOS_ISA_LEVEL    v2, v3 or v4: kernel flavor and rakuos-v3/v4 repos
#   RAKUOS_VARIANT      base or minimal (minimal also runs post-build-overlay.sh)
#   RAKUOS_GPU          none, or nvidia for the NVIDIA images, which only run
#                       nvidia.sh on top of the image they're built FROM
#   NVIDIA_LEGACY       1 for the legacy NVIDIA (580xx) images
#   RAKUOS_STAGING      1 on the staging branch (-staging packages and kernel)
#
# Global build args: available to the FROM lines below.
ARG FEDORA_VERSION="45"
ARG BASE_IMAGE_REPO="quay.io/bootc-devel/fedora-bootc-45-minimal"
ARG BASE_IMAGE_TAG="latest"
ARG CHUNKAH_CONFIG_STR

# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /

FROM ${BASE_IMAGE_REPO}:${BASE_IMAGE_TAG} AS builder
# Re-declare ARG inside this stage so it is in scope, then persist it as an
# environment variable for RUN scripts that read $FEDORA_VERSION at runtime.
ARG FEDORA_VERSION
ENV FEDORA_VERSION=${FEDORA_VERSION}
ARG RAKUOS_STAGING="0"
ENV RAKUOS_STAGING=${RAKUOS_STAGING}
# Build args are in the environment of every RUN below. chunkah repacks the
# filesystem into a fresh image config, so none of this reaches the final
# image's environment.
ARG RAKUOS_ISA_LEVEL="v2"
ARG RAKUOS_VARIANT="base"
ARG RAKUOS_GPU="none"
ARG NVIDIA_LEGACY="0"

# Same on every image: for the NVIDIA ones these are already in place in
# the image they build FROM, and redoing them changes nothing.
RUN rm -rf /opt && ln -s -T var/opt /opt
RUN rm -rf /usr/local && ln -s -T ../var/usrlocal /usr/local
RUN mkdir -vp /nix
RUN mkdir -vp /snap
COPY system_files /

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    --mount=type=secret,id=mok_key,target=/run/secrets/mok_key,required=false \
    set -e; \
    case "${RAKUOS_GPU}" in \
      none) \
        /ctx/build.sh; \
        /ctx/drivers.sh; \
        /ctx/post-build.sh; \
        if [ "${RAKUOS_VARIANT}" = "minimal" ]; then /ctx/post-build-overlay.sh; fi ;; \
      nvidia) \
        /ctx/nvidia.sh ;; \
      *) \
        echo "Unknown RAKUOS_GPU '${RAKUOS_GPU}' (want none or nvidia)" >&2; exit 1 ;; \
    esac; \
    /ctx/assign-components.sh generated; \
    /ctx/reset-mtimes.sh

COPY system_files /
# Clean up real runtime state (systemd units started mid-build, akmods/
# cryptsetup/etc. lock and socket files) that only ever makes sense on a
# live booted system, before the lint step inspects the committed image.
# This runs as its own RUN, after every mounted (--mount=type=secret/
# cache/tmpfs) build step above has already finished and unmounted, so it
# only ever touches plain files already baked into the layer — never a
# live mount the build engine itself still has open.
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=bind,source=system_files,target=/run/rakuos-system-files,ro \
    /ctx/assign-components.sh files rakuos-base-files /run/rakuos-system-files; \
    find /run -mindepth 1 -delete 2>/dev/null || true; \
    find /tmp -mindepth 1 -delete 2>/dev/null || true; \
    find /boot -mindepth 1 -delete 2>/dev/null || true; \
    /ctx/reset-mtimes.sh

# RUN bootc container lint

# chunkah v0.7.1, pinned: another version can plan layers differently,
# which would change every layer of the next update.
FROM quay.io/coreos/chunkah@sha256:71e593421c5de7dcc7c8c5c50e98d3bac572055a76f399f61a491d123c20a523 AS chunkah
# org.rakuos.kernel.release: the kernel release of this image, what `uname -r`
# shows once it's booted, read from the finished root filesystem (the only
# kernel with a vmlinuz). It can't be a CI --label like
# org.rakuos.fedora.version: the kernel is only known after the build.
ARG CHUNKAH_CONFIG_STR
RUN --mount=from=builder,src=/,target=/chunkah,ro \
    --mount=type=bind,target=/run/src,rw \
        KREL=$(basename "$(dirname "$(ls /chunkah/usr/lib/modules/*/vmlinuz | head -1)")") && \
        [ -n "$KREL" ] && \
        chunkah build --prune /sysroot/ --max-layers 256 --threads 4 --compressed \
          --label ostree.commit- --label ostree.final-diffid- \
          --label "org.rakuos.kernel.release=${KREL}" \
          > /run/src/out.ociarchive

FROM oci-archive:out.ociarchive
LABEL containers.bootc=1
