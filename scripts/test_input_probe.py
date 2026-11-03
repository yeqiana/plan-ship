#!/usr/bin/env python3
"""Read-only test-dir inventory. Requirement dependency judgment belongs to the Agent."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SECRET_SUFFIXES={'.pem','.key','.p12','.pfx'}
SECRET_NAMES={'.env','id_rsa','id_ed25519','credentials.json','secrets.json'}


def probe(workspace:Path, required:list[str]|None=None, max_files:int=500)->dict:
    required=required or []
    if not workspace.is_dir():
        return {'status':'BLOCKED','reason':'无效工作区','files':[]}
    root=workspace/'test-dir'
    if root.is_symlink() or (hasattr(root,'is_junction') and root.is_junction()):
        return {'status':'BLOCKED','reason':'test-dir 是链接/junction，拒绝读取','files':[]}
    for key in required:
        p=Path(key)
        if p.is_absolute() or any(s in ('.','..') for s in p.parts) or not p.parts or '\\' in key:
            return {'status':'BLOCKED','reason':f'非法测试文件相对路径：{key}','files':[]}
    if not root.exists():
        return {'status':'BLOCKED_MISSING_REQUIRED' if required else 'OPTIONAL_ABSENT', 'files':[], 'missing':required,'ask_user':bool(required),'note':'未明确需要外部文件时自动继续'}
    if not root.is_dir():
        return {'status':'BLOCKED','reason':'test-dir 不是目录','files':[]}
    files=[]
    for path in root.rglob('*'):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            return {'status':'BLOCKED','reason':'test-dir 包含符号链接/junction','files':files}
        if not path.is_file():
            continue
        if len(files)>=max_files:
            return {'status':'BLOCKED_INVENTORY_LIMIT','files':files,'reason':'文件数量超出扫描上限，不能误称已完整读取'}
        rel=path.relative_to(root).as_posix()
        if path.name.lower() in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES:
            files.append({'path':rel,'status':'SENSITIVE_SKIPPED'})
            continue
        h=hashlib.sha256()
        try:
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1<<20),b''):
                    h.update(block)
            files.append({'path':rel,'bytes':path.stat().st_size,'sha256':h.hexdigest(),'status':'OBSERVED'})
        except OSError as exc:
            files.append({'path':rel,'status':'UNREADABLE','reason':str(exc)})
    missing=[]
    listed={x['path']:x for x in files}
    for key in required:
        normalized=Path(key).as_posix()
        if normalized not in listed or listed[normalized]['status']!='OBSERVED':
            missing.append(key)
    status=('BLOCKED_MISSING_REQUIRED' if missing else 'READY_WITH_FILES')
    if not required and not files:
        status='OPTIONAL_EMPTY'
    return {'status':status,'files':files,'missing':missing,'ask_user':bool(missing),'note':'只盘点文件，不擅自认定需求是否依赖这些素材；Agent 应先根据真实需求决定 required'}


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,required=True)
    ap.add_argument('--required',action='append',default=[],help='已由需求证明必要的 test-dir 相对路径；可重复')
    args=ap.parse_args()
    data=probe(args.workspace,args.required)
    print(json.dumps(data,ensure_ascii=False,indent=2))
    return 2 if data['status'].startswith('BLOCKED') else 0

if __name__=='__main__':
    raise SystemExit(main())
