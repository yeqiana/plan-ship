#!/usr/bin/env python3
"""Fail-closed release verification: exact archive bytes against one Git tree."""
from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


class ReleaseError(ValueError):
    pass


def git(repo: Path, *args: str) -> bytes:
    command = subprocess.run(['git', '-C', str(repo), *args],
                             capture_output=True, check=False)
    if command.returncode:
        raise ReleaseError('Git 读取失败：' + command.stderr.decode('utf-8', errors='replace'))
    return command.stdout


def tracked_tree(repo: Path, ref: str) -> dict[str, bytes]:
    """Read Git tree objects, not the mutable working directory."""
    rows = git(repo, 'ls-tree', '-rz', '--full-tree', ref).split(b'\0')
    expected = {}
    for row in rows:
        if not row:
            continue
        header, raw_name = row.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split(' ')
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ReleaseError('Git tree 包含符号链接或不受支持对象')
        name = raw_name.decode('utf-8')
        expected[name] = git(repo, 'cat-file', 'blob', oid)
    return expected


def check_zip(repo: Path, archive: Path, ref: str = 'HEAD') -> list[str]:
    """Compare archive payload exactly. Never extract into the filesystem."""
    issues = []
    try:
        expected = tracked_tree(repo, ref)
        if not expected:
            return ['Git Tree 为空，禁止发行']
        with zipfile.ZipFile(archive, 'r') as pack:
            items = pack.infolist()
            if len(items) > 10000 or sum(info.file_size for info in items) > 256 * 1024 * 1024:
                raise ReleaseError('ZIP 条目数量或总解压体积超限')
            # Accept either flat entries or the single conventional archive root.
            # Never accept a mixture of both, arbitrary root renaming or aliases.
            prefix = repo.resolve().name + '/'
            files = [info.filename for info in items if not info.is_dir()]
            wrapped = any(name.startswith(prefix) for name in files)
            if wrapped and not all(name.startswith(prefix) for name in files):
                issues.append('ZIP 同时包含带根目录与无根目录的文件')
            listed: dict[str, bytes] = {}
            for info in items:
                raw_name = info.filename
                name = raw_name[len(prefix):] if wrapped and raw_name.startswith(prefix) else raw_name
                path = PurePosixPath(name)
                if (not name or name.startswith(('/', '\\')) or
                        '\\' in name or '..' in path.parts or
                        not name.endswith('/') and path.as_posix() != name or
                        ':' in path.parts[0] or
                        info.flag_bits & 0x1):
                    issues.append('不安全的 ZIP 路径或加密条目：' + name)
                    continue
                if info.is_dir():
                    # A ZIP directory is metadata only, not a payload. Reject
                    # any directory outside a permitted wrapped project root.
                    if raw_name == prefix and wrapped:
                        continue
                    if not name.endswith('/') or name.startswith('/'):
                        issues.append('无效目录条目：' + raw_name)
                    continue
                if name in listed:
                    issues.append('ZIP 重复条目：' + name)
                    continue
                unix_mode = (info.external_attr >> 16) & 0o170000
                if unix_mode not in (0, 0o100000):
                    issues.append('ZIP 包含链接或特殊文件：' + name)
                    continue
                if info.file_size > 20 * 1024 * 1024:
                    issues.append('ZIP 单文件超出安全限制：' + name)
                    continue
                listed[name] = pack.read(info)
            missing = expected.keys() - listed.keys()
            unexpected = listed.keys() - expected.keys()
            if missing:
                issues.append('ZIP 缺少 Git 文件：' + ', '.join(sorted(missing)[:20]))
            if unexpected:
                issues.append('ZIP 存在 Git 外额外文件：' + ', '.join(sorted(unexpected)[:20]))
            changed = [name for name in expected.keys() & listed.keys()
                       if expected[name] != listed[name]]
            if changed:
                issues.append('ZIP 与 Git Tree 内容不一致：' + ', '.join(sorted(changed)[:20]))
    except (ReleaseError, OSError, zipfile.BadZipFile, EOFError, RuntimeError, ValueError) as exc:
        issues.append('ZIP 校验失败：' + str(exc))
    return issues


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    cli.add_argument('--zip', type=Path, required=True)
    cli.add_argument('--ref', default='HEAD')
    args = cli.parse_args()
    failures = check_zip(args.repo.resolve(), args.zip.resolve(), args.ref)
    print(json.dumps({'status': 'PASS' if not failures else 'BLOCKED',
                      'git_ref': args.ref, 'errors': failures},
                     ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == '__main__':
    sys.exit(main())
