#!/usr/bin/env python3
"""Optional controlled Python mutation run (local, not cryptographically trusted).

The sandbox is a temporary filesystem *copy*, not an OS security boundary.
Run only trusted project tests. It never edits the original business source.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = '1.3.4'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(workspace: Path, relative: str) -> Path:
    p = Path(relative)
    if not relative or p.is_absolute() or '..' in p.parts or '\\' in relative:
        raise ValueError('路径必须是安全的相对路径')
    target = workspace / p
    if not target.resolve().is_relative_to(workspace.resolve()):
        raise ValueError('拒绝工作区外部路径')
    parent = workspace
    for part in p.parts:
        parent /= part
        if parent.is_symlink():
            raise ValueError('拒绝符号链接')
    return target


def run_mutation(workspace: Path, plan: Path, source_rel: str, snap_rel: str,
                 patch_rel: str, test_rel: str, node_id: str, test_id: str,
                 output_rel: str = None) -> dict:
    workspace = workspace.resolve()
    plan = plan.resolve(strict=True)
    if plan.parent.parent != (workspace / '.idea' / 'docs').resolve():
        raise ValueError('方案必须是 .idea/docs/<方案>/ 中的正式文件')
    plan_dir = plan.parent
    source = inside(workspace, source_rel)
    mutated_file = inside(workspace, snap_rel)
    patch = inside(workspace, patch_rel)
    test_src = inside(workspace, test_rel)
    if (not all(p.is_file() for p in (source, mutated_file, patch, test_src)) or
        test_src.suffix != '.py' or not node_id.startswith(test_rel.replace('\\', '/') + '::') or
        source.suffix != '.py' or source.stem.startswith('test_') or
        set(Path(source_rel).parts) & {'.idea', 'tests', 'test', 'test-dir', '.git'} or
        not mutated_file.is_relative_to(plan_dir) or not patch.is_relative_to(plan_dir) or
        'evidence' not in mutated_file.relative_to(plan_dir).parts or
        'evidence' not in patch.relative_to(plan_dir).parts):
        raise ValueError('无效的生产源文件、变异快照、补丁或测试源码')
    baseline_bytes, mutant_bytes = source.read_bytes(), mutated_file.read_bytes()
    baseline_hash, mutant_hash, test_hash = sha(source), sha(mutated_file), sha(test_src)
    if baseline_bytes == mutant_bytes or len(mutant_bytes) > 2_000_000:
        raise ValueError('变异源码必须与基线不同且大小受限')
    expected_patch = ''.join(difflib.unified_diff(
        baseline_bytes.decode('utf-8').replace('\r\n', '\n').splitlines(keepends=True),
        mutant_bytes.decode('utf-8').replace('\r\n', '\n').splitlines(keepends=True),
        fromfile='a/'+Path(source_rel).as_posix(),tofile='b/'+Path(source_rel).as_posix())).encode()
    if not expected_patch or patch.read_bytes().replace(b'\r\n', b'\n') != expected_patch:
        raise ValueError('变异补丁与当前基线不匹配')
    run_id='MUT-'+uuid.uuid4().hex[:12].upper()
    nonce=uuid.uuid4().hex
    dest=inside(workspace, output_rel or (plan_dir/'evidence').relative_to(workspace).as_posix())
    if not dest.is_relative_to(plan_dir):
        raise ValueError('输出证据必须属于同一方案目录')
    # No named artifacts are overwritten. All outputs are controlled by this run.
    report_path=dest/(run_id+'.xml')
    log_path=dest/(run_id+'.log')
    record_path=dest/(run_id+'.json')
    if any(p.exists() or p.is_symlink() for p in (report_path,log_path,record_path)):
        raise ValueError('证据文件冲突，拒绝覆盖')
    with tempfile.TemporaryDirectory(prefix='plan-ship-mutation-') as temp:
        sandbox=Path(temp)/'workspace'
        def exclude(root: str, names: list[str]) -> list[str]:
            forbidden={'.git','.idea','.venv','venv','node_modules','__pycache__','.pytest_cache',
                       '.mypy_cache','.ruff_cache','target','build','dist','.env','.npmrc','.pypirc'}
            for name in names:
                if ((Path(root)/name).is_symlink() or
                    (hasattr(Path(root)/name, 'is_junction') and (Path(root)/name).is_junction())):
                    raise ValueError('工作区包含符号链接，无法安全复制')
            return [n for n in names if n in forbidden or n.startswith('.env.') or n.endswith(('.pem','.key','.p12'))]
        shutil.copytree(workspace,sandbox,ignore=exclude)
        s_source, s_test=sandbox/source_rel,sandbox/test_rel
        if sha(s_source)!=baseline_hash or sha(s_test)!=test_hash:
            raise ValueError('复制后的原始源码指纹不一致')
        hook_name='plan_ship_hook_'+uuid.uuid4().hex[:12]
        hook_out=Path(temp)/'trace.json'
        # A pytest hook observes which source module is *actually loaded* by the test.
        hook_code='''import hashlib,json,os,sys\nfrom pathlib import Path\ndef pytest_runtest_makereport(item,call):\n    if call.when != "call" or item.nodeid != os.environ["PLAN_SHIP_NODE"]:\n        return\n    target=Path(os.environ["PLAN_SHIP_MUTANT"]).resolve()\n    loaded=[]\n    for mod in tuple(sys.modules.values()):\n        f=getattr(mod,"__file__",None)\n        if f:\n            try:\n                p=Path(f).resolve()\n                if p==target:\n                    loaded.append(hashlib.sha256(p.read_bytes()).hexdigest())\n            except OSError:\n                pass\n    t=Path(os.environ["PLAN_SHIP_TEST"])\n    record={"nodeid":item.nodeid,"target_module_loaded":os.environ["PLAN_SHIP_MUT_SHA"] in loaded,"loaded_hashes":loaded,"test_source_sha256":hashlib.sha256(t.read_bytes()).hexdigest(),"call_failed":bool(call.excinfo)}\n    Path(os.environ["PLAN_SHIP_HOOK_OUT"]).write_text(json.dumps(record))\n'''
        (sandbox/(hook_name+'.py')).write_text(hook_code,encoding='utf-8')
        env=os.environ.copy()
        env['PYTHONPATH']=str(sandbox)+os.pathsep+env.get('PYTHONPATH','')
        env.update({'PLAN_SHIP_NODE':node_id,'PLAN_SHIP_MUTANT':str(s_source),
                    'PLAN_SHIP_MUT_SHA':mutant_hash,'PLAN_SHIP_TEST':str(s_test),
                    'PLAN_SHIP_HOOK_OUT':str(hook_out)})
        def execute(phase: str, expected_hash: str):
            hook_out.unlink(missing_ok=True)
            junit_file=Path(temp)/(phase+'.xml')
            cmd=[sys.executable,'-B','-m','pytest','-q',node_id,'--junitxml='+str(junit_file),'-p',hook_name]
            env['PLAN_SHIP_MUT_SHA']=expected_hash
            run=subprocess.run(cmd,cwd=sandbox,capture_output=True,text=True,env=env,timeout=180)
            if not junit_file.is_file() or not hook_out.is_file():
                raise ValueError(f'{phase} 阶段缺少真实 pytest/JUnit/加载记录')
            observation=json.loads(hook_out.read_text(encoding='utf-8'))
            cases=[n for n in ET.parse(junit_file).getroot().iter('testcase') if
                   n.get('classname','')+'::'+n.get('name','')==test_id]
            if (len(cases)!=1 or observation.get('nodeid')!=node_id or
                observation.get('target_module_loaded') is not True or
                observation.get('test_source_sha256')!=test_hash or
                sha(s_source)!=expected_hash or sha(s_test)!=test_hash or
                sha(source)!=baseline_hash or sha(test_src)!=test_hash):
                raise ValueError(f'{phase} 阶段源码/目标测试/模块加载证据无效')
            failed=bool(cases[0].find('failure') is not None or cases[0].find('error') is not None)
            if (run.returncode==0) != (not failed) or observation.get('call_failed') != failed:
                raise ValueError(f'{phase} 阶段退出状态与目标用例不一致')
            return run, observation, junit_file, cmd, failed
        baseline_run, baseline_trace, _, _, baseline_failed=execute('baseline',baseline_hash)
        if baseline_failed:
            raise ValueError('原始代码的目标测试未 PASS，禁止判定变异杀伤')
        s_source.write_bytes(mutant_bytes)
        process, trace, junit, command, mutant_failed=execute('mutation',mutant_hash)
        if not mutant_failed:
            raise ValueError('变异代码未使目标测试 FAIL，禁止判定变异杀伤')
        s_source.write_bytes(baseline_bytes)
        restored_run, restored_trace, _, _, restored_failed=execute('restored',baseline_hash)
        if restored_failed:
            raise ValueError('恢复原始代码后目标测试未 PASS，禁止判定变异杀伤')
        if (process.returncode==0 or not junit.is_file() or not hook_out.is_file() or
            sha(s_source)!=baseline_hash or sha(s_test)!=test_hash or
            sha(source)!=baseline_hash or sha(test_src)!=test_hash):
            raise ValueError('真实变异执行没有失败、未记录测试加载或源码在运行期间发生改变')
        # 变异执行记录保留中间阶段的加载指纹和失败证明。
        if (trace.get('nodeid')!=node_id or not trace.get('target_module_loaded') or
            not trace.get('call_failed') or trace.get('test_source_sha256')!=test_hash):
            raise ValueError('测试未加载指定的变异生产模块，或测试源码/运行状态不符合要求')
        tree=ET.parse(junit)
        cases=[n for n in tree.getroot().iter('testcase') if
               n.get('classname','')+'::'+n.get('name','')==test_id and
               (n.find('failure') is not None or n.find('error') is not None)]
        if len(cases)!=1:
            raise ValueError('目标 test_id 未在 JUnit 中唯一失败')
        # Link report to this invocation with a run nonce inside XML properties.
        suites=[n for n in tree.getroot().iter('testsuite')]
        if not suites:
            raise ValueError('JUnit 缺少 testsuite')
        props=suites[0].find('properties')
        if props is None:
            props=ET.Element('properties'); suites[0].insert(0,props)
        for key,value in {'plan_ship_mutation_run_id':run_id,'plan_ship_mutation_nonce':nonce,
                          'plan_ship_mutated_source_sha256':mutant_hash}.items():
            prop=ET.SubElement(props,'property'); prop.set('name',key);prop.set('value',value)
        report_data=ET.tostring(tree.getroot(),encoding='utf-8',xml_declaration=True)
        log_data=(f'PLAN_SHIP_MUTATION_RUN={run_id}\nNONCE={nonce}\n'+
                  'COMMAND='+json.dumps(command,ensure_ascii=False)+'\n'+process.stdout+'\n'+process.stderr).encode('utf-8')
        record={'schema_version':'1.0','runner_version':VERSION,
                'runner_script_sha256':sha(Path(__file__)),
                'command':command,'run_id':run_id,'nonce':nonce,
                'status':'MUTATION_KILLED_HUMAN_REVIEW_REQUIRED','runner':'pytest',
                'execution_mode':'isolated_temporary_copy_not_security_sandbox',
                'mutation_source_path':source_rel,'baseline_source_sha256':baseline_hash,
                'mutated_snapshot_path':snap_rel,'mutated_source_sha256':mutant_hash,
                'mutation_patch_path':patch_rel,'mutation_patch_sha256':sha(patch),
                'test_source_path':test_rel,'test_source_sha256':test_hash,
                'pytest_nodeid':node_id,'test_id':test_id,'exit_code':process.returncode,
                'trace':trace,'phase_outcomes':{'baseline':'PASS','mutation':'FAIL','restored':'PASS'},
                'baseline_trace':baseline_trace,'restored_trace':restored_trace,
                'negative_report_path':report_path.relative_to(workspace).as_posix(),
                'negative_report_sha256':hashlib.sha256(report_data).hexdigest(),
                'negative_log_path':log_path.relative_to(workspace).as_posix(),
                'negative_log_sha256':hashlib.sha256(log_data).hexdigest()}
        dest.mkdir(parents=True,exist_ok=True)
        # Write only after verification; cannot overwrite any preexisting artifact.
        for path,data in ((report_path,report_data),(log_path,log_data),
                          (record_path,(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode())):
            with path.open('xb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
        return {'record_path':record_path.relative_to(workspace).as_posix(),
                'record_sha256':sha(record_path),'run_id':run_id,'status':record['status']}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','plan','source','snapshot','patch','test-source','node-id','test-id'):
        ap.add_argument('--'+name,required=True)
    ap.add_argument('--output-dir')
    args=ap.parse_args()
    try:
        result=run_mutation(Path(args.workspace),Path(args.plan),args.source,args.snapshot,
                            args.patch,args.test_source,args.node_id,args.test_id,args.output_dir)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:
        print('ACCEPTANCE_NOT_VERIFIED:',exc);return 2

if __name__=='__main__':
    raise SystemExit(main())
