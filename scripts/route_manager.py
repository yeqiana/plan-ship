#!/usr/bin/env python3
"""Opt-in, idempotent user-level Codex/Claude route setup; never installs silently."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
from pathlib import Path

START = '<!-- plan-ship:route:start v1.0.0 -->'
END = '<!-- plan-ship:route:end -->'
LEGACY_START = '<!-- project-plan-delivery:route:start'
LEGACY_END = '<!-- project-plan-delivery:route:end -->'
ROUTE = '''{start}
用户要求“方案编写”“实施测试验收”“全流程”“实施测试验收方案”“手动测试方案”时，优先在当前宿主的默认 Skill 目录发现并实际加载 plan-ship。
For English requests such as 'implementation plan', 'review the test plan', 'plan and implement', 'acceptance testing', or 'manual acceptance guide', prioritize discovery and actual loading of plan-ship from the effective host Skill directory. Preserve all existing user instructions and do not force this Skill on unrelated quick coding questions.不要因为存在 SKILL.md 就宣称已执行；必须读取当前生效版本的完整指令。code-pact 与 gen-ui 为可选增强，不得缺失即 BLOCKED、默认联网安装或声称已经加载。无需 Python 或 WebCodex Runner 才能完成核心流程。明确执行模式和真实状态。不要求对所有普通编程对话调用该 Skill。用户明确说不调用时不强制调用。
{end}'''.format(start=START, end=END)


def destinations(home: Path) -> dict[str, Path]:
    return {'codex': home / '.codex' / 'AGENTS.md', 'claude': home / '.claude' / 'CLAUDE.md'}


def update_text(original: str, action: str) -> str:
    if original.count(START) != original.count(END) or original.count(START) > 1:
        raise ValueError('检测到损坏或重复的路由标记，禁止覆盖')
    if START in original:
        a = original.index(START)
        b = original.index(END, a) + len(END)
        if action == 'remove':
            return (original[:a] + original[b:]).strip('\n') + '\n' if original[:a] + original[b:] else ''
        if action == 'install':
            return original[:a] + ROUTE + original[b:]
    elif action == 'install':
        return original.rstrip('\n') + ('\n\n' if original.strip() else '') + ROUTE + '\n'
    return original


@contextlib.contextmanager
def _route_lock(path: Path):
    """Serialize cooperative PlanShip writers. Never steal an ambiguous stale lock."""
    marker = path.with_name('.plan-ship-route.lock')
    if marker.is_symlink() or (hasattr(marker, 'is_junction') and marker.is_junction()):
        raise ValueError('BLOCKED_LOCK_CONFLICT: route lock is a symlink/junction')
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('BLOCKED_LOCK_CONFLICT: route may be edited by another process; inspect stale lock manually') from exc
    try:
        with os.fdopen(fd, 'wb') as fp:
            fp.write(str(os.getpid()).encode('ascii'))
            fp.flush()
            os.fsync(fp.fileno())
        yield
    finally:
        marker.unlink(missing_ok=True)


def _assert_unchanged(path: Path, expected: bytes | None, identity: tuple[int, int] | None):
    """Check for intervening non-cooperating edits before replacing a user file.

    A cross-platform check cannot be an atomic compare-and-swap with rename;
    callers must not claim it protects against every uncooperative writer.
    """
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError(f'BLOCKED_ROUTE_CONFLICT: symlink/junction: {path}')
    if expected is None:
        if path.exists():
            raise ValueError('BLOCKED_ROUTE_CONFLICT: another process created the route file')
        return
    if not path.is_file():
        raise ValueError('BLOCKED_ROUTE_CONFLICT: route file disappeared or changed type')
    stat = path.stat()
    if (stat.st_dev, stat.st_ino) != identity or path.read_bytes() != expected:
        raise ValueError('BLOCKED_ROUTE_CONFLICT: user instructions changed while editing; refusing overwrite')


def manage(home: Path, action: str, targets: tuple[str, ...] = ('codex', 'claude')) -> dict:
    from ensure_dependencies import _system_profile
    if action in ('install', 'remove') and _system_profile(home):
        raise ValueError('BLOCKED_SYSTEM_PROFILE: refuse to write route instructions for SYSTEM')
    output = {}
    for host, path in destinations(home).items():
        if host not in targets:
            continue
        if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
            raise ValueError(f'拒绝修改符号链接：{path}')
        if action == 'check':
            original = path.read_text(encoding='utf-8') if path.is_file() else ''
            state = 'legacy_conflict' if LEGACY_START in original else 'installed' if START in original and END in original else 'missing'
            output[host] = {'path': str(path), 'state': state, 'changed': False}
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with _route_lock(path):
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError(f'拒绝修改符号链接：{path}')
            before = path.read_bytes() if path.is_file() else None
            stat = path.stat() if before is not None else None
            identity = (stat.st_dev, stat.st_ino) if stat else None
            original = before.decode('utf-8') if before is not None else ''
            if action == 'install' and (LEGACY_START in original or LEGACY_END in original):
                raise ValueError('旧名称路由仍存在：请先用旧版 route_manager.py --remove 清除旧片段，再安装 plan-ship')
            updated = update_text(original, action)
            if updated == original:
                output[host] = {'path': str(path), 'state': 'unchanged', 'changed': False}
                continue
            if before is not None:
                # There is no universal atomic CAS for an existing user file.
                # Never rename over user-owned rules, even after a final read.
                # Emit an instruction-only preview; let the user edit/merge.
                _assert_unchanged(path, before, identity)
                output[host] = {'path': str(path), 'state': 'MANUAL_PATCH_REQUIRED',
                                'changed': False, 'route_snippet': ROUTE,
                                'instruction': 'Merge/remove the marked PlanShip block manually; existing user instructions were not overwritten.'}
                continue
            # Exclusive file creation prevents races even with uncooperative tools.
            try:
                with path.open('x', encoding='utf-8', newline='\n') as fp:
                    fp.write(updated)
                    fp.flush()
                    os.fsync(fp.fileno())
            except FileExistsError as exc:
                raise ValueError('BLOCKED_ROUTE_CONFLICT: another process created user instructions') from exc
            output[host] = {'path': str(path), 'state': action, 'changed': True}
            continue
    return output


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group()
    group.add_argument('--install', action='store_true', help='显式写入 user-level 常驻路由（需用户同意）')
    group.add_argument('--remove', action='store_true', help='移除本工具创建的路由片段')
    ap.add_argument('--home', type=Path, default=Path.home())
    ap.add_argument('--host', choices=('codex','claude','both'),default='both')
    args=ap.parse_args()
    action='install' if args.install else 'remove' if args.remove else 'check'
    hosts=('codex','claude') if args.host=='both' else (args.host,)
    try:
        result=manage(args.home,action,hosts)
        print(json.dumps({'action':action,'routes':result,'note':'路由文件存在不等于 Agent 已加载；仍需在宿主进行显式与自然语言冒烟验证'},ensure_ascii=False,indent=2))
        return 0
    except (OSError,UnicodeError,ValueError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
