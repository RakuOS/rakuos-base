#!/bin/bash
# Run build-image.sh in the same quay.io/buildah/stable container the
# GitLab pipeline uses, so the buildah version and behaviour match.
#
# GitHub's runners have little room on / but a large temporary disk on
# /mnt: the build context, buildah's storage and its /var/tmp all go there.
set -euo pipefail

WORK=/mnt/work
sudo mkdir -p "${WORK}" /mnt/containers /mnt/var-tmp
sudo cp -a . "${WORK}/"
df -h / /mnt

sudo podman run --rm --privileged \
  --security-opt label=disable \
  -v "${WORK}":/src -w /src \
  -v /mnt/containers:/var/lib/containers \
  -v /mnt/var-tmp:/var/tmp \
  -e STORAGE_DRIVER=overlay -e BUILDAH_FORMAT=oci \
  -e CONTAINERFILE -e QUAY_REPO -e DESC_SUFFIX -e KIND \
  -e BASE_REPO -e EXTRA_BUILD_ARGS \
  -e QUAY_USER -e QUAY_TOKEN -e QUAY_API_TOKEN \
  -e GITLAB_SECURE_FILES_TOKEN -e COSIGN_PASSWORD \
  -e BRANCH="${GITHUB_REF_NAME}" \
  -e FEDORA_VERSION_OVERRIDE="${FEDORA_VERSION_OVERRIDE:-}" \
  -e RUN_ID="${GITHUB_RUN_ID}" \
  -e SOURCE_URL -e REVISION="${GITHUB_SHA}" \
  quay.io/buildah/stable:latest \
  bash .github/scripts/build-image.sh

df -h / /mnt
