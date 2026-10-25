"""M2.1: read saved first-party M1 ID support; never render, infer or score."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark_config import camera_pose
from e_harness.spatial_diagnostics import compare_pairs, measure_visible_pair


def read(path):
    return json.loads(Path(path).read_text())


def rgb(path):
    with Image.open(path) as image:
        return np.asarray(image.convert('RGB'))


def load_saved(folder):
    """Check saved associations, without recertifying M1 as a new trusted execution."""
    folder=Path(folder)
    meta,execution=read(folder/'export_metadata.json'),read(folder/'execution.json')
    image=rgb(folder/'render.png');size=list(image.shape[1::-1])
    if size!=meta['image_size']:
        raise ValueError('Saved RGB and metadata grids differ')
    camera_pose(meta['camera']['matrix_world'],require_fixed=True)
    if (execution['camera_before_export']!=meta['camera'] or execution['camera_after_export']!=meta['camera']
            or execution.get('source_kind')!='source_controlled_fixture'
            or execution.get('agent_python_executed') is not False):
        raise ValueError('Saved fixture/camera association differs from M1 record')
    ids={name:int(number) for number,name in meta['semantic_ids'].items()}
    masks={};checks={}
    id_path=folder/'object_id.npy'
    raw_ids=np.load(id_path,allow_pickle=False) if id_path.is_file() else None
    if raw_ids is not None and raw_ids.shape!=image.shape[:2]:
        raise ValueError('Saved Object-ID array is off the RGB grid')
    for name in ('anchor','other'):
        if name not in ids:
            raise ValueError('Expected first-party fixture unit not mapped: '+name)
        with Image.open(folder/'render_masks'/(name+'.png')) as mask:
            array=np.asarray(mask.convert('L'))
        if array.shape!=image.shape[:2] or not np.isin(array,[0,255]).all():
            raise ValueError('ID mask is not binary on the saved RGB grid')
        masks[name]=array>0
        if raw_ids is not None and not np.array_equal(masks[name],raw_ids==ids[name]):
            raise ValueError('Saved PNG mask differs from same-run Object-ID array')
        checks[name]=dict(object_id=ids[name],mask='render_masks/'+name+'.png',
            png_matches_local_id_array=True if raw_ids is not None else None,
            interpretation='Fixture identity, not an RGB detector or semantic GT')
    return image,masks,meta,execution,checks


def controls(masks,size):
    """Known, unclipped image-plane translation and unavailable localization; CPU only."""
    original=measure_visible_pair(masks,size)
    shifted={}
    for name,mask in masks.items():
        shifted[name]=np.zeros_like(mask)
        shifted[name][3:,5:]=mask[:-3,:-5]
        if np.count_nonzero(shifted[name])!=np.count_nonzero(mask):
            raise ValueError('Control translation clips support; invariance not applicable')
    moved=measure_visible_pair(shifted,size)
    values=('relative_distance','delta_y','boundary_gap')
    changes={key:None if original[key] is None or moved[key] is None else moved[key]-original[key]
             for key in values}
    missing=dict(masks);missing[next(iter(missing))]=None
    unavailable=measure_visible_pair(missing,size)
    return dict(source='synthetic_oracle_logic; no new RGB or Blender scene',
        unchanged=dict(changes=compare_pairs(original,original),expected='zero offset changes'),
        common_translation=dict(dx_pixels=5,dy_pixels=3,clipping=False,changes=changes,
            passed=all(value is not None and abs(value)<1e-12 for value in changes.values())),
        unavailable=dict(reason='First object localization withheld, not confirmed missing',
            values={key:unavailable[key] for key in ('left_of','relative_distance','delta_y','boundary_gap')},
            passed=all(unavailable[key] is None for key in ('left_of','relative_distance','delta_y','boundary_gap'))),
        reviewed=False,participates_in_energy=False)


def plot(path,images,masks,measurements,change,appearance):
    font=lambda n:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',n)
    fmt=lambda value,precision=6:'N/A' if value is None else f'{value:.{precision}f}'
    canvas=Image.new('RGB',(1400,1100),'white');draw=ImageDraw.Draw(canvas)
    draw.text((24,15),'M2.1 | visible Object-ID Oracle | unreviewed / provisional / debug',fill='black',font=font(26))
    scale=600/images[0].shape[1]
    for col,(title,array,support,value) in enumerate(zip(('Baseline Reference','Changed Render'),images,masks,measurements)):
        x=25+col*700;draw.text((x,65),title,fill='black',font=font(25))
        marked=array.copy()
        for key,color in (('anchor',[255,190,0]),('other',[0,225,255])):
            mask=support[key];padded=np.pad(mask,1)
            edge=mask & ~(padded[:-2,1:-1]&padded[2:,1:-1]&padded[1:-1,:-2]&padded[1:-1,2:])
            marked[edge]=color
        image=Image.fromarray(marked).resize((600,600),Image.Resampling.NEAREST)
        layer=ImageDraw.Draw(image)
        centres=[]
        for key in ('anchor','other'):
            center=value['normalized_centers'].get(key)
            if center is None:continue
            cx,cy=center[0]*600,center[1]*600;centres.append((cx,cy))
            layer.ellipse((cx-5,cy-5,cx+5,cy+5),fill='white',outline='black',width=2)
        if len(centres)==2:
            height=max(10,min(v['bbox'][1] for v in value['localizations'].values())-15)*scale
            for cx,cy in centres:layer.line((cx,height,cx,cy),fill='white',width=2)
            layer.line((centres[0][0],height,centres[1][0],height),fill='black',width=3)
            for cx,cy in centres:layer.line((cx,height-6,cx,height+6),fill='black',width=3)
        if value['boundary_rows']:
            row=value['boundary_rows'][len(value['boundary_rows'])//2]
            layer.line((row['first_right_edge']*scale,(row['y']+.5)*scale,
                        row['second_left_edge']*scale,(row['y']+.5)*scale),fill=(255,0,255),width=4)
        canvas.paste(image,(x,105))
        texts=[f"left_of: {value['left_of']}",
            f"Centre distance: {fmt(value['relative_distance'])} W ("+
                fmt(None if value['relative_distance'] is None else value['relative_distance']*array.shape[1],1)+' px)',
            f"Mean boundary gap: {fmt(value['boundary_gap'])} W ({fmt(value['boundary_gap_pixels'],3)} px)",
            f"Shared rows: {len(value['boundary_rows'])}; vertical offset: {fmt(value['delta_y'])} H"]
        for i,text in enumerate(texts):draw.text((x,720+i*34),text,fill='black',font=font(21))
    lines=[
        'Historical VLM left_of: yes -> yes, satisfied (unchanged). No new VLM calls.',
        f"Changed - Baseline: centre {fmt(change['relative_distance_change'])} W; gap {fmt(change['boundary_gap_change'])} W",
        f"Existing Global Appearance: {appearance:.8f}. Continuous values remain diagnostic, never Energy.",
        'White brackets = bbox-centre separation. Magenta = one representative shared-row gap.',
        'Gap value averages ALL shared rows. Masks are visible pixel support, not full 3D shape.',
        'No new rendering. Oracle localization does not validate RGB-only evidence extraction.']
    for i,text in enumerate(lines):draw.text((24,875+i*32),text,fill='black',font=font(21))
    canvas.save(path)


def run(m1,m2,output):
    m1,m2,output=Path(m1).resolve(),Path(m2).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError('Never overwrite an existing experiment')
    loaded=[load_saved(m1/side) for side in ('baseline','changed')]
    a,b=loaded
    for key in ('camera','intrinsics_pixels','image_size'):
        if a[2][key]!=b[2][key]:raise ValueError('M1 sides differ: '+key)
    if a[3]['render_after_export']!=b[3]['render_after_export']:
        raise ValueError('M1 render settings differ')
    # Read M2 answers, never invoke an Adapter or modify an old verdict.
    old=read(m2/'verification_results.json');report=read(m2/'report.json')
    for side,key,data in (('reference','reference_rgb',a),('render','render_rgb',b)):
        image_path=(m2/old['image_pair'][key]).resolve()
        if not np.array_equal(rgb(image_path),data[0]):
            raise ValueError('M2 answers belong to different RGB pixels')
        if (m2/old[side]['image_binding']['source_rgb']).resolve()!=image_path:
            raise ValueError('M2 model image binding conflicts with its declared pair')
    relation=[row for row in old['results'] if row['energy']=='spatial']
    if len(relation)!=1:raise ValueError('Expected the one saved M2 spatial relation; do not invent one')
    measurements=[measure_visible_pair(data[1],data[2]['image_size']) for data in loaded]
    change=compare_pairs(*measurements)
    for key in ('relative_distance','boundary_gap','boundary_gap_pixels'):
        first,second=(v[key] for v in measurements)
        change[key+'_change']=None if first is None or second is None else second-first
    paths=lambda p:os.path.relpath(p,output)
    diagnostic=dict(reviewed=False,usage='provisional/debug',formal_eligible=False,
        score=None,participates_in_energy=False,
        provenance=dict(m1_directory=paths(m1),m2_directory=paths(m2),
            prior_execution_chain=paths(m1/'execution_chain.json'),
            fixture_source='e_harness/runtime/benchmark_blender.py::fixture (read only)',
            fixture_units=dict(anchor='red body, 1 x 1 x 1.5 cuboid',other='blue body, unit cube'),
            localization_source='saved first-party Blender Object-ID, synthetic Oracle only',
            new_blender_executions=0,new_model_calls=0,prior_receipt_not_new_execution=True),
        source_checks=dict(same_camera=True,same_intrinsics=True,same_render_settings=True,
            same_grid=True,pose_matches_T0=True,m2_rgb_pair_matches_m1_pixels=True,
            mask_checks={side:data[4] for side,data in zip(('reference','changed'),loaded)}),
        diagnostics=dict(vlm_discrete_relation=dict(source=paths(m2/'verification_results.json'),
                original_record=deepcopy(relation[0]),modified=False,energy_contribution=False),
            continuous_spatial=dict(reference=measurements[0],changed=measurements[1],change=change),
            cached_appearance=dict(source=paths(m2/'report.json'),
                global_value=next(r['value'] for r in report['metric_records']
                                  if r['level']=='global' and r['energy']=='appearance'),
                fixed_region_measurements=deepcopy(report['diagnostics']['fixed_region_measurements']),
                recomputed=False)),
        existing_evaluation=dict(source=paths(m2/'report.json'),
            conditional_values={k:v['value'] for k,v in report['energies'].items()},
            formulas_weights_and_aggregation_unchanged=True),
        controls=controls(a[1],a[2]['image_size']),
        limitations=['Not RGB-only localization or a new Spatial Energy score',
            'Visible bbox centres can change with occlusion; not whole-object or 3D centres',
            'Boundary gap uses shared scanlines and may contain other objects; not 3D free space',
            'Low-resolution ID pass, aliasing, transparency and visibility affect pixel extents',
            'Translation invariance applies only to unclipped equal 2D shifts, not arbitrary camera motion',
            'M2 questions correctly preserve count/order but do not measure continuous separation'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'spatial_diagnostics.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    plot(output/'comparison.png',[d[0] for d in loaded],[d[1] for d in loaded],measurements,change,
         diagnostic['diagnostics']['cached_appearance']['global_value'])
    summary(output,diagnostic)
    return diagnostic


def summary(output,document):
    spatial=document['diagnostics']['continuous_spatial'];ref,changed=spatial['reference'],spatial['changed']
    relation=document['diagnostics']['vlm_discrete_relation']['original_record']
    lines=['# M2.1 Continuous Spatial Evidence Validation','','**reviewed:false · provisional/debug · Synthetic Oracle；没有正式 Spatial 分数。**','',
        '复用 M1 RGB、相机记录及 Object-ID 支持，不重新执行 M1/M2，不运行 Blender/GPU/VLM。',
        '离散关系、连续中心距离、可见边界间隙是三个不同量。旧 M2 回答与证据原样保留。','',
        '| 测量 | Baseline Reference | Changed | Changed − Reference |','| --- | --- | --- | --- |',
        f"| 旧 VLM left_of | {relation['reference_answer']} | {relation['render_answer']} | {relation['status']}（不修改） |",
        f"| Oracle bbox 中心 left_of | {ref['left_of']} | {changed['left_of']} | 离散顺序不变 |"]
    for key,label in (('relative_distance','水平中心间距 / 图宽'),('boundary_gap','共同行平均边界间隙 / 图宽'),
                      ('boundary_gap_pixels','共同行平均边界间隙 / px'),('delta_y','相对垂直偏移 / 图高')):
        delta=spatial['change'].get(key+'_change')
        lines.append(f"| {label} | {ref[key]} | {changed[key]} | {delta} |")
    lines += ['', '中心使用可见 Object-ID Mask 的紧外接框中心，复用 measure_pair/compare_pairs；不是 Mask 质心或完整物体三维中心。',
        '边界间隙是在两物体均有像素的每一行，计算第二物体最左像素左边缘减第一物体最右像素右边缘，再对全部共同行取平均；'
        '没有共同行时为 N/A。它不是外接框包络间隙，亦不表示三维距离或确认无其他内容的空隙。','',
        '## 结果与互补性','',
        '两个几何仍保持左右顺序，中心间距与可见边界间隙均减小，因此无需把 satisfied 改为 violated。',
        f"已有 Global Appearance={document['diagnostics']['cached_appearance']['global_value']}；它响应 RGB 差异但不能直接说明间距减小。"
        '本轮连续量提供该投影几何解释，既有条件 Energy 数值原样引用，不改公式、权重、聚合或 Runtime blocked。',
        '固定 ROI 的已有 Appearance 诊断在 JSON 中保留；不重新定位 ROI，不把各诊断相加。','',
        '## 控制验证','',
        f"- 不变输入：offset change 为零，见 JSON → controls.unchanged。",
        f"- 相同二维平移 (+5,+3) px 且不裁切：{document['controls']['common_translation']}。",
        f"- 一个对象定位不可用：{document['controls']['unavailable']}。",
        '- 这些是 CPU Oracle 数学/接口控制，不是 VLM 或 RGB 检测有效性测试。','',
        '## 来源与限制','',
        'anchor/other 来自可信自制 Fixture 的 ID 映射；红色主体实际是长方体，蓝色为立方体，历史模型的“立方体”用词未回写。'
        'Oracle 标签没有参与生成新的 Reference RGB Evidence，未宣称从 RGB 自动获得对象对应。',
        '逐侧检查 T0、相机内参、分辨率与保存的执行记录，确认 M2 图片像素与 M1 配对。'
        '本机额外验证 PNG Mask 与已有 object_id.npy 相同；公开复现可只用已发布 PNG，原始数组未公开时该项为 null。'
        '这些是对历史可信产物的离线读取，不是一次新的可信执行或完整文件真实性证明。',
        '可见边界受采样、遮挡、透明度影响；共同平移不裁切时的二维不变性不适用于任意相机变化。'
        '没有可靠定位时返回 N/A，不判定 Confirmed Missing，不重复惩罚语义缺失。','',
        '红色可见外接框宽度由58 px变为54 px，中心因此不等于固定物体原点的投影。'
        '复用 helper 附带的 bbox_area_ratio_proxy 只作范围代理，不据此判断真实三维尺寸变化。','',
        '## 复现','', '从仓库根目录，在既有 NumPy/Pillow 环境执行；输出目录必须不存在：','',
        '```bash','python3 -B scripts/continuous_spatial_pilot.py --output /tmp/projecte-m21-new',
        "python3 -B -m unittest discover -s tests -p 'test_*spatial*.py'",'```','',
        '[对照 PNG](comparison.png) · [真实测量、控制及来源](spatial_diagnostics.json)。',
        '本轮仅三个结果文件；没有新的 HTML、Mask、Reference Evidence、模型调用或正式分数。'
        '完成后停止，不对两个几何继续调参，不启动 M3。']
    (output/'summary.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m1',type=Path,default=ROOT/'results/trusted_blender_e2e_pilot')
    parser.add_argument('--m2',type=Path,default=ROOT/'results/m2_reference_vlm_e2e')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.m1,args.m2,args.output)


if __name__=='__main__':main()
