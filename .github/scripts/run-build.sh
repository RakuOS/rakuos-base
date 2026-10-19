#!/bin/bash
# Run build-image.sh in the same quay.io/buildah/stable container the
# GitLab pipeline uses, so the buildah version and behaviour match.
#
# Like the GitLab jobs, buildah keeps its storage and /var/tmp inside the
# container (/var/lib/containers is an image volume on the runner's disk);
# only the build context is bound in. build-image.sh switches buildah from
# fuse-overlayfs to the kernel overlay driver.
set -euo pipefail

WORK=/mnt/work
sudo mkdir -p "${WORK}"
sudo cp -a . "${WORK}/"
df -h /

export BRANCH="${GITHUB_REF_NAME}"
export RUN_ID="${GITHUB_RUN_ID}"
export REVISION="${GITHUB_SHA}"
export FEDORA_VERSION_OVERRIDE="${FEDORA_VERSION_OVERRIDE:-}"

# Variables handed to the build container. `podman run -e NAME` copies NAME
# from podman's own environment, and sudo clears the environment, so they
# have to be kept explicitly with --preserve-env (this also keeps the
# secrets off the command line).
PASS_VARS=(
  CONTAINERFILE QUAY_REPO DESC_SUFFIX KIND BASE_REPO EXTRA_BUILD_ARGS
  QUAY_USER QUAY_TOKEN QUAY_API_TOKEN GITLAB_SECURE_FILES_TOKEN COSIGN_PASSWORD
  BRANCH RUN_ID REVISION SOURCE_URL FEDORA_VERSION_OVERRIDE
)
env_args=()
for v in "${PASS_VARS[@]}"; do
  env_args+=(-e "${v}")
done

sudo --preserve-env="$(IFS=,; echo "${PASS_VARS[*]}")" podman run --rm --privileged \
  --security-opt label=disable \
  -v "${WORK}":/src -w /src \
  -e STORAGE_DRIVER=overlay -e BUILDAH_FORMAT=oci \
  "${env_args[@]}" \
  quay.io/buildah/stable:latest \
  bash .github/scripts/build-image.sh

df -h /
