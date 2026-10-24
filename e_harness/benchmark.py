"""Offline Agentic Image-to-3D evaluation and explicitly reviewed CPU rendering."""
import argparse
from copy import deepcopy
import fcntl
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

from .benchmark_config import (ENERGIES, POLICY, ROOT, RENDER, SCENE_BENCHMARK,
                               camera_check, camera_pose, write_json)
from .benchmark_evidence import (area_mask, build_reference, candidate_reference, load_document,
                                 local_dino_extractor, reliability, rgb)
from .benchmark_metrics import aggregate, compare
from .benchmark_structure import structural_report


def read_json(path):
    return json.loads(Path(path).read_text()) if path else None


def json_evidence(evidence):
    """Array data goes into masks.npz; JSON contains concise traceable metadata."""
    if isinstance(evidence,dict):
        return {k:json_evidence(v) for k,v in evidence.items() if k not in {'mask','anchor_exclusion'}}
    if isinstance(evidence,list):
        return [json_evidence(v) for v in evidence]
    if isinstance(evidence,np.ndarray):
        return evidence.tolist()
    return evidence


def evaluate(input_rgb, render_rgb, reference=None, rendered=None, *, geometry=None,
             triage=None, rules=None, extract=None, vlm=None, render_metadata=None,
             human_annotation=None, valid_mask=None, withhold_region_overlaps=False):
    evidence = build_reference(input_rgb, reference)
    rows, diagnostics = compare(input_rgb, render_rgb, evidence, rendered, extract=extract, vlm=vlm,
                               valid_mask=valid_mask, withhold_region_overlaps=withhold_region_overlaps)
    energies, observation = aggregate(rows)
    structure = structural_report(geometry, triage, rules)
    active = [r for r in rows if r['q']>0 and r.get('aggregation_eligible', True)]
    valid = [r for r in active if r['value'] is not None]
    def coverage(level):
        selected=[r for r in rows if r['level']==level]
        return sum(r['q']>0 and r['value'] is not None and r.get('aggregation_eligible', True)
                   for r in selected)/len(selected) if selected else None
    h,w=input_rgb.shape[:2]
    region_union=np.zeros((h,w),float)
    for region in evidence['regions']:
        if reliability(region):
            region_union=np.maximum(region_union,area_mask(region,(h,w)))
    known_anchors=[a for a in evidence['anchors'] if reliability(a)]
    known_ids={m['reference_id'] for m in diagnostics['anchor_matching'] if m['status']!='unknown'}
    unknown=[dict(id=r['id'],reason=r.get('aggregation_reason') or r['reason']) for r in rows
             if r['q']==0 or r['value'] is None or not r.get('aggregation_eligible', True)]
    # Conflicting human evidence is retained and explicitly reported, not resolved from render.
    conflicts=deepcopy(evidence.get('conflicting_evidence',[]))
    conflicts += [dict(id=r['id'],reason='Explicitly marked conflicting reference evidence; excluded')
                  for r in evidence['regions']+evidence['anchors'] if r.get('conflicted')]
    report=dict(scene_validity=dict(status='unverified',reason='Static RGB only; Blender scene not loaded'),
        energies=energies,observation_energy=observation,structural_energy=structure['energy'],
        structure=structure, evidence_coverage=len(valid)/len(rows) if rows else None,
        observation_status='unavailable' if observation is None else 'valid' if len(valid)==len(rows) else 'partial',
        evidence_counts=dict(expected=len(rows),eligible=len(active),valid=len(valid)),
        eligible_evidence_coverage=len(valid)/len(active) if active else None,
        uncertainty=dict(region_coverage=coverage('region'),region_pixel_coverage=float((region_union>0).mean()),
            anchor_coverage=len(known_ids)/len(known_anchors) if known_anchors else None,
            anchor_evidence_review_coverage=len(known_anchors)/len(evidence['anchors']) if evidence['anchors'] else None,
            structural_check_coverage=structure['check_coverage'],unknown_evidence=unknown,
            conflicting_evidence=conflicts,unreviewed_anchor_count=len(evidence['anchors'])-len(known_anchors)),
        error_diagnostics=diagnostics,metric_records=rows,reference_evidence=json_evidence(evidence),
        render_metadata=render_metadata,policy=POLICY,
        interpretation='Errors in [0,1], lower is better. Observation and 3D energies are conditional on available evidence. No ranking/total/confidence calibration.',
        human_annotation=human_annotation, calibration_status='not_calibrated')
    report['scene_validity'] = camera_check(render_metadata)
    report['uncertainty']['unknown_evidence'].append(dict(id='fixed_camera_contract',
                                                        reason=report['scene_validity']['reason']))
    return report, evidence


def write_report(out, report, input_rgb, render_rgb, evidence):
    out=Path(out)
    write_json(out/'report.json',report)
    saved_evidence = dict(report['reference_evidence'], mask_archive='reference_masks.npz')
    write_json(out/'reference_evidence.json',saved_evidence)
    masks={r['id']:area_mask(r,input_rgb.shape[:2]) for r in evidence['regions']+evidence['anchors']}
    np.savez_compressed(out/'reference_masks.npz',**masks)
    # Local standalone report with fixed-coordinate evidence overlays; no external JS/assets.
    images=[]
    for array in [input_rgb,render_rgb]:
        im=Image.fromarray(array).copy();draw=ImageDraw.Draw(im)
        for row in evidence['regions']+evidence['anchors']:
            if 'bbox' in row:
                draw.rectangle(row['bbox'],outline='yellow' if reliability(row) else 'orange',width=2)
                draw.text(tuple(row['bbox'][:2]),row['id'],fill='white',stroke_width=1,stroke_fill='black')
        images.append(im)
    width,height=images[0].size
    preview=Image.new('RGB',(width*2,height));preview.paste(images[0],(0,0));preview.paste(images[1],(width,0))
    preview.save(out/'comparison.png')
    def fmt(value):
        return 'N/A' if value is None else f'{value:.6f}'
    table=''.join(f"<tr><td>{name}</td><td>{fmt(item['value'])}</td><td>{item['status']}</td><td>{fmt(item['coverage'])}</td></tr>" for name,item in report['energies'].items())
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Project e evaluation</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:30px auto}img{max-width:100%}td,th{padding:8px;text-align:left}pre{white-space:pre-wrap}</style>'
        '<h1>Project e evaluation</h1><p>Reference left; render right. Yellow: reviewed geometry; orange: unreviewed candidates.</p>'
        '<img src="comparison.png"><table><tr><th>Energy</th><th>Error ↓</th><th>Status</th><th>Coverage</th></tr>'+table+'</table>'
        f"<p>Conditional E_observation: {fmt(report['observation_energy'])} ({report['observation_status']}); E_3D: {fmt(report['structural_energy'])}; evidence coverage: {fmt(report['evidence_coverage'])}</p>"
        '<p>Coverage = valid / all expected records, including unreviewed/unknown entries. Reliability weights measurements within an energy; fixed policy weights aggregate available energies.</p>'
        '<p>Provisional weights; unreviewed candidates are not GT. No calibrated verdict or final rank.</p>'
        '<p><a href="report.json">Complete diagnostics (JSON)</a></p><pre>'+html.escape(json.dumps(report['uncertainty'],ensure_ascii=False,indent=2))+'</pre>',encoding='utf-8')


def render_cpu(out, *, fixture=None, blend=None, reviewed=False, config=None, intrinsics=None, groups=None, rules=None):
    """Only built-in fixtures or explicitly human-reviewed static .blend. Never exec Agent Python."""
    if (fixture is None)==(blend is None):
        raise ValueError('Choose exactly one trusted fixture or reviewed static blend')
    if blend and not reviewed:
        raise PermissionError('Static blend rendering requires explicit human review (--reviewed-blend). Agent Python replay uses the existing per-step approval entry.')
    if fixture and fixture not in {'baseline','deleted','moved','color','distribution','penetration','billboard','ortho'}:
        raise ValueError('Unknown trusted fixture')
    config=deepcopy(config or RENDER)
    camera_pose(config['matrix_world'], require_fixed=True)
    if config['samples']!=8 or min(config['resolution'])<16 or max(config['resolution'])>1024:
        raise ValueError('CPU profile uses 8 samples and dimensions 16..1024')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT/'scripts'))
    from manual_cpu_render import launch
    from manual_reviewed_replay import LIMITS
    job=dict(output=str(out),render=config,fixture=fixture,blend=str(Path(blend).resolve()) if blend else None,
             intrinsics=intrinsics,groups=groups or [],rules=rules or {})
    write_json(out/'job.json',job)
    # Share the serial lock with prior supervised replays even if old runs were removed.
    (ROOT/'runs').mkdir(exist_ok=True)
    with (ROOT/'runs/.manual_reviewed_replay.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        result=launch(out,out,ROOT/'e_harness/runtime/benchmark_blender.py',out/'job.json',label='benchmark')
    result['success']=(result['success'] and result['cleanup_complete'] and
                       (out/'result.json').exists() and (out/'render.png').exists())
    if not result['success'] and not result.get('error'):
        result['error']='Missing expected render/result artifact or incomplete cleanup'
    result['scene_validity'] = 'valid' if result['success'] else 'invalid'
    write_json(out/'launch.json',result)
    return result


def gpu_available(uuid):
    """Conservative repeated observation. No claim of hard device isolation."""
    if os.environ.get('CUDA_VISIBLE_DEVICES') != uuid:
        raise ValueError('Set CUDA_VISIBLE_DEVICES to the single explicitly selected UUID before launch')
    for sample in range(3):
        command=['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits']
        rows=subprocess.run(command,check=True,capture_output=True,text=True,timeout=5).stdout.splitlines()
        selected=[r for r in rows if r.split(',')[0].strip()==uuid]
        processes=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],check=True,capture_output=True,text=True,timeout=5).stdout
        if len(selected)!=1 or [v.strip() for v in selected[0].split(',')[1:]]!=['0','0'] or uuid in processes:
            raise RuntimeError('Selected GPU is occupied or cannot be verified idle')
        if sample<2:
            time.sleep(2)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    off=sub.add_parser('offline',help='Auditable manifest replay; no models, APIs or Blender')
    off.add_argument('--manifest',type=Path,required=True)
    off.add_argument('--output',type=Path,required=True)
    ev=sub.add_parser('evaluate',help='Compare existing RGBs; no Blender or API execution')
    ev.add_argument('--input',type=Path,required=True);ev.add_argument('--render',type=Path,required=True)
    ev.add_argument('--reference',type=Path);ev.add_argument('--candidate-reference',type=Path)
    for key in ['render-evidence','geometry','triage','rules','render-metadata','human-annotation']:
        ev.add_argument('--'+key,type=Path)
    ev.add_argument('--dino-model',type=Path);ev.add_argument('--gpu-uuid')
    ev.add_argument('--output',type=Path,required=True)
    re=sub.add_parser('render',help='Render trusted fixture or explicitly reviewed static scene')
    source=re.add_mutually_exclusive_group(required=True)
    source.add_argument('--fixture',choices=['baseline','deleted','moved','color','distribution','penetration','billboard','ortho'])
    source.add_argument('--blend',type=Path)
    re.add_argument('--reviewed-blend',action='store_true')
    for key in ['camera','intrinsics','groups','rules']:
        re.add_argument('--'+key,type=Path)
    re.add_argument('--output',type=Path,required=True)
    pilot=sub.add_parser('pilot',help='Read one existing contrast24 pilot; no model/Blender execution')
    pilot.add_argument('--scene',choices=['C1_02_A','R1_05','C1_01_B'],required=True)
    pilot.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.output.exists():
        p.error('Output already exists; choose a new result directory')
    if args.action=='offline':
        from .benchmark_offline import run_manifest
        report = run_manifest(args.manifest,args.output)
        print(json.dumps(dict(report=str(args.output/'report.json'),
                              camera_protocol=report['scene_validity']['camera_protocol'],
                              formal_eligible=False,usage=report['usage']),indent=2))
        return 0
    if args.action=='render':
        result=render_cpu(args.output,fixture=args.fixture,blend=args.blend,reviewed=args.reviewed_blend,
                          config=read_json(args.camera),intrinsics=read_json(args.intrinsics),
                          groups=(read_json(args.groups) or {}).get('groups'),rules=read_json(args.rules))
        print(json.dumps(result,indent=2));return 0 if result['success'] else 1
    model_status=None
    if args.action=='pilot':
        scene=args.scene
        base=SCENE_BENCHMARK/'results/contrast24_evidence_pilot_debug'
        renderdir=SCENE_BENCHMARK/'results/contrast24_evaluation_debug/scenes'/scene
        paths=list((ROOT/'datasets/contrast24/images').glob(scene+'.*'))
        if len(paths)!=1:
            raise ValueError('Expected one preserved dataset RGB')
        a,b=rgb(paths[0]),rgb(renderdir/'render.png')
        ref=candidate_reference(base/'scenes'/scene/'candidate_objects.json')
        geometry=read_json(renderdir/'geometry.json')
        legacy=read_json(base/'geometry_witness_classification.json')
        triage=dict(source=str(base/'geometry_witness_classification.json'),reviewed=legacy['reviewed'],
            legacy_records=[r for r in legacy['records'] if r['scene_id']==scene])
        report,evidence=evaluate(a,b,ref,geometry=geometry,triage=triage,
                                render_metadata=read_json(renderdir/'export_metadata.json'))
        report['provenance']=dict(input=str(paths[0]),render=str(renderdir/'render.png'),
            use='Historical static pipeline debug only; source camera was not the new benchmark T0',
            candidates='Review status unchanged; no semantic/structural accuracy claim')
    else:
        if args.reference and args.candidate_reference:
            p.error('Choose --reference or --candidate-reference')
        if args.gpu_uuid and not args.dino_model:
            p.error('--gpu-uuid requires --dino-model')
        a,b=rgb(args.input),rgb(args.render)
        ref=candidate_reference(args.candidate_reference) if args.candidate_reference else load_document(args.reference) if args.reference else None
        extract=None
        if args.dino_model:
            try:
                if args.gpu_uuid:
                    gpu_available(args.gpu_uuid)
                import torch
                torch.set_num_threads(2)
                extract=local_dino_extractor(args.dino_model,device='cuda:0' if args.gpu_uuid else 'cpu',preserve_frame=True)
                model_status=dict(status='available',device='cuda:0' if args.gpu_uuid else 'cpu',source=str(args.dino_model))
            except Exception as exc:
                model_status=dict(status='unavailable',reason=f'{type(exc).__name__}: {exc}')
        report,evidence=evaluate(a,b,ref,load_document(args.render_evidence) if args.render_evidence else None,
            geometry=read_json(args.geometry),triage=read_json(args.triage),rules=read_json(args.rules),
            extract=extract,render_metadata=read_json(args.render_metadata),human_annotation=read_json(args.human_annotation))
        report['provenance']=dict(input=str(args.input.resolve()),render=str(args.render.resolve()),dino=model_status,
                                  api_calls=0,agent_python_executed=False)
    args.output.mkdir(parents=True,exist_ok=False)
    write_report(args.output,report,a,b,evidence)
    print(json.dumps(dict(report=str(args.output/'report.html'),energies=report['energies'],
                          observation_energy=report['observation_energy'],structural_energy=report['structural_energy']),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
