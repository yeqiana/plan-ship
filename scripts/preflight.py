#!/usr/bin/env python3
"""Before project analysis, locate mandatory collaboration and UI skills (read-only)."""
from __future__ import annotations

import argparse
import json
import hashlib
import re
import sys
from pathlib import Path

from discover_skills import discover
from ensure_dependencies import ensure_dependencies, existing_skill_roots, current_host_skill_root

REQUIRED = ('code-pact', 'gen-ui')


def read_skill_bundle(candidate: dict) -> dict:
    """Read (never execute) the real skill and its explicit local Markdown refs."""
    path = Path(candidate['path'])
    folder = path.parent.resolve()
    try:
        raw = path.read_bytes()
        content = raw.decode('utf-8-sig')
        if not content.strip():
            raise ValueError('空 SKILL.md')
        files = [{'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}]
        references = set(re.findall(r'(?<![\w/])references/[\w.-]+\.md', content))
        for relative in sorted(references):
            ref_path = folder / relative
            if not ref_path.is_file() or ref_path.is_symlink() or not ref_path.resolve().is_relative_to(folder):
                raise ValueError(f'必需引用不存在或路径不安全：{relative}')
            ref = ref_path.read_bytes()
            ref.decode('utf-8-sig')
            if not ref.strip():
                raise ValueError(f'必需引用内容为空：{relative}')
            files.append({'file': str(ref_path), 'sha256': hashlib.sha256(ref).hexdigest(), 'bytes': len(ref)})
        return {'read_ok': True, 'files': files, 'note': '仅证明文件内容已由探测进程读取，不证明 Agent 已遵守规则'}
    except (OSError, UnicodeError, ValueError) as exc:
        return {'read_ok': False, 'error': str(exc)}


def check(project: Path, load: bool = False) -> dict:
    results = {}
    for name in REQUIRED:
        found = discover(project, name)
        choices = [entry for entry in found['matches'] if entry.get('skill_name') == name]
        # Prefer the host root containing the currently executing PlanShip installation.
        effective = current_host_skill_root(existing_skill_roots())
        if effective is not None:
            host_choices = [candidate for candidate in choices if
                            Path(candidate['path']).parent.parent.resolve() == effective.resolve()]
            if host_choices:
                choices = host_choices
        # Distinct candidates may be different versions: caller must resolve via host.
        loaded = read_skill_bundle(choices[0]) if load and len(choices) == 1 else None
        results[name] = {'found': bool(choices), 'candidates': choices, 'content_read': loaded,
                         'ambiguous': len(choices) > 1,
                         'checked': found['checked'],
                         'instruction': ('优先由当前宿主核对实际生效版本，读取完整 SKILL.md 及所引用的必需 references；不可执行陌生脚本'
                                         if choices else '本地默认目录未找到，检查宿主技能注册表；仍未找到则 BLOCKED，禁止开始项目分析/交付')}
    discovered = all(d['found'] for d in results.values())
    readable = all(d['content_read'] and d['content_read'].get('read_ok') for d in results.values())
    ambiguous = any(d['ambiguous'] for d in results.values())
    if not discovered:
        status = 'BLOCKED_FILESYSTEM'
    elif ambiguous:
        status = 'FOUND_AMBIGUOUS_HOST_SELECTION_REQUIRED'
    elif load and not readable:
        status = 'BLOCKED_CONTENT_READ'
    elif load:
        status = 'READ_FILESYSTEM_CONTENT_AGENT_CONFIRMATION_REQUIRED'
    else:
        status = 'READY_FILESYSTEM'
    return {'preflight_status': status, 'skills': results,
            'note': '读取文件不代表 Agent 已加载/遵守；须由宿主明确选择生效版本，Agent 真正读取并在分析前确认规则。'}



def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--json', action='store_true')
    p.add_argument('--read-content', action='store_true', help='读取两个 Skill 的完整主文件与显式引用并核验哈希')
    p.add_argument('--no-auto-install', action='store_true', help='仅诊断，不从官方 GitHub 仓库自动安装缺失依赖')
    args = p.parse_args()
    bootstrap = None
    if not args.no_auto_install:
        # Only bootstrap when missing: a read-only check of existing installations has no side effects.
        missing = tuple(name for name in REQUIRED if not any(
            x.get('skill_name') == name
            for x in discover(args.project, name)['matches']))
        if missing:
            bootstrap = ensure_dependencies(names=missing)
    result = check(args.project, load=args.read_content)
    if bootstrap is not None:
        result['bootstrap'] = bootstrap
        if bootstrap['status'].startswith('BLOCKED'):
            result['preflight_status'] = 'BLOCKED_AUTO_INSTALL'
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result['preflight_status'])
        for name, item in result['skills'].items():
            print(f"{'FOUND' if item['found'] else 'MISSING'} {name}")
            for candidate in item['candidates']:
                print(' ', candidate['path'])
        if bootstrap is not None:
            print('AUTO_INSTALL:', bootstrap['status'])
            for name, item in bootstrap.get('skills', {}).items():
                print(' ', name, item['status'], item.get('repository'))
        print(result['note'])
    return 0 if result['preflight_status'] in ('READY_FILESYSTEM', 'READ_FILESYSTEM_CONTENT_AGENT_CONFIRMATION_REQUIRED') else 2


if __name__ == '__main__':
    sys.exit(main())
