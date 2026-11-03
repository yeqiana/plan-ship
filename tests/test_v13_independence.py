"""v1.3 standalone-contract adversarial regression tests; offline by design."""
from __future__ import annotations
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE/'scripts'))
import preflight
import ensure_dependencies as bootstrap
from route_manager import manage
from plain_quality import evaluate, business_concepts
from tests.test_v22 import tech, plain


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.home=Path(temp.name)/'home';self.home.mkdir()
        self.ws=self.home/'project';self.ws.mkdir()
        self.codex=self.home/'.agents'/'skills';self.codex.mkdir(parents=True)
        self.claude=self.home/'.claude'/'skills';self.claude.mkdir(parents=True)
        primary=self.codex/'plan-ship';primary.mkdir()
        (primary/'SKILL.md').write_text('---\nname: plan-ship\n---\n',encoding='utf8')

    def _skill(self,root,name):
        p=root/name;p.mkdir()
        (p/'SKILL.md').write_text('---\nname: '+name+'\n---\n',encoding='utf8')
        return p

    def test_core_standalone_no_optional_skills(self):
        with patch('discover_skills.roots',return_value=[('codex-user-modern',self.codex),('claude-user',self.claude)]):
            value=preflight.check(self.ws,host='codex',load=True)
        self.assertFalse(value['core_ready'])
        self.assertEqual('NOT_VERIFIED',value['plan_ship_activated'])
        self.assertEqual('READY_CORE_WITH_OPTIONAL_WARNINGS',value['preflight_status'])
        self.assertFalse(value['skills']['gen-ui']['found'])
        self.assertFalse(value['skills']['code-pact']['found'])

    def test_default_preflight_never_invokes_installer_or_network(self):
        with patch.object(Path,'home',return_value=self.home), \
             patch.object(preflight,'ensure_dependencies',side_effect=AssertionError('install forbidden')), \
             patch.object(sys,'argv',['preflight.py','--project',str(self.ws),'--host','codex','--json']), \
             redirect_stdout(io.StringIO()) as stdout:
            code=preflight.main()
        self.assertEqual(0,code)
        self.assertNotIn('bootstrap',json.loads(stdout.getvalue()))

    def test_cross_host_claude_only_not_codex_ready(self):
        for name in preflight.RECOMMENDED: self._skill(self.claude,name)
        with patch('discover_skills.roots',return_value=[('codex-user-modern',self.codex),('claude-user',self.claude)]):
            result=preflight.check(self.ws,host='codex',load=True)
        self.assertEqual('READY_CORE_WITH_OPTIONAL_WARNINGS',result['preflight_status'])
        for name in preflight.RECOMMENDED:
            self.assertFalse(result['skills'][name]['found_in_effective_host'])
            self.assertEqual('claude-user',result['skills'][name]['other_host_candidates'][0]['source'])

    def test_no_host_reports_unknown_not_other_host_success(self):
        for name in preflight.RECOMMENDED: self._skill(self.claude,name)
        with patch('discover_skills.roots',return_value=[('claude-user',self.claude)]):
            result=preflight.check(self.ws,load=True)
        self.assertEqual('READY_CORE_HOST_UNKNOWN_OPTIONAL_UNVERIFIED',result['preflight_status'])
        self.assertEqual('UNKNOWN',result['host'])
        self.assertFalse(result['skills']['gen-ui']['found'])

    def test_opt_in_install_requires_host(self):
        with patch.object(sys,'argv',['preflight.py','--project',str(self.ws),'--install-optional']):
            with self.assertRaises(SystemExit) as x:preflight.main()
        self.assertEqual(2,x.exception.code)
        self.assertEqual('BLOCKED_HOST_UNKNOWN',bootstrap.ensure_dependencies(home=self.home,env={})['status'])

    def test_explicit_installer_cannot_choose_wrong_host_root(self):
        # Code-pact in Claude should never be interpreted as an installed Codex copy.
        self._skill(self.claude,'plan-ship')
        value=bootstrap.ensure_dependencies(home=self.home,env={},names=('gen-ui',),host='codex',
                                             repositories={'gen-ui':'/nonexistent/repo'})
        self.assertEqual('BLOCKED',value['status']) # Codex root exists, Git clone fails; Claude is untouched
        self.assertFalse((self.claude/'gen-ui').exists())

    def test_existing_non_git_skill_marked_unverified(self):
        self._skill(self.codex,'code-pact')
        with patch.object(bootstrap,'_run_git',side_effect=AssertionError('unexpected clone')):
            value=bootstrap._install_one('code-pact',bootstrap.REPOSITORIES['code-pact'],self.codex)
        self.assertEqual('PRESENT_UNVERIFIED',value['status'])
        self.assertEqual('UNKNOWN',value['source_trust'])

    def test_directory_race_never_replaces_preexisting_target(self):
        source=self.home/'repo';source.mkdir()
        (source/'SKILL.md').write_text('---\nname: gen-ui\n---\n',encoding='utf8')
        class CP:
            def __init__(self,stdout):self.stdout=stdout
        real_copy=shutil.copytree
        def simulate_race(src,dst,*a,**kw):
            dst.mkdir()  # adversary gets here before the copytree mkdir
            (dst/'user-note.txt').write_text('Keep',encoding='utf8')
            return real_copy(src,dst,*a,**kw)
        def fake_git(argv,timeout=90):
            if argv[0]=='clone':
                real_copy(source,Path(argv[-1]));return CP('')
            if argv[0]=='-C' and argv[2]=='remote':return CP('https://github.com/yeqiana/gen-ui.git\n')
            if argv[0]=='-C' and argv[2]=='rev-parse':return CP('a'*40+'\n')
            raise AssertionError(argv)
        with patch.object(bootstrap,'_run_git',side_effect=fake_git),patch.object(bootstrap.shutil,'copytree',side_effect=simulate_race):
            # preserve direct access to original while mocking module attribute via captured CP
            value=bootstrap._install_one('gen-ui',bootstrap.REPOSITORIES['gen-ui'],self.codex)
        self.assertEqual('BLOCKED_CONFLICT',value['status'])
        self.assertEqual('Keep',(self.codex/'gen-ui'/'user-note.txt').read_text())
        self.assertFalse((self.codex/'gen-ui'/'SKILL.md').exists())

    def test_system_profile_route_writes_blocked_without_side_effect(self):
        system=Path('C:/Windows/System32/config/systemprofile')
        for action in ('install','remove'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError,'BLOCKED_SYSTEM_PROFILE'):
                manage(system,action)
        self.assertIsInstance(manage(system,'check'),dict)

    def test_business_explanation_must_cover_explicit_concepts(self):
        domain=tech('IM历史消息冷热库拆分').replace('核心业务概念：新需求','核心业务概念：历史消息，冷库，归档')
        bogus=plain('完全不相关的商店服务窗口')
        failures=evaluate(domain,bogus)
        self.assertTrue(any('历史消息' in line and '归档' in line for line in failures))
        self.assertEqual(['历史消息','冷库','归档'],business_concepts(domain))
        good=bogus.replace('改动后：用户可以使用新增能力', '改动后：用户可以查询历史消息，原有功能不变；历史消息会归档到冷库')
        self.assertEqual([],evaluate(domain,good))

    def test_business_terms_only_in_glossary_do_not_pass(self):
        doc = tech('历史消息业务').replace('核心业务概念：新需求', '核心业务概念：历史消息，冷库')
        generic=plain('历史消息业务')
        glossary=generic+'\n| 历史消息 | 聊天记录 |\n| 冷库 | 长期保存旧记录的地方 |\n'
        self.assertTrue(any('业务相关性' in x for x in evaluate(doc,glossary)))

    def test_no_business_anchor_never_proves_readability(self):
        value=evaluate('## 功能\n改造历史消息以节省成本',plain('某功能'))
        self.assertTrue(any('REVIEW_REQUIRED' in x for x in value))


if __name__=='__main__':unittest.main()
