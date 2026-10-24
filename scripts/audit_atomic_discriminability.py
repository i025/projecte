"""Render a frozen evidence/visible-difference audit; offline replay only.

The input JSON contains explicitly labelled assistant audit drafts. This script
does not extract semantics, detect differences automatically or run a verifier.
"""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_evidence import load_document
from scripts.region_grounding_experiment import edges,box
from scripts.region_first_generalization import panel_grid


def read(path):return json.loads(Path(path).read_text())


def csv_table(path,rows,fields):
    with path.open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({key:'; '.join(map(str,row[key])) if isinstance(row[key],list) else row[key] for key in fields})


def pair(panels,path,width=750):
    # Reuse the existing 2x2 renderer, remove its unused row for a two-panel view.
    panel_grid(panels,path,width=width)
    if len(panels)==2:
        with Image.open(path) as image:cropped=image.crop((0,0,image.width,image.height//2))
        cropped.save(path)


def render(out):
    frozen=out/'reference_evidence_frozen.json';original=frozen.read_bytes()
    assert (out/'reference_freeze_receipt.json').exists(),'Reference must be frozen before phase-two rendering'
    doc=load_document(frozen);a=np.asarray(Image.open(out/'reference.png').convert('RGB'))
    b=np.asarray(Image.open(out/'render.png').convert('RGB'));assert a.shape==b.shape
    masks={r['id']:r['mask']>0 for r in doc['regions']};(out/'views').mkdir(exist_ok=True)
    overview=[('Reference RGB',Image.fromarray(a)),('Historical real Agent Render',Image.fromarray(b))]
    for name,rgb in [('Reference / frozen ROIs',a),('Render / SAME pixel ROIs',b)]:
        marked=rgb.copy()
        for region,color in [('R2',[255,165,0]),('R3',[35,145,255])]:marked[edges(masks[region])]=color
        overview.append((name,Image.fromarray(marked)))
    pair(overview,out/'comparison.png')
    for region,mask in masks.items():
        x0,y0,x1,y1=box(mask);sl=np.s_[y0:y1,x0:x1];panels=[]
        for side,rgb in [('Reference',a),('Real Render',b)]:
            marked=rgb.copy();marked[edges(mask)]=[255,165,0]
            panels.append((side+' / '+region+' frozen ROI, full crop context',Image.fromarray(marked[sl])))
        pair(panels,out/'views'/(region+'_comparison.png'))
    for item in read(out/'display_contexts.json')['zooms']:
        panels=[]
        for side in ('reference','render'):
            image=Image.open(out/(side+'.png')).crop(item['bbox'])
            panels.append((side+' / post-freeze display context',image))
        pair(panels,out/'views'/(item['id']+'_comparison.png'),width=550)
    audit=read(out/'difference_audit.json');matrix=read(out/'detection_matrix.json')
    fields=['id','region_id','kind','observation','uncertainty','reference_evidence_ids','evidence_coverage',
            'capability_class','atomic_verifier_status','actual_atomic_detection','applicable_energy','missing_or_failure_reason']
    csv_table(out/'difference_audit.csv',audit['observations'],fields)
    csv_table(out/'detection_matrix.csv',matrix['rows'],fields)
    quality=read(out/'reference_evidence_quality_audit.json')
    esc=html.escape
    def cell(value):return esc(json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value))
    parts=['<!doctype html><meta charset="utf-8"><title>R2/R3 Atomic Evidence 区分能力审计</title>',
        '<style>body{font:16px sans-serif;line-height:1.7;margin:24px;background:#f6f7f9;color:#18212e}img{max-width:100%}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #bcc4ce;padding:8px;text-align:left;vertical-align:top}.scroll{overflow-x:auto}pre{white-space:pre-wrap}.warning{background:#fff0d3;padding:14px}.posthoc{background:#f4e4e9;padding:14px}</style>',
        '<h1>bw_0073 R2/R3：Atomic Evidence 区分能力审计</h1>',
        '<p class="warning">非严格盲测：主代理此前已知Render差异。本轮先由未继承前文的独立上下文助手只读Reference/Plan/ROI，冻结14条草稿后才开展第二阶段。草稿、静态差异和方法审查都不是人工GT，全部reviewed=false / provisional-debug。</p>',
        '<p><a href="report.md">报告与复现</a> · <a href="reference_evidence_frozen.json">只读冻结Reference</a> · <a href="reference_freeze_receipt.json">冻结记录</a> · <a href="difference_audit.csv">差异审计CSV</a> · <a href="detection_matrix.csv">检测能力CSV</a> · <a href="reference_evidence_quality_audit.json">证据文本质量审查</a></p>',
        '<img src="comparison.png">']
    for region in ('R2','R3'):
        parts+=['<h2>'+region+'：同坐标图像与冻结命题</h2><img src="views/'+region+'_comparison.png">',
            '<p>轮廓是原有ROI；矩形裁剪只为展示上下文，不生成新ROI，也不把轮廓外的可见目标视作缺失。</p>',
            '<table><tr><th>ID / 类型</th><th>冻结命题</th><th>问题 / 期望</th><th>来源与审核</th></tr>']
        for atom in doc['atomic_evidence']:
            if atom['region_id']!=region:continue
            parts+=['<tr>'+''.join('<td>'+cell(value)+'</td>' for value in [atom['id']+' / '+atom['type'],atom['claim'],atom['question']+' / '+json.dumps(atom['expected'],ensure_ascii=False),atom['source']+' / reviewed=false / reliability=0'])+'</tr>']
        parts+=['</table>']
    parts+=['<h2>核心对照：可见差异与证据区分能力</h2><p>“有证据”不等于已检测。新冻结命题没有运行验证器；下表是可审计的覆盖分析。既有图像距离也不能证明某条具体原子命题被违反。</p>',
        '<div class="scroll"><table><tr><th>差异ID / 区域</th><th>实际图像观察候选</th><th>冻结证据 / 覆盖</th><th>分类及适用Energy</th><th>未检出原因</th><th>不确定性</th></tr>']
    for row in matrix['rows']:
        parts+=['<tr>'+''.join('<td>'+cell(value)+'</td>' for value in [row['id']+' / '+row['region_id'],row['observation'],str(row['reference_evidence_ids'])+' / '+row['evidence_coverage'],matrix['classes'][row['capability_class']]+' / '+str(row['applicable_energy']),row['missing_or_failure_reason']+' / 未执行新原子验证，不能声称已检出',row['uncertainty']])+'</tr>']
    parts+=['</table></div><p>没有新增自动检出或召回率。R3此前没有相应的真实原子付费验证；未执行不能写成验证器检出失败。</p>',
        '<h2>先前三个Satisfied到底检查了什么</h2><table><tr><th>问题</th><th>Reference / Render</th><th>测量内容</th><th>未覆盖</th></tr>']
    for row in read(out/'prior_question_analysis.json')['questions']:
        parts+=['<tr>'+''.join('<td>'+cell(value)+'</td>' for value in [row['id'],str(row['reference'])+' / '+str(row['render'])+' / '+row['status'],row['what_it_checks'],row['what_it_misses']])+'</tr>']
    parts+=['</table><h2>冻结后静态上下文放大</h2><p>以下是审核用放大图，坐标记录在display_contexts.json；不是新评价ROI或新的Reference证据。</p>']
    for item in read(out/'display_contexts.json')['zooms']:parts+=['<img src="views/'+item['id']+'_comparison.png">']
    parts+=['<h2>不可判定项</h2><pre>'+cell(audit['unjudgeable_cases'])+'</pre>',
        '<details><summary>Reference证据自身的不足：展开14条文字审查</summary><pre>'+cell(quality)+'</pre></details>',
        '<p>能加载JSON不代表新候选能被现有固定问答Schema验证；<a href="interface_compatibility.json">接口兼容性检查与待办</a>。</p>',
        '<details class="posthoc"><summary>看过Render后的4项诊断提案；不能混入Reference-only证据</summary><pre>'+cell(read(out/'posthoc_diagnostic_protocol.json'))+'</pre></details>',
        '<details><summary>5组Synthetic Controls协议：未生成、未执行</summary><pre>'+cell(read(out/'synthetic_controls_protocol.json'))+'</pre></details>',
        '<h2>既有图像诊断；本轮没有重跑指标</h2><table><tr><th>ROI</th><th>Appearance</th><th>Perceptual</th></tr>']
    for row in read(out/'prior_image_diagnostics.json')['rows']:
        if not row['id'].startswith('polygon_'):continue
        parts+=['<tr><td>'+row['id']+'</td><td>'+f'{row["appearance"]:.6f}'+'</td><td>'+f'{row["perceptual"]:.6f}'+'</td></tr>']
    parts+=['</table><p>仅复用真实历史测量；Mask兼容性见mask_compatibility.json。不能从非矩形DINO距离推断语义类别正确。历史相机不符合T0，Reference相机未知，未进行正式评分。</p>']
    (out/'comparison.html').write_text('\n'.join(parts))
    assert frozen.read_bytes()==original,'Frozen Reference must never be rewritten'
    print('Audit CSV and review page rebuilt; no models, APIs or new experiments.')


def replay(source,out):
    out.mkdir(parents=True,exist_ok=False)
    for path in source.iterdir():
        if path.suffix in {'.json','.png','.md'}:shutil.copyfile(path,out/path.name)
    for name in ('rois',):shutil.copytree(source/name,out/name)
    (out/'reference_evidence_frozen.json').chmod(0o444)
    render(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['render','replay']);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path);args=parser.parse_args()
    if args.stage=='render':render(args.output.resolve())
    else:
        if args.source is None:parser.error('replay needs --source')
        replay(args.source.resolve(),args.output.resolve())
