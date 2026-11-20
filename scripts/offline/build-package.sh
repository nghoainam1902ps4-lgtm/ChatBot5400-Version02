#!/usr/bin/env bash
# Build the ChatBot5400 offline update package on a machine WITH Internet
# (Linux / WSL2). docs/deployment/OFFLINE_UPDATE_WINDOWS_BUILD.md.
#
#   scripts/offline/build-package.sh --version 1.3.0-rc.1 [--platform linux/amd64] \
#       [--base-ref v1.2.0] [--sign-key ~/.ssh/cb5400_release] [--out dist/offline] [--no-build]
#
# 0. checks, BEFORE any Docker work, that the VERSION file of the commit can be
#    packaged under --version (VERSION 1.2.0 -> 1.2.0 or 1.2.0-<suffix> only);
# 1. builds the image from the CURRENT commit (clean checkout required) with the
#    offline profile: Docling + EasyOCR + Tesseract baked in, OCI labels
#    (version, revision); tag chatbot5400:<version> (never "latest");
# 2. calls offline_package.py build: git bundle FIRST (a named ref for the commit,
#    verified), source archive, inventory (inside the image, --network none),
#    docker save, manifest, SHA256SUMS, signature. A failed build leaves no
#    half-made package folder behind.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="" PLATFORM="linux/amd64" BASE_REF="v1.2.0" SIGN_KEY="" OUT="$ROOT/dist/offline" BUILD=1 NOTES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --base-ref) BASE_REF="$2"; shift 2 ;;
    --sign-key) SIGN_KEY="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --release-notes) NOTES="$2"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ -n "$VERSION" ] || { echo "--version is required" >&2; exit 2; }
cd "$ROOT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "commit or stash your changes first" >&2; exit 2; }
COMMIT="$(git rev-parse HEAD)"
TAG="chatbot5400:${VERSION}"
# Nothing Docker-related runs when the version cannot be packaged (F-27).
python3 "$ROOT/scripts/offline/offline_package.py" check-version --version "$VERSION" --git-ref "$COMMIT" --repo "$ROOT"
git rev-parse -q --verify "${BASE_REF}^{commit}" >/dev/null || { echo "--base-ref $BASE_REF does not exist in this checkout" >&2; exit 2; }
git merge-base --is-ancestor "$BASE_REF" "$COMMIT" || { echo "--base-ref $BASE_REF is not an ancestor of HEAD" >&2; exit 2; }
if [ "$BUILD" = 1 ]; then
  if docker image inspect "$TAG" >/dev/null 2>&1; then
    echo "image $TAG already exists: remove it deliberately or use --no-build" >&2; exit 2
  fi
  docker buildx build --platform "$PLATFORM" --load \
    --build-arg OCR_INSTALL_TESSERACT=true \
    --build-arg OCR_PREINSTALL_RUNTIMES=true \
    --label "org.opencontainers.image.version=${VERSION}" \
    --label "org.opencontainers.image.revision=${COMMIT}" \
    --label "org.opencontainers.image.title=ChatBot5400" \
    --target runtime -t "$TAG" .
fi
mkdir -p "$OUT"
ARGS=(build --version "$VERSION" --image "$TAG" --platform "$PLATFORM" --git-ref "$COMMIT" --base-ref "$BASE_REF" --out "$OUT" --repo "$ROOT")
[ -n "$SIGN_KEY" ] && ARGS+=(--sign-key "$SIGN_KEY")
[ -n "$NOTES" ] && ARGS+=(--release-notes "$NOTES")
if git rev-parse -q --verify "refs/tags/v${VERSION}" >/dev/null; then ARGS+=(--bundle-refs "v${VERSION}"); fi
exec python3 "$ROOT/scripts/offline/offline_package.py" "${ARGS[@]}"
