"""Small manifest adapter for static RGB evaluation. Never launches a model or renderer."""
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .benchmark_config import POLICY, write_json
from .benchmark_evidence import area_mask, load_document, reliability
from .benchmark_metrics import numerical_errors, perceptual_error


def fit_render(image, size):
    """Existing full-frame fit: geometry only, centered padding, no content alignment."""
    scale = min(size[0]/image.width, size[1]/image.height)
    resized = [max(1, round(image.width*scale)), max(1, round(image.height*scale))]
    offset = [(size[i]-resized[i])//2 for i in (0, 1)]
    rgba = image.convert('RGBA').resize(tuple(resized), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, (145, 145, 145))
    canvas.paste(rgba.convert('RGB'), tuple(offset))
    valid = np.zeros(size[::-1], bool)
    x, y = offset
    valid[y:y+resized[1], x:x+resized[0]] = np.asarray(rgba.getchannel('A')) == 255
    return np.asarray(canvas), valid, dict(original_size=list(image.size), common_size=list(size),
        nominal_scale=scale, resized_size=resized, offset_xy=offset, padding_is_not_observation=True,
        content_alignment=False,
        transform='uniform full-frame fit with integer rounding, centered letterbox; no crop/search/warp')


def optional_document(path, *, evidence=False):
    if path is None:
        return None, dict(status='unavailable', reason='Optional input not supplied', source=None)
    try:
        document = load_document(path) if evidence else json.loads(path.read_text())
        if not isinstance(document, dict):
            raise ValueError('Expected a JSON object')
        return document, dict(status='available', source=str(path), reviewed=document.get('reviewed'))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, dict(status='unavailable', source=str(path), reason=f'{type(exc).__name__}: {exc}')


def prepare_images(reference, rendered, coordinates):
    if coordinates.get('convention') != 'reference_pixel_xyxy':
        raise ValueError('Declare convention=reference_pixel_xyxy (top-left edges, x right, y down)')
    mapping = coordinates.get('render_mapping')
    if mapping not in ('identity', 'uniform_fit') or not str(coordinates.get('basis', '')).strip():
        raise ValueError('Explicit render_mapping and coordinate basis required; no automatic alignment')
    with Image.open(reference) as image:
        rgba = image.convert('RGBA')
        a = np.asarray(rgba.convert('RGB'))
        valid_reference = np.asarray(rgba.getchannel('A')) == 255
    with Image.open(rendered) as image:
        native_size = list(image.size)
        if mapping == 'identity':
            if image.size != rgba.size:
                raise ValueError('Identity requires equal image sizes; no legal size conversion was supplied')
            other = image.convert('RGBA')
            b = np.asarray(other.convert('RGB'))
            valid_render = np.asarray(other.getchannel('A')) == 255
            transform = dict(original_size=native_size, common_size=list(rgba.size),
                resized_size=native_size, offset_xy=[0, 0], nominal_scale=1.,
                content_alignment=False, padding_is_not_observation=True, transform='identity')
        else:
            b, valid_render, transform = fit_render(image, rgba.size)
    for key, value in coordinates.get('expected_transform', {}).items():
        if key not in transform or transform[key] != value:
            raise ValueError('Recorded coordinate transform differs: '+key)
    valid = valid_reference & valid_render
    if valid.sum() < POLICY['min_pixels']:
        raise ValueError('Insufficient jointly valid observed pixels')
    return a, b, valid, transform, native_size


def region_diagnostics(a, b, evidence, valid, extract=None):
    """Fixed-domain numerical diagnostics do not approve semantic candidates."""
    safe = valid.copy()
    safe[:, :-1] &= valid[:, 1:]
    safe[:-1, :] &= valid[1:, :]
    count = np.zeros(valid.shape, np.uint16)
    rows, masks = [], {}
    for row in evidence['regions']:
        if row.get('source') == 'deterministic RGB grid':
            continue
        mask = area_mask(row, valid.shape)
        masks[row['id']] = mask
        count += (mask > 0) & valid
        observed = mask * safe
        values, detail = numerical_errors(a, b, observed) if observed.sum() >= POLICY['min_pixels'] else ({}, {})
        perceptual, perceptual_reason = (perceptual_error(a,b,observed,extract)
            if observed.sum() >= POLICY['min_pixels'] else (None,'Insufficient valid Region pixels'))
        rows.append(dict(id=row['id'], description=row.get('description', row.get('name')),
            reviewed=row.get('reviewed', False), evidence_reliability=reliability(row),
            reference_pixels=float(mask.sum()), valid_pixel_weight=float((mask*valid).sum()),
            measurement_pixel_weight=float(observed.sum()),
            appearance=values.get('appearance'), perceptual=perceptual,
            perceptual_reason=perceptual_reason,
            numerical_proxies=dict(spatial=values.get('spatial'), statistical=values.get('statistical')),
            measurement_scope=detail.get('scope'), semantic=None,
            semantic_reason='No new semantic validator; candidate ROI is not reviewed category evidence',
            energy_contribution=False, usage='provisional/debug fixed-domain diagnostic'))
    return rows, masks, dict(named_region_count=len(rows), overlap_pixels=int((count>1).sum()),
        overlap_fraction_of_valid=float((count>1).sum()/valid.sum()),
        max_multiplicity=int(count.max()), unassigned_valid_pixels=int(((count==0)&valid).sum()),
        local_aggregate=None, reason='Per-ROI losses are not summed. Overlapping named scopes are withheld from energy aggregation; Global/Dense remain available.')


def comparison_png(path, a, b, masks, diagnostics, report):
    """A clear two-column full-image and fixed-coordinate crop comparison."""
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        font = ImageFont.truetype(font_path, 19)
    except OSError:
        font = ImageFont.load_default()
    width, cell_height = 720, 430
    canvas = Image.new('RGB', (width*2, (len(masks)+1)*(cell_height+58)+78), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.text((15, 8), 'Offline diagnostic | fixed Reference coordinates | no formal score', fill='black', font=font)
    draw.text((15, 34), report['scene_validity']['camera_protocol']+' | Perceptual N/A (no inference)', fill='black', font=font)
    panels = [('Reference RGB', 'Saved Agent Render', a, b)]
    by_id = {r['id']:r for r in diagnostics}
    for key, mask in masks.items():
        ys, xs = np.nonzero(mask > 0)
        if not len(xs):
            continue
        bounds = (slice(ys.min(), ys.max()+1), slice(xs.min(), xs.max()+1))
        images = []
        for rgb in (a, b):
            marked = rgb.copy()
            support = mask > 0
            edge = support & (~np.roll(support, 1, 0) | ~np.roll(support, -1, 0)
                              | ~np.roll(support, 1, 1) | ~np.roll(support, -1, 1))
            marked[edge] = [255, 175, 25]
            images.append(marked[bounds])
        value = by_id[key]['appearance']
        text = 'N/A' if value is None else f'{value:.5f}'
        panels.append((key+' Reference / unchanged ROI', key+' Render / Appearance '+text, *images))
    for index, (ta, tb, ia, ib) in enumerate(panels):
        top = 78+index*(cell_height+58)
        for col, (title, array) in enumerate(((ta, ia), (tb, ib))):
            draw.text((col*width+12, top), title, fill='black', font=font)
            image = Image.fromarray(array)
            image.thumbnail((width-24, cell_height), Image.Resampling.LANCZOS)
            canvas.paste(image, (col*width+(width-image.width)//2, top+36))
    canvas.save(path)


def run_manifest(manifest_path, output, *, extract=None, extract_provenance=None):
    """Default remains pure offline. An explicit local extractor permits existing DINO metrics.

    No manifest boolean/path can start inference. The calling controller must load
    the extractor itself and supply its provenance; formulas/weights are unchanged.
    """
    if extract is not None and not extract_provenance:
        raise ValueError('Explicit extractor provenance is required')
    from .benchmark import evaluate  # keep the legacy CLI import acyclic
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Output exists; historical results cannot be overwritten')
    manifest = json.loads(manifest_path.read_text())
    def source(value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Input paths must be strings, relative to the manifest or absolute')
        return (manifest_path.parent / value).resolve()
    tick = time.monotonic()
    ref_path, render_path = (source(manifest[key]) for key in ('reference_rgb', 'render_rgb'))
    a, b, valid, transform, native_size = prepare_images(ref_path, render_path, manifest.get('coordinates', {}))
    if manifest.get('valid_pixels'):
        with Image.open(source(manifest['valid_pixels'])) as image:
            supplied = np.asarray(image.convert('L'))
        if supplied.shape != valid.shape or not np.isin(supplied, [0, 255]).all():
            raise ValueError('valid_pixels must be a binary PNG on the Reference grid')
        valid &= supplied == 255
    if valid.sum() < POLICY['min_pixels']:
        raise ValueError('Insufficient jointly valid observed pixels')
    ref_source = source(manifest.get('reference_evidence'))
    # Required evidence must fail visibly; optional unavailable inputs do not stop RGB measures.
    reference = load_document(ref_source) if ref_source else None
    inputs, states = {}, {}
    for key in ('render_evidence', 'geometry', 'triage', 'rules', 'render_metadata'):
        inputs[key], states[key] = optional_document(source(manifest.get(key)), evidence=key=='render_evidence')
    if inputs['render_evidence'] is not None:
        from .benchmark_evidence import build_reference
        try:
            build_reference(b, inputs['render_evidence'])  # validation only; do not invent Render grid evidence
        except (ValueError, KeyError, TypeError) as exc:
            inputs['render_evidence'] = None
            states['render_evidence'].update(status='unavailable', reason=f'{type(exc).__name__}: {exc}')
    # Bad optional structural schemas must not discard usable Observation results.
    from .benchmark_structure import structural_report
    try:
        structural_report(inputs['geometry'], inputs['triage'], inputs['rules'])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        states['structural_inputs'] = dict(status='unavailable', reason=f'{type(exc).__name__}: {exc}')
        inputs.update(geometry=dict(status='unavailable', reason=states['structural_inputs']['reason']), triage=None, rules=None)
    report, evidence = evaluate(a, b, reference, inputs['render_evidence'],
        geometry=inputs['geometry'], triage=inputs['triage'], rules=inputs['rules'],
        render_metadata=inputs['render_metadata'], valid_mask=valid, withhold_region_overlaps=True,
        extract=extract)
    diagnostics = {}
    for key in ('groups', 'structural_layout'):
        payload, state = optional_document(source(manifest.get('diagnostics', {}).get(key)))
        diagnostics[key] = dict(**state, evidence=payload, energy_contribution=False,
            interpretation='Attached verbatim for audit; review, applicability and calibrated comparison are not inferred')
    # Result import only. Running the offline entry never launches a verifier.
    verification, state = optional_document(source(manifest.get('vlm_verification')))
    unmatched_verification = verification
    if verification is not None:
        try:
            from .verification_adapter import validate_diagnostics
            verification = validate_diagnostics(verification)
            pair = verification.get('image_pair')
            if not isinstance(pair, dict) or set(pair) != {'reference_rgb', 'render_rgb'}:
                raise ValueError('Verification has no explicit image_pair binding; historical answers are not assigned to current images')
            verification_path = source(manifest['vlm_verification'])
            for key, expected in (('reference_rgb', ref_path), ('render_rgb', render_path)):
                value = pair[key]
                if not isinstance(value, str) or (verification_path.parent/value).resolve() != expected:
                    raise ValueError('Verification image_pair differs from manifest: '+key)
            for side, key in (('reference', 'reference_rgb'), ('render', 'render_rgb')):
                binding = verification[side].get('image_binding')
                if binding and (verification_path.parent/binding['source_rgb']).resolve() != (ref_path if side=='reference' else render_path):
                    raise ValueError('Recorded model image source conflicts with image_pair: '+side)
            state['pair_binding'] = 'matched_paths_unverified_content'
            unmatched_verification = None
        except (ValueError, KeyError, TypeError, AttributeError, ImportError) as exc:
            verification = None
            state.update(status='unavailable', reason=f'{type(exc).__name__}: {exc}')
    diagnostics['vlm_verification'] = dict(**state, evidence=verification,
        unmatched_evidence=unmatched_verification, applicable_to_current_pair=verification is not None,
        energy_contribution=False, interpretation='Diagnostic-only imported answers; no model invocation, review promotion or numeric Energy mapping')
    regions, masks, overlaps = region_diagnostics(a, b, evidence, valid, extract)
    camera = report['scene_validity']
    metadata = inputs['render_metadata'] or {}
    declared_resolution = metadata.get('resolution')
    if declared_resolution is None and isinstance(metadata.get('render'), dict):
        r = metadata['render']
        try:
            percentage = r.get('percentage', 100)/100
            if 'resolution_x' in r and 'resolution_y' in r:
                declared_resolution = [int(r['resolution_x']*percentage), int(r['resolution_y']*percentage)]
        except (ValueError, TypeError, OverflowError):
            camera['reasons'].append('Recorded resolution fields are invalid; resolution consistency unavailable')
            camera['reason'] = '; '.join(camera['reasons'])
    resolution_match = (declared_resolution == native_size) if isinstance(declared_resolution,list) else None
    if resolution_match is False:
        camera['reasons'].append('Recorded camera resolution differs from original Render RGB')
        camera['reason'] = '; '.join(camera['reasons'])
    for record in report['metric_records']:
        record['evidence_category'] = ('synthetic_oracle' if manifest.get('evidence_category')=='synthetic_oracle'
            else 'unreviewed_candidate' if record['q']==0 else 'conditional_core_measurement')
        record['measurement_available'] = record['value'] is not None
    report.update(usage='provisional/debug', reviewed=False, formal_eligible=False,
        evidence_category=manifest.get('evidence_category', 'unverified_offline'),
        diagnostics=dict(**diagnostics, fixed_region_measurements=regions, region_overlap=overlaps),
        coordinates=dict(**manifest['coordinates'], applied_transform=transform,
            valid_pixels=int(valid.sum()), canvas_pixels=int(valid.size), valid_mask='valid_pixels.png',
            measurement_pixels=report['error_diagnostics']['measurement_pixels'],
            support_rule='Joint opaque pixels; RGB/edge metrics also require valid right/down gradient neighbours; fixed ROI never moved'),
        provenance=dict(manifest=str(manifest_path), reference_rgb=str(ref_path), render_rgb=str(render_path),
            reference_evidence=str(ref_source) if ref_source else None, optional_inputs=states,
            supplied_provenance=manifest.get('provenance', {}), api_calls=0,
            model_inferences=0 if extract is None else None, dino=extract_provenance,
            blender_executions=0, agent_code_executed=False),
        measurement_interpretation=dict(appearance='Actual RGB L1; affected by camera, lighting and visibility',
            spatial='Core image-edge proxy unless independently reviewed Anchor/occupancy evidence exists; not 3D layout correctness',
            statistical='Existing texture/multiscale edge-distribution proxies unless reviewed occupancy exists; not object density',
            semantic='Reviewed evidence only; attached Group/Structural answers never become scores',
            perceptual=('N/A: no DINO inference in this entry' if extract is None else
                'Existing local DINO metric; crop/black-fill/aspect-ratio confounds remain; not semantic correctness'),
            observation='Conditional debug aggregate of core eligible records; not a formal Benchmark result'),
        elapsed_seconds=time.monotonic()-tick)
    checks = dict(camera=camera, metadata_resolution_matches_native_rgb=resolution_match,
        camera_comparability=manifest.get('camera_comparability', 'unknown'), optional_inputs=states,
        shared_grid=list(a.shape[1::-1]), reference_roi_fixed=True, alignment_search=False,
        valid_pixels=report['coordinates']['valid_pixels'], measurement_pixels=report['coordinates']['measurement_pixels'],
        overlapping_named_regions_withheld=report['error_diagnostics']['overlap_aggregation_withheld'],
        diagnostic_inputs_excluded_from_energy=True, evidence_review_flags_not_promoted=True,
        numerical_records=[dict(id=r['id'], energy=r['energy'], level=r['level'], q=r['q'],
            aggregation_weight=r['aggregation_weight']) for r in report['metric_records']
            if r['q']>0 and r['value'] is not None and r.get('aggregation_eligible',True)],
        no_model_api_agent_or_blender_execution=extract is None,
        explicit_local_extractor=extract_provenance,formal_eligible=False)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'report.json', report)
    write_json(output/'integration_checks.json', checks)
    Image.fromarray(valid.astype('uint8')*255).save(output/'valid_pixels.png')
    comparison_png(output/'comparison.png', a, b, masks, regions, report)
    def fmt(value):
        return 'N/A' if value is None else f'{value:.6f}'
    lines = ['# Offline Evaluation Integration', '',
        '**provisional/debug — no formal Benchmark score.**', '',
        'The entry reuses build_reference → compare → aggregate and independent structural_report. '
        +('No model, API, Agent or Blender is executed.' if extract is None else
          'An explicitly supplied local DINO extractor runs; no API, Agent or Blender is executed.'), '',
        '| Energy | Conditional value | Coverage | Interpretation |', '| --- | --- | --- | --- |']
    for key, value in report['energies'].items():
        lines.append(f"| {key} | {fmt(value['value'])} | {fmt(value['coverage'])} | {report['measurement_interpretation'][key]} |")
    lines += ['', f"Conditional Observation: {fmt(report['observation_energy'])}; independent 3D Structural: {fmt(report['structural_energy'])}.",
        '', 'Camera: '+camera['camera_protocol']+'. '+camera['reason'], '',
        f"Valid pixels: {valid.sum()}/{valid.size}; gradient-safe measurement pixels: {checks['measurement_pixels']}. Explicit mapping: {manifest['coordinates']['render_mapping']}; no alignment search.", '',
        '## Fixed Region diagnostics', '', '| Region | Appearance | Perceptual | Reviewed |', '| --- | --- | --- | --- |']
    lines += [f"| {r['id']} | {fmt(r['appearance'])} | {fmt(r['perceptual'])} | {r['reviewed']} |" for r in regions]
    lines += ['', f"Named overlap pixels: {overlaps['overlap_pixels']}. {overlaps['reason']}",
        '', 'Group and Structural Layout evidence are attached verbatim in report.json → diagnostics, without Energy contribution. Missing/invalid optional files remain unavailable. Unknown is never replaced by zero.',
        '', 'Required manual work: camera/provenance audit, Reference evidence review and reliable cross-image verification. External JSON cannot certify trusted execution; even a matching pose remains unverified.',
        '', '## Reproduce offline', '', 'From the project root, with the documented sibling scene-benchmark dependency and the manifest inputs present:', '',
        '```bash', f'python3 -B -m e_harness.benchmark offline --manifest {manifest_path} --output /tmp/projecte-offline-new-output', '```', '',
        'The output directory must not already exist. Real-image visual derivatives are not cleared for public redistribution.']
    if verification is not None:
        lines += ['', '## Imported VLM Verification (unreviewed, no Energy contribution)', '',
            '| Evidence / Region / Group | Question | Reference | Render / counterpart | Comparison |',
            '| --- | --- | --- | --- | --- |']
        for row in verification['results']:
            fields = [str(row.get(k) if row.get(k) is not None else 'N/A').replace('|', '\\|').replace('\n', ' ')
                      for k in ('evidence_id', 'region_id', 'group_id', 'question', 'reference_answer', 'render_answer', 'status')]
            lines.append('| '+' / '.join(fields[:3])+' | '+' | '.join(fields[3:])+' |')
        lines += ['', 'Backends: '+verification['reference']['backend']+' / '+verification['render']['backend']+
            '. Raw answers, frozen prompt, model provenance and request failures remain in report.json.']
    (output/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return report
