"""Bounded real-image batch controller. Generated Python is data, never host-executed.

Reuse the existing planner, CLI adapter, evaluator and policy. An unqualified
execution environment stops only execution-dependent stages, not the batch.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import ast
import csv
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

from .benchmark_config import ENERGIES, FIXED_T0, POLICY, ROOT
from .benchmark_evidence import build_reference, local_dino_extractor
from .benchmark_structure import structural_report
from .verification_adapter import answer_packet, codex_answer, compare_answers, contract, parse_answer
from scripts.reference_vlm_pilot import (evidence_from_plan, obj, planning_protocol,
                                        verification_protocol, LEGACY_PROTOCOL)


def save(path, value, *, exclusive=False):
    path=Path(path)
    if exclusive:
        with path.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
    else:
        temporary=path.with_suffix(path.suffix+'.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
        temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def agent_protocol(config):
    """Only RGB and a common task; no Reference claims, answers or scene vocabulary."""
    return contract(dict(
        system='You reconstruct an editable 3D Blender scene from one RGB image. Return JSON only.',
        user='Create self-contained Blender 4.2 Python using bpy, math and mathutils only. '
        'Build actual 3D geometry, materials, lights and an active camera to reproduce the visible scene. '
        'No external assets, downloads, textures from the input image, filesystem/network access, '
        'subprocesses, handlers, rendering or saving files. The harness performs rendering and export. '
        'Start with an empty scene. Use distinct queryable objects and meaningful names; do not enumerate '
        'invisible objects. Choose world geometry to fit this prescribed camera-to-world T0 (Z-up; '
        'camera local -Z forward, +Y up): '+json.dumps(config['camera_matrix'])+'. '
        'The harness will enforce exactly this T0 after construction; do not move the camera to fit the scene. '
        'You may choose perspective or orthographic intrinsics: lens 1..300 mm for PERSP, positive '
        'ortho_scale for ORTHO, positive sensor dimensions, abs(shift_x/y)<=2, 0<clip_start<clip_end. '
        'Render resolution follows the input aspect ratio with longest edge '+str(config['max_edge'])+
        ' pixels, CPU Cycles 8 samples, 2 threads. One generation, no repair or render feedback. '
        'Return only {"blender_python":"complete Python source"}, without Markdown or explanation.',
        schema=obj(dict(blender_python=dict(type='string',minLength=20,maxLength=100000)))))


def planning_options(config):
    """Explicit opt-in for new runs; missing config preserves frozen v0.1 replay."""
    settings=config.get('planning',dict(protocol_version=LEGACY_PROTOCOL))
    if not isinstance(settings,dict) or not set(settings) <= {'protocol_version','evidence_budget'} or 'protocol_version' not in settings:
        raise ValueError('planning requires protocol_version and optional evidence_budget only')
    planning_protocol(**settings)  # reject typos/bad budgets before any call or output
    return deepcopy(settings)


def load_config(path):
    # JSON is a YAML subset: no extra YAML parser or executable configuration.
    config=read(path)
    planning_options(config)
    if config['camera_matrix']!=FIXED_T0 or config['policy']!=json.loads(json.dumps(POLICY)):
        raise ValueError('Batch must preserve the existing T0 and Energy policy')
    agent=config['agent']
    if (set(agent)!={'backend','model','generations','repairs','feedback','timeout_seconds'} or
            agent['backend']!='codex_cli' or agent['generations']!=1 or agent['repairs']!=0 or
            agent['feedback']!='none' or not 0<agent['timeout_seconds']<=300 or
            not isinstance(agent['model'],str) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,99}',agent['model'])):
        raise ValueError('v0.1 uses one bounded CLI generation without feedback/retry')
    if config['max_calls_per_scene']!=4 or not 64<=config['max_edge']<=1024:
        raise ValueError('Invalid frozen image/call budget')
    samples=config['samples']; ids=[r['id'] for r in samples]
    if not samples or len(samples)>8 or len(set(ids))!=len(ids) or any(
            not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}',v) for v in ids):
        raise ValueError('Require 1..8 unique safe sample IDs')
    for row in samples:
        if not row.get('local_evaluation_basis') or row.get('redistribution')!='withheld':
            raise ValueError('Document local use basis and withhold unlicensed images')
    return config


def execution_preflight():
    """Actual harmless capability probe; no generated code, Blender or credential access.

    A namespace smoke test is deliberately insufficient. There is no switch that
    promotes a cached declaration into permission to execute Python on the host.
    """
    names=('podman','docker','bwrap','runc','crun','apptainer','singularity',
           'qemu-system-x86_64','virsh')
    tools={name:shutil.which(name) for name in names}
    try:
        result=subprocess.run(['/usr/bin/unshare','--user','--map-root-user','--net',
            '--mount','--pid','--fork','--mount-proc','/usr/bin/true'],
            capture_output=True,text=True,timeout=10,check=False)
        smoke=dict(exit_code=result.returncode,stderr=result.stderr)
    except (OSError,subprocess.TimeoutExpired) as exc:
        smoke=dict(error=str(exc))
    return dict(checked_at=datetime.now(timezone.utc).isoformat(),tools=tools,
        namespace_smoke=smoke,cgroup_delegation_writable=os.access('/sys/fs/cgroup',os.W_OK),
        kvm_available=Path('/dev/kvm').exists(),remote_executor_configured=False,
        qualified_untrusted_executor=False,runtime_status='blocked',blender_executions=0,
        reasons=['No qualified, adversarially checked untrusted-code executor is installed/configured.',
            'Existing CPU launcher has no filesystem confinement or per-job storage/process quota.',
            'No configured remote container/VM executor; no new cloud service/account is assumed.',
            'Namespace smoke success and resource monitoring alone do not meet the execution contract.'],
        required=['host-secret isolation','network disabled','CPU/memory/PID/disk/time hard limits',
                  'unprivileged execution','complete process-tree cleanup','same-execution camera/artifact binding'])


def prepare(config, output):
    frozen=output/'config.frozen.json'
    protocols=dict(planning=planning_protocol(**planning_options(config)),agent=agent_protocol(config))
    if frozen.exists():
        if read(frozen)!=config or read(output/'protocols.json')!=protocols:
            raise ValueError('Frozen config/prompts changed; choose a new experiment, never resume with new rules')
        dataset=read(output/'dataset_manifest.json')
        for row in dataset['samples']:
            if row['status']=='available':
                with Image.open(output/row['reference_rgb']) as image:
                    if list(image.size)!=row['evaluation_size']:
                        raise ValueError('Frozen Reference image grid changed')
                    image.verify()
        return dataset
    output.mkdir(parents=True,exist_ok=False)
    samples=[]
    # Reserve full selection before any model call; even a bad source remains selected.
    save(frozen,config,exclusive=True);save(output/'protocols.json',protocols,exclusive=True)
    for row in config['samples']:
        folder=output/row['id'];folder.mkdir()
        item=deepcopy(row); source=(ROOT/row['reference_rgb']).resolve()
        item.update(source_rgb=str(source),reviewed=False,usage='provisional/debug')
        try:
            if row.get('task_document'):
                task=read(ROOT/row['task_document'])
                if task['task_id']!=row['id'] or len(task['reference_images'])!=1:
                    raise ValueError('Task ID or primary-image count mismatch')
                declared=(ROOT/row['task_document']).parent/task['reference_images'][0]['task_relative_path']
                if declared.resolve()!=source:
                    raise ValueError('Source image is not the task-declared Reference')
            with Image.open(source) as image:
                item['native_size']=list(image.size)
                image=image.convert('RGB')
                image.thumbnail((config['max_edge'],config['max_edge']),Image.Resampling.LANCZOS)
                image.save(folder/'reference.png')
                item.update(status='available',evaluation_size=list(image.size),
                    reference_rgb=f"{row['id']}/reference.png",
                    coordinates='Aspect-preserving thumbnail only, no content alignment; ROI grid is frozen resized RGB')
        except (OSError,ValueError,KeyError) as exc:
            item.update(status='unavailable',error=f'{type(exc).__name__}: {exc}')
        samples.append(item)
    dataset=dict(samples=samples,selected=len(samples),requested=8,shortfall=8-len(samples),
        selection_frozen_before_model_calls=True,all_third_party_visuals_public=False,
        local_use='User-authorized local research on already distributed benchmark inputs; no image-specific rights clearance inferred',
        image_specific_rights_independently_cleared=0,reviewed=False)
    save(output/'dataset_manifest.json',dataset,exclusive=True)
    return dataset


def call_once(folder, stage, image, protocol, config):
    """Durable reservation, including failures/interruption. Resume never repeats it."""
    packet_path=folder/(stage+'.json'); reservation=folder/(stage+'.reservation.json')
    if packet_path.exists():
        packet=read(packet_path)
        if packet.get('actual_input')!=protocol:
            raise ValueError('Saved call contract differs from frozen input')
        return packet
    if reservation.exists():
        return dict(status='unavailable',raw_answer=None,actual_input=protocol,
            error='Interrupted reserved attempt; not retried',model_requested=config['agent']['model'],
            request_submitted=None,elapsed_seconds=None,token_usage={})
    save(reservation,dict(stage=stage,image=str(image),actual_input=protocol,
        model=config['agent']['model'],reserved_at=datetime.now(timezone.utc).isoformat()),exclusive=True)
    packet=codex_answer(image,protocol,ledger=[],model=config['agent']['model'],
        timeout=config['agent']['timeout_seconds'],max_requests=1,request_id=stage)
    save(packet_path,packet,exclusive=True)
    return packet


def generate_scene(sample, output, config):
    folder=output/sample['id']; status=dict(id=sample['id'],reviewed=False,
        usage='provisional/debug',formal_eligible=False,input_status=sample['status'])
    if sample['status']!='available':
        return dict(status,planning='unavailable',agent='unavailable',execution='not_attempted_input_unavailable',
            reason=sample.get('error','Reference input unavailable'))
    image=folder/'reference.png'
    settings=planning_options(config)
    planning=call_once(folder,'planning_response',image,planning_protocol(**settings),config)
    try:
        evidence=evidence_from_plan(planning,sample['evaluation_size'],**settings)
        if (folder/'reference_evidence.json').exists():
            if read(folder/'reference_evidence.json')!=evidence:
                raise ValueError('Frozen Reference Evidence changed')
        else:
            save(folder/'reference_evidence.json',evidence,exclusive=True)
        status['planning']='valid'
    except (ValueError,KeyError,TypeError) as exc:
        evidence=None;status.update(planning='unavailable',planning_error=str(exc))
    # Independent task/cwd: this call receives no plan/evidence/answers/evaluation.
    packet=call_once(folder,'agent_response',image,agent_protocol(config),config)
    try:
        parsed=parse_answer(packet.get('raw_answer'),agent_protocol(config)['schema'])
        if packet['status']!='valid' or parsed['status']!='valid':
            raise ValueError('Agent output unavailable/invalid; no repair')
        code=parsed['document']['blender_python']
        target=folder/'generated_scene.py'
        if target.exists():
            if target.read_text()!=code:raise ValueError('Saved code differs from raw Agent answer')
        else:
            target.write_text(code,encoding='utf-8')
        ast.parse(code)  # Parse only: never import, exec or run model Python on host.
        status.update(agent='valid_python_unexecuted',generation_rounds=1)
    except (ValueError,KeyError,TypeError,SyntaxError) as exc:
        status.update(agent='unavailable',agent_error=str(exc),generation_rounds=1)
    if evidence is not None and evidence['atomic_evidence']:
        protocol,questions=verification_protocol(evidence)
        save(folder/'verification_questions.json',dict(protocol=protocol,questions=questions))
        answers=call_once(folder,'reference_answers',image,protocol,config)
        status['reference_verification']=answers['status']
        status['evidence_count']=len(evidence['atomic_evidence'])
    else:
        status['reference_verification']='unavailable'
    status.update(execution='blocked_unqualified_isolation',camera='not_executed',
        render_verification='unavailable_no_new_render',blender_success=False,
        energies={k:dict(value=None,coverage=0.,status='unavailable',
                        reason='No safe execution / no current Agent Render') for k in ENERGIES},
        structural=dict(value=None,coverage=0.,status='unavailable',reason='No executed geometry'),
        observation_energy=None,reason='Untrusted generated code retained; no host fallback')
    save(folder/'pending_job.json',dict(reference_rgb='reference.png',python='generated_scene.py',
        source_status=status['agent'],camera_matrix=config['camera_matrix'],
        resolution=sample['evaluation_size'],intrinsics='Agent-selected, validate with existing benchmark_camera',
        execution='blocked',required_artifacts=['RGB','Depth','Object-ID/Mask','Geometry',
            'actual camera before/after export','bounded launcher record'],
        resource_limits=config['execution_limits'],
        note='Pending task, not an execution receipt. Never pass this code to the supervised host-only launcher.'))
    return status


def dino_check(config, output, dataset):
    path=output/'dino_check.json'
    if path.exists():return read(path)
    tick=time.monotonic()
    try:
        extract=local_dino_extractor(ROOT/config['dino_model'],device='cpu')
        sample=next(r for r in dataset['samples'] if r['status']=='available')
        with Image.open(output/sample['reference_rgb']) as im:
            features=extract([im.convert('RGB')])
        if not np.isfinite(features).all() or features.ndim!=2:
            raise ValueError('Nonfinite/malformed DINO features')
        check=dict(status='valid',feature_shape=list(features.shape),model=config['dino_model'],
            source_image=sample['id'],device='cpu',actual_inference=True,download=False,
            energy_value=None,reason='Real Reference-only availability inference, not a pairwise Perceptual score')
    except Exception as exc:
        check=dict(status='unavailable',error=f'{type(exc).__name__}: {exc}',energy_value=None)
    check['elapsed_seconds']=time.monotonic()-tick
    save(path,check,exclusive=True)
    return check


def aggregate_scenes(rows):
    """All selected samples remain the denominator. N/A never contributes zero."""
    def energy(key):
        valid=[r['energies'][key]['value'] for r in rows if r.get('energies',{}).get(key,{}).get('value') is not None]
        return dict(valid_samples=len(valid),total_samples=len(rows),
            availability_fraction=len(valid)/len(rows) if rows else None,
            conditional_mean=float(np.mean(valid)) if valid else None,
            conditional_min=min(valid) if valid else None,conditional_max=max(valid) if valid else None,
            values=valid,interpretation='Available-only conditional distribution; failures retained in total, not scored zero')
    return dict(total_samples=len(rows),generation_valid_python=sum(r['agent']=='valid_python_unexecuted' for r in rows),
        generation_rate=sum(r['agent']=='valid_python_unexecuted' for r in rows)/len(rows) if rows else None,
        generation_rate_definition='Syntax-valid code / selected inputs, NOT successfully constructed scenes',
        scene_generation_success_rate=None,execution_attempts=0,
        blender_successes=sum(r.get('blender_success',False) for r in rows),protocol_compliant_executions=0,
        protocol_compliance_fraction=0. if rows else None,conditional_executed_protocol_compliance=None,
        energies={k:energy(k) for k in ENERGIES},
        structural=dict(valid_samples=0,total_samples=len(rows),value=None,coverage=0.),
        unreviewed_evidence_fraction=1. if any(r.get('evidence_count') for r in rows) else None,
        formal_release_eligible=False,usage='provisional/debug',reviewed=False,
        completion='partial_real_model_execution_blocked_at_untrusted_Blender',
        not_a_complete_end_to_end_benchmark=True)


def write_outputs(config, output, dataset, rows, checks, dino):
    aggregate=aggregate_scenes(rows)
    planning_counts=Counter()
    atomic_types=Counter()
    for sample in dataset['samples']:
        evidence_path=output/sample['id']/'reference_evidence.json'
        if evidence_path.exists():
            evidence=read(evidence_path)
            planning_counts.update({k:len(evidence[k]) for k in ('regions','groups','anchors')})
            atomic_types.update(e['type'] for e in evidence['atomic_evidence'])
    aggregate['reference_planning']=dict(node_counts=dict(planning_counts),atomic_types=dict(atomic_types),
        reviewed=False,group_aware_path_exercised=planning_counts['groups']>0,
        interpretation='Candidate allocation, not correctness or full metric applicability')
    calls=[]
    for sample in dataset['samples']:
        for stage in ('planning_response','agent_response','reference_answers','render_answers'):
            packet_path=output/sample['id']/(stage+'.json')
            reservation=packet_path.with_suffix('.reservation.json')
            if packet_path.exists() or reservation.exists():
                p=read(packet_path) if packet_path.exists() else dict(status='unavailable',
                    model_requested=config['agent']['model'],error='Interrupted reserved attempt, no retry')
                calls.append(dict(sample_id=sample['id'],stage=stage,status=p['status'],
                    model_requested=p.get('model_requested'),model_observed=p.get('model_observed'),
                    elapsed_seconds=p.get('elapsed_seconds'),token_usage=p.get('token_usage',{}),
                    request_submitted=p.get('request_submitted'),attempts=1,retries=0,
                    cli_subprocess_started='invocation' in p,error=p.get('error')))
    aggregate['model_cost']=dict(attempts=len(calls),agent_attempts=sum(c['stage']=='agent_response' for c in calls),
        token_usage={k:sum((r['token_usage'].get(k) or 0) for r in calls) for k in ('input_tokens','output_tokens')},
        seconds=sum(r['elapsed_seconds'] or 0 for r in calls),currency_cost=None,
        usage_reported_calls=sum(r['token_usage'].get('input_tokens') is not None for r in calls),
        missing_usage_calls=sum(r['token_usage'].get('input_tokens') is None for r in calls),
        note='Token sums are reported-only lower bounds if any usage is missing; CLI usage includes platform context, not API price/billing')
    # Reuse the existing comparison interface, explicitly representing an unexecuted
    # Render as unavailable rather than a Mock, historical answer or zero error.
    for row in rows:
        folder=output/row['id'];f=folder/'reference_evidence.json'
        if not f.exists():continue
        evidence=read(f)
        with Image.open(folder/'reference.png') as image:
            build_reference(np.asarray(image.convert('RGB')),evidence)  # compatibility validation, no review promotion
        if not evidence['atomic_evidence']:continue  # no fabricated questions or extra VQA call
        protocol,questions=verification_protocol(evidence)
        ref=folder/'reference_answers.json'
        if not ref.exists():continue
        reference=read(ref)
        unavailable=answer_packet(None,backend='not_executed',source_kind='unavailable',
            protocol=protocol,metadata=dict(reason='No qualified new Blender execution / Render',new_model_calls=0))
        comparison=compare_answers(reference,unavailable,questions)
        comparison['binding_status']='unavailable_no_render_pair'
        save(folder/'verification_results.json',comparison)
        row['verification_states']=dict(Counter(r['status'] for r in comparison['results']))
        row['structural_details']=structural_report(dict(status='unavailable',reason='No executed geometry'))
        # Automatic Reference-only overlay for the single human audit packet, local only.
        with Image.open(folder/'reference.png') as image:
            image=image.convert('RGB');draw=ImageDraw.Draw(image)
            for region in evidence['regions']:
                draw.rectangle(region['bbox'],outline='#ffb000',width=2)
                draw.text(region['bbox'][:2],region['id'],fill='black',stroke_width=1,stroke_fill='white')
            image.save(folder/'reference_regions_local_only.png')
    save(output/'run_manifest.json',dict(config='config.frozen.json',samples=rows,calls=calls,
        max_calls=len(dataset['samples'])*4,automatic_retries=0,actual_blender_executions=0,
        safety_boundary='Runtime remains blocked; generated source parsed, never imported/executed'))
    save(output/'aggregate_results.json',aggregate)
    save(output/'execution_checks.json',dict(**checks,dino=dino))
    fields=['id','input_status','planning','agent','execution','camera','reference_verification',
            *[v for k in ENERGIES for v in (k,k+'_coverage')],'structural','structural_coverage',
            'unavailable_reason','cli_attempts','known_input_tokens','known_output_tokens','cli_seconds','reviewed']
    with (output/'per_scene_results.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            values={k:row.get(k) for k in fields if k in row and k!='structural'}
            for k in ENERGIES:
                value=row.get('energies',{}).get(k,{}).get('value')
                values[k]=value if value is not None else 'N/A'
                values[k+'_coverage']=row.get('energies',{}).get(k,{}).get('coverage',0.)
            values.update(structural='N/A',structural_coverage=0.)
            scene_calls=[c for c in calls if c['sample_id']==row['id']]
            values.update(unavailable_reason=row.get('reason',row.get('error','Awaiting stages')),
                cli_attempts=len(scene_calls),
                known_input_tokens=sum(c['token_usage'].get('input_tokens') or 0 for c in scene_calls),
                known_output_tokens=sum(c['token_usage'].get('output_tokens') or 0 for c in scene_calls),
                cli_seconds=sum(c['elapsed_seconds'] or 0 for c in scene_calls))
            writer.writerow(values)
    lines=['# Benchmark v0.1 — actual partial run','',
        '**reviewed:false; provisional/debug; NOT a completed end-to-end Benchmark or formal score.**','',
        f"Selected {len(rows)}/8 real RGB inputs; {aggregate['generation_valid_python']} syntax-valid new scene programs; "
        f"{len(calls)} real CLI attempts; 0 Blender executions. No historical Render or fixture substituted.", '',
        '## Per-scene status','', '| Sample | Planning | Agent code | Reference VQA | Execution |',
        '| --- | --- | --- | --- | --- |']
    lines += [f"| {r['id']} | {r['planning']} | {r['agent']} | {r.get('reference_verification','unavailable')} | {r['execution']} |" for r in rows]
    lines += ['', 'All five pairwise Energies and independent Structural are N/A (valid sample count 0). '
        'No safe new Render/geometry exists; availability Coverage is 0, not a zero error. '
        'No VQA comparison is invented from Reference answers alone.', '',
        f"Actual CLI attempts: {len(calls)}; Agent generation attempts: {aggregate['model_cost']['agent_attempts']}; "
        f"reported input/output tokens: {aggregate['model_cost']['token_usage']}; "
        f"CLI elapsed sum: {aggregate['model_cost']['seconds']:.3f}s. Currency cost unavailable. "
        f"No remote model snapshot claimed; model_requested={config['agent']['model']}, backend=Codex CLI.", '',
        '## Reference planning coverage','',
        f"Nodes: {dict(planning_counts)}. Atomic evidence types: {dict(atomic_types)}. "
        'These are automatic candidates, not GT. If no Group is proposed, the Group-aware path '
        'has not been exercised. Presence/count-heavy questions do not establish arrangement or '
        'continuous-layout sensitivity. No missing Group/question is added after seeing results.', '',
        '## Actual boundary','', *['- '+reason for reason in checks['reasons']], '',
        'DINO: '+dino['status']+'. '+dino.get('reason',dino.get('error','')), '',
        '## Limitations','',
        'Codex CLI tools are disabled and cwd/images are isolated per call, but filesystem read confinement '
        'and exact remote model snapshot are not established. This is not a strict blind/base-model test. '
        'No scene-specific prompt edits, repairs, retries or render feedback. Reference evidence was frozen '
        'before Agent generation; the Agent receives only its RGB and common T0 task.', '',
        'Local evaluation uses user-authorized existing benchmark images. The distribution documents evaluation use; '
        'image-specific copyright clearance is not established. No third-party visual/Blender asset is published. '
        'These are eight existing external RGB inputs, not eight verified real-world photographs: '
        'the selection includes artwork and potentially rendered references. These remain selected, '
        'with their scope limitation, rather than being discarded after model generation. '
        'Reference viewpoint is unknown; enforcing output T0 alone would not remove camera/reconstruction ambiguity.', '',
        '## To finish','',
        'Provide and validate an unprivileged container/VM executor with the recorded hard resource and isolation '
        'requirements, then connect its same-execution exports to the existing Offline Evaluator. '
        'This batch deliberately has no unvalidated executor fallback. Resume does not rerun reserved model calls. '
        'Review all Reference candidates and subsequent VQA/Structural candidates independently before formal scores.', '',
        '[Dataset](dataset_manifest.json) · [All calls/statuses](run_manifest.json) · '
        '[Per scene](per_scene_results.csv) · [Aggregate](aggregate_results.json) · '
        '[Execution checks](execution_checks.json) · [Human audit](audit_packet.md) · [Reproduce](reproduce.md)']
    (output/'benchmark_report.md').write_text('\n'.join(lines)+'\n')
    audit=['# Batch human audit — all items UNREVIEWED','',
        'No independent human annotation has occurred. Do not set reviewed=true automatically. '
        'Render/VQA comparison/Structural review is pending safe execution.','',
        '| Sample / Evidence | Region / Group / Anchor | Reference claim | Neutral question | Reference answer | Human review |',
        '| --- | --- | --- | --- | --- | --- |']
    for row in rows:
        f=output/row['id']/'reference_evidence.json'
        if not f.exists():continue
        evidence=read(f); p=output/row['id']/'reference_answers.json'
        packet=read(p) if p.exists() else {}
        document=packet.get('parsed',{}).get('document') or {}
        for e in evidence['atomic_evidence']:
            parts=[row['id']+'/'+e['id'],' / '.join(str(e[k]) for k in ('region_id','group_id','anchor_id')),
                   e['claim'],e['question'],str(document.get(e['id'],'unavailable')),'unreviewed']
            audit.append('| '+' | '.join(p.replace('|','\\|').replace('\n',' ') for p in parts)+' |')
    audit += ['', 'For each: check RGB support, Region/Group/Anchor scope, question neutrality, visibility and '
        'class ambiguity. After safe rendering: check paired identity, candidate violation support, camera '
        'ambiguity, and whether structural candidates are actual 3D problems. All review flags remain false.']
    (output/'audit_packet.md').write_text('\n'.join(audit)+'\n')
    return aggregate


def run_batch(config_path):
    config=load_config(config_path);output=(ROOT/config['output']).resolve()
    # A single lock protects durable call reservations and all serial work.
    (ROOT/'runs').mkdir(exist_ok=True)
    with (ROOT/'runs/.benchmark_batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        dataset=prepare(config,output)
        if not (output/'protocol.md').exists():
            (output/'protocol.md').write_text('# Frozen Benchmark v0.1 protocol\n\n'
                'See config.frozen.json, protocols.json and dataset_manifest.json frozen before model calls.\n\n'
                f"{len(dataset['samples'])} preselected real RGB; same longest-edge{config['max_edge']} preprocessing; Codex CLI {config['agent']['model']}; "
                'one Reference plan, one code generation, one Reference VQA and at most one Render VQA per sample. '
                'No repair, retry or render feedback. Shared timeout300s; tools disabled; stages serial. '
                'All evidence reviewed=false; original Energy policy/T0 unchanged. '
                'No untrusted host execution. Qualified isolation required before Blender. '
                'No formal score until evidence review and execution/protocol eligibility. '
                'All failures/NA remain in denominator.\n')
        if not (output/'environment_lock.md').exists():
            versions={}
            for package in ('numpy','Pillow','scipy','torch','transformers','jsonschema'):
                try:versions[package]=importlib.metadata.version(package)
                except importlib.metadata.PackageNotFoundError:versions[package]=None
            (output/'environment_lock.md').write_text('# Observed environment (not a portable lockfile)\n\n'
                +sys.version+'\n\n'+json.dumps(versions,indent=2)+'\n\n'
                'Existing sibling scene-benchmark and local DINOv2 weights required; no downloads. '
                'Blender candidate: existing4.2.0 binary; not run for this batch. No qualified code executor.\n')
        (output/'reproduce.md').write_text('# Reproduce / resume\n\n'
            'Use the declared Python dependencies, compatible sibling scene-benchmark, local input RGB '
            'at dataset_manifest paths and locally authenticated Codex CLI. Do not copy credentials.\n\n'
            '```bash\nOMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 '
            'python -B -m e_harness.benchmark batch --config configs/benchmark_v01.yaml\n```\n\n'
            'This command makes real model requests only for never-reserved stages. Same frozen output '
            'resumes without retries; changed config/prompts are rejected. All reserved interruptions remain '
            'unavailable. For a new model experiment choose a new output and freeze it first. '
            'No model-generated Python is executed by this entry without a qualified executor; currently '
            'execution is blocked. No model request is made by the legacy offline/replay entry.\n')
        checks=execution_preflight()
        dino=dino_check(config,output,dataset)
        rows=[dict(id=s['id'],input_status=s['status'],planning='not_attempted',agent='not_attempted',
            execution='not_attempted',reviewed=False,formal_eligible=False) for s in dataset['samples']]
        for index,sample in enumerate(dataset['samples']):
            print('Batch sample '+sample['id']+': starting/resuming bounded stages',flush=True)
            try:
                row=generate_scene(sample,output,config)
            except Exception as exc:
                # Preserve scene failure and continue; never discard selected denominator.
                row=dict(id=sample['id'],input_status=sample['status'],planning='unavailable',
                    agent='unavailable',execution='failed_controller',error=f'{type(exc).__name__}: {exc}',
                    reviewed=False,formal_eligible=False)
            save(output/sample['id']/'scene_status.json',row)
            rows[index]=row
            write_outputs(config,output,dataset,rows,checks,dino)
        return dict(output=str(output),**write_outputs(config,output,dataset,rows,checks,dino))
