"""Reference-only extraction experiment; never loads Agent renders or Blender.

Run phases serially in a new results directory. Model workers use only local
weights and an explicitly checked GPU. These are unreviewed candidates, not GT.
"""
import argparse
import csv
import gc
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import contextlib
import io

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_config import write_json
from e_harness.benchmark_evidence import sam2_box_masks
from compare_region_segmentation import boundary, bbox, colors

TASKS = ['bw_9064', 'bw_0074', 'bw_0073', 'bw_0043', 'bw_0075']
METHODS = ['slic_100', 'slic_200', 'slic_400', 'sam2_auto', 'sam2_prompted',
           'sam3_auto', 'sam3_text', 'sam3_visual', 'slic_sam2', 'slic_sam3']

# Loose, unreviewed visual prompts authored from the reference RGB alone.
# Fractions are converted to ORIGINAL pixel xyxy before either model sees them.
PROMPTS = {
    'bw_0074': [
        ('monitor', 'anchor', [.167, .44, .31, .573]),
        ('transparent chair', 'anchor', [.074, .622, .263, .99]),
        ('sofa', 'anchor', [.303, .645, 1, 1]),
        ('globe', 'anchor', [.183, .168, .236, .247]),
        ('aquarium', 'anchor', [.426, .523, .54, .622]),
        ('records group', 'region', [.701, .13, 1, .5]),
        ('books group', 'region', [.10, .14, .395, .434]),
        ('bookshelf', 'region', [.085, .095, 1, .872]),
        ('wall', 'region', [.105, 0, .98, .10]),
        ('wood floor', 'region', [.037, .847, .322, 1])],
    'bw_0073': [
        ('chair leftmost', 'anchor', [.332, .567, .422, .852]),
        ('chair second', 'anchor', [.414, .562, .501, .863]),
        ('chair third', 'anchor', [.509, .563, .598, .866]),
        ('chair rightmost', 'anchor', [.590, .561, .689, .864]),
        ('pendant light', 'anchor', [.440, .105, .568, .351]),
        ('potted plant', 'anchor', [.524, .384, .580, .482]),
        ('fruit bowl', 'anchor', [.471, .466, .539, .525]),
        ('wood floor', 'region', [.10, .698, .87, 1]),
        ('marble backsplash', 'region', [.162, .404, .346, .570]),
        ('cabinets', 'region', [.704, 0, 1, .73]),
        ('island countertop', 'region', [.336, .488, .672, .578]),
        ('ceiling', 'region', [.16, 0, .76, .30])],
    'bw_0043': [
        ('flower', 'anchor', [.15, .024, .75, .975]),
        ('leaves', 'region', [.68, .02, .99, .99]),
        ('background vegetation', 'region', [0, 0, .20, .99])],
    'bw_0075': [
        ('painted sky', 'region', [0, 0, 1, .18]),
        ('painted clouds', 'region', [0, .09, 1, .52]),
        ('painted hills', 'region', [0, .42, 1, .77]),
        ('painted foreground hills', 'region', [0, .73, 1, 1])],
}
TEXTS = {
    'bw_9064': ['table', 'chair', 'refrigerator', 'potted plant', 'wall', 'ceiling', 'wood floor'],
    'bw_0074': ['bookshelf', 'books', 'vinyl records', 'monitor', 'chair', 'sofa', 'globe', 'aquarium'],
    'bw_0073': ['chair', 'cabinets', 'countertop', 'pendant light', 'plant', 'bowl', 'window', 'wood floor'],
    'bw_0043': ['flower', 'petals', 'leaves', 'stem'],
    'bw_0075': ['painted sky', 'clouds', 'painted hills'],
}


def read(path):
    return json.loads(Path(path).read_text())


def new_json(path, data):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)


def prepare(out):
    if any(out.iterdir()):
        raise FileExistsError('Prepare requires an empty new directory')
    rows = list(csv.DictReader((ROOT / 'results/blenderworld_runs_inventory/selected.csv').open(encoding='utf-8-sig')))
    manifest = dict(tasks=[], render_used=False, reviewed=False, max_work_edge=1536,
                    note='No task-specific query text or Agent artifacts used to author prompts.')
    for task in TASKS:
        matches = [r for r in rows if r['task_id'] == task]
        row = matches[0]
        ref = Path(row['reference_image'])
        original = Path(row['original_reference_image'])
        input_file = ref.parents[1] / 'input.json'
        task_file = original.parents[1] / 'task.json'
        config_file = ROOT.parent / 'BlenderWorld/runs' / row['run_id'] / 'config.json'
        inp, task_meta, config = read(input_file), read(task_file), read(config_file)
        assert inp['task_id'] == task_meta['task_id'] == task
        declared = [str(x['task_relative_path']) for x in task_meta['reference_images']]
        assert str(ref.relative_to(input_file.parent)) in inp['files']
        assert str(original.relative_to(task_file.parent)) in declared
        assert Path(config['task']['path']).resolve() == input_file.parents[2].resolve()
        image = Image.open(ref).convert('RGB')
        assert Image.open(original).size == image.size
        folder = out / 'references' / task
        folder.mkdir(parents=True)
        shutil.copyfile(ref, folder / ('reference' + ref.suffix))
        work = image.copy()
        work.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        work.save(folder / 'working.png')
        width, height = image.size
        if task == 'bw_9064':
            prior = read(ROOT / 'results/bw_9064_evidence_review/candidate_evidence.json')
            prompts = [dict(id=a['id'], category=a['category'], role='anchor', bbox=a['bbox']) for a in prior['anchors']]
            prompts += [dict(id=key, category=category, role='region', bbox=box) for key, category, box in [
                ('wall_back', 'wall', [248, 105, 1429, 743]), ('ceiling', 'ceiling', [78, 0, 1595, 107]),
                ('floor', 'wood floor', [0, 741, 1672, 941]), ('wall_left', 'wall', [0, 0, 249, 851]),
                ('wall_right', 'wall', [1428, 0, 1672, 851])]]
        else:
            prompts = [dict(id='p%02d' % i, category=category, role=role,
                            bbox=[round(box[0]*width), round(box[1]*height), round(box[2]*width), round(box[3]*height)])
                       for i, (category, role, box) in enumerate(PROMPTS[task])]
        for prompt in prompts:
            prompt.update(reviewed=False, mask_reviewed=False, reliability=0.,
                          source='fixed_test_reference_rgb_candidate', prompt_author='assistant_reference_rgb_inspection', precision='loose_bbox_not_GT')
        info = dict(task_id=task, image_size=list(image.size), working_size=list(work.size),
                    reference_image=str(ref.resolve()), original_reference_image=str(original.resolve()),
                    reference_copy=str((folder / ('reference' + ref.suffix)).relative_to(out)),
                    working_image=str((folder / 'working.png').relative_to(out)),
                    provenance=dict(input_json=str(input_file), task_json=str(task_file), run_config=str(config_file),
                                    run_ids=[r['run_id'] for r in matches], metadata_correspondence_verified=True),
                    visual_prompts=prompts, text_prompts=TEXTS[task], reviewed=False, render_used=False,
                    coordinate_note='Masks nearest-resized to original RGB; statistics use the working grid.')
        new_json(folder / 'prompts.json', info)
        view = work.copy(); draw = ImageDraw.Draw(view)
        for p in prompts:
            box = [round(v * work.size[i % 2] / image.size[i % 2]) for i, v in enumerate(p['bbox'])]
            draw.rectangle(box, outline='yellow' if p['role'] == 'anchor' else 'cyan', width=2)
            draw.text((box[0], box[1]), p['id'] + ': ' + p['category'], fill='white', stroke_width=1, stroke_fill='black')
        view.save(folder / 'prompts_overlay.png')
        manifest['tasks'].append(info)
    new_json(out / 'manifest.json', manifest)


def method_folder(out, task, method):
    return out / 'methods' / task / method


def work_image(out, task):
    return np.asarray(Image.open(out / task['working_image']).convert('RGB'))


def mask_statistics(masks):
    shape = masks.shape[1:]
    counts = masks.sum(axis=0, dtype=np.uint16)
    areas = masks.sum(axis=(1, 2))
    duplicates, containment, overlap_pairs = [], [], []
    for i in range(len(masks)):
        for j in range(i):
            intersection = int(np.count_nonzero(masks[i] & masks[j]))
            if not intersection:
                continue
            iou = intersection / max(1, int(areas[i]+areas[j])-intersection)
            if iou >= .9:
                duplicates.append([j, i, iou])
            elif intersection / max(1, int(min(areas[i], areas[j]))) >= .95:
                containment.append([j, i])
            else:
                overlap_pairs.append([j, i])
    components = [int(ndimage.label(m)[1]) for m in masks]
    return dict(mask_count=len(masks), raw_mask_union_coverage=float((counts > 0).mean()),
                unknown_residual_fraction=float((counts == 0).mean()), overlap_fraction=float((counts > 1).mean()),
                duplicate_pairs_iou_ge_09=duplicates, nested_pairs_containment_ge_095=containment,
                partial_overlap_pairs=overlap_pairs, component_counts=components,
                tiny_mask_count=int(np.count_nonzero(areas < 16)), statistics_grid=[shape[1], shape[0]],
                accuracy_iou=None, accuracy_boundary_f1=None, reviewed_semantic_coverage=0.,
                reviewed_unknown_fraction=1., note='Overlap and connected components are diagnostics, not accuracy or proven conflicts.')


def save_masks(out, task, method, masks, metadata, run):
    folder = method_folder(out, task['task_id'], method)
    folder.mkdir(parents=True, exist_ok=True)
    masks = np.asarray(masks, dtype=bool).reshape((-1, task['working_size'][1], task['working_size'][0]))
    assert len(masks) == len(metadata)
    valid = masks.any(axis=(1, 2))
    run['empty_predictions'] = [row for row, keep in zip(metadata, valid) if not keep]
    run['raw_prediction_count'] = len(masks)
    metadata = [row for row, keep in zip(metadata, valid) if keep]
    masks = masks[valid]
    image = work_image(out, task)
    stats = mask_statistics(masks)
    region_dir = out / 'region_candidates' / task['task_id'] / method
    anchor_dir = out / 'anchor_candidates' / task['task_id'] / method
    region_dir.mkdir(parents=True); anchor_dir.mkdir(parents=True)
    regions, anchors = [], []
    overlay = image.copy()
    rng = np.random.default_rng(9064)
    for i, (mask, meta) in enumerate(zip(masks, metadata)):
        if not mask.any():
            raise ValueError('Empty retained mask')
        role = meta.get('role', 'region')
        mask_id = task['task_id'] + '_' + method + '_m%03d' % i
        target = (anchor_dir if role == 'anchor' else region_dir) / (mask_id + '.png')
        restored = Image.fromarray(mask.astype(np.uint8)*255).resize(tuple(task['image_size']), Image.Resampling.NEAREST)
        restored.save(target)
        row = dict(meta, id=mask_id, bbox=list(restored.getbbox()), reviewed=False, mask_reviewed=False,
                   reliability=0., importance=1., status='observable', mask=str(target.relative_to(out)),
                   metrics=['spatial', 'appearance', 'statistical', 'perceptual'],
                   provenance=dict(reference=task['reference_image'], method=method, render_used=False))
        if row.get('category'):
            row['metrics'].insert(0, 'semantic')
        (anchors if role == 'anchor' else regions).append(row)
        color = rng.integers(50, 245, size=3)
        overlay[mask] = np.uint8(.60*overlay[mask]+.40*color)
        overlay[boundary(mask.astype(np.uint8))] = color
    unknown = ~masks.any(axis=0)
    if unknown.any():
        path = region_dir / 'unknown.png'
        restored = Image.fromarray(unknown.astype(np.uint8)*255).resize(tuple(task['image_size']), Image.Resampling.NEAREST)
        restored.save(path)
        regions.append(dict(id=task['task_id']+'_'+method+'_unknown', bbox=list(restored.getbbox()),
                            mask=str(path.relative_to(out)), region_role='unknown_fallback', category=None,
                            status='unknown', reviewed=False, mask_reviewed=False, reliability=0.,
                            description='Residual not covered by this method; semantic status is unreviewed for all masks.',
                            metrics=['appearance', 'statistical', 'perceptual']))
    unknown_view = image.copy()
    unknown_view[unknown] = np.uint8(.35*image[unknown]+.65*np.array([255, 20, 90]))
    Image.fromarray(overlay).save(folder / 'overlay.png')
    Image.fromarray(unknown_view).save(folder / 'unknown_overlay.png')
    np.savez_compressed(folder / 'working_masks.npz', masks=masks)
    for directory, key, rows in [(region_dir, 'regions', regions), (anchor_dir, 'anchors', anchors)]:
        converted = []
        for row in rows:
            item = dict(row)
            item['mask'] = os.path.relpath(out / row['mask'], directory)
            converted.append(item)
        new_json(directory / 'candidates.json', dict(image_size=task['image_size'], reference_image=task['reference_image'],
                 reviewed=False, inventory_complete=False, regions=converted if key == 'regions' else [],
                 anchors=converted if key == 'anchors' else [], relations=[]))
    run.update(stats, status='available', task_id=task['task_id'], method=method, region_count=len(regions),
               anchor_count=len(anchors), dense_coverage_with_fallback=1., reviewed=False, mask_reviewed=False,
               prompt_author='automatic_grid' if method=='sam2_auto' else 'assistant_reference_rgb_fixed_test',
               human_reviewed_prompt_count=0,
               raw_score_note='Uncalibrated model scores are never evidence reliability or true correctness probabilities.')
    new_json(folder / 'run.json', run)
    new_json(folder / 'mask_metadata.json', dict(regions=regions, anchors=anchors, reviewed=False))


def slic_phase(out, manifest):
    from skimage.segmentation import slic
    import skimage
    for task in manifest['tasks']:
        image = work_image(out, task)
        for count in [100, 200, 400]:
            folder = method_folder(out, task['task_id'], 'slic_' + str(count))
            folder.mkdir(parents=True)
            if (folder / 'run.json').exists():
                raise FileExistsError(folder)
            start = time.monotonic()
            labels = slic(image, n_segments=count, compactness=10., sigma=1., max_num_iter=10,
                          convert2lab=True, enforce_connectivity=True, start_label=0, channel_axis=-1)
            seconds = time.monotonic()-start
            counts = np.bincount(labels.ravel())
            np.savez_compressed(folder / 'dense_labels.npz', labels=labels.astype(np.int32))
            # Original-grid label image: integer label IDs, never semantic classes.
            region_dir = out / 'region_candidates' / task['task_id'] / ('slic_' + str(count))
            region_dir.mkdir(parents=True)
            Image.fromarray(labels.astype(np.uint16)).resize(tuple(task['image_size']), Image.Resampling.NEAREST).save(region_dir / 'dense_labels.png')
            overlay = np.uint8(.7*image+.3*colors(labels)); overlay[boundary(labels)] = [255, 225, 20]
            Image.fromarray(overlay).save(folder / 'overlay.png')
            new_json(folder / 'run.json', dict(status='available', task_id=task['task_id'], method='slic_'+str(count),
                mask_count=len(counts), region_count=0, anchor_count=0, requested_segments=count,
                dense_coverage_with_fallback=1., raw_mask_union_coverage=1., unknown_residual_fraction=0.,
                reviewed_unknown_fraction=1., reviewed_semantic_coverage=0., semantic_unknown_fraction=1.,
                overlap_fraction=0., duplicate_pairs_iou_ge_09=[], tiny_mask_count=int((counts < 16).sum()),
                boundary_pixel_fraction=float(boundary(labels).mean()), area_quantiles=np.quantile(counts, [0, .25, .5, .75, 1]).tolist(),
                wall_seconds=seconds, gpu_peak_allocated_mib=None, prompt_type='none', prompt_count=0,
                statistics_grid=task['working_size'], implementation='scikit-image '+skimage.__version__,
                params=dict(compactness=10., sigma=1., max_num_iter=10, enforce_connectivity=True),
                reviewed=False, semantic_claim=False, note='Dense visual patches only; no final semantic Regions created.'))
            print(task['task_id'], 'SLIC', count, len(counts), '%.3fs' % seconds, flush=True)


def gpu_check(uuid, idle=False):
    raw = subprocess.run(['nvidia-smi', '-i', uuid, '--query-gpu=uuid,memory.total,memory.used,utilization.gpu',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout.strip()
    actual, total, used, util = [x.strip() for x in raw.split(',')]
    processes = subprocess.run(['nvidia-smi', '-i', uuid, '--query-compute-apps=pid,used_memory',
                                '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout.strip()
    pids = [int(line.split(',')[0]) for line in processes.splitlines() if line.strip()]
    if actual != uuid or int(total) < 16000 or any(pid != os.getpid() for pid in pids):
        raise RuntimeError('Selected GPU has another compute process or insufficient capacity')
    if idle and (int(used) > 128 or int(util) != 0):
        raise RuntimeError('Selected GPU is not idle')
    return dict(uuid=actual, total_mib=int(total), used_mib=int(used), utilization_percent=int(util), pids=pids,
                recorded_at=time.time())


def sam2_phase(out, manifest):
    import torch
    from transformers import Sam2Model, Sam2Processor, pipeline
    uuid = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not uuid.startswith('GPU-') or ',' in uuid:
        raise ValueError('Use a single explicit GPU UUID')
    initial = gpu_check(uuid, idle=True)
    torch.set_num_threads(2); torch.set_num_interop_threads(1)
    torch.cuda.set_per_process_memory_fraction(.20, 0)
    checkpoints = Path('/home/xymo/models/sam2')
    load_start = time.monotonic()
    processor = Sam2Processor.from_pretrained(checkpoints, local_files_only=True)
    model, loading = Sam2Model.from_pretrained(checkpoints, local_files_only=True, output_loading_info=True)
    if any(loading.get(k) for k in ['missing_keys', 'mismatched_keys', 'error_msgs']):
        raise ValueError('Incomplete local SAM2 image weights')
    model = model.to('cuda:0').eval()
    auto = pipeline('mask-generation', model=model, image_processor=processor.image_processor, device=0)
    load_seconds = time.monotonic()-load_start
    for task in manifest['tasks']:
        before = gpu_check(uuid)
        folder = method_folder(out, task['task_id'], 'sam2_auto')
        if (folder / 'run.json').exists(): raise FileExistsError(folder)
        image = Image.open(out / task['working_image']).convert('RGB')
        torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); start = time.monotonic()
        with torch.inference_mode():
            result = auto(image, points_per_batch=8, points_per_crop=16, crops_n_layers=0,
                          pred_iou_thresh=.88, stability_score_thresh=.95, crops_nms_thresh=.7,
                          output_bboxes_mask=True)
        torch.cuda.synchronize(); seconds = time.monotonic()-start
        masks = np.asarray(result['masks'], dtype=bool)
        scores = np.asarray(result['scores'].cpu() if hasattr(result['scores'], 'cpu') else result['scores'])
        metadata = [dict(role='region', raw_iou_head_score=float(score), category=None,
                         prompt_source='automatic_uniform_grid', prompt_point_association='unknown_after_pipeline_NMS') for score in scores]
        grid = [[(x+.5)/16*task['image_size'][0], (y+.5)/16*task['image_size'][1]] for y in range(16) for x in range(16)]
        save_masks(out, task, 'sam2_auto', masks, metadata, dict(wall_seconds=seconds, load_seconds=load_seconds,
            gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
            gpu_peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
            gpu_before=before, gpu_after=gpu_check(uuid), prompt_type='automatic_grid_no_human_prompt',
            prompt_count=256, provided_prompt_count=0, grid_original_xy=grid,
            params=dict(points_per_crop=16, points_per_batch=8, crop_layers=0, pred_iou_thresh=.88,
                        stability_score_thresh=.95, nms_threshold=.7), implementation='Transformers MaskGenerationPipeline/Sam2Model',
            checkpoint=str(checkpoints), loading_info={k:list(v) if isinstance(v,set) else v for k,v in loading.items()}))
        print(task['task_id'], 'SAM2 auto', len(masks), '%.3fs' % seconds, flush=True)
        del result, masks; gc.collect(); torch.cuda.empty_cache()
    del auto, model, processor; gc.collect(); torch.cuda.empty_cache()
    for task in manifest['tasks']:
        before = gpu_check(uuid)
        folder = method_folder(out, task['task_id'], 'sam2_prompted')
        if (folder / 'run.json').exists(): raise FileExistsError(folder)
        prompts = task['visual_prompts']
        boxes = [[v * task['working_size'][i % 2] / task['image_size'][i % 2] for i,v in enumerate(p['bbox'])] for p in prompts]
        torch.cuda.reset_peak_memory_stats(); start = time.monotonic()
        masks, scores, info = sam2_box_masks(Image.open(out / task['working_image']).convert('RGB'), boxes, checkpoints, device='cuda:0')
        seconds = time.monotonic()-start
        metadata = [dict(p, raw_iou_head_score=float(s), prompt_bbox=p['bbox'], working_prompt_bbox=b) for p,s,b in zip(prompts,scores,boxes)]
        save_masks(out, task, 'sam2_prompted', masks, metadata, dict(wall_seconds=seconds,
            inference_seconds=info['inference_seconds'], load_included_in_wall=True,
            gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
            gpu_peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
            gpu_before=before, gpu_after=gpu_check(uuid), prompt_type='fixed_test_reference_rgb_loose_bbox',
            prompt_count=len(prompts), provided_prompt_count=len(prompts), info=info,
            implementation='Existing benchmark.evidence.sam2_box_masks', checkpoint=str(checkpoints)))
        print(task['task_id'], 'SAM2 prompted', len(masks), '%.3fs' % seconds, flush=True)
        del masks; gc.collect(); torch.cuda.empty_cache()
    new_json(out / 'sam2_resource_summary.json', dict(initial=initial, final=gpu_check(uuid),
             process_memory_cap_fraction=.20, serial=True, cpu_threads=2, device='cuda:0', reviewed=False))


def combine_phase(out, manifest):
    """Keep SLIC as a dense base and SAM masks as overlapping upper layers.

    Linking never splits or semantically relabels the dense partition, and never
    modifies a SAM boundary. Small cells are not all promoted to final Regions.
    """
    for task in manifest['tasks']:
        base = method_folder(out, task['task_id'], 'slic_200')
        labels = np.load(base / 'dense_labels.npz', allow_pickle=False)['labels']
        sizes = np.bincount(labels.ravel())
        for method, source in [('slic_sam2', 'sam2_prompted'), ('slic_sam3', 'sam3_visual')]:
            folder = method_folder(out, task['task_id'], method)
            if (folder / 'run.json').exists(): continue
            source_folder = method_folder(out, task['task_id'], source)
            if not (source_folder / 'run.json').exists(): continue
            source_run = read(source_folder / 'run.json')
            if source_run['status'] != 'available': continue
            folder.mkdir(parents=True)
            start = time.monotonic()
            masks = np.load(source_folder / 'working_masks.npz', allow_pickle=False)['masks']
            source_rows = read(source_folder / 'mask_metadata.json')
            rows = sorted([r for r in source_rows['regions'] + source_rows['anchors'] if r.get('region_role') != 'unknown_fallback'], key=lambda r:r['id'])
            assert len(rows) == len(masks)
            links = []
            crossings = set()
            for mask, row in zip(masks, rows):
                intersections = np.bincount(labels[mask], minlength=len(sizes))
                straddling = (intersections > 0) & (intersections < sizes)
                crossings.update(np.flatnonzero(straddling).tolist())
                links.append(dict(mask_id=row['id'], dense_cells=[dict(label=int(i), fraction=float(intersections[i]/sizes[i]))
                                   for i in np.flatnonzero(intersections)], reviewed=False))
            seconds = time.monotonic()-start
            new_json(folder / 'hierarchy.json', dict(global_reference=task['reference_image'],
                dense_basis=str((base / 'dense_labels.npz').relative_to(out)),
                upper_regions=str((out / 'region_candidates' / task['task_id'] / source / 'candidates.json').relative_to(out)),
                anchors=str((out / 'anchor_candidates' / task['task_id'] / source / 'candidates.json').relative_to(out)),
                connections=links, relation='overlapping_support_not_unique_ownership', reviewed=False,
                unlinked_or_ambiguous_cells='Retain Unknown; no automatic semantic merge'))
            image = np.asarray(Image.open(source_folder / 'overlay.png').convert('RGB')).copy()
            image[boundary(labels)] = [255, 225, 20]
            Image.fromarray(image).save(folder / 'overlay.png')
            run = dict(source_run)
            run.update(method=method, source_method=source, independent_inference=False,
                       wall_seconds=seconds, inherited_source_wall_seconds=source_run['wall_seconds'],
                       gpu_peak_allocated_mib=None, gpu_peak_reserved_mib=None,
                       dense_base_cells=len(sizes), boundary_straddling_cells=len(crossings),
                       anchors_changed=False, upper_masks_changed=False, hierarchy_links=len(links),
                       note='Same SAM candidates plus SLIC support links; coverage is not evidence of improved accuracy.')
            new_json(folder / 'run.json', run)


def sam3_phase(out, manifest):
    import torch
    uuid = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not uuid.startswith('GPU-') or ',' in uuid:
        raise ValueError('Use a single explicit GPU UUID')
    initial = gpu_check(uuid, idle=True)
    torch.set_num_threads(2); torch.set_num_interop_threads(1)
    # A hard budget for this experiment, NOT an estimate based on SAM2 usage.
    torch.cuda.set_per_process_memory_fraction(.40, 0)
    config = read(out / 'sam3_environment.json')
    sys.path.insert(0, config['official_code'])
    from sam3.model_builder import build_sam3_image_model
    from sam3.model.sam3_image_processor import Sam3Processor
    checkpoint = Path(config['model_directory']) / 'sam3.pt'
    tokenizer = Path(config['official_code']) / 'sam3/assets/bpe_simple_vocab_16e6.txt.gz'
    assert checkpoint.is_file() and tokenizer.is_file()
    buffer = io.StringIO()
    start = time.monotonic()
    with contextlib.redirect_stdout(buffer):
        model = build_sam3_image_model(checkpoint_path=str(checkpoint), bpe_path=str(tokenizer),
                   load_from_HF=False, device='cuda', enable_inst_interactivity=True, compile=False)
    load_seconds = time.monotonic()-start
    (out / 'sam3_load_stdout.txt').write_text(buffer.getvalue())
    if 'missing_keys=' in buffer.getvalue():
        raise RuntimeError('Official builder reports missing checkpoint keys; refusing random-weight candidates')
    processor = Sam3Processor(model, device='cuda', confidence_threshold=.5)
    auto_reason = 'Official image API exposes text/concept and interactive prompts; no supported no-prompt AutomaticMaskGenerator found in this checkout. Not emulated with text prompts.'
    anchor_concepts = {'table', 'chair', 'refrigerator', 'potted plant', 'monitor', 'sofa', 'globe',
                       'aquarium', 'pendant light', 'plant', 'bowl', 'flower'}
    for task in manifest['tasks']:
        new_json(method_folder(out, task['task_id'], 'sam3_auto') / 'run.json',
                 dict(status='unavailable', task_id=task['task_id'], method='sam3_auto', reason=auto_reason, reviewed=False))
        image = Image.open(out / task['working_image']).convert('RGB')
        before = gpu_check(uuid)
        torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); start = time.monotonic()
        with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
            state = processor.set_image(image)
        torch.cuda.synchronize(); encoding_seconds = time.monotonic()-start
        masks, metadata, prompt_runs = [], [], []
        decode_start = time.monotonic()
        with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
            for concept in task['text_prompts']:
                gpu_check(uuid)
                processor.reset_all_prompts(state)
                torch.cuda.synchronize(); prompt_start = time.monotonic()
                result = processor.set_text_prompt(prompt=concept, state=state)
                torch.cuda.synchronize(); prompt_seconds = time.monotonic()-prompt_start
                found = result['masks'].detach().cpu().numpy().astype(bool).reshape((-1, image.height, image.width))
                scores = result['scores'].float().detach().cpu().numpy().reshape(-1)
                boxes = result['boxes'].float().detach().cpu().numpy().reshape((-1, 4))
                prompt_runs.append(dict(concept=concept, mask_count=len(found), seconds=prompt_seconds, reviewed=False))
                for index, (mask, score, box) in enumerate(zip(found, scores, boxes)):
                    if not mask.any():
                        continue
                    masks.append(mask)
                    metadata.append(dict(category=concept, role='anchor' if concept in anchor_concepts else 'region',
                        prompt_type='fixed_test_reference_rgb_text_concept', prompt_concept=concept,
                        concept_instance_index=index, raw_model_score=float(score), raw_working_box=box.tolist(),
                        source='official_Sam3Processor.set_text_prompt', inter_concept_deduplication=False))
        torch.cuda.synchronize(); decoder_seconds = time.monotonic()-decode_start
        save_masks(out, task, 'sam3_text', masks, metadata, dict(wall_seconds=encoding_seconds+decoder_seconds,
            encoding_seconds=encoding_seconds, decoder_seconds=decoder_seconds, load_seconds=load_seconds,
            gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
            gpu_peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
            gpu_before=before, gpu_after=gpu_check(uuid), prompt_type='fixed_test_reference_rgb_text_concept',
            prompt_count=len(task['text_prompts']), provided_prompt_count=len(task['text_prompts']),
            text_prompts=task['text_prompts'], per_prompt=prompt_runs, confidence_filter_threshold=.5,
            checkpoint=str(checkpoint), bpe_path=str(tokenizer), load_from_HF=False,
            implementation='Official SAM3 PyTorch Sam3Processor concept segmentation', precision='bfloat16 autocast',
            shared_image_encoding_with='sam3_visual', no_cross_concept_deduplication=True))
        print(task['task_id'], 'SAM3 text', len(masks), '%.3fs' % (encoding_seconds+decoder_seconds), flush=True)
        del masks, result
        processor.reset_all_prompts(state)
        before = gpu_check(uuid)
        prompts = task['visual_prompts']
        boxes = np.array([[v * task['working_size'][i % 2] / task['image_size'][i % 2] for i,v in enumerate(p['bbox'])] for p in prompts], dtype=np.float32)
        torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); start = time.monotonic()
        with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
            masks, scores, _ = model.predict_inst(state, point_coords=None, point_labels=None, box=boxes, multimask_output=False)
        torch.cuda.synchronize(); seconds = time.monotonic()-start
        masks = np.asarray(masks, dtype=bool).reshape((-1, image.height, image.width))
        scores = np.asarray(scores).reshape(-1)
        metadata = [dict(p, raw_iou_head_score=float(s), prompt_bbox=p['bbox'], working_prompt_bbox=b.tolist(),
                         source='official_Sam3Image.predict_inst_single_instance_not_concept_search') for p,s,b in zip(prompts,scores,boxes)]
        save_masks(out, task, 'sam3_visual', masks, metadata, dict(wall_seconds=seconds,
            shared_encoding_seconds=encoding_seconds, full_image_compute_seconds=encoding_seconds+seconds,
            encoding_reused=True, load_seconds=load_seconds,
            gpu_peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
            gpu_peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
            gpu_before=before, gpu_after=gpu_check(uuid), prompt_type='fixed_test_reference_rgb_loose_bbox',
            prompt_count=len(prompts), provided_prompt_count=len(prompts), checkpoint=str(checkpoint),
            bpe_path=str(tokenizer), load_from_HF=False, precision='bfloat16 autocast',
            implementation='Official SAM3 interactive instance branch, multimask_output=False'))
        print(task['task_id'], 'SAM3 visual', len(masks), '%.3fs cached decoder' % seconds, flush=True)
        del state, masks; gc.collect(); torch.cuda.empty_cache()
    new_json(out / 'sam3_resource_summary.json', dict(initial=initial, final=gpu_check(uuid),
             process_memory_cap_fraction=.40, serial=True, cpu_threads=2, load_seconds=load_seconds,
             checkpoint=str(checkpoint), load_from_HF=False, official_builder_missing_keys_reported=False))
    new_json(out / 'sam3_status.json', dict(status='available', text='available', visual='available',
             automatic='unavailable', automatic_reason=auto_reason, reviewed=False))


def diagnostics_phase(out, manifest):
    for task in manifest['tasks']:
        for method in ['sam2_auto', 'sam2_prompted', 'sam3_text', 'sam3_visual']:
            folder=method_folder(out, task['task_id'], method)
            if not (folder/'mask_metadata.json').exists(): continue
            data=read(folder/'mask_metadata.json')
            rows=sorted([r for r in data['regions']+data['anchors'] if r.get('region_role')!='unknown_fallback'], key=lambda r:r['id'])
            masks=np.load(folder/'working_masks.npz', allow_pickle=False)['masks']
            assert len(rows)==len(masks)
            for role in ['anchor', 'region']:
                target=folder/(role+'_overlay.png')
                if target.exists(): continue
                view=work_image(out, task).copy(); rng=np.random.default_rng(9064)
                selected=[]
                for row,mask in zip(rows,masks):
                    if row.get('role', 'region') != role: continue
                    color=rng.integers(50,245,size=3)
                    view[mask]=np.uint8(.6*view[mask]+.4*color)
                    view[boundary(mask.astype(np.uint8))]=color
                    selected.append((row,mask))
                image=Image.fromarray(view);draw=ImageDraw.Draw(image)
                for row,mask in selected:
                    x,y,_,_=bbox(mask)
                    label=row['id'].split('_')[-1]+': '+str(row.get('category') or 'unknown class')
                    draw.text((x,y),label,fill='white',stroke_width=1,stroke_fill='black')
                if not selected: draw.text((12,12),'No class-assigned '+role+' candidates',fill='white',stroke_width=1,stroke_fill='black')
                image.save(target)
            areas=masks.sum(axis=(1,2)); total=masks.shape[1]*masks.shape[2]
            new_json(folder/'quality_diagnostics.json', dict(coarse_area_threshold_fraction=.02,
                large_region_masks=int(sum(a>=.02*total and r.get('role','region')!='anchor' for a,r in zip(areas,rows))),
                raw_regions=len(data['regions'])-int(any(r.get('region_role')=='unknown_fallback' for r in data['regions'])),
                unknown_regions=int(any(r.get('region_role')=='unknown_fallback' for r in data['regions'])),
                anchors=len(data['anchors']), semantic_consistency='unreviewed',
                over_under_segmentation_accuracy=None, source='Candidate diagnostics only', reviewed=False))


def report_phase(out, manifest):
    rows = []
    for task in manifest['tasks']:
        for method in METHODS:
            path = method_folder(out, task['task_id'], method) / 'run.json'
            if path.exists():
                rows.append(read(path))
            else:
                unavailable = read(out / 'sam3_status.json') if method.startswith('sam3') or method == 'slic_sam3' else {}
                rows.append(dict(task_id=task['task_id'], method=method, status='unavailable',
                                 reason=unavailable.get('reason', 'No completed local inference'), reviewed=False))
    fields = ['task_id', 'method', 'status', 'mask_count', 'region_count', 'anchor_count', 'dense_base_cells',
              'dense_coverage_with_fallback', 'raw_mask_union_coverage', 'unknown_residual_fraction',
              'reviewed_unknown_fraction', 'reviewed_semantic_coverage', 'overlap_fraction', 'duplicate_pair_count',
              'partial_overlap_pair_count', 'tiny_mask_count', 'boundary_pixel_fraction', 'boundary_straddling_cells',
              'wall_seconds', 'inference_seconds', 'encoding_seconds', 'decoder_seconds', 'shared_encoding_seconds',
              'full_image_compute_seconds', 'load_seconds', 'gpu_peak_allocated_mib', 'gpu_peak_reserved_mib',
              'prompt_type', 'prompt_count', 'provided_prompt_count', 'human_reviewed_prompt_count', 'prompt_author', 'reason']
    summary_path = out / 'summary.csv'
    if summary_path.exists(): raise FileExistsError(summary_path)
    with summary_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in rows:
            item = dict(row)
            if row['status'] == 'available':
                item.update(duplicate_pair_count=len(row.get('duplicate_pairs_iou_ge_09', [])),
                            partial_overlap_pair_count=len(row.get('partial_overlap_pairs', [])))
            writer.writerow(item)
    new_json(out / 'summary.json', dict(results=rows, reviewed=False, render_used=False,
        no_accuracy_without_review=True, scoring_performed=False, statistics_scope='Working grid, maximum edge 1536px'))
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>五场景 Region Extraction 对照</title>',
             '<style>body{font:15px system-ui;margin:20px;color:#222}.scroll{overflow-x:auto}table{border-collapse:collapse;table-layout:fixed;min-width:2450px;width:100%}td,th{border:1px solid #bbb;padding:8px;vertical-align:top;width:290px}img{width:100%;height:auto}small{display:block}code{overflow-wrap:anywhere}.na{background:#eee;padding:15px}summary{cursor:pointer}</style>',
             '<h1>五场景 Reference Region Extraction</h1><p>仅原始 RGB；所有候选 reviewed=false、mask_reviewed=false、reliability=0。无正式重建评分，无人工 GT，因此无准确率 IoU/Boundary F1。Unknown 残余与审核语义 Unknown 是不同概念；审核语义 Unknown 始终100%。</p>',
             '<p><a href="summary.csv">统计 CSV</a> · <a href="summary.json">完整统计</a> · <a href="report.md">报告</a> · <a href="manifest.json">来源与全部提示</a></p>']
    columns = [('Reference', None), ('SLIC (100 / 200 / 400)', 'slic'), ('SAM2 Auto', 'sam2_auto'),
               ('SAM2 Prompted', 'sam2_prompted'), ('SAM3 Auto', 'sam3_auto'), ('SAM3 Text', 'sam3_text'),
               ('SAM3 Visual', 'sam3_visual'), ('Combination', 'combination')]
    by_key = {(r['task_id'], r['method']):r for r in rows}

    def cell(task, method):
        row = by_key[task['task_id'], method]
        if row['status'] != 'available':
            return '<div class="na">N/A: '+html.escape(row.get('reason', 'Unavailable'))+'</div>'
        folder = method_folder(out, task['task_id'], method).relative_to(out).as_posix()
        content = f'<b>{html.escape(method)}</b><a href="{folder}/overlay.png"><img loading="lazy" src="{folder}/overlay.png"></a>'
        content += '<small>Masks / cells: %s; 上层Regions: %s; Anchors: %s<br>原始覆盖 %.2f%%; 残余Unknown %.2f%%; overlap %.2f%%<br>耗时 %.3fs; 峰值显存 %s MiB<br>%s; prompts=%s</small>' % (
            row.get('mask_count'), row.get('region_count'), row.get('anchor_count'), 100*row.get('raw_mask_union_coverage', 0),
            100*row.get('unknown_residual_fraction', 0), 100*row.get('overlap_fraction', 0), row.get('wall_seconds', 0),
            str(round(row['gpu_peak_allocated_mib'], 1)) if row.get('gpu_peak_allocated_mib') is not None else 'N/A',
            html.escape(row.get('prompt_type', 'none')), row.get('prompt_count', 0))
        content += f'<a href="{folder}/run.json">运行/原始分数元数据</a>'
        if (out/folder/'anchor_overlay.png').exists():
            content += f'<details><summary>Anchor 边界 / 区域分层</summary><a href="{folder}/anchor_overlay.png"><img loading="lazy" src="{folder}/anchor_overlay.png"></a><a href="{folder}/region_overlay.png">Region-only Overlay</a> · <a href="{folder}/quality_diagnostics.json">候选诊断</a></details>'
        if (out / folder / 'unknown_overlay.png').exists(): content += f' · <a href="{folder}/unknown_overlay.png">残余Unknown</a>'
        if (out / folder / 'hierarchy.json').exists(): content += f' · <a href="{folder}/hierarchy.json">多粒度联系</a>'
        return content

    for task in manifest['tasks']:
        parts.append('<h2>'+task['task_id']+'</h2><div class="scroll"><table><tr>'+''.join('<th>'+c[0]+'</th>' for c in columns)+'</tr><tr>')
        for title, method in columns:
            if method is None:
                ref = html.escape(task['reference_copy']); prompt = 'references/'+task['task_id']+'/prompts_overlay.png'
                content = f'<a href="{ref}"><img loading="lazy" src="{ref}"></a><small>Original: {task["image_size"]}; working: {task["working_size"]}</small>'
                content += f'<details><summary>参考侧统一候选框（不是GT）</summary><img loading="lazy" src="{prompt}"><a href="references/{task["task_id"]}/prompts.json">所有 bbox / text prompts</a></details>'
            elif method == 'slic': content = ''.join(cell(task, 'slic_'+str(n)) for n in [100, 200, 400])
            elif method == 'combination': content = cell(task, 'slic_sam2')+cell(task, 'slic_sam3')
            else: content = cell(task, method)
            parts.append('<td>'+content+'</td>')
        parts.append('</tr></table></div>')
    parts.append('</html>')
    (out / 'comparison.html').write_text('\n'.join(parts))
    markdown = ['# 五场景 Reference Region Extraction 对照', '',
        '本轮仅生成参考 RGB 的候选。没有运行 Agent、Blender、VLM 或重建评分，也没有更改正式 Evidence Extraction、Runtime blocked 状态、五类能量或权重。', '',
        '## 来源与坐标', '',
        'Inventory → run config.task.path → input.json.task_id/files → dataset task.json.reference_images 已逐图核对；路径见 [manifest.json](manifest.json)。仅从原始 RGB 制定提示，没有读取 Agent Render。', '',
        '| 任务 | 原始尺寸 | 工作尺寸 | 固定测试候选框 | 文本概念 |',
        '|---|---|---|---:|---:|']
    for task in manifest['tasks']:
        markdown.append('| %s | %s | %s | %d | %d |' % (task['task_id'], task['image_size'], task['working_size'], len(task['visual_prompts']), len(task['text_prompts'])))
    markdown += ['', 'SLIC 与模型输入都采用同一张最长边≤1536的工作 RGB。二值 Mask 最近邻恢复到原始网格，bbox 是恢复后 Mask 的原始像素 xyxy；这不恢复降采样丢失的细节。统计采用明确记录的工作网格，Overlay 也采用工作尺寸。', '',
        '## 实测候选统计', '',
        '下表的 Unknown 是原始 Mask 并集之外的残余，不是语义正确率。补入 Unknown 后基础覆盖为100%；所有候选未审核，因此审核语义覆盖始终0%、审核语义 Unknown 始终100%。SLIC 100%仅表示视觉网格覆盖。Regions计数包含一个非空残余Unknown；完整逐Mask信息保存在 candidates.json / mask_metadata.json。', '',
        '| 任务 | 方法 | Mask/视觉块 | 原始覆盖 | 残余Unknown | 重叠像素 | 重复对 | Anchors |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        if row['status'] == 'available' and row['method'] not in ['slic_100', 'slic_400', 'slic_sam2', 'slic_sam3']:
            markdown.append('| %s | %s | %d | %.2f%% | %.2f%% | %.2f%% | %d | %d |' % (
                row['task_id'], row['method'], row['mask_count'], row['raw_mask_union_coverage']*100,
                row['unknown_residual_fraction']*100, row['overlap_fraction']*100,
                len(row.get('duplicate_pairs_iou_ge_09', [])), row['anchor_count']))
    markdown += ['', '重复对阈值为候选间IoU≥0.9，包含关系单独记录，部分重叠也单独记录。它们是候选结构诊断，不是针对GT的IoU，也不能直接视为分割错误或空间冲突。没有人工审核Mask，accuracy IoU、Boundary F1均为N/A。', '',
        '## 公平性、时间与资源', '',
        '- SLIC不使用人工提示。SAM2 Auto采用固定16×16自动正点网格，单层无裁剪、每批8点，pred-IoU阈值0.88、稳定性阈值0.95、官方NMS阈值0.7；所有图相同。原始网格保留在run.json。官方流水线NMS后单个Mask与原始点的对应没有返回，明确记unknown，不反推。',
        '- SAM2 Prompted与SAM3 Visual使用逐项相同的原图候选bbox，均由助手静态查看RGB拟定为固定测试松框，未经人工确认，不是人工GT。SAM3 Visual使用官方predict_inst单实例分支，multimask_output=False；不使用概念搜索框接口冒充实例提示。',
        '- SAM3 Text是另一组由助手从RGB拟定的固定概念提示，保存每图完整词表、每词耗时、实例数、原始分数及框。保留跨概念重复，不以模型分数当可靠性；置信阈值0.5只用于官方候选过滤。不能与无需人工提示的方法直接排优劣。',
        '- 两模型原始参考工作图及bbox相同，但内部编码分辨率不同（SAM2为1024×1024，SAM3为1008×1008）；SAM2使用FP32，SAM3采用官方支持的BF16 autocast。这些设置均保留，未进行数值精度或阈值搜索。',
        '- SLIC+SAM2与SLIC+SAM3均以同一SLIC-200网格为基础，分别保留对应统一框提示的原始SAM Mask。联系记录像素支持比例，可以多对多；不切碎全部超像素、不强制唯一语义归属、不自动合并或覆盖Unknown。上层Mask/Anchor未变化，因此组合没有新增模型准确性证据。',
        '- GPU只使用复查空闲的单张A100 40GB（UUID见资源JSON），SAM2与SAM3严格串行；CPU线程2。SAM2显存硬预算20%、SAM3硬预算40%，这是资源上限而非SAM3需求估计。实际分配/保留峰值逐项保存。', '',
        '| 方法 | 已完成图数 | 平均实际调用秒 | 最大已分配MiB | 最大保留MiB |',
        '|---|---:|---:|---:|---:|']
    for method in METHODS:
        available = [r for r in rows if r['method']==method and r['status']=='available']
        if not available: continue
        peak = [r['gpu_peak_allocated_mib'] for r in available if r.get('gpu_peak_allocated_mib') is not None]
        reserved = [r['gpu_peak_reserved_mib'] for r in available if r.get('gpu_peak_reserved_mib') is not None]
        markdown.append('| %s | %d | %.3f | %s | %s |' % (method, len(available), np.mean([r['wall_seconds'] for r in available]),
            '%.1f'%max(peak) if peak else 'N/A', '%.1f'%max(reserved) if reserved else 'N/A'))
    markdown += ['', '时间口径：SLIC是算法调用；SAM2 Auto共用已加载模型，wall不含一次模型加载；SAM2 Prompted复用已有适配器，wall含本次适配器加载、预处理和推理，另存纯forward时间。SAM3 Text含图像编码与该图全部概念查询；SAM3 Visual实际wall仅含复用编码后的实例分支调用，shared_encoding_seconds及full_image_compute_seconds给出编码成本。组合wall仅含CPU支持联系构建，另记继承源耗时。不能把这些不同口径的wall当作公平的模型速度排名。', '',
        '## 不可用项与环境', '']
    unavailable = {}
    for row in rows:
        if row['status'] != 'available': unavailable.setdefault(row['method'], set()).add(row.get('reason', 'unknown'))
    if unavailable:
        for method, reasons in unavailable.items(): markdown.append('- '+method+': '+'; '.join(sorted(reasons)))
    else: markdown.append('- 所列方法均有真实运行结果。')
    markdown += ['', 'SAM3权重唯一下载源为[ModelScope facebook/sam3](https://www.modelscope.cn/models/facebook/sam3)，仅sam3.pt和必要配置，未重复下载model.safetensors。代理绕过与DNS映射只作用于下载进程，未修改系统配置。下载记录见sam3_download.json。使用[官方SAM3源码](https://github.com/facebookresearch/sam3)，本地checkpoint、显式load_from_HF=False，BPE来自官方代码资源。没有申请模型权限、Hugging Face模型下载或自建哈希校验。', '',
        '额外依赖经用户授权装在独立/tmp环境，复用现有PyTorch；环境路径与安装日志保留。官方源码的包元数据NumPy上限与现有Python3.13环境可能不一致，没有为满足元数据降级共享NumPy/PyTorch；这里只验证实际源码导入、checkpoint加载与本轮图像推理，不声称完整训练/视频依赖兼容。', '',
        '## 逐图静态观察（均不是人工GT审核）', '']
    notes = read(out/'inspection_notes.json') if (out/'inspection_notes.json').exists() else {}
    for task, observations in notes.get('observations', {}).items():
        markdown.append('### '+task+'\n')
        markdown.extend('- '+observation for observation in observations)
        markdown.append('')
    markdown += ['## 结论与适用范围', '',
        '1. 大面积Region：优先查看带明确区域意图的SAM提示结果；SLIC适合作为稳定全图覆盖基础，几百块切分不是最终语义Region。书柜或绘画带状纹理应保留集合Region候选，完整程度需要人工审核。',
        '2. 重要Anchor：统一框提示提供可逐实例对比的条件；SAM2/SAM3实例Mask均需审核接触边界、透明椅、细腿、花瓣与枝叶。没有人工边界GT，不能宣布总体最优。',
        '3. SAM3重复实例：以每词实际实例数和逐图观察为依据；一次chair查询得到多个候选是额外发现能力，不等于召回率提升，重复/误检也必须保留。与SAM2人工逐椅框比较时必须计入提示差异。',
        '4. 过/欠分割：SLIC在连续表面与复杂笔触上明显切碎；SAM候选可能把物体集合与柜体混合，也可能只提取局部、漏掉椅子或大片背景。连通分量多也可能来自真实遮挡，不能自动记错。',
        '5. 组合价值：用于保存覆盖与候选层级值得保留；本实验的简单联系不会改善原Mask边界，也没有证明分割准确率更高。不做不受审核的语义合并。',
        '6. 可自动化：密集视觉网格、模型候选、来源/坐标保存、覆盖/重叠/重复统计、预览与清单检查。仍需人工：语义类别、重要性、组/实例粒度、完整性、边界与冲突裁决。',
        '7. 层级：Global原图 → Dense SLIC多粒度底层 → 可重叠Coarse Regions/集合 → 独立Anchor实例；以支持联系而非唯一父节点表达。残余及不能可靠解释的内容保留Unknown；所有reviewed=false、mask_reviewed=false、reliability=0。', '',
        '## 复现', '', '从项目根目录运行，每轮选择不存在的新目录。以下路径需要当前临时环境仍存在；清理/tmp后需按已授权隔离方案重建。', '', '```bash',
        'export REGION_OUT=results/multiscene_region_extraction_new',
        'export PYTHONPATH=/tmp/project_e_slic_deps_rlhjhcvv',
        'export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase prepare',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase slic',
        '# 必须先复查空闲GPU；下列UUID不是GPU预约。只允许顺序执行。',
        'export CUDA_VISIBLE_DEVICES=GPU-158426a4-6684-7863-8cbe-ed6595f97683',
        'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1',
        'timeout 600 /home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase sam2',
        'cp results/multiscene_region_extraction/sam3_environment.json "$REGION_OUT"/',
        'timeout 600 /tmp/project_e_sam3_env_yhqvf4jo/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase sam3',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase combine',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase diagnostics',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase report',
        '/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase validate',
        '```', '',
        '本轮已执行15次SLIC、五图SAM2 Auto与五图SAM2 Prompted；SAM3完成情况见上表及sam3.log。静态检查结果见[validation.json](validation.json)。未计算未经审核的准确率或五能量/重建分数。']
    (out/'report.md').write_text('\n'.join(markdown)+'\n')


def validate_phase(out, manifest):
    from html.parser import HTMLParser
    from urllib.parse import unquote, urlsplit
    from e_harness.benchmark_evidence import load_document
    # Small controlled cases validate union, residual, overlap and duplicate
    # meanings without claiming segmentation accuracy from unreviewed masks.
    a = np.zeros((4, 4), bool); a[:, :3] = True
    b = np.zeros((4, 4), bool); b[:, 2:] = True
    stats = mask_statistics(np.array([a, b]))
    assert stats['raw_mask_union_coverage'] == 1 and stats['overlap_fraction'] == .25
    assert stats['unknown_residual_fraction'] == 0 and stats['accuracy_iou'] is None
    assert len(mask_statistics(np.array([a, a]))['duplicate_pairs_iou_ge_09']) == 1
    assert mask_statistics(np.zeros((0, 4, 4), bool))['unknown_residual_fraction'] == 1
    unique_ids, masks_checked, docs_checked = set(), 0, 0
    for path in sorted(out.glob('*_candidates/*/*/candidates.json')):
        data = read(path); docs_checked += 1
        assert data['reviewed'] is False and data['inventory_complete'] is False
        width, height = data['image_size']
        for row in data.get('regions', []) + data.get('anchors', []):
            assert row['id'] not in unique_ids
            unique_ids.add(row['id'])
            assert row['reviewed'] is False and row['mask_reviewed'] is False and row['reliability'] == 0
            x0, y0, x1, y1 = row['bbox']
            assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
            with Image.open(path.parent / row['mask']) as mask:
                assert mask.size == (width, height)
                assert list(mask.getbbox()) == row['bbox']
                palette = mask.getcolors(maxcolors=3)
                assert palette is not None and {value for count,value in palette}.issubset({0, 255})
            masks_checked += 1
    # Exercise the actual existing evidence loader on a small real document.
    for path in sorted((out/'anchor_candidates/bw_0043').glob('*/candidates.json')):
        loaded = load_document(path)
        assert loaded['reviewed'] is False
        assert all(row['mask'].shape == (loaded['image_size'][1], loaded['image_size'][0]) for row in loaded['anchors'])
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.links=[]
        def handle_starttag(self, tag, attrs):
            self.links.extend(v for k,v in attrs if k in ('href', 'src') and v)
    parser=Links(); parser.feed((out/'comparison.html').read_text())
    links=0
    for value in parser.links:
        parsed=urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path: continue
        assert (out/unquote(parsed.path)).is_file(), value
        links += 1
    for task in manifest['tasks']:
        for n in [100, 200, 400]:
            folder = method_folder(out, task['task_id'], 'slic_'+str(n))
            labels = np.load(folder/'dense_labels.npz', allow_pickle=False)['labels']
            assert list(labels.shape[::-1]) == task['working_size'] and labels.min() == 0
            assert read(folder/'run.json')['reviewed_semantic_coverage'] == 0
    for path in out.glob('methods/*/*/run.json'):
        row=read(path)
        assert row['reviewed'] is False
        if row['status']=='available': assert row['reviewed_semantic_coverage'] == 0
    hierarchy_links=0
    for path in out.glob('methods/*/*/hierarchy.json'):
        data=read(path)
        assert data['reviewed'] is False
        for field in ['dense_basis','upper_regions','anchors']: assert (out/data[field]).is_file()
        n=int(np.load(out/data['dense_basis'],allow_pickle=False)['labels'].max())+1
        for link in data['connections']:
            assert link['mask_id'] in unique_ids and link['reviewed'] is False
            assert all(0<=cell['label']<n and 0<cell['fraction']<=1 for cell in link['dense_cells'])
            hierarchy_links+=1
    result=dict(passed=True, documents=docs_checked, original_grid_binary_masks=masks_checked,
                unique_candidate_ids=len(unique_ids), html_links=links, controlled_statistic_cases=4,
                hierarchy_mask_links=hierarchy_links,
                actual_evidence_loader_checked=True, scoring_performed=False,
                all_candidates_unreviewed=True, no_agent_render_used=True)
    new_json(out/'validation.json', result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['prepare', 'slic', 'sam2', 'sam3', 'combine', 'diagnostics', 'report', 'validate'], required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    if args.phase == 'prepare': prepare(out)
    else:
        manifest = read(out / 'manifest.json')
        if args.phase == 'slic': slic_phase(out, manifest)
        elif args.phase == 'sam2': sam2_phase(out, manifest)
        elif args.phase == 'sam3': sam3_phase(out, manifest)
        elif args.phase == 'combine': combine_phase(out, manifest)
        elif args.phase == 'diagnostics': diagnostics_phase(out, manifest)
        elif args.phase == 'report': report_phase(out, manifest)
        elif args.phase == 'validate': validate_phase(out, manifest)


if __name__ == '__main__':
    main()
