#!/usr/bin/env python3
"""方案目录与技术/大白话文档的一对一幂等发布。仅标准库。"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import shutil
from pathlib import Path

INDEX = '.document-index.json'
LOCK = '.document-index.lock'
TRANSACTION = '.publish-transaction'
SCHEMA = '1.0'
NUMERIC = re.compile(r'^(\d+)\. (.+)\.md$')
KEY_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
MARKER = '关联技术原文 SHA-256：'
PLACEHOLDER = re.compile(r'\{\{[^\n]*?\}\}|\bTODO\b|\bTBD\b', re.I)


class DocumentError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_name(name: str) -> str:
    if not isinstance(name, str) or not name or name != name.strip() or len(name) > 100:
        raise DocumentError('方案名称/文档标题为空、前后含空格或过长')
    if any(c in name for c in '<>:"/\\|?*') or any(ord(c) < 32 or ord(c) == 127 for c in name) or name.endswith('.') or name.startswith('.'):
        raise DocumentError('方案名称/文档标题含路径或 Windows 禁止字符')
    if name.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise DocumentError('方案名称/文档标题使用 Windows 保留名称')
    return name


def root_for(workspace: Path, name: str) -> Path:
    """Fail closed on junctions/symlinks at each controlled directory boundary.

    Checking only resolved docs against resolved plan lets an external docs link
    redefine the trust boundary. Reject aliases even when they point inward.
    """
    valid_name(name)
    project = workspace.resolve(strict=True)
    if not project.is_dir():
        raise DocumentError('workspace 不是有效项目目录')
    parent = project
    for part in ('.idea', 'docs', name):
        child = parent / part
        if child.is_symlink():
            raise DocumentError(f'项目文档路径禁止符号链接/junction：{child}')
        # Windows junctions are not always reported as is_symlink on older runtimes.
        if hasattr(child, 'is_junction') and child.is_junction():
            raise DocumentError(f'项目文档路径禁止 junction：{child}')
        try:
            child.resolve().relative_to(project)
        except ValueError as exc:
            raise DocumentError('项目文档真实路径逃逸 workspace，BLOCKED') from exc
        parent = child
    return parent


def safe_file(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise DocumentError(f'文档目标不得是符号链接或 junction：{path}')


@contextlib.contextmanager
def exclusive(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOCK
    safe_file(path)
    with path.open('a+b') as fp:
        fp.seek(0)
        fp.write(b'\0')
        fp.flush()
        if os.name == 'nt':
            import msvcrt
            fp.seek(0)
            msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                fp.seek(0)
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


def atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(f'.{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp')
    with temp.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)



def _path_state(path: Path) -> str | None:
    safe_file(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise DocumentError(f'发布目标不是普通文件：{path}')
    return digest(path.read_bytes())


def _transaction_folder(folder: Path) -> Path:
    txn = folder / TRANSACTION
    safe_file(txn)
    return txn


def _clear_transaction(txn: Path) -> None:
    shutil.rmtree(txn)


def recover_transaction(folder: Path) -> str:
    """Under the exclusive lock: safely finish or roll back an interrupted publish.

    Never overwrite changes that don't match the transaction's old/new fingerprints.
    """
    txn = _transaction_folder(folder)
    if not txn.exists():
        return 'CLEAN'
    if not txn.is_dir():
        raise DocumentError('事务状态损坏：不是目录')
    try:
        manifest = json.loads((txn / 'journal.json').read_text(encoding='utf-8'))
        if manifest.get('schema') != 'v2.3' or len(manifest['files']) != 3:
            raise ValueError('事务日志 schema 不符')
        items = manifest['files']
        states = []
        for item in items:
            rel = Path(item['path'])
            target = folder / rel
            if rel.is_absolute() or '..' in rel.parts or target.resolve().parent not in (folder.resolve(), (folder / '大白话解释').resolve()):
                raise ValueError('事务目标路径不安全')
            current = _path_state(target)
            if current not in (item['before'], item['after']):
                raise DocumentError(f'事务期间发现外部人工改动，拒绝恢复并覆盖：{rel}')
            states.append(current)
        if all(state == item['after'] for state, item in zip(states, items)):
            _clear_transaction(txn)
            return 'COMMITTED'
        # Reverse order, atomically restoring only the hashes backed up before commit.
        for item in reversed(items):
            target = folder / item['path']
            if item['before'] is None:
                if target.exists():
                    target.unlink()
            else:
                backup = txn / item['backup']
                safe_file(backup)
                contents = backup.read_bytes()
                if digest(contents) != item['before']:
                    raise DocumentError('事务备份校验失败：拒绝覆盖')
                # Use the independent primitive so fault injection in `atomic` cannot
                # leave us unable to revert. A disk error here leaves the journal.
                _restore_atomic(target, contents)
        _clear_transaction(txn)
        return 'ROLLED_BACK'
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DocumentError(f'发布事务无法安全恢复：{exc}') from exc


def _restore_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name('.restore-' + os.urandom(8).hex())
    try:
        with temp.open('xb') as fp:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def transactional_publish(folder: Path, payload: list[tuple[Path, bytes]]) -> None:
    """Durable write-ahead journal; retry/recover without clobbering user edits."""
    txn = _transaction_folder(folder)
    if txn.exists():
        raise DocumentError('已有未完成发布事务；请先 recover')
    txn.mkdir()
    entries = []
    try:
        for index, (path, new) in enumerate(payload):
            safe_file(path)
            before = _path_state(path)
            backup = f'backup-{index}.bin'
            if before is not None:
                _restore_atomic(txn / backup, path.read_bytes())
            entries.append({'path': path.relative_to(folder).as_posix(), 'before': before,
                            'after': digest(new), 'backup': backup})
        atomic(txn / 'journal.json', (json.dumps({'schema':'v2.3', 'files':entries}, ensure_ascii=False) + '\n').encode())
        # journal is durable before any target changes
        for path, new in payload:
            atomic(path, new)
        _clear_transaction(txn)
    except BaseException:
        if (txn / 'journal.json').is_file():
            recover_transaction(folder)  # raises on non-recoverable manual modifications
        else:
            _clear_transaction(txn)
        raise


def get_index(folder: Path, create: bool = False, logical_name: str | None = None) -> dict:
    file = folder / INDEX
    safe_file(file)
    if not file.exists():
        if not create:
            raise DocumentError('未初始化方案目录/缺失文档索引')
        return {'schema_version': SCHEMA, 'plan_name': logical_name, 'documents': {}}
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
    except (ValueError, OSError) as e:
        raise DocumentError(f'文档索引损坏：{e}') from e
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA or not isinstance(data.get('documents'), dict):
        raise DocumentError('文档索引 schema 不符')
    if logical_name is not None and data.get('plan_name') != logical_name:
        raise DocumentError('同名目录已有不同方案名称，拒绝覆盖')
    return data


def init(workspace: Path, name: str) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    folder = root_for(workspace, name)
    with exclusive(folder):
        recover_transaction(folder)
        index = get_index(folder, create=True, logical_name=name)
        for child in ('大白话解释', '.drafts'):
            destination = folder / child
            if destination.is_symlink():
                raise DocumentError(f'方案子目录禁止使用符号链接：{child}')
            destination.mkdir(exist_ok=True)
        if not (folder / INDEX).exists():
            atomic(folder / INDEX, (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode())
    return folder


def publish(workspace: Path, name: str, key: str, title: str, technical_file: Path, plain_file: Path) -> tuple[Path, Path]:
    if not KEY_RE.fullmatch(key):
        raise DocumentError('文档逻辑键必须是字母开头的字母/数字/_/-')
    valid_name(title)
    folder = root_for(workspace, name)
    if _transaction_folder(folder).exists():
        with exclusive(folder):
            recover_transaction(folder)
    if not (folder / INDEX).is_file():
        raise DocumentError('先执行 init 初始化方案目录')
    safe_file(folder / '.drafts')
    staging = (folder / '.drafts').resolve()
    if staging.parent != folder.resolve():
        raise DocumentError('临时草稿目录不得是指向方案目录外的符号链接')
    technical_file, plain_file = technical_file.resolve(), plain_file.resolve()
    if technical_file.parent != staging or plain_file.parent != staging:
        raise DocumentError('草稿必须位于当前方案目录的 .drafts 内')
    try:
        tech_data, plain_data = technical_file.read_bytes(), plain_file.read_bytes()
        tech_text, plain_text = tech_data.decode('utf-8-sig'), plain_data.decode('utf-8-sig')
    except (OSError, UnicodeError) as e:
        raise DocumentError(f'无法读取 UTF-8 MD 草稿：{e}') from e
    if not tech_text.lstrip().startswith('# ') or len(tech_text.strip()) < 120 or PLACEHOLDER.search(tech_text):
        raise DocumentError('技术版正文不完整，或存在 TODO/模板占位符')
    if not plain_text.lstrip().startswith('# ') or len(plain_text.strip()) < 120 or PLACEHOLDER.search(plain_text):
        raise DocumentError('大白话版本不完整，或存在 TODO/模板占位符')
    if '图解' not in plain_text and '```mermaid' not in plain_text:
        raise DocumentError('大白话版本必须含图解说明或 Mermaid 图，不能只有口号')
    if MARKER in plain_text:
        raise DocumentError('大白话草稿中不得手填技术版本哈希，交由发布器自动写入')
    # Explain in agent-produced prose; add deterministic provenance marker without changing facts.
    hash_value = digest(tech_data)
    plain_text = plain_text.replace('\r\n', '\n').rstrip() + f'\n\n> {MARKER}`{hash_value}`\n'
    plain_data = plain_text.encode('utf-8')
    with exclusive(folder):
        recover_transaction(folder)
        index = get_index(folder, logical_name=name)
        existing = index['documents'].get(key)
        if existing is not None and (not isinstance(existing, dict) or existing.get('title') != title):
            raise DocumentError('逻辑键已有另一标题；防止同一 key 指向不同文档')
        if existing is None:
            used = {item.get('number') for item in index['documents'].values() if isinstance(item, dict)}
            used.update(int(m.group(1)) for p in folder.glob('*.md') if (m := NUMERIC.fullmatch(p.name)))
            number = max(used or {0}) + 1
        else:
            number = existing['number']
        filename = f'{number}. {title}.md'
        tech_dest = folder / filename
        plain_dest = folder / '大白话解释' / filename
        for dest in (tech_dest, plain_dest):
            safe_file(dest)
            if dest.exists() and (existing is None or dest.name != existing.get('filename')):
                raise DocumentError(f'目标文件已存在且非同一逻辑文档：{dest}')
        if existing is not None and existing.get('filename') != filename:
            raise DocumentError('原有文档文件名发生冲突')
        if existing is not None:
            for old_file, hash_field in ((tech_dest, 'technical_sha256'), (plain_dest, 'plain_sha256')):
                if not old_file.is_file() or digest(old_file.read_bytes()) != existing.get(hash_field):
                    raise DocumentError('已登记文档被手工修改/缺失，请先对账后同步发布，拒绝覆盖用户改动')
        explain_dir = folder / '大白话解释'
        if explain_dir.is_symlink() or explain_dir.resolve().parent != folder.resolve():
            raise DocumentError('大白话目录不得指向方案外部')
        explain_dir.mkdir(exist_ok=True)
        index['documents'][key] = {
            'number': number, 'title': title, 'filename': filename,
            'technical_sha256': hash_value, 'plain_sha256': digest(plain_data),
        }
        transactional_publish(folder, [(tech_dest, tech_data), (plain_dest, plain_data),
            (folder / INDEX, (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode())])
    return tech_dest, plain_dest


def verify_file(file: Path, workspace: Path) -> list[str]:
    errors: list[str] = []
    # The lexical path matters: resolve() here would hide a malicious alias.
    folder = file.absolute().parent
    try:
        valid_name(folder.name)
        expected = root_for(workspace, folder.name)
        if expected != folder or file.is_symlink():
            return ['最终文档必须位于 .idea/docs/<方案名称>/ 且禁止符号链接']
        if _transaction_folder(folder).exists():
            return ['存在未恢复的发布事务；先运行 recover']
        base = (workspace.resolve() / '.idea' / 'docs')
    except (DocumentError, OSError, ValueError) as exc:
        return [f'文档真实路径不安全：{exc}']
    if folder == base or folder.parent != base or not folder.is_dir():
        return ['最终文档必须位于 .idea/docs/<方案名称>/ 根目录']
    try:
        index = get_index(folder)
        if index.get('plan_name') != folder.name:
            return ['文档索引关联的方案名称与所在目录不一致']
        documents = index['documents']
        linked = [item for item in documents.values() if isinstance(item, dict) and item.get('filename') == file.name]
        if len(linked) != 1:
            return ['最终文档没有唯一文档逻辑键索引']
        item = linked[0]
        m = NUMERIC.fullmatch(file.name)
        if not m or int(m.group(1)) != item.get('number'):
            errors.append('文档顺序编号与索引不一致')
        safe_file(folder / '大白话解释')
        plain_file = folder / '大白话解释' / file.name
        safe_file(plain_file)
        if not file.is_file() or not plain_file.is_file():
            errors.append('缺少技术文档或同名大白话解释副本')
            return errors
        data, plain = file.read_bytes(), plain_file.read_bytes()
        if digest(data) != item.get('technical_sha256'):
            errors.append('技术文档修改后未同步发布大白话版本')
        if digest(plain) != item.get('plain_sha256') or f'{MARKER}`{digest(data)}`' not in plain.decode('utf-8-sig'):
            errors.append('大白话文档缺失、遭修改或关联的技术版本已过期')
        plain_text = plain.decode('utf-8-sig')
        from plain_quality import evaluate as check_explanation
        errors.extend(check_explanation(data.decode('utf-8-sig'), plain_text))
        if '图解' not in plain_text and '```mermaid' not in plain_text:
            errors.append('大白话版本缺少图解或 Mermaid 说明')
        for status in ('BLOCKED', '未执行', '未通过'):
            if status in data.decode('utf-8-sig') and status not in plain_text:
                errors.append(f'大白话版本遗漏技术原文关键状态：{status}')
    except (OSError, UnicodeError, DocumentError, ValueError) as exc:
        errors.append(f'文档索引或副本校验失败：{exc}')
    return errors


def verify_all(workspace: Path, name: str) -> list[str]:
    try:
        folder = root_for(workspace, name)
        if _transaction_folder(folder).exists():
            return ['存在未恢复的发布事务；先运行 recover']
        index = get_index(folder, logical_name=name)
    except DocumentError as exc:
        return [str(exc)]
    errors: list[str] = []
    documents = index['documents']
    known = set()
    seen_nums = set()
    for key, item in documents.items():
        if not KEY_RE.fullmatch(key) or not isinstance(item, dict) or not isinstance(item.get('filename'), str):
            errors.append(f'文档索引项无效：{key}')
            continue
        filename = item['filename']
        if filename in known or item.get('number') in seen_nums:
            errors.append(f'编号或文件名重复：{filename}')
        known.add(filename)
        seen_nums.add(item.get('number'))
        errors.extend(f'{filename}: {err}' for err in verify_file(folder / filename, workspace))
    for file in folder.glob('*.md'):
        if file.name not in known:
            errors.append(f'方案目录下存在未登记的正式 Markdown：{file.name}')
    for file in (folder / '大白话解释').glob('*.md'):
        if file.name not in known:
            errors.append(f'存在无对应技术文档的大白话副本：{file.name}')
    for file in folder.rglob('*.md'):
        relative = file.relative_to(folder)
        if len(relative.parts) > 1 and relative.parts[0] not in ('.drafts', '大白话解释'):
            errors.append(f'正式 Markdown 必须登记在方案目录根并有大白话副本：{relative}')
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    for action in ('init', 'publish', 'verify', 'recover'):
        s = sub.add_parser(action)
        s.add_argument('--workspace', required=True, type=Path)
        s.add_argument('--name', required=True)
        if action == 'publish':
            s.add_argument('--key', required=True)
            s.add_argument('--title', required=True)
            s.add_argument('--technical-file', required=True, type=Path)
            s.add_argument('--plain-file', required=True, type=Path)
    args = p.parse_args()
    try:
        if args.action == 'init':
            print('READY:', init(args.workspace, args.name))
        elif args.action == 'publish':
            a, b = publish(args.workspace, args.name, args.key, args.title, args.technical_file, args.plain_file)
            print('PUBLISHED:', a, '\nPLAIN:', b)
        elif args.action == 'recover':
            folder = root_for(args.workspace, args.name)
            with exclusive(folder):
                print('RECOVER:', recover_transaction(folder))
        else:
            issues = verify_all(args.workspace, args.name)
            if issues:
                for issue in issues:
                    print('FAIL:', issue)
                return 1
            print('PASS: 方案目录文档索引、编号与大白话副本一致')
    except DocumentError as exc:
        print('BLOCKED:', exc)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
