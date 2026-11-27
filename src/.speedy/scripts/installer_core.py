"""
installer_core.py — Động cơ Ownership Manifest, Đóng gói, Cài đặt, Cập nhật (Staging) và Rollback.
Đảm bảo an toàn tuyệt đối:
- Không bao giờ xóa hay ghi đè dữ liệu vận hành trong `ai-workspace/` của người dùng.
- Không xóa các skill/rule riêng của dự án trong `.agents/` nằm ngoài `manifest.json`.
- Phát hiện xung đột khi người dùng đã tùy chỉnh `AGENTS.md` hoặc file kit-owned (khác SHA-256 gốc).
- Luôn tạo bản sao lưu khôi phục (Rollback) trước khi áp dụng thay đổi.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contracts import ErrorCode, SpeedyError
from storage import atomic_write_bytes, atomic_write_json, file_sha256, read_json_safe, utc_now_iso

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")

EXCLUDE_PACKAGE_NAMES = {"__pycache__", ".DS_Store", ".pytest_cache", "manifest.json"}
SENSITIVE_FILENAMES = {".env", "id_rsa", "credentials.json"}

SPEEDY_GITIGNORE_BEGIN = "# >>> Speedy DevKit (local) >>>"
SPEEDY_GITIGNORE_END = "# <<< Speedy DevKit (local) <<<"
SPEEDY_GITIGNORE_ENTRIES = (
    "/.agents/",
    "/.speedy/",
    "/ai-workspace/",
    "/AGENTS.md",
)


def ensure_speedy_gitignore(target_root: Path) -> Dict[str, Any]:
    """
    Thêm (hoặc đồng bộ) khối ignore của Speedy DevKit vào `.gitignore` của dự án đích
    một cách idempotent mà tuyệt đối không sửa hay xóa các dòng có sẵn của người dùng.
    """
    gi_path = target_root.resolve() / ".gitignore"
    block = "\n".join([SPEEDY_GITIGNORE_BEGIN, *SPEEDY_GITIGNORE_ENTRIES, SPEEDY_GITIGNORE_END]) + "\n"
    existed = gi_path.is_file()
    existing = gi_path.read_text(encoding="utf-8", errors="replace") if existed else ""

    pattern = re.compile(
        rf"{re.escape(SPEEDY_GITIGNORE_BEGIN)}.*?{re.escape(SPEEDY_GITIGNORE_END)}\r?\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        new_content = pattern.sub(block, existing, count=1)
        action = "unchanged" if new_content == existing else "updated"
    else:
        sep = "" if (not existing or existing.endswith("\n")) else "\n"
        spacer = "\n" if existing.strip() else ""
        new_content = f"{existing}{sep}{spacer}{block}"
        action = "created" if not existed else "appended"

    if action != "unchanged":
        atomic_write_bytes(gi_path, new_content.encode("utf-8"))

    return {"action": action, "path": ".gitignore", "entries": list(SPEEDY_GITIGNORE_ENTRIES)}


def parse_semver(version_str: str) -> Tuple[int, int, int, str]:
    m = SEMVER_RE.match((version_str or "").strip())
    if not m:
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"Chuỗi phiên bản không đúng chuẩn SemVer (MAJOR.MINOR.PATCH): '{version_str}'.",
        )
    # Bản chính thức (không có hậu tố pre-release) lớn hơn bản pre-release cùng số
    pre = m.group(4) or "~"
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)


def classify_package_file(rel_posix: str) -> str:
    """
    Phân loại quyền sở hữu cho từng file trong gói Speedy:
    - `seed_once`: chỉ khởi tạo nếu chưa tồn tại (toàn bộ vùng `ai-workspace/`).
    - `user_customizable`: thuộc gói nhưng người dùng hay tùy chỉnh (`AGENTS.md`) -> hỏi nếu đã đổi khác bản gốc.
    - `kit_owned`: thuộc lõi `.speedy/` và các entry `.agents/` của Speedy -> cập nhật tự động nếu người dùng chưa sửa tay.
    """
    if rel_posix.startswith("ai-workspace/"):
        return "seed_once"
    if rel_posix == "AGENTS.md":
        return "user_customizable"
    return "kit_owned"


def build_ownership_manifest(package_root: Path) -> Dict[str, Any]:
    root = package_root.resolve()
    ver_path = root / ".speedy" / "VERSION"
    if not ver_path.is_file():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Thiếu file VERSION tại: {ver_path}")
    version = ver_path.read_text(encoding="utf-8").strip()
    parse_semver(version)

    entries: Dict[str, Dict[str, Any]] = {}
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        if any(part in EXCLUDE_PACKAGE_NAMES for part in fpath.relative_to(root).parts):
            continue
        if fpath.name in SENSITIVE_FILENAMES or fpath.suffix in {".pyc", ".bak", ".lock"}:
            raise SpeedyError(
                ErrorCode.CONTRACT_VIOLATION,
                f"Phát hiện file nhạy cảm hoặc file tạm không được phép đóng gói: {fpath.relative_to(root)}",
            )
        rel = fpath.relative_to(root).as_posix()
        entries[rel] = {
            "sha256": file_sha256(fpath),
            "size": fpath.stat().st_size,
            "ownership": classify_package_file(rel),
        }

    return {
        "schema_version": 1,
        "product": "Speedy DevKit",
        "version": version,
        "generated_at": utc_now_iso(),
        "file_count": len(entries),
        "files": entries,
    }


def write_manifest_in_place(package_root: Path) -> Dict[str, Any]:
    manifest = build_ownership_manifest(package_root)
    atomic_write_json(package_root / ".speedy" / "manifest.json", manifest)
    return manifest


def verify_package_integrity(package_root: Path) -> Dict[str, Any]:
    """Xác thực gói nguồn tại vùng staging khớp 100% với `.speedy/manifest.json`."""
    root = package_root.resolve()
    mpath = root / ".speedy" / "manifest.json"
    if not mpath.is_file():
        raise SpeedyError(ErrorCode.CONTRACT_VIOLATION, f"Gói Speedy thiếu file manifest: {mpath}")

    manifest = read_json_safe(mpath)
    parse_semver(str(manifest.get("version", "")))
    files_map = manifest.get("files", {})
    if not isinstance(files_map, dict) or not files_map:
        raise SpeedyError(ErrorCode.CONTRACT_VIOLATION, "Manifest rỗng hoặc sai định dạng.")

    for rel, meta in files_map.items():
        fpath = root / rel
        if not fpath.is_file():
            raise SpeedyError(ErrorCode.CONTRACT_VIOLATION, f"Gói Speedy bị thiếu file khai báo trong manifest: {rel}")
        actual_sha = file_sha256(fpath)
        if actual_sha != meta.get("sha256"):
            raise SpeedyError(
                ErrorCode.CONTRACT_VIOLATION,
                f"Checksum không khớp cho file '{rel}' trong gói nguồn (expected={meta.get('sha256')}, actual={actual_sha}).",
            )
    return manifest


def export_clean_package(source_src_dir: Path, out_dir: Path) -> Dict[str, Any]:
    """Đóng gói thư mục `src/` ra một thư mục phát hành độc lập kèm `manifest.json` đã kiểm định."""
    src_root = source_src_dir.resolve()
    manifest = write_manifest_in_place(src_root)

    # Đảm bảo không có dữ liệu runtime giả trong src/ai-workspace
    for rt_sub in ("sessions", "audit", "plans", "specs", "state", "logs", "reports", "tmp"):
        rt_dir = src_root / "ai-workspace" / rt_sub
        if rt_dir.is_dir():
            stray = [p.name for p in rt_dir.iterdir() if p.name != ".gitkeep"]
            if stray:
                raise SpeedyError(
                    ErrorCode.CONTRACT_VIOLATION,
                    f"Không thể đóng gói: thư mục runtime mẫu 'ai-workspace/{rt_sub}' đang chứa dữ liệu thật/giả: {stray}",
                )

    dest = out_dir.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    for rel in manifest["files"]:
        src_file = src_root / rel
        dst_file = dest / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

    shutil.copy2(src_root / ".speedy" / "manifest.json", dest / ".speedy" / "manifest.json")
    verified = verify_package_integrity(dest)
    return {
        "status": "packaged",
        "version": verified["version"],
        "output_dir": str(dest),
        "file_count": verified["file_count"],
    }


def plan_install_or_update(
    package_root: Path,
    target_root: Path,
    *,
    force_overwrite_conflicts: bool = False,
) -> Dict[str, Any]:
    """Lập kế hoạch cài đặt/cập nhật chi tiết mà chưa chạm vào bất kỳ file nào của dự án đích."""
    incoming = verify_package_integrity(package_root)
    target = target_root.resolve()
    target.mkdir(parents=True, exist_ok=True)

    prev_manifest_path = target / ".speedy" / "manifest.json"
    prev_files: Dict[str, Dict[str, Any]] = {}
    prev_version: Optional[str] = None
    if prev_manifest_path.is_file():
        try:
            prev_data = read_json_safe(prev_manifest_path)
            prev_files = prev_data.get("files", {}) if isinstance(prev_data.get("files"), dict) else {}
            prev_version = str(prev_data.get("version") or "")
        except SpeedyError:
            prev_files = {}

    to_create: List[str] = []
    to_update: List[str] = []
    unchanged: List[str] = []
    preserved_seed: List[str] = []
    conflicts: List[Dict[str, str]] = []
    obsolete_to_remove: List[str] = []

    incoming_files: Dict[str, Dict[str, Any]] = incoming["files"]

    for rel, meta in sorted(incoming_files.items()):
        ownership = meta.get("ownership", "kit_owned")
        new_sha = meta["sha256"]
        dst_path = target / rel

        if not dst_path.exists():
            to_create.append(rel)
            continue

        if ownership == "seed_once":
            # Bảo toàn tuyệt đối mọi file đã có trong ai-workspace/
            preserved_seed.append(rel)
            continue

        live_sha = file_sha256(dst_path)
        if live_sha == new_sha:
            unchanged.append(rel)
            continue

        prev_sha = (prev_files.get(rel) or {}).get("sha256")
        # Nếu trước đó đã cài Speedy và người dùng chưa hề sửa file này (live_sha == prev_sha) -> cập nhật êm!
        if prev_sha and live_sha == prev_sha:
            to_update.append(rel)
        elif force_overwrite_conflicts:
            to_update.append(rel)
        else:
            reason = (
                "File đã có sẵn trong dự án trước khi cài Speedy"
                if prev_sha is None
                else "File đã được người dùng tùy chỉnh khác với bản gốc của Speedy"
            )
            conflicts.append({"path": rel, "reason": reason})

    # Phát hiện các file kit-owned cũ đã bị loại bỏ ở phiên bản mới
    for old_rel, old_meta in sorted(prev_files.items()):
        if old_rel in incoming_files or old_meta.get("ownership") == "seed_once":
            continue
        old_path = target / old_rel
        if not old_path.is_file():
            continue
        live_sha = file_sha256(old_path)
        if live_sha == old_meta.get("sha256") or force_overwrite_conflicts:
            obsolete_to_remove.append(old_rel)
        else:
            conflicts.append(
                {
                    "path": old_rel,
                    "reason": "File kit-owned cũ đã ngừng hỗ trợ nhưng người dùng đã chỉnh sửa nên không tự xóa.",
                }
            )

    # Liệt kê các file tùy chỉnh riêng của dự án trong .agents/ được giữ nguyên
    preserved_user_customizations: List[str] = []
    target_agents = target / ".agents"
    if target_agents.is_dir():
        for existing_f in sorted(target_agents.rglob("*")):
            if existing_f.is_file():
                rel_ag = existing_f.relative_to(target).as_posix()
                if rel_ag not in incoming_files and rel_ag not in obsolete_to_remove:
                    preserved_user_customizations.append(rel_ag)

    return {
        "previous_version": prev_version,
        "incoming_version": incoming["version"],
        "target_root": str(target),
        "to_create": to_create,
        "to_update": to_update,
        "unchanged": unchanged,
        "preserved_runtime_and_seed": preserved_seed,
        "preserved_user_customizations": preserved_user_customizations,
        "obsolete_to_remove": obsolete_to_remove,
        "conflicts": conflicts,
        "gitignore_recommendations": list(SPEEDY_GITIGNORE_ENTRIES),
    }


def apply_install_or_update(
    package_root: Path,
    target_root: Path,
    *,
    dry_run: bool = True,
    force_overwrite_conflicts: bool = False,
    allow_with_conflicts_skipped: bool = False,
    update_gitignore: bool = True,
) -> Dict[str, Any]:
    """
    Thực thi cài đặt hoặc cập nhật Speedy vào `target_root`:
    - Mặc định `dry_run=True`.
    - Nếu có `conflicts` khi chạy thật (`dry_run=False`) mà chưa bật `force_overwrite_conflicts` hoặc `allow_with_conflicts_skipped`,
      hệ thống dừng an toàn để xin ý kiến người dùng (không ghi đè âm thầm).
    - Tạo thư mục backup đầy đủ để có thể `rollback_install` khôi phục 100%.
    """
    pkg = package_root.resolve()
    target = target_root.resolve()
    plan = plan_install_or_update(pkg, target, force_overwrite_conflicts=force_overwrite_conflicts)

    if dry_run:
        return {"applied": False, "dry_run": True, "backup_dir": None, "plan": plan}

    if plan["conflicts"] and not (force_overwrite_conflicts or allow_with_conflicts_skipped):
        raise SpeedyError(
            ErrorCode.CONTRACT_VIOLATION,
            f"Phát hiện {len(plan['conflicts'])} file xung đột với tùy chỉnh của dự án; dừng để tránh ghi đè âm thầm.",
            details={"conflicts": plan["conflicts"]},
            remediation="Xem danh sách xung đột, chọn giữ nguyên file dự án (--skip-conflicts) hoặc cho phép ghi đè (--force-overwrite).",
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = target / "ai-workspace" / "tmp" / "backups" / f"speedy-backup-{stamp}"
    backup_files_dir = backup_dir / "files"
    backup_files_dir.mkdir(parents=True, exist_ok=True)

    # Sao lưu các file sẽ bị sửa/xóa + manifest cũ + .gitignore cũ trước khi chạm vào đĩa
    overwritten_or_removed = list(plan["to_update"]) + list(plan["obsolete_to_remove"])
    if (target / ".speedy" / "manifest.json").is_file():
        overwritten_or_removed.append(".speedy/manifest.json")
    had_prev_gitignore = (target / ".gitignore").is_file()
    if update_gitignore and had_prev_gitignore:
        overwritten_or_removed.append(".gitignore")

    for rel in overwritten_or_removed:
        orig = target / rel
        if orig.is_file():
            bdest = backup_files_dir / rel
            bdest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(orig, bdest)

    backup_meta = {
        "created_at": utc_now_iso(),
        "target_root": str(target),
        "previous_version": plan["previous_version"],
        "incoming_version": plan["incoming_version"],
        "created_files": list(plan["to_create"]),
        "backed_up_files": overwritten_or_removed,
        "had_previous_manifest": (target / ".speedy" / "manifest.json").is_file(),
        "had_previous_gitignore": had_prev_gitignore,
        "gitignore_updated": bool(update_gitignore),
    }
    atomic_write_json(backup_dir / "backup-manifest.json", backup_meta)

    gitignore_res: Optional[Dict[str, Any]] = None
    try:
        for rel in plan["to_create"] + plan["to_update"]:
            src_f = pkg / rel
            dst_f = target / rel
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(dst_f, src_f.read_bytes())

        for rel in plan["obsolete_to_remove"]:
            obs_f = target / rel
            if obs_f.is_file():
                obs_f.unlink()

        # Cập nhật manifest mới (nhưng nếu có file conflict được giữ nguyên thì bảo toàn hash cũ của file đó để lần sau vẫn nhận biết!)
        prev_manifest_path = target / ".speedy" / "manifest.json"
        prev_files = (
            read_json_safe(prev_manifest_path).get("files", {})
            if prev_manifest_path.is_file()
            else {}
        )
        new_manifest = read_json_safe(pkg / ".speedy" / "manifest.json")
        if plan["conflicts"] and allow_with_conflicts_skipped and not force_overwrite_conflicts:
            new_files = new_manifest.setdefault("files", {})
            for conflict in plan["conflicts"]:
                c_path = conflict["path"]
                if c_path in prev_files:
                    new_files[c_path] = prev_files[c_path]
                else:
                    new_files.pop(c_path, None)
        atomic_write_json(prev_manifest_path, new_manifest)

        if update_gitignore:
            gitignore_res = ensure_speedy_gitignore(target)
    except Exception as exc:
        rollback_from_backup(backup_dir, target)
        raise SpeedyError(
            ErrorCode.VERIFICATION_FAILED,
            f"Lỗi trong lúc cập nhật, đã tự động rollback về trạng thái cũ: {exc}",
        ) from exc

    return {
        "applied": True,
        "dry_run": False,
        "backup_dir": str(backup_dir),
        "created_count": len(plan["to_create"]),
        "updated_count": len(plan["to_update"]),
        "removed_obsolete_count": len(plan["obsolete_to_remove"]),
        "skipped_conflicts_count": len(plan["conflicts"]),
        "gitignore": gitignore_res,
        "plan": plan,
    }


def rollback_from_backup(backup_dir: Path, target_root: Optional[Path] = None) -> Dict[str, Any]:
    """Khôi phục nguyên trạng các file bị cập nhật/xóa và gỡ bỏ các file mới thêm từ bản backup."""
    bdir = backup_dir.resolve()
    meta = read_json_safe(bdir / "backup-manifest.json")
    target = (target_root or Path(str(meta["target_root"]))).resolve()
    bfiles = bdir / "files"

    removed_new: List[str] = []
    for rel in meta.get("created_files", []):
        # Không bao giờ xóa dữ liệu người dùng mới tạo trong ai-workspace/sessions hay audit
        if rel.startswith(("ai-workspace/sessions/", "ai-workspace/audit/", "ai-workspace/plans/")):
            continue
        f = target / rel
        if f.is_file():
            f.unlink()
            removed_new.append(rel)

    restored: List[str] = []
    for rel in meta.get("backed_up_files", []):
        bf = bfiles / rel
        if bf.is_file():
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(dst, bf.read_bytes())
            restored.append(rel)

    if not meta.get("had_previous_manifest") and (target / ".speedy" / "manifest.json").is_file():
        (target / ".speedy" / "manifest.json").unlink()
    if meta.get("gitignore_updated") and not meta.get("had_previous_gitignore") and (target / ".gitignore").is_file():
        (target / ".gitignore").unlink()

    return {
        "rolled_back": True,
        "restored_version": meta.get("previous_version"),
        "restored_files_count": len(restored),
        "removed_new_files_count": len(removed_new),
    }


def update_from_source(
    target_root: Path,
    *,
    source: Optional[str] = None,
    dry_run: bool = True,
    force_overwrite_conflicts: bool = False,
    allow_with_conflicts_skipped: bool = False,
) -> Dict[str, Any]:
    """
    Cập nhật Speedy trong dự án ứng dụng từ đường dẫn gói cục bộ hoặc Git repository có tag `speedy-vX.Y.Z`.
    Không bao giờ tự động dùng `git remote origin` của ứng dụng.
    """
    target = target_root.resolve()
    cfg_path = target / ".speedy" / "config" / "source.json"
    cfg = read_json_safe(cfg_path) if cfg_path.is_file() else {}
    env_file_src = ""
    env_file = target / "ai-workspace" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#") and "=" in clean:
                k, v = clean.split("=", 1)
                if k.strip() == "SPEEDY_SOURCE_URL":
                    env_file_src = v.strip().strip('"').strip("'")
                    break
    resolved_src = (
        source
        or os.environ.get("SPEEDY_SOURCE_URL", "").strip()
        or env_file_src
        or str(cfg.get("source_url") or "").strip()
    )
    if not resolved_src:
        raise SpeedyError(
            ErrorCode.NOT_FOUND,
            "Chưa cấu hình nguồn cập nhật Speedy (source_url đang trống).",
            remediation="Truyền '--source <path_hoặc_git_url>', đặt biến môi trường SPEEDY_SOURCE_URL, hoặc cập nhật .speedy/config/source.json.",
        )

    local_cand = Path(resolved_src).expanduser()
    if local_cand.is_dir() and ((local_cand / ".speedy").is_dir() or (local_cand / "src" / ".speedy").is_dir()):
        pkg_dir = (local_cand / "src") if (local_cand / "src" / ".speedy").is_dir() else local_cand
        return apply_install_or_update(
            pkg_dir,
            target,
            dry_run=dry_run,
            force_overwrite_conflicts=force_overwrite_conflicts,
            allow_with_conflicts_skipped=allow_with_conflicts_skipped,
        )

    # Nếu là Git URL: tìm tag speedy-v* mới nhất theo semver và clone vào vùng staging tạm
    tag_prefix = str(cfg.get("tag_prefix") or "speedy-v")
    try:
        ls_proc = subprocess.run(
            ["git", "ls-remote", "--tags", resolved_src, f"refs/tags/{tag_prefix}*"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Không thể truy vấn Git remote '{resolved_src}': {exc}") from exc

    if ls_proc.returncode != 0:
        raise SpeedyError(
            ErrorCode.NOT_FOUND,
            f"Không thể đọc danh sách tag từ '{resolved_src}': {ls_proc.stderr.strip()}",
        )

    tags: List[Tuple[Tuple[int, int, int, str], str]] = []
    for line in ls_proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ref = parts[1].strip()
        if ref.endswith("^{}"):
            ref = ref[:-3]
        tag_name = ref.replace("refs/tags/", "")
        if not tag_name.startswith(tag_prefix):
            continue
        ver_part = tag_name[len(tag_prefix) :]
        try:
            tags.append((parse_semver(ver_part), tag_name))
        except SpeedyError:
            continue

    if not tags:
        raise SpeedyError(
            ErrorCode.NOT_FOUND,
            f"Repository nguồn '{resolved_src}' chưa có tag phát hành dạng '{tag_prefix}X.Y.Z'.",
        )

    tags.sort(key=lambda item: item[0])
    latest_ver_tuple, latest_tag = tags[-1]
    current_ver_file = target / ".speedy" / "VERSION"
    if current_ver_file.is_file():
        cur_ver_str = current_ver_file.read_text(encoding="utf-8").strip()
        if parse_semver(cur_ver_str) >= latest_ver_tuple:
            return {
                "applied": False,
                "status": "UP_TO_DATE",
                "current_version": cur_ver_str,
                "latest_tag": latest_tag,
            }

    with tempfile.TemporaryDirectory(prefix="speedy-staging-") as staging_tmp:
        clone_proc = subprocess.run(
            ["git", "clone", "--depth=1", "--branch", latest_tag, resolved_src, staging_tmp],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if clone_proc.returncode != 0:
            raise SpeedyError(
                ErrorCode.NOT_FOUND,
                f"Tải tag '{latest_tag}' về vùng staging thất bại: {clone_proc.stderr.strip()}",
            )
        subpath = str(cfg.get("package_subpath") or "src")
        staged_pkg = (Path(staging_tmp) / subpath) if (Path(staging_tmp) / subpath / ".speedy").is_dir() else Path(staging_tmp)
        return apply_install_or_update(
            staged_pkg,
            target,
            dry_run=dry_run,
            force_overwrite_conflicts=force_overwrite_conflicts,
            allow_with_conflicts_skipped=allow_with_conflicts_skipped,
        )
