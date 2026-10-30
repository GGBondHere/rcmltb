"""Update trusted source repositories without shell interpolation or history removal."""

from os import environ, replace
from pathlib import Path, PurePosixPath
from shutil import copy2, copytree, rmtree
from subprocess import CalledProcessError, run
from tempfile import TemporaryDirectory
from uuid import uuid4


_PRIVATE_DIRS = {"data", "downloads", "tokens", "rclone", "accounts", "thumbnails", "qbittorrent", "qbittorrent-data"}
_PRIVATE_FILES = {"config.env", "config.py", "credentials.json", "cookies.txt", ".netrc", "botlog.txt", "log.txt", ".env"}


def _git(root, hooks, *arguments):
    environment = dict(environ, GIT_TERMINAL_PROMPT="0")
    try:
        return run(
            ["git", "-c", f"core.hooksPath={hooks}", "-C", str(root), *arguments],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment,
        ).stdout
    except CalledProcessError as error:
        raise ValueError(f"Git {arguments[0]} failed; source was not forcibly overwritten") from error


def _source_files(root, hooks, revision):
    files = []
    seen = set()
    for entry in _git(root, hooks, "ls-tree", "-r", "-z", "--full-tree", revision).split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, _ = metadata.split()
        path = PurePosixPath(name)
        parts = [part.lower() for part in path.parts]
        if (
            mode not in {"100644", "100755"} or kind != "blob"
            or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
            or not parts or parts[0] in _PRIVATE_DIRS or ".git" in parts
            or parts[0] in _PRIVATE_FILES or parts[0].startswith(".env.")
            or path.name.lower().endswith((".pickle", ".session", ".session-journal", ".session-wal", ".session-shm"))
            or name.lower() in seen
        ):
            raise ValueError("Upstream source contains an unsupported path or runtime configuration")
        seen.add(name.lower())
        files.append(name)
    if not files:
        raise ValueError("Upstream repository has no source files")
    return files


def _target(root, name):
    target = root.joinpath(*PurePosixPath(name).parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError("Update path leaves the application directory")
    for component in (target, *target.parents):
        if component == root:
            break
        if component.is_symlink():
            raise ValueError("Update path contains a symbolic link")
    return target


def update_source(repository, branch="master", root="."):
    root = Path(root).resolve()
    if not isinstance(repository, str) or not repository or repository.startswith("-") or any(c.isspace() or ord(c) < 32 for c in repository):
        raise ValueError("Invalid UPSTREAM_REPO")
    if "::" in repository or ("://" in repository and not repository.startswith(("https://", "http://", "ssh://", "file://"))):
        raise ValueError("Unsupported Git transport")
    if not isinstance(branch, str) or not branch or branch.startswith("-"):
        raise ValueError("Invalid UPSTREAM_BRANCH")

    with TemporaryDirectory(prefix="rcmltb-update-") as temporary:
        temporary = Path(temporary)
        hooks = temporary / "hooks"
        hooks.mkdir()
        _git(root, hooks, "check-ref-format", "--branch", branch)
        if (root / ".git").exists():
            if _git(root, hooks, "status", "--porcelain", "--untracked-files=normal", "--", ".", ":(top,exclude)log.txt", ":(top,exclude)botlog.txt").strip():
                raise ValueError("Local changes exist; automatic update skipped")
            _git(root, hooks, "fetch", "--quiet", "--no-tags", "--", repository, f"refs/heads/{branch}")
            for name in _source_files(root, hooks, "FETCH_HEAD"):
                _target(root, name)
            _git(root, hooks, "merge", "--ff-only", "--no-edit", "--no-overwrite-ignore", "FETCH_HEAD")
            return

        checkout = temporary / "checkout"
        checkout.mkdir()
        _git(checkout, hooks, "init", "--quiet")
        _git(checkout, hooks, "fetch", "--quiet", "--no-tags", "--depth=1", "--", repository, f"refs/heads/{branch}")
        files = _source_files(checkout, hooks, "FETCH_HEAD")
        _git(checkout, hooks, "checkout", "--quiet", "--detach", "FETCH_HEAD")
        _git(checkout, hooks, "remote", "add", "origin", repository)
        targets = [(name, _target(root, name)) for name in files]
        # A source-only image has no history to compare. Keep replaced files for recovery.
        backup = _target(root, f"data/update-backups/{uuid4().hex}")
        backup.mkdir(parents=True)
        replaced = []
        owns_metadata = False
        try:
            for name, target in targets:
                old = backup.joinpath(*PurePosixPath(name).parts)
                existed = target.exists()
                if existed:
                    if not target.is_file():
                        raise ValueError("Source update would replace a directory")
                    old.parent.mkdir(parents=True, exist_ok=True)
                    copy2(target, old)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = target.with_name(f".{target.name}.update-{uuid4().hex}")
                try:
                    copy2(checkout.joinpath(*PurePosixPath(name).parts), staged)
                    replace(staged, target)
                finally:
                    staged.unlink(missing_ok=True)
                replaced.append((target, old, existed))
            metadata = root / ".git"
            metadata.mkdir()
            owns_metadata = True
            copytree(checkout / ".git", metadata, dirs_exist_ok=True)
            with (metadata / "info" / "exclude").open("a", encoding="utf-8") as stream:
                stream.write("\n/data/\n")
        except Exception:
            for target, old, existed in reversed(replaced):
                if existed:
                    copy2(old, target)
                else:
                    target.unlink(missing_ok=True)
            if owns_metadata:
                metadata = root / ".git"
                if metadata.resolve() == root.joinpath(".git") and metadata.resolve().is_relative_to(root):
                    rmtree(metadata)
            raise
