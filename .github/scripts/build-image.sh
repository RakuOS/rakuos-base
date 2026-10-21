#!/bin/bash
# Build, push and sign one RakuOS image variant. Runs inside the
# quay.io/buildah/stable container started by run-build.sh, from
# .github/workflows/build.yml.
#
# Per-variant settings (from the workflow matrix):
#   CONTAINERFILE      Containerfile to build
#   QUAY_REPO          quay.io repository to push to
#   DESC_SUFFIX        appended to IMAGE_DESC in the description label
#   KIND               "fedora": built on Fedora bootc, gets FEDORA_VERSION
#                      "derived": built FROM another RakuOS image, gets
#                      BASE_IMAGE_TAG (the branch's tag)
#   BASE_REPO          derived only: image repository to build FROM
#                      (empty = the Containerfile's default)
#   EXTRA_BUILD_ARGS   space-separated KEY=VALUE build args
# Plus BRANCH, FEDORA_VERSION_OVERRIDE, RUN_ID, SOURCE_URL, REVISION and the
# secrets QUAY_USER, QUAY_TOKEN, QUAY_API_TOKEN, GITLAB_SECURE_FILES_TOKEN,
# COSIGN_PASSWORD.
set -euo pipefail

# ── This image ───────────────────────────────────────────────
IMAGE_DESC="RakuOS Base"
IMAGE_KEYWORDS="bootc,fedora,atomic"
# org.rakuos.fedora.version label per branch (as in .gitlab-ci.yml).
FEDORA_MAIN="44"
FEDORA_STAGING="45"
# 1 = fetch MOK.key and pass it to the build as the mok_key secret.
NEEDS_MOK="1"
DEFAULT_TAG="latest"
DEFAULT_BRANCH="main"
# rakuos-base on GitLab: MOK.key and cosign.key live in its Secure Files
# (every image repo signs with the same cosign key).
SECURE_FILES_PROJECT="81410875"

case "${BRANCH}" in
  "${DEFAULT_BRANCH}") FEDORA_VERSION="${FEDORA_MAIN}"; BRANCH_SLUG="${DEFAULT_TAG}" ;;
  "staging")           FEDORA_VERSION="${FEDORA_STAGING}"; BRANCH_SLUG="staging" ;;
  "rawhide")           FEDORA_VERSION="rawhide"; BRANCH_SLUG="rawhide" ;;
  # Temporary until this branch switches to the CentOS Stream flow.
  "rakuosel")          FEDORA_VERSION="10"; BRANCH_SLUG="rakuosel" ;;
  *)
    FEDORA_VERSION="45"
    BRANCH_SLUG="$(printf '%s' "${BRANCH}" | tr '[:upper:]' '[:lower:]' | sed 's#[^a-z0-9._-]#-#g')"
    ;;
esac
FEDORA_VERSION="${FEDORA_VERSION_OVERRIDE:-${FEDORA_VERSION}}"
# The build scripts install the -staging rakuos-release packages when 1.
RAKUOS_STAGING="0"
[ "${BRANCH}" = "staging" ] && RAKUOS_STAGING="1"
DATE_TAG="$(date -u +%Y%m%d)"

if [ "${BRANCH}" = "${DEFAULT_BRANCH}" ]; then
  PRIMARY_TAG_NAME="${DEFAULT_TAG}"
  ALIAS_TAGS="${DEFAULT_TAG}.${DATE_TAG} ${DATE_TAG}"
else
  PRIMARY_TAG_NAME="${BRANCH_SLUG}"
  ALIAS_TAGS="${BRANCH_SLUG}.${DATE_TAG}"
fi
PRIMARY_QUAY_TAG="${QUAY_REPO}:${PRIMARY_TAG_NAME}"
TEMP_TAG="${QUAY_REPO}:ci-temp-${RUN_ID}"

echo "Branch ${BRANCH} → FEDORA_VERSION=${FEDORA_VERSION} slug=${BRANCH_SLUG} RAKUOS_STAGING=${RAKUOS_STAGING}"
echo "Building ${CONTAINERFILE} → ${PRIMARY_QUAY_TAG} (+ ${ALIAS_TAGS})"

dnf install -y --quiet jq

# Use the kernel's overlay driver instead of the image's default
# fuse-overlayfs. On the GitHub runners' kernel (6.17-azure) chunkah reading
# the builder rootfs through fuse-overlayfs produced layers buildah could not
# unpack ("unpacking failed ... unexpected EOF") in every variant. The
# container is privileged and /var/lib/containers is an ext4 volume, so
# native overlay works here.
sed -i -e '/^mount_program *=/d' -e 's/^mountopt *=.*/mountopt = "nodev"/' \
  /etc/containers/storage.conf
# buildah puts the upper dir of RUN --mount=type=bind,rw overlays in its
# temp dir (/var/tmp by default), which here sits on the container's own
# overlayfs root; the kernel overlay driver refuses an upper dir there
# ("setting up overlay of /src ... invalid argument"). Keep it on the ext4
# volume instead.
export TMPDIR=/var/lib/containers/tmp
mkdir -p "${TMPDIR}"
buildah info | jq -c '.store | {GraphDriverName, GraphOptions, GraphStatus}' || true

# Run a registry or network command, retrying any failure. Quay sometimes
# answers 401/403/404/5xx for a short while; buildah's own --retry treats the
# 4xx ones as permanent, so retry the whole command here: 5 attempts, waiting
# 15s, 30s, 60s and 120s. The command line isn't printed (logins carry the
# token).
retry() {
  local attempt=1 max=5 delay=15
  until "$@"; do
    if [ "${attempt}" -ge "${max}" ]; then
      echo "ERROR: $1 failed ${max} times, giving up" >&2
      return 1
    fi
    echo "$1 failed (attempt ${attempt}/${max}); retrying in ${delay}s..." >&2
    sleep "${delay}"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}
CURL_RETRY=(--retry 5 --retry-all-errors --retry-delay 10)

# Download a file from rakuos-base's GitLab Secure Files; fail if missing.
fetch_secure_file() {
  local name="$1" dest="$2" id
  id=$(curl -sf "${CURL_RETRY[@]}" --header "PRIVATE-TOKEN: ${GITLAB_SECURE_FILES_TOKEN}" \
      "https://gitlab.com/api/v4/projects/${SECURE_FILES_PROJECT}/secure_files" \
      | jq -r --arg n "${name}" '.[] | select(.name == $n) | .id')
  if [ -z "${id}" ] || [ "${id}" = "null" ]; then
    echo "ERROR: ${name} not found in rakuos-base Secure Files" >&2
    exit 1
  fi
  curl -sf "${CURL_RETRY[@]}" --header "PRIVATE-TOKEN: ${GITLAB_SECURE_FILES_TOKEN}" -o "${dest}" \
      "https://gitlab.com/api/v4/projects/${SECURE_FILES_PROJECT}/secure_files/${id}/download"
  chmod 600 "${dest}"
}

build_args=(--build-arg RAKUOS_STAGING="${RAKUOS_STAGING}")
if [ "${KIND}" = "derived" ]; then
  build_args+=(--build-arg BASE_IMAGE_TAG="${BRANCH_SLUG}")
  [ -n "${BASE_REPO:-}" ] && build_args+=(--build-arg BASE_IMAGE_REPO="${BASE_REPO}")
else
  build_args+=(--build-arg FEDORA_VERSION="${FEDORA_VERSION}")
fi
for arg in ${EXTRA_BUILD_ARGS:-}; do
  build_args+=(--build-arg "${arg}")
done

# Images that build kernel modules sign them with the MOK key, and the
# kernel only loads signed modules (module.sig_enforce=1): never skip it.
secret_args=()
if [ "${NEEDS_MOK}" = "1" ]; then
  fetch_secure_file MOK.key /tmp/MOK.key
  secret_args=(--secret "id=mok_key,src=/tmp/MOK.key")
  echo "MOK.key downloaded — modules will be signed"
fi

# Pull every image the Containerfile builds FROM first, with retries, so
# buildah build (pull policy "missing") never has to reach the registry
# itself. Retrying the whole build would repeat it on real build errors.
from_images() {
  local repo_default base_repo ref
  repo_default=$(sed -n 's/^ARG BASE_IMAGE_REPO="\(.*\)"$/\1/p' "${CONTAINERFILE}" | head -n 1)
  base_repo="${BASE_REPO:-${repo_default}}"
  awk '/^FROM /{print $2}' "${CONTAINERFILE}" | while read -r ref; do
    case "${ref}" in scratch | oci-archive:* | oci:*) continue ;; esac
    ref="${ref//'${FEDORA_VERSION}'/${FEDORA_VERSION}}"
    ref="${ref//'${BASE_IMAGE_REPO}'/${base_repo}}"
    ref="${ref//'${BASE_IMAGE_TAG}'/${BRANCH_SLUG}}"
    case "${ref}" in
      *'$'*) echo "WARNING: can't resolve FROM ${ref}; buildah will pull it" >&2 ;;
      */*) echo "${ref}" ;;  # registry image (a bare name is an earlier stage)
    esac
  done | sort -u
}
for ref in $(from_images); do
  echo "Pulling ${ref}"
  retry buildah pull --quiet "${ref}" >/dev/null
done

buildah build \
  --file "${CONTAINERFILE}" \
  "${build_args[@]}" \
  --skip-unused-stages=false \
  -v "$(pwd)":/run/src --security-opt=label=disable \
  "${secret_args[@]}" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --label "org.opencontainers.image.version=${BRANCH_SLUG}.${DATE_TAG}" \
  --label "org.opencontainers.image.description=${IMAGE_DESC}${DESC_SUFFIX}" \
  --label "org.opencontainers.image.source=${SOURCE_URL}" \
  --label "org.opencontainers.image.revision=${REVISION}" \
  --label "org.opencontainers.image.vendor=RakuOS" \
  --label "org.opencontainers.image.keywords=${IMAGE_KEYWORDS}" \
  --label "org.rakuos.fedora.version=${FEDORA_VERSION}" \
  --label "containers.bootc=1" \
  --tag "${TEMP_TAG}" \
  .
rm -f /tmp/MOK.key

retry buildah login -u "${QUAY_USER}" -p "${QUAY_TOKEN}" quay.io
echo "Pushing ${PRIMARY_QUAY_TAG}"
retry buildah push --compression-format zstd:chunked "${TEMP_TAG}" "docker://${PRIMARY_QUAY_TAG}"

REPO_PATH="${QUAY_REPO#quay.io/}"
# The new tag can take a moment to show up in Quay's API after the push.
quay_digest() {
  local d
  d=$(curl -sf -H "Authorization: Bearer ${QUAY_API_TOKEN}" \
    "https://quay.io/api/v1/repository/${REPO_PATH}/tag/?specificTag=${PRIMARY_TAG_NAME}&limit=1" \
    | jq -r '.tags[0].manifest_digest // empty') && [ -n "${d}" ] && echo "${d}"
}
DIGEST=$(retry quay_digest)
echo "Manifest digest: ${DIGEST}"
for alias in ${ALIAS_TAGS}; do
  echo "Aliasing :${alias} → ${DIGEST}"
  retry curl -sf -X PUT \
    -H "Authorization: Bearer ${QUAY_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"manifest_digest\": \"${DIGEST}\"}" \
    "https://quay.io/api/v1/repository/${REPO_PATH}/tag/${alias}"
done

# Sign with the same cosign version and key as the GitLab pipeline.
curl -fsSL "${CURL_RETRY[@]}" "https://github.com/sigstore/cosign/releases/download/v1.0.0/cosign-linux-amd64" \
  -o /usr/local/bin/cosign
chmod +x /usr/local/bin/cosign
mkdir -p ~/.docker
retry buildah login --authfile ~/.docker/config.json -u "${QUAY_USER}" -p "${QUAY_TOKEN}" quay.io
fetch_secure_file cosign.key /tmp/cosign.key
echo "Signing ${PRIMARY_QUAY_TAG}..."
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" retry cosign sign \
  -key /tmp/cosign.key \
  -a "repo=${SOURCE_URL}" \
  -a "branch=${BRANCH}" \
  "${PRIMARY_QUAY_TAG}"
rm -f /tmp/cosign.key
echo "Image built, pushed and signed."
