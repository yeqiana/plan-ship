#!/usr/bin/env python3
"""Opt-in, idempotent user-level Codex/Claude route setup; never installs silently."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from pathlib import Path

START = '<!-- plan-ship:route:start v1.0.0 -->'
END = '<!-- plan-ship:route:end -->'
LEGACY_START = '<!-- project-plan-delivery:route:start'
LEGACY_END = '<!-- project-plan-delivery:route:end -->'
ROUTE = '''{start}
用户要求“方案编写”“实施测试验收”“全流程”“实施测试验收方案”“手动测试方案”时，优先在当前宿主的默认 Skill 目录发现并实际加载 plan-ship。
For English requests such as 'implementation plan', 'review the test plan', 'plan and implement', 'acceptance testing', or 'manual acceptance guide', prioritize discovery and actual loading of plan-ship from the effective host Skill directory. Preserve all existing user instructions and do not force this Skill on unrelated quick coding questions.不要因为存在 SKILL.md 就宣称已执行；必须读取当前生效版本的完整指令。分析业务项目之前还必须实际加载 ai-coding-collaboration 与 intelligent-ui。明确执行模式和真实状态；缺失依赖则 BLOCKED。不要求对所有普通编程对话调用该 Skill。用户明确说不调用时不强制调用。
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


def manage(home: Path, action: str, targets: tuple[str, ...] = ('codex', 'claude')) -> dict:
    output = {}
    for host, path in destinations(home).items():
        if host not in targets:
            continue
        if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
            raise ValueError(f'拒绝修改符号链接：{path}')
        original = path.read_text(encoding='utf-8') if path.is_file() else ''
        if action == 'check':
            state = 'legacy_conflict' if LEGACY_START in original else 'installed' if START in original and END in original else 'missing'
            output[host] = {'path': str(path), 'state': state, 'changed': False}
            continue
        if action == 'install' and (LEGACY_START in original or LEGACY_END in original):
            raise ValueError('旧名称路由仍存在：请先用旧版 route_manager.py --remove 清除旧片段，再安装 plan-ship')
        updated = update_text(original, action)
        if updated == original:
            output[host] = {'path': str(path), 'state': 'unchanged', 'changed': False}
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_name(path.name + '.plan-ship.backup')
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
        fd, temp = tempfile.mkstemp(prefix='.plan-ship-route-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                f.write(updated)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        output[host] = {'path': str(path), 'state': action, 'changed': True}
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
