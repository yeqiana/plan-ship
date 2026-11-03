#!/usr/bin/env python3
"""OPTIONAL read-only visibility report; PlanShip core needs no Python or other Skills."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from discover_skills import discover
from ensure_dependencies import ensure_dependencies

RECOMMENDED = ('code-pact', 'gen-ui')
REQUIRED = RECOMMENDED  # backwards-compatible export; not mandatory since v1.3


def read_skill_bundle(candidate: dict) -> dict:
    """Read a selected Skill's Markdown and same-directory reference files; never execute it."""
    path = Path(candidate['path'])
    folder = path.parent.resolve()
    try:
        raw = path.read_bytes()
        content = raw.decode('utf-8-sig')
        if not content.strip():
            raise ValueError('空 SKILL.md')
        files = [{'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}]
        refs = set(re.findall(r'(?<![\w/])references/[\w.-]+\.md', content))
        for relative in sorted(refs):
            ref_path = folder / relative
            if not ref_path.is_file() or ref_path.is_symlink() or not ref_path.resolve().is_relative_to(folder):
                raise ValueError(f'必需引用不存在或路径不安全：{relative}')
            data = ref_path.read_bytes()
            data.decode('utf-8-sig')
            if not data.strip():
                raise ValueError(f'必需引用内容为空：{relative}')
            files.append({'file': str(ref_path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
        return {'read_ok': True, 'files': files,
                'note': '仅证明此脚本读取了文件，不能证明当前 Agent 已经加载或遵守该 Skill'}
    except (OSError, UnicodeError, ValueError) as exc:
        return {'read_ok': False, 'error': str(exc)}


def check(project: Path, load: bool = False, host: str | None = None) -> dict:
    """Keep other hosts' Skills OUT of effective-host readiness; all integrations optional."""
    if host not in (None, 'codex', 'claude'):
        raise ValueError('host must be codex or claude')
    result = {}
    for name in RECOMMENDED:
        discovered = discover(project, name)
        all_matches = [entry for entry in discovered['matches'] if entry.get('skill_name') == name]
        own = [entry for entry in all_matches if entry['source'].startswith(host + '-') ] if host else []
        # Discovery in a different agent never implies that this host has loaded it.
        read = read_skill_bundle(own[0]) if load and len(own) == 1 else None
        result[name] = {'optional': True, 'found_anywhere': bool(all_matches),
                        'found_in_effective_host': bool(own), 'found': bool(own),
                        'candidates': own, 'other_host_candidates': [x for x in all_matches if x not in own],
                        'ambiguous': len(own) > 1, 'content_read': read,
                        'checked': discovered['checked'], 'loaded_by_host': 'UNVERIFIED',
                        'source_trust': 'UNVERIFIED',
                        'instruction': 'Optional only; absence or unreadable content never blocks PlanShip core.'}
    status = ('READY_CORE_HOST_UNKNOWN_OPTIONAL_UNVERIFIED' if not host else
              'READY_CORE_WITH_OPTIONAL_WARNINGS' if any(
                  not x['found'] or x['ambiguous'] or (load and not (x['content_read'] or {}).get('read_ok'))
                  for x in result.values()) else 'READY_CORE_OPTIONAL_FILES_READ_AGENT_CONFIRMATION_REQUIRED'
              if load else 'READY_CORE_OPTIONAL_FILES_FOUND_AGENT_CONFIRMATION_REQUIRED')
    return {'preflight_status': status, 'host': host or 'UNKNOWN', 'core_ready': True,
            'skills': result, 'note': 'No WebCodex, Python or auxiliary Skill is needed to USE PlanShip. '
            'This optional diagnostic cannot verify real host invocation.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--host', choices=('codex', 'claude'),
                   help='Host being diagnosed; without this, never infer readiness from another host')
    p.add_argument('--json', action='store_true')
    p.add_argument('--read-content', action='store_true')
    p.add_argument('--no-auto-install', action='store_true',
                   help='Deprecated alias for the default, read-only behavior')
    p.add_argument('--install-optional', action='store_true',
                   help='Explicitly authorized optional install; requires --host, Git and existing Skills root')
    args = p.parse_args()
    if args.install_optional and not args.host:
        p.error('--install-optional requires explicit --host codex|claude')
    if args.install_optional and args.no_auto_install:
        p.error('--install-optional conflicts with --no-auto-install')
    bootstrap = None
    if args.install_optional:
        prior = check(args.project, host=args.host)
        missing = tuple(n for n in RECOMMENDED if not prior['skills'][n]['found_in_effective_host'])
        if missing:
            bootstrap = ensure_dependencies(names=missing, host=args.host)
    result = check(args.project, load=args.read_content, host=args.host)
    if bootstrap is not None:
        result['bootstrap'] = bootstrap
        if bootstrap['status'].startswith('BLOCKED'):
            result['preflight_status'] = 'OPTIONAL_INSTALL_FAILED_CORE_STILL_AVAILABLE'
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result['preflight_status'])
        for name, entry in result['skills'].items():
            print(name, 'AVAILABLE' if entry['found'] else 'OPTIONAL_MISSING')
        if bootstrap is not None:
            print('OPT_IN_INSTALL:', bootstrap['status'])
        print(result['note'])
    return 2 if bootstrap and bootstrap['status'].startswith('BLOCKED') else 0


if __name__ == '__main__':
    sys.exit(main())
