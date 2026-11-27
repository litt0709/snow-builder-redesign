#!/usr/bin/env bash
# scripts/install.sh — Cài đặt Speedy DevKit bằng 1 lệnh từ Git vào thư mục dự án hiện tại.
#
# Cách dùng mặc định (chạy tại thư mục gốc dự án của bạn):
#   curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash
#
# Truyền thêm tùy chọn:
#   curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash -s -- --dry-run
#   curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash -s -- --ref main
#   SPEEDY_SOURCE_URL=git@github.com:litt0709/snow-builder-redesign.git bash scripts/install.sh

set -euo pipefail

DEFAULT_REPO_URL="https://github.com/litt0709/snow-builder-redesign.git"
REPO_URL="${SPEEDY_SOURCE_URL:-$DEFAULT_REPO_URL}"
TARGET_DIR="$PWD"
REQUESTED_REF="${SPEEDY_REF:-}"
TAG_PREFIX="${SPEEDY_TAG_PREFIX:-speedy-v}"
DRY_RUN=0
FORCE_OVERWRITE=0
NO_GITIGNORE=0

usage() {
  cat <<'EOF'
Speedy DevKit — Remote 1-Command Installer

Cách dùng:
  install.sh [tùy chọn]

Tùy chọn:
  --target <dir>       Thư mục gốc dự án đích (mặc định: thư mục hiện tại)
  --source <git_url>   URL Git repository nguồn (mặc định: SPEEDY_SOURCE_URL hoặc repo chính thức)
  --ref <tag|branch>   Cài đúng tag hoặc nhánh chỉ định (mặc định: tag speedy-v* mới nhất, fallback nhánh mặc định)
  --dry-run            Chỉ xem trước kế hoạch cài đặt, không ghi file
  --force-overwrite    Ghi đè cả file bị xung đột với dự án (vẫn tạo backup)
  --no-gitignore       Không tự động thêm thư mục Speedy vào .gitignore dự án
  -h, --help           Hiển thị trợ giúp này
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { echo "[Speedy] Thiếu giá trị cho --target" >&2; exit 2; }
      TARGET_DIR="$2"
      shift 2
      ;;
    --source)
      [[ $# -ge 2 ]] || { echo "[Speedy] Thiếu giá trị cho --source" >&2; exit 2; }
      REPO_URL="$2"
      shift 2
      ;;
    --ref)
      [[ $# -ge 2 ]] || { echo "[Speedy] Thiếu giá trị cho --ref" >&2; exit 2; }
      REQUESTED_REF="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force-overwrite)
      FORCE_OVERWRITE=1
      shift
      ;;
    --no-gitignore)
      NO_GITIGNORE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[Speedy] Tham số không hợp lệ: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "[Speedy] Lỗi: cần cài đặt 'git' trước." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[Speedy] Lỗi: cần cài đặt 'python3' (>= 3.9) trước." >&2; exit 1; }

if [[ -z "$REPO_URL" || "$REPO_URL" == -* ]]; then
  echo "[Speedy] Lỗi: --source / SPEEDY_SOURCE_URL không hợp lệ: '$REPO_URL'" >&2
  exit 2
fi
if [[ -n "$REQUESTED_REF" && "$REQUESTED_REF" == -* ]]; then
  echo "[Speedy] Lỗi: --ref không hợp lệ: '$REQUESTED_REF'" >&2
  exit 2
fi

TMP_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t speedy-install)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

RESOLVED_REF="$REQUESTED_REF"
SOURCE_KIND="branch"

if [[ -z "$RESOLVED_REF" ]]; then
  echo "[Speedy] Đang kiểm tra phiên bản mới nhất từ: $REPO_URL"
  TAGS_RAW="$(git ls-remote --tags -- "$REPO_URL" "refs/tags/${TAG_PREFIX}*" 2>"$TMP_DIR/git-ls.err" || true)"
  LATEST_TAG="$(printf '%s\n' "$TAGS_RAW" | python3 -c '
import re, sys
prefix = sys.argv[1]
semver_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")
found = []
for line in sys.stdin:
    parts = line.strip().split("\t")
    if len(parts) < 2:
        continue
    ref = parts[1]
    if ref.endswith("^{}"):
        ref = ref[:-3]
    tag = ref.replace("refs/tags/", "", 1)
    if not tag.startswith(prefix):
        continue
    m = semver_re.match(tag[len(prefix):])
    if m:
        found.append(((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "~"), tag))
if found:
    found.sort(key=lambda x: x[0])
    print(found[-1][1])
' "$TAG_PREFIX")"

  if [[ -n "$LATEST_TAG" ]]; then
    RESOLVED_REF="$LATEST_TAG"
    SOURCE_KIND="tag"
  else
    HEAD_SYMREF="$(git ls-remote --symref -- "$REPO_URL" HEAD 2>>"$TMP_DIR/git-ls.err" | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2; exit}' || true)"
    RESOLVED_REF="${HEAD_SYMREF:-main}"
    SOURCE_KIND="branch"
  fi
else
  if [[ "$RESOLVED_REF" == "${TAG_PREFIX}"* ]]; then
    SOURCE_KIND="tag"
  fi
fi

if [[ "$RESOLVED_REF" == -* ]]; then
  echo "[Speedy] Lỗi: ref phân giải không hợp lệ: '$RESOLVED_REF'" >&2
  exit 2
fi

echo "[Speedy] Đang tải nguồn ($SOURCE_KIND: $RESOLVED_REF)..."
if ! git clone --depth=1 --branch "$RESOLVED_REF" -- "$REPO_URL" "$TMP_DIR/repo" >/dev/null 2>"$TMP_DIR/git-clone.err"; then
  echo "[Speedy] Lỗi: không thể tải ref '$RESOLVED_REF' từ '$REPO_URL'." >&2
  if [[ -s "$TMP_DIR/git-clone.err" ]]; then
    cat "$TMP_DIR/git-clone.err" >&2
  fi
  exit 1
fi

COMMIT_SHA="$(git -C "$TMP_DIR/repo" rev-parse HEAD)"

INSTALL_ARGS=(
  "--target" "$TARGET_DIR"
  "--source-url" "$REPO_URL"
  "--source-ref" "$RESOLVED_REF"
  "--source-kind" "$SOURCE_KIND"
  "--installed-commit" "$COMMIT_SHA"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  INSTALL_ARGS+=("--dry-run")
else
  INSTALL_ARGS+=("--apply")
  if [[ "$FORCE_OVERWRITE" -eq 1 ]]; then
    INSTALL_ARGS+=("--force-overwrite")
  else
    INSTALL_ARGS+=("--skip-conflicts")
  fi
fi

if [[ "$NO_GITIGNORE" -eq 1 ]]; then
  INSTALL_ARGS+=("--no-gitignore")
fi

RESULT_JSON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$TMP_DIR/repo/scripts/install.py" "${INSTALL_ARGS[@]}")"
printf '%s\n' "$RESULT_JSON"

if [[ "$DRY_RUN" -eq 0 ]]; then
  PYTHONDONTWRITEBYTECODE=1 python3 -c '
import json, sys
data = json.loads(sys.argv[1])
plan = data.get("plan") or {}
gi = data.get("gitignore") or {}
ver = plan.get("incoming_version", "?")
gi_act = gi.get("action", "skipped")
bdir = data.get("backup_dir", "N/A")
print("")
print(f"[Speedy] Cài đặt hoàn tất v{ver} ({sys.argv[2]}: {sys.argv[3]}, commit: {sys.argv[4][:7]}).")
print(f"[Speedy] .gitignore: {gi_act} | Backup: {bdir}")
print("[Speedy] Lần sau muốn cập nhật Speedy trong dự án này, chỉ cần gọi slash command: /update-speedy")
' "$RESULT_JSON" "$SOURCE_KIND" "$RESOLVED_REF" "$COMMIT_SHA"
fi
