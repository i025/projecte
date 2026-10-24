"""Serial CPU end-to-end controls using built-in, source-reviewed primitives only."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from e_harness.benchmark import evaluate, render_cpu, write_report
from e_harness.benchmark_config import FIXED_T0, write_json
from e_harness.benchmark_evidence import local_dino_extractor, rgb


def annotations(folder):
    """Explicit synthetic oracle, not an automatic real-image detector or name-based GT."""
    meta=json.loads((folder/'export_metadata.json').read_text())
    labels={'anchor':'red_cuboid','other':'blue_cube'}
    rows=[]
    for key,label in labels.items():
        path=folder/'render_masks'/f'{key}.png'
        if not path.exists():
            continue
        mask=np.asarray(Image.open(path).convert('L'))>0
        y,x=np.nonzero(mask)
        if len(x):
            rows.append(dict(id=key,category=label,bbox=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],
                reviewed=True,reliability=1.,importance=1.,source='Known source-controlled synthetic fixture oracle'))
    return dict(anchors=rows,reviewed=True,inventory_complete=True,image_size=meta['image_size'])


def groups(variant):
    names=['floor','other']+['repeat_'+str(i) for i in range(6)]
    if variant!='deleted':names.append('anchor')
    return [dict(unit_id=n,scene_ids=[n],reviewed=True,source='Known synthetic primitive identity') for n in names]


def controlled_panels():
    """Small raster oracles: exact repeated-element masks, no detector or Agent code."""
    from copy import deepcopy
    side = 160
    spread = [(x,y) for y in [56,96,136] for x in [24,72,120]]
    anchor_boxes = {'a':[8,8,20,20], 'b':[132,8,144,20]}

    def panel(positions=spread, color=(210,60,30), shift=0, deleted=False):
        image = np.zeros((side,side,3),np.uint8)
        occupancy = np.zeros((side,side),float)
        for x,y in positions:
            image[y:y+8,x:x+8] = color
            occupancy[y:y+8,x:x+8] = 1.
        boxes = {k:list(v) for k,v in anchor_boxes.items()}
        boxes['a'] = [8+shift,8,20+shift,20]
        if deleted:
            del boxes['a']
        for key,box in boxes.items():
            x0,y0,x1,y1 = box
            image[y0:y1,x0:x1] = color if key=='a' else (30,60,210)
        observed = dict(reviewed=True,inventory_complete=True,
            anchors=[dict(id=k,category='cube' if k=='a' else 'sphere',bbox=v,
                importance=1.,reliability=1.,reviewed=True,source='Trusted synthetic raster oracle')
                for k,v in boxes.items()],
            regions=[dict(id='repeats',bbox=[0,0,side,side],reviewed=True,
                element_occupancy=occupancy,occupancy_reviewed=True)])
        return image,observed

    def reference(observed):
        return dict(anchors=deepcopy(observed['anchors']),regions=[dict(observed['regions'][0],
            description='Known repeated squares; occupancy excludes salient anchors',
            metrics=['spatial','appearance','statistical','perceptual'])])

    base,inventory = panel()
    ref = reference(inventory)
    color,color_inventory = panel(color=(60,210,30))  # equal arithmetic grayscale
    bright,bright_inventory = panel(color=(250,130,100))
    moved,moved_inventory = panel(shift=32)
    deleted,deleted_inventory = panel(deleted=True)
    band_positions = [(x,y) for y in [48,64,80] for x in [32,80,128]]
    band,band_inventory = panel(band_positions)
    band_ref = reference(band_inventory)
    no_sem = deepcopy(ref); no_sem['anchors'] = []
    baselines = {
        'standard': (base,base,ref,inventory),
        'band': (band,band,band_ref,band_inventory),
        'color_error': (base,bright,ref,bright_inventory),
        'moved_error': (base,moved,ref,moved_inventory),
        'deleted_error': (base,deleted,ref,deleted_inventory),
        'no_semantics': (base,base,no_sem,dict(inventory,anchors=[])),
    }
    cases = {}
    def add(name, baseline, rendered, observed, reference_override=None, **meta):
        a,_,r,_ = baselines[baseline]
        cases[name] = dict(baseline=baseline,input=a,render=rendered,
            reference=deepcopy(reference_override if reference_override is not None else r),
            observed=deepcopy(observed),**meta)
    add('self','standard',base,inventory)
    add('delete_anchor','standard',deleted,deleted_inventory)
    for fraction in [.05,.10,.20,.40]:
        image,observed = panel(shift=round(side*fraction))
        add(f'move_{round(fraction*100):02d}','standard',image,observed,shift_fraction=fraction)
    image,observed = panel([(x,y) for y in [56,96,136] for x in [8,56,104]])
    add('same_count_arrangement','standard',image,observed,elements=9,element_pixels=576)
    image,observed = panel([(x,y) for y in [80,96,112] for x in [56,72,88]])
    add('clustering','standard',image,observed,elements=9,element_pixels=576)
    add('color_equal_gray','standard',color,color_inventory)
    add('color_luminance','standard',bright,bright_inventory)
    image,observed = panel([(x,y) for y in [112,128,144] for x in [32,80,128]])
    add('coverage_preserved_rearrangement','band',image,observed,elements=9,element_pixels=576)
    candidates = deepcopy(ref)
    candidates['anchors'].append(dict(id='unreviewed',category='unknown',bbox=[64,24,76,36],
        importance=50.,reliability=0.,reviewed=False))
    add('add_q_zero','color_error',bright,bright_inventory,candidates)
    important = deepcopy(ref); important['anchors'][0]['importance'] = 8.
    add('increase_importance','moved_error',moved,moved_inventory,important)
    add('increase_missing_importance','deleted_error',deleted,deleted_inventory,important)
    add('dino_without_semantics','no_semantics',color,dict(color_inventory,anchors=[]),no_sem)
    add('missing_perceptual','standard',base,inventory,disable_features=True)
    return baselines,cases


def validate_metrics(root, extract, before_path=None):
    """Same pixels/evidence before/after, plus deltas relative to each case's baseline."""
    import csv
    import html
    import importlib.util
    import types
    from e_harness.benchmark import json_evidence
    from e_harness.benchmark_config import ENERGIES
    from e_harness.benchmark_evidence import build_reference
    from e_harness.benchmark_metrics import compare

    old = None
    old_evidence = None
    if before_path:
        # Audited repository source snapshots, only in this offline experiment runner.
        # This is not a production evaluator registry or an Agent execution entry.
        import importlib
        package = types.ModuleType('_project_e_before')
        package.__path__ = [str(before_path.resolve().parent)]
        sys.modules[package.__name__] = package
        old = importlib.import_module('_project_e_before.benchmark_metrics')
        old_evidence = importlib.import_module('_project_e_before.benchmark_evidence')

    baselines,cases = controlled_panels()
    def measure(a,b,ref,observed,features):
        after,evidence = evaluate(a,b,ref,observed,extract=features)
        result = dict(after=dict(energies={k:r['value'] for k,r in after['energies'].items()},
            observation_energy=after['observation_energy'],coverage=after['evidence_coverage'],
            counts=after['evidence_counts'],report=after))
        if old:
            prior = old_evidence.build_reference(a,ref)
            records,diagnostics = old.compare(a,b,prior,observed,extract=features)
            scores,observation = old.aggregate(records)
            eligible = [r for r in records if r['q']>0]
            valid = [r for r in eligible if r['value'] is not None]
            result['before'] = dict(energies={k:r['value'] for k,r in scores.items()},
                observation_energy=observation,coverage=len(valid)/len(eligible) if eligible else None,
                counts=dict(expected=len(records),eligible=len(eligible),valid=len(valid)),
                report=dict(energies=scores,metric_records=records,error_diagnostics=diagnostics))
        return result,evidence

    def persist(folder,a,b,ref,observed,result,evidence):
        folder.mkdir()
        Image.fromarray(a).save(folder/'input.png')
        Image.fromarray(b).save(folder/'render.png')
        write_json(folder/'reference.json',json_evidence(ref))
        write_json(folder/'render_evidence.json',json_evidence(observed))
        write_report(folder,result['after']['report'],a,b,evidence)
        if 'before' in result:
            write_json(folder/'before.json',result['before']['report'])

    measured_baselines = {}
    for name,(a,b,ref,observed) in baselines.items():
        result,evidence = measure(a,b,ref,observed,extract)
        persist(root/('baseline_'+name),a,b,ref,observed,result,evidence)
        measured_baselines[name] = result
    output = {}
    for name,case in cases.items():
        features = None if case.get('disable_features') else extract
        result,evidence = measure(case['input'],case['render'],case['reference'],case['observed'],features)
        baseline = measured_baselines[case['baseline']]
        compact = dict(baseline=case['baseline'])
        for stage,measurement in result.items():
            first = baseline[stage]
            compact[stage] = {k:v for k,v in measurement.items() if k!='report'}
            compact[stage]['delta_energies'] = {
                k:measurement['energies'][k]-first['energies'][k]
                if measurement['energies'][k] is not None and first['energies'][k] is not None else None
                for k in ENERGIES}
            compact[stage]['delta_observation'] = measurement['observation_energy']-first['observation_energy']
            compact[stage]['delta_coverage'] = measurement['coverage']-first['coverage']
        compact['control'] = {k:v for k,v in case.items() if k in {'elements','element_pixels','shift_fraction'}}
        if 'elements' in compact['control']:
            ra = baselines[case['baseline']][2]['regions'][0]['element_occupancy']
            rb = case['observed']['regions'][0]['element_occupancy']
            compact['control']['baseline_occupancy_pixels'] = float(ra.sum())
            compact['control']['render_occupancy_pixels'] = float(rb.sum())
        output[name] = compact
        persist(root/name,case['input'],case['render'],case['reference'],case['observed'],result,evidence)

    def value(name,energy):return output[name]['after']['energies'][energy]
    shifts = [value('move_'+str(n).zfill(2),'spatial') for n in [5,10,20,40]]
    checks = dict(self_zero=all(v is None or abs(v)<1e-6 for v in output['self']['after']['energies'].values()),
        deletion_semantic=value('delete_anchor','semantic')>0,
        color_semantic_zero=all(value(n,'semantic')==0 for n in ['color_equal_gray','color_luminance']),
        distribution_responds=all(output[n]['after']['delta_energies']['statistical']>0 for n in
            ['same_count_arrangement','clustering','coverage_preserved_rearrangement']),
        coverage_preserved=all(output[n]['control']['baseline_occupancy_pixels']==output[n]['control']['render_occupancy_pixels']
            for n in ['same_count_arrangement','clustering','coverage_preserved_rearrangement']),
        q_zero_invariant=all(
            (value('add_q_zero',k) is None and measured_baselines['color_error']['after']['energies'][k] is None) or
            (output['add_q_zero']['after']['delta_energies'][k] is not None and
             abs(output['add_q_zero']['after']['delta_energies'][k])<1e-12) for k in ENERGIES) and
            abs(output['add_q_zero']['after']['delta_observation'])<1e-12,
        q_zero_coverage_visible=output['add_q_zero']['after']['delta_coverage']<0,
        importance_spatial=output['increase_importance']['after']['delta_energies']['spatial']>0,
        importance_appearance=output['increase_importance']['after']['delta_energies']['appearance']>0,
        importance_semantic=output['increase_missing_importance']['after']['delta_energies']['semantic']>0,
        missing_evidence_na=value('missing_perceptual','perceptual') is None,
        spatial_strength_nondecreasing=all(a<=b+1e-12 for a,b in zip(shifts,shifts[1:])))
    if extract:
        checks.update(dino_without_semantics=(value('dino_without_semantics','semantic') is None and
            value('dino_without_semantics','perceptual') is not None),
            missing_evidence_coverage=output['missing_perceptual']['after']['delta_coverage']<0,
            importance_perceptual=output['increase_importance']['after']['delta_energies']['perceptual']>0)
    summary = dict(success=all(checks.values()),checks=checks,cases=output,
        baselines={name:{stage:{k:v for k,v in data.items() if k!='report'} for stage,data in item.items()}
            for name,item in measured_baselines.items()},
        actual_dino_cpu=bool(extract),api_calls=0,gpu_used=False,blender_used=False,
        before_source=str(before_path) if before_path else None,
        coverage_definition=dict(before='valid / q-positive planned records',after='valid / all expected records; q-zero retained'),
        skipped=['GPU: not used','Real VLM/API: not authorized or invoked','Real Agent replay: not executed']+
                ([] if extract else ['DINO not requested; feature-dependent checks skipped, Perceptual N/A']))
    with (root/'response_matrix.csv').open('w',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['case','baseline','stage',*ENERGIES,'observation','coverage',
                         *['delta_'+k for k in ENERGIES],'delta_observation','delta_coverage'])
        for name,item in output.items():
            for stage in ['before','after']:
                if stage in item:
                    d=item[stage]
                    writer.writerow([name,item['baseline'],stage,*[d['energies'][k] for k in ENERGIES],
                        d['observation_energy'],d['coverage'],*[d['delta_energies'][k] for k in ENERGIES],
                        d['delta_observation'],d['delta_coverage']])
    def fmt(v):return 'N/A' if v is None else f'{v:.6f}'
    headers = ''.join('<th>'+x+'</th>' for x in ['Case','Baseline','Stage',*['Δ '+k for k in ENERGIES],'Δ observation','Δ coverage'])
    rows = ''
    for name,item in output.items():
        for stage in ['before','after']:
            if stage in item:
                d=item[stage]
                rows += '<tr><td><a href="'+name+'/report.html">'+name+'</a></td><td>'+item['baseline']+'</td><td>'+stage+'</td>'+''.join(
                    '<td>'+fmt(x)+'</td>' for x in [*[d['delta_energies'][k] for k in ENERGIES],d['delta_observation'],d['delta_coverage']])+'</tr>'
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Project e metric validity</title>'
        '<style>body{font:14px system-ui;margin:24px}td,th{padding:7px;text-align:right}tr:nth-child(even){background:#eee}</style>'
        '<h1>Metric corrections: actual paired CPU experiments</h1>'
        '<p>Every delta uses its explicitly named baseline. Before and after use identical RGB/annotations and the same existing DINO weights.</p>'
        '<p>Coverage denominator changed; do not interpret its before/after difference as a quality improvement. N/A is never converted to zero.</p>'
        '<p>Repeated-element occupancy is a known synthetic oracle. Real-image gradients remain an edge-distribution proxy.</p>'
        '<p><a href="summary.json">Absolute values, baselines and all deltas</a> · <a href="response_matrix.csv">Complete CSV</a></p>'
        '<table><tr>'+headers+'</tr>'+rows+'</table>',encoding='utf-8')
    return summary


def validate_missing(root):
    """Tiny raster oracles, including per-object review; no model or Blender."""
    from copy import deepcopy
    from PIL import ImageDraw
    if (root/'missing_tests.json').exists():
        raise FileExistsError('Preserve prior missing-evidence results')
    image=np.zeros((48,64,3),np.uint8);image[8:20,8:20]=[200,60,20]
    item=dict(id='a',category='square',bbox=[8,8,20,20],importance=1.,reviewed=True,
              reliability=1.,source='Known visible raster fixture')
    reference=dict(anchors=[item])
    def verdict(status,**extra):
        return dict(status=status,reviewed=True,reliability=1.,verification_type='synthetic_oracle',
                    evidence_scope='input_view',source='Known visible raster fixture',**extra)
    cases={}
    def add(name,rendered,observed,ref=None,original=None):
        report,_=evaluate(image if original is None else original,rendered,reference if ref is None else ref,observed)
        cases[name]=dict(states={m['reference_id']:m['verification_status'] for m in report['error_diagnostics']['anchor_matching']},
            extras=report['error_diagnostics']['extra_anchors'],inventory=report['error_diagnostics']['inventory'],
            energies={k:v['value'] for k,v in report['energies'].items()},observation=report['observation_energy'],
            coverage=report['evidence_coverage'],metric_records=report['metric_records'])
        return cases[name]
    present=add('matched',image,dict(anchors=[item]))
    moved=np.zeros_like(image);moved[28:40,44:56]=[200,60,20]
    add('misplaced',moved,dict(anchors=[dict(item,bbox=[44,28,56,40])]))
    im=Image.fromarray(np.zeros_like(image));ImageDraw.Draw(im).polygon([(8,19),(14,8),(19,19)],fill=(200,60,20))
    add('semantic_mismatch',np.array(im),dict(anchors=[dict(item,category='triangle')]))
    add('confirmed_missing_oracle',np.zeros_like(image),dict(anchors=[],reviewed=True,inventory_complete=True))
    add('detector_false_negative',image,dict(anchors=[]))
    human=verdict('confirmed_missing',reference_id='a');human['verification_type']='human'
    add('single_anchor_human_absence',np.zeros_like(image),dict(anchors=[],anchor_verdicts=[human]))
    extra=dict(item,id='extra',bbox=[40,8,52,20]);more=image.copy();more[8:20,40:52]=[200,60,20]
    add('confirmed_extra',more,dict(anchors=[item,extra],anchor_verdicts=[verdict('confirmed_extra',rendered_id='extra')]))
    add('unknown_extra',more,dict(anchors=[item,extra]))
    green=np.zeros_like(image);green[24:]=[20,180,20]
    gray=green.copy();gray[24:]=[110,110,110]
    region=dict(id='grass',category='grass',bbox=[0,24,64,48],reviewed=True,presence_evidence=True,
                metrics=['semantic','appearance','perceptual'])
    add('region_content_replaced',gray,dict(regions=[dict(id='grass',reviewed=True,occupancy_reviewed=True,
        occupancy_category='grass',element_occupancy=np.zeros((48,64)))]),dict(regions=[region]),green)
    add('region_detector_failed',gray,dict(regions=[]),dict(regions=[region]),green)
    changed=image.copy();changed[8:20,8:20]=[20,150,200]
    base=add('color_error_baseline',changed,dict(anchors=[item]))
    qzero=deepcopy(reference);qzero['anchors'].append(dict(item,id='pending',reviewed=False,reliability=0.,importance=50.))
    after=add('add_q_zero',changed,dict(anchors=[item]),qzero)
    checks=dict(matched=present['states']['a']=='matched',misplaced=cases['misplaced']['states']['a']=='misplaced',
        semantic_mismatch=cases['semantic_mismatch']['states']['a']=='semantic_mismatch',
        confirmed_missing=cases['confirmed_missing_oracle']['states']['a']=='confirmed_missing',
        false_negative_unknown=cases['detector_false_negative']['states']['a']=='unknown',
        single_absence=cases['single_anchor_human_absence']['states']['a']=='confirmed_missing' and not cases['single_anchor_human_absence']['inventory']['complete'],
        confirmed_extra=cases['confirmed_extra']['extras']==['extra'],unknown_extra=cases['unknown_extra']['extras']==[],
        region_visual_response=all(cases[n]['energies']['appearance']>0 for n in ['region_content_replaced','region_detector_failed']),
        region_missing_requires_verified_occupancy=cases['region_content_replaced']['energies']['semantic']==1. and cases['region_detector_failed']['energies']['semantic'] is None,
        q_zero_invariant=base['energies']==after['energies'] and base['observation']==after['observation'],
        q_zero_coverage=after['coverage']<base['coverage'],no_instance_mask_needed=all('mask' not in a for a in reference['anchors']))
    for name in ['confirmed_missing_oracle','single_anchor_human_absence']:
        checks[name+'_not_tripled']=all(r['value'] is None for r in cases[name]['metric_records']
            if r['level']=='anchor' and r['energy'] in {'spatial','appearance','perceptual'})
    result=dict(success=all(checks.values()),checks=checks,cases=cases,api_calls=0,gpu_used=False,blender_used=False,
                note='Synthetic raster oracle only; Perceptual N/A without local DINO. These are not bw_9064 reconstruction scores.')
    write_json(root/'missing_tests.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dino-model',type=Path,help='Optional existing local DINO; CPU only, never downloads')
    p.add_argument('--validate-metrics', action='store_true', help='Paired raster controls without Blender')
    p.add_argument('--validate-missing', action='store_true', help='Verified absence/Unknown raster controls without Blender/models')
    p.add_argument('--before-metrics', type=Path, help='Audited pre-change metric source beside evidence/config snapshots')
    args=p.parse_args()
    if args.validate_metrics and args.validate_missing:
        p.error('Choose one CPU validation suite')
    if args.before_metrics and not args.validate_metrics:
        p.error('--before-metrics requires --validate-metrics')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
    started=time.monotonic()
    summary=dict(success=False,checks={},variants={},api_calls=0,gpu_used=False,
                 scope='Synthetic pipeline/perturbation checks; not calibrated reconstruction accuracy',
                 skipped=['GPU unavailable/not requested','Live VLM: no authorized verified model','Real Agent replay: human approval required'])
    try:
        if args.validate_missing:
            summary=validate_missing(root)
            print(json.dumps(dict(success=summary['success'],checks=summary['checks']),indent=2))
            return 0 if summary['success'] else 1
        extract=None
        if args.dino_model:
            import torch
            torch.set_num_threads(2)
            extract=local_dino_extractor(args.dino_model,'cpu',preserve_frame=True)
        if args.validate_metrics:
            summary=validate_metrics(root,extract,args.before_metrics)
            summary['seconds']=round(time.monotonic()-started,3)
            write_json(root/'summary.json',summary)
            print(json.dumps(dict(success=summary['success'],checks=summary['checks'],seconds=summary['seconds']),indent=2))
            return 0 if summary['success'] else 1
        rules=dict(up_axis='+Z',support_receivers_complete=True,
            support=[dict(unit_id='anchor',expected=True,receivers=['floor'],reviewed=True,attachment_known_absent=True)],
            degeneration=[dict(unit_id='anchor',components=['anchor'],reviewed=True,must_enclose_volume=True)])
        for variant in ['baseline','deleted','moved','color','distribution','penetration','billboard','ortho']:
            if time.monotonic()-started>300:
                raise TimeoutError('Smoke total wall time budget exceeded')
            folder=root/variant
            launch=render_cpu(folder,fixture=variant,groups=groups(variant),rules=rules)
            if not launch['success'] or not launch['cleanup_complete']:
                raise RuntimeError(f'{variant} render failed: {launch}')
            meta=json.loads((folder/'export_metadata.json').read_text())
            summary['checks'][variant+'_fixed_T0']=bool(np.allclose(meta['camera']['matrix_world'],FIXED_T0,atol=1e-6))
            summary['checks'][variant+'_intrinsics']=bool(abs(meta['camera']['lens_mm']-42)<1e-6 and abs(meta['camera']['shift_x']-.05)<1e-6)
            depth=np.load(folder/'depth_camera_z.npy',allow_pickle=False)
            ids=np.load(folder/'component_id.npy',allow_pickle=False)
            normals=np.load(folder/'normal_world.npy',allow_pickle=False)
            h,w=meta['image_size'][::-1]
            summary['checks'][variant+'_data_passes']=(depth.shape==ids.shape==(h,w) and
                normals.shape==(h,w,3) and bool(np.isfinite(normals).all()) and
                bool((ids>0).any()) and bool(np.isfinite(depth[ids>0]).all()) and
                bool((depth[ids>0]>0).all()))
            summary['checks'][variant+'_reprojection']=meta['position_reprojection_max_error_pixels']<.05
            if variant=='ortho':
                summary['checks']['ortho_projection']=meta['intrinsics_pixels'] is None and abs(meta['ortho_scale']-7)<1e-6
                continue
            observed=annotations(folder)
            if variant=='baseline':
                reference=annotations(folder)
                reference.update(regions=[dict(id='whole_texture',bbox=[0,0,*meta['image_size']],
                    description='Whole reference image texture/appearance',metrics=['appearance','spatial','statistical','perceptual'],
                    reviewed=True,reliability=1.)],
                    verification_questions=[dict(id='visible_material',energy='appearance',
                        question='Does visible surface material differ?',reviewed=True,reliability=1.)])
                write_json(root/'reference.json',reference)
                reference_rgb=rgb(folder/'render.png')
            geometry=json.loads((folder/'geometry.json').read_text())
            # Only the known independent synthetic pair is semantically judged.
            # This is not a triage promotion of any historical experiment.
            pair=next((r for r in geometry['collisions'] if set(r['unit_ids'])=={'anchor','other'}),None)
            triage=dict(pairs=[dict(unit_ids=['anchor','other'],reviewed=True,
                classification='implausible_penetration' if pair['status']=='penetration' else 'independent_objects',
                reason='Controlled independent synthetic cubes')] if pair else [])
            report,evidence=evaluate(reference_rgb,rgb(folder/'render.png'),reference,observed,
                geometry=geometry,triage=triage,rules=rules,extract=extract,render_metadata=meta)
            report['provenance']=dict(synthetic_oracle=True,reference_frozen_from_baseline=True,api_calls=0)
            summary['checks'][variant+'_vlm_unavailable']=any(r['id']=='visible_material' and r['value'] is None
                                                           for r in report['metric_records'])
            write_report(folder,report,reference_rgb,rgb(folder/'render.png'),evidence)
            write_json(folder/'render_evidence.json',observed)
            write_json(folder/'triage.json',triage)
            write_json(folder/'rules.json',rules)
            summary['variants'][variant]=dict(energies={k:r['value'] for k,r in report['energies'].items()},
                observation_energy=report['observation_energy'],structural_energy=report['structural_energy'],
                structural_energies={k:r['value'] for k,r in report['structure']['energies'].items()},
                evidence_coverage=report['evidence_coverage'],report=str(folder/'report.html'),
                peak_rss_bytes=launch['peak_rss_bytes'],render_seconds=launch['seconds'])
        baseline=summary['variants']['baseline']
        def increased(variant,energy):
            return summary['variants'][variant]['energies'][energy]>baseline['energies'][energy]+1e-8
        for item in summary['variants'].values():
            item['delta_energies']={k:v-baseline['energies'][k] if v is not None and baseline['energies'][k] is not None else None
                for k,v in item['energies'].items()}
            item['delta_observation']=item['observation_energy']-baseline['observation_energy']
        summary['checks']['color_preserves_anchor_semantics']=summary['variants']['color']['energies']['semantic']==baseline['energies']['semantic']
        summary['checks'].update(identity_zero=abs(baseline['observation_energy'])<1e-6,
            deletion_semantic=increased('deleted','semantic'),movement_spatial=increased('moved','spatial'),
            color_appearance=increased('color','appearance'),distribution_statistics=increased('distribution','statistical'),
            penetration_detected=summary['variants']['penetration']['structural_energies']['penetration']==1.,
            billboard_detected=summary['variants']['billboard']['structural_energies']['degeneration']==1.,
            vlm_unavailable_safe=all(summary['checks'][v+'_vlm_unavailable'] for v in summary['variants']))
        if extract:
            summary['checks']['five_energies_numeric']=all(all(v is not None for v in row['energies'].values()) for row in summary['variants'].values())
            summary['checks']['dino_responds_to_deletion']=increased('deleted','perceptual')
        else:
            summary['skipped'].append('DINO not requested; Perceptual stays N/A')
        rejected=render_cpu(root/'invalid_intrinsics',fixture='baseline',intrinsics=dict(type='PERSP',lens=0.))
        summary['checks']['illegal_intrinsics_rejected']=(not rejected['success'] and rejected['cleanup_complete']
            and rejected['scene_validity']=='invalid' and not (root/'invalid_intrinsics/render.png').exists())
        summary['expected_failure']=rejected
        summary['success']=all(summary['checks'].values())
    except Exception as exc:
        summary['error']=f'{type(exc).__name__}: {exc}'
    summary['seconds']=round(time.monotonic()-started,3)
    write_json(root/'summary.json',summary)
    print(json.dumps(summary,indent=2))
    return 0 if summary['success'] else 1


if __name__=='__main__':raise SystemExit(main())
