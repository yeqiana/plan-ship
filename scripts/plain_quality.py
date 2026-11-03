#!/usr/bin/env python3
"""Conservative plain-language quality gates; not a substitute for human comprehension."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

REQUIRED={
    '一句话': ('一句话','一句话结论'),
    '为什么': ('为什么','背景'),
    '改动前后': ('改造前后','改动前后','之前和之后'),
    '生活类比': ('生活类比','打个比方','生活中的例子'),
    '图解': ('图解','流程图','看图理解'),
    '验证步骤': ('怎么验证','如何验收','怎么判断'),
    '风险与状态': ('风险与状态','失败怎么办','风险和当前状态'),
    '术语': ('术语小词典','术语解释','专业名词解释'),
}
BUSINESS_ANCHORS = re.compile(r'(?m)^\s*(?:[-*]\s*)?(?:核心业务概念|Business concepts)\s*[：:]\s*(.+?)\s*$')
STATUSES=('BLOCKED','未执行','未通过','未验证')
PLACEHOLDER=re.compile(r'\{\{[^\n{}]+\}\}|\b(?:TODO|TBD)\b',re.I)


def business_concepts(technical: str) -> list[str]:
    """Require explicit project-specific anchors; deterministic check, not semantic AI judgment."""
    matches = BUSINESS_ANCHORS.findall(technical)
    if not matches:
        return []
    terms = [x.strip().strip('`* ') for x in re.split(r'[,，、;；|]', matches[0])]
    return [x for x in terms if 2 <= len(x) <= 60 and not '{{' in x][:12]


def evaluate(technical:str,plain:str)->list[str]:
    errors=[]
    concepts=business_concepts(technical)
    if not concepts:
        errors.append('大白话业务相关性 REVIEW_REQUIRED：技术版缺少“核心业务概念：...”明确锚点，不能以模板结构冒充业务解释通过')
    else:
        main_content = re.split(r'(?m)^##\s+(?:术语|专业名词)', plain, maxsplit=1)[0]
        missing=[x for x in concepts if x not in main_content]
        if missing:
            errors.append('大白话业务相关性不通过，正文缺少核心业务概念：'+', '.join(missing))
        before_after = re.search(r'(?ms)^##\s+[^\n]*(?:改动前后|改造前后|之前和之后)[^\n]*\n(.*?)(?=^##\s+|\Z)', plain)
        if before_after and concepts[0] not in before_after.group(1):
            errors.append('大白话改动前后缺少首个业务概念：'+concepts[0])
    if PLACEHOLDER.search(plain): errors.append('大白话文档含未替换的模板占位符')
    if technical.strip()==plain.strip(): errors.append('大白话文档不得直接复制技术版')
    if len(plain.strip())<360: errors.append('大白话解释缺少足够具体的业务示例与步骤')
    headings=re.findall(r'(?m)^#{2,3}\s+([^\n]+)',plain)
    for label,aliases in REQUIRED.items():
        matches=[(i,h) for i,h in enumerate(headings) if any(token in h for token in aliases)]
        if not matches:
            errors.append('大白话解释缺少章节：'+label)
    if '```mermaid' not in plain and not re.search(r'\S+\s*(?:-->|→|⇒)\s*\S+',plain):
        errors.append('缺少可独立阅读的流程图或步骤箭头图解')
    if '```mermaid' in plain and not re.search(r'(?:图中的|上图|图解说明|箭头表示)',plain):
        errors.append('有图但缺少对图中节点与箭头的文字解释')
    for status in STATUSES:
        if status in technical and status not in plain:
            errors.append('大白话解释遗漏技术文档原有状态：'+status)
    if '|' not in plain.split('## 术语')[-1] and not re.search(r'术语.{1,15}[：:].{4,}',plain):
        errors.append('专业术语缺少具体解释')
    if re.search(r'(?:略|详见技术版|自行理解|与技术文档相同)',plain):
        errors.append('存在将关键解释推给技术文档的语句')
    return errors


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--technical',type=Path,required=True)
    ap.add_argument('--plain',type=Path,required=True)
    args=ap.parse_args()
    try:
        errors=evaluate(args.technical.read_text(encoding='utf-8'),args.plain.read_text(encoding='utf-8'))
    except (OSError,UnicodeError) as exc:
        errors=[str(exc)]
    print(json.dumps({'status':'PASS' if not errors else 'BLOCKED','errors':errors,'note':'结构与显式业务概念的文字覆盖检查，不等于真实读者理解或语义准确；仍需人工复核'},ensure_ascii=False,indent=2))
    return 2 if errors else 0

if __name__=='__main__':
    raise SystemExit(main())
