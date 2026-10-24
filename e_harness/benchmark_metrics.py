"""Five normalized errors at shared Global/Region/Anchor granularities."""
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment

from .benchmark_config import ENERGIES, POLICY
from .benchmark_evidence import area_mask, reliability, vlm_verify
from benchmark.background import cosine, dino_rgb_pixels
from benchmark.metrics import bbox_iou, mask_iou


def record(energy, level, key, value, q=1., reason=None, aggregation_weight=1., **details):
    if energy not in ENERGIES or level not in POLICY['levels'] or not np.isfinite(q) or not 0<=q<=1:
        raise ValueError('Unknown metric/level or invalid reference reliability')
    if value is not None and (not np.isfinite(value) or not 0 <= value <= 1):
        raise ValueError(f'Invalid normalized {energy} error: {value}')
    if not np.isfinite(aggregation_weight) or aggregation_weight <= 0:
        raise ValueError('Aggregation weight must be positive and finite; it is not reliability')
    return dict(energy=energy, level=level, id=key, value=value, q=q,
                aggregation_weight=float(aggregation_weight),
                status='valid' if value is not None else 'unavailable', reason=reason, **details)


def mean_error(values):
    return float(np.mean(values)) if len(values) else None


def weighted(a, mask):
    return np.sum(a * mask) / mask.sum()


def gradients(image):
    gray = image.astype(float).mean(2) / 255.
    dx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    dy = np.abs(np.diff(gray, axis=0, append=gray[-1:]))
    return gray, np.maximum(dx, dy)


def coarse(array, mask, n=4):
    values = []
    h, w = mask.shape
    for iy in range(n):
        for ix in range(n):
            ys, xs = slice(iy*h//n, (iy+1)*h//n), slice(ix*w//n, (ix+1)*w//n)
            m = mask[ys, xs]
            values.append(float(weighted(array[ys, xs], m)) if m.sum() else 0.)
    return np.asarray(values)


def distribution_error(a, b, mask):
    """Fixed-coordinate multiscale occupancy means, normalized to [0,1]."""
    per_scale = {str(n): float(np.abs(coarse(a, mask, n)-coarse(b, mask, n)).mean())
                 for n in POLICY['distribution_grids']}
    weights = POLICY['distribution_grids']
    value = sum(per_scale[str(n)]*weight for n, weight in weights.items())/sum(weights.values())
    return float(value), per_scale


def numerical_errors(a, b, mask):
    """Measured RGB/edge/texture proxies; no inferred object or material identity."""
    ga, ea = gradients(a)
    gb, eb = gradients(b)
    appearance = sum(float(weighted(np.abs(a[..., c].astype(float)-b[..., c]) / 255., mask))
                     for c in range(3)) / 3
    # Coarse edges are compared at the SAME reference coordinates, never searched.
    ba, bb = (ea >= POLICY['edge_threshold']).astype(float), (eb >= POLICY['edge_threshold']).astype(float)
    spatial = float(np.abs(coarse(ba, mask, 8)-coarse(bb, mask, 8)).mean())
    hist = [np.histogram(g, bins=16, range=(0, 1), weights=mask)[0] / mask.sum() for g in [ga, gb]]
    histogram_distance = float(np.abs(np.cumsum(hist[0])-np.cumsum(hist[1])).mean())
    coverage = abs(float(weighted(ba-bb, mask)))
    texture = abs(float(weighted(ea-eb, mask)))
    distributions, per_scale = distribution_error(ba, bb, mask)
    texture_proxy = float(np.mean([histogram_distance, coverage, texture]))
    components = POLICY['statistical_components']
    statistical = (components['texture']*texture_proxy+components['distribution']*distributions)/sum(components.values())
    return dict(appearance=appearance, spatial=spatial, statistical=statistical), dict(
        color_l1=appearance, coarse_boundary_error=spatial, grayscale_wasserstein=histogram_distance,
        edge_coverage_error=coverage, gradient_mean_error=texture,
        texture_statistics_proxy=texture_proxy, edge_distribution_proxy=distributions,
        edge_distribution_per_scale=per_scale,
        scope='RGB appearance, coarse edges and texture distribution proxies; not semantic segmentation or element counts')


def perceptual_error(a, b, mask, extract):
    if extract is None:
        return None, 'Local DINO extractor unavailable; no substitute feature score'
    ys, xs = np.nonzero(mask > 0)
    if not len(xs):
        return None, 'Empty reference region'
    box = (slice(ys.min(), ys.max()+1), slice(xs.min(), xs.max()+1))
    crops = [np.uint8(np.clip(im[box] * mask[box][..., None], 0, 255)) for im in [a, b]]
    distances = []
    try:
        for scale in POLICY['multiscale']:
            resized = []
            for crop in crops:
                side = POLICY['dino_size']
                ratio = side * scale / max(crop.shape[:2])
                w, h = max(1, round(crop.shape[1]*ratio)), max(1, round(crop.shape[0]*ratio))
                dh, dw = side-h, side-w
                padding = ((dh//2, dh-dh//2), (dw//2, dw-dw//2))
                resized.append(dino_rgb_pixels(crop, np.ones(crop.shape[:2], bool),
                    [w,h], padding, np.zeros(3,np.uint8)))
            vectors = extract(resized)
            if len(vectors) != 2:
                raise ValueError('DINO must return two feature vectors')
            similarity = cosine(*vectors)
            if similarity is None:
                raise ValueError('Invalid or zero DINO features')
            # Raw 1-cos lies in [0,2], normalized by 2 for aggregation.
            distances.append(float(np.clip((1-similarity)/2, 0, 1)))
        return float(np.mean(distances)), None
    except Exception as exc:
        return None, f'DINO extraction failed: {type(exc).__name__}: {exc}'


def match_anchors(reference, rendered, shape, *, reference_complete=False):
    """Input-view correspondence; missing/extra need independently reviewed evidence.

    Optional rendered.anchor_verdicts: reference_id/rendered_id, status (matched,
    confirmed_missing, confirmed_extra), reviewed, reliability, verification_type
    (human or synthetic_oracle), source, evidence_scope='input_view'. No VLM self-score
    or detector non-detection is an absence verifier. 'missing' is retained as the
    legacy status spelling; verification_status explicitly says confirmed_missing.
    """
    refs = [a for a in reference if reliability(a)]
    supplied = rendered is not None
    rendered = rendered or {}
    if rendered.get('image_size', list(shape[::-1])) != list(shape[::-1]):
        raise ValueError('Rendered evidence must use the input-view RGB grid')
    candidates = rendered.get('anchors', [])
    ids = [r['id'] for r in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('Rendered Anchor IDs must be unique')
    # A missing/unreviewed detector inventory does not establish absence.
    complete = (rendered.get('inventory_complete') is True and rendered.get('reviewed') is True
                and rendered.get('evidence_scope', 'input_view') == 'input_view'
                and all(reliability(a) for a in candidates)
                and not rendered.get('unresolved_salient_candidates'))
    usable = [a for a in candidates if reliability(a) and a.get('evidence_scope', 'input_view') == 'input_view'
              and a.get('visible_in_input_view') is not False]
    complete = complete and len(usable) == len(candidates)
    for row in usable:
        area_mask(row, shape)
    size = np.array(shape[::-1], float)
    ref_ids, render_ids = {a['id'] for a in refs}, {a['id'] for a in usable}
    verdicts, absent, explicit, extra_verdicts = [], {}, {}, {}
    for v in rendered.get('anchor_verdicts', []):
        q = reliability(v)
        accepted = (q > 0 and v.get('verification_type') in {'human', 'synthetic_oracle'}
                    and isinstance(v.get('source'), str) and bool(v['source'].strip())
                    and v.get('evidence_scope') == 'input_view')
        status = v.get('status')
        valid_ids = ((status == 'confirmed_missing' and v.get('reference_id') in ref_ids) or
                     (status == 'confirmed_extra' and v.get('rendered_id') in render_ids) or
                     (status == 'matched' and v.get('reference_id') in ref_ids and v.get('rendered_id') in render_ids))
        accepted = accepted and valid_ids
        verdicts.append(dict(v, accepted=accepted,
            reason=None if accepted else 'Needs reviewed human/oracle input-view verdict, source and valid endpoints'))
        if accepted:
            target, key = ((absent, v['reference_id']) if status == 'confirmed_missing' else
                           (extra_verdicts, v['rendered_id']) if status == 'confirmed_extra' else
                           (explicit, v['reference_id']))
            if key in target:
                raise ValueError('Duplicate verified Anchor verdict; resolve the review conflict explicitly')
            target[key] = v
    linked_ids = [v['rendered_id'] for v in explicit.values()]
    if len(linked_ids) != len(set(linked_ids)):
        raise ValueError('Verified correspondence must be one-to-one')
    conflicts = {key for key, v in explicit.items() if key in absent or v['rendered_id'] in extra_verdicts}
    conflict_render_ids = {explicit[key]['rendered_id'] for key in conflicts}
    costs = np.full((len(refs), len(usable)), POLICY['match_max_cost'] + 1.)
    for i, a in enumerate(refs):
        for j, b in enumerate(usable):
            ca, cb = (np.array(a['bbox'][:2])+a['bbox'][2:])/2, (np.array(b['bbox'][:2])+b['bbox'][2:])/2
            pos = float(np.linalg.norm((ca-cb)/size)/np.sqrt(2))
            iou = bbox_iou(np.array(a['bbox']), np.array(b['bbox']))
            if a['id'] in absent or b['id'] in extra_verdicts:
                continue
            if a['id'] in explicit:
                if explicit[a['id']]['rendered_id'] == b['id']:
                    costs[i, j] = 0.
                continue
            if b['id'] in linked_ids:
                continue
            # A remote unrelated class is not a semantic replacement. Same-category
            # instances can still match after large displacement and zero IoU.
            if a['category'] == b['category'] or iou >= .25:
                costs[i, j] = .6 * (a['category'] != b['category']) + .25*pos + .15*(1-iou)
    pairs = {}
    used = set()
    if costs.size:
        # Dummies allow either endpoint to remain unmatched under the cost gate.
        padded = np.full((len(refs), len(usable)+len(refs)), POLICY['match_max_cost'])
        padded[:, :len(usable)] = costs
        ii, jj = linear_sum_assignment(padded)
        for i, j in zip(ii, jj):
            if j < len(usable) and costs[i, j] < POLICY['match_max_cost']:
                pairs[refs[i]['id']] = usable[j]
                used.add(j)
    rows = []
    for a in refs:
        b = pairs.get(a['id'])
        conflict = a['id'] in conflicts
        delta = max(np.abs(((np.array(a['bbox'][:2])+a['bbox'][2:])/2-
                            (np.array(b['bbox'][:2])+b['bbox'][2:])/2)/size)) if b else None
        status = ('semantic_mismatch' if a['category'] != b['category'] else
                  'misplaced' if delta > POLICY['misplaced_center_fraction'] else 'matched') if b else (
                      'missing' if complete or a['id'] in absent else 'unknown')
        if conflict:
            status = 'unknown'
        q = min(reliability(a), reliability(b)) if b else min(reliability(a), reliability(absent[a['id']])) if a['id'] in absent else reliability(a)
        if a['id'] in explicit:
            q = min(q, reliability(explicit[a['id']]))
        if conflict:
            pairs.pop(a['id'], None)
        rows.append(dict(reference_id=a['id'], rendered_id=b['id'] if b else None, status=status,
                         verification_status='confirmed_missing' if status == 'missing' else status,
                         category=a['category'], q=q, weight=a['importance']*q,
                         max_center_displacement=delta,
                         reason='Conflicting reviewed presence/absence verdicts' if conflict else
                                'Complete reviewed input-view inventory' if status == 'missing' and a['id'] not in absent else
                                'Reviewed per-Anchor absence verdict' if status == 'missing' else
                                'Detector non-detection or incomplete evidence is not verified absence' if status == 'unknown' else None))
    extras = [b['id'] for j, b in enumerate(usable) if j not in used and
              b['id'] not in conflict_render_ids and (reference_complete or b['id'] in extra_verdicts)]
    unknown_extras = [b['id'] for j, b in enumerate(usable) if j not in used and b['id'] not in extras]
    tp = sum(r['weight'] for r in rows if r['status'] in {'matched', 'misplaced'})
    fn = sum(r['weight'] for r in rows if r['status'] in {'missing', 'semantic_mismatch'})
    fp = sum(b.get('importance', 1.) * min(reliability(b), reliability(extra_verdicts[b['id']]))
             if b['id'] in extra_verdicts else b.get('importance', 1.) * reliability(b)
             for b in usable if b['id'] in extras) + sum(r['weight'] for r in rows if r['status'] == 'semantic_mismatch')
    energy = 1-2*tp/(2*tp+fn+fp) if 2*tp+fn+fp else None
    return energy, pairs, rows, extras, dict(complete=complete, supplied=supplied,
        reference_complete=reference_complete, unknown_candidates=len(candidates)-len(usable),
        unknown_extras=unknown_extras,
        unknown_rendered_candidates=[a['id'] for a in candidates if a['id'] not in render_ids],
        extra_records=[dict(rendered_id=b['id'], status='confirmed_extra' if b['id'] in extras else 'unknown',
                            reason='Reviewed per-Anchor extra verdict or complete reviewed reference inventory' if b['id'] in extras else
                                   'Unmatched rendered object; reference extraction may be incomplete')
                       for j,b in enumerate(usable) if j not in used],
        verdict_records=verdicts, tp=tp, fn=fn, fp=fp)


def compare(a, b, reference, rendered=None, *, extract=None, vlm=None):
    if a.shape != b.shape or a.ndim != 3 or a.shape[2] != 3:
        raise ValueError('Reference and render must share the same HxWx3 RGB grid; no image alignment/warping')
    rows, diagnostics = [], []
    shape = a.shape[:2]
    # One set of energies, with a fixed level mixture. Global always retains weight.
    sections = [(dict(id='global', metrics=['appearance','perceptual'], reviewed=True,
                     reliability=1.), np.ones(shape), 'global')]
    masks = [area_mask(r, shape) * (1-reference['anchor_exclusion']) for r in reference['regions']]
    multiplicity = np.maximum(1, np.sum([m for r, m in zip(reference['regions'], masks) if reliability(r)], axis=0)) if masks else np.ones(shape)
    sections += [(r, m/multiplicity, 'region') for r, m in zip(reference['regions'], masks)]
    for item, mask, level in sections:
        q, key = reliability(item), item['id']
        metrics = item.get('metrics', ['appearance','spatial','statistical','perceptual'])
        if set(metrics)-set(ENERGIES):
            raise ValueError('Unknown Region metric')
        if not q or mask.sum() < POLICY['min_pixels']:
            reason = 'Unreviewed/unknown evidence' if not q else 'Insufficient region pixels after Anchor exclusion'
            for k in metrics:
                if k=='statistical':
                    rows += [record(k,level,key+':'+part,None,q,reason,aggregation_weight=weight)
                             for part,weight in POLICY['statistical_components'].items()]
                else:
                    rows.append(record(k,level,key,None,q,reason))
            if level=='region' and item.get('layout_evidence') is True and 'spatial' in metrics:
                rows.append(record('spatial',level,key+':occupancy',None,q,reason))
            continue
        errors, detail = numerical_errors(a, b, mask)
        dino = (None, None)
        if 'perceptual' in metrics:
            dino = perceptual_error(a, b, mask, extract)
        for k in metrics:
            if k == 'statistical':
                weights = POLICY['statistical_components']
                rows.append(record(k, level, key+':texture', detail['texture_statistics_proxy'], q,
                    aggregation_weight=weights['texture'], method='Texture statistics proxy'))
                value, reason = detail['edge_distribution_proxy'], None
                scales, method = detail['edge_distribution_per_scale'], 'Multiscale edge distribution proxy'
                # Applicability is fixed by reference evidence. Missing rendered occupancy
                # must stay N/A rather than silently falling back to an easier proxy.
                if item.get('occupancy_reviewed') is True and 'element_occupancy' in item:
                    other = next((r for r in (rendered or {}).get('regions', []) if r['id']==key and reliability(r)), None)
                    method = 'Multiscale reviewed element occupancy distribution'
                    if other and other.get('occupancy_reviewed') is True and 'element_occupancy' in other:
                        first = area_mask({'mask': item['element_occupancy']}, shape)
                        second = area_mask({'mask': other['element_occupancy']}, shape)
                        value, scales = distribution_error(first, second, mask)
                    else:
                        value, scales = None, None
                        reason = 'Reference expects reviewed element occupancy; rendered evidence unavailable'
                rows.append(record(k, level, key+':distribution', value, q, reason,
                    aggregation_weight=weights['distribution'], method=method, per_scale=scales))
                continue
            if k == 'semantic':
                other = next((r for r in (rendered or {}).get('regions', []) if r['id']==key and reliability(r)), None)
                value, reason = None, 'Reviewed reference and rendered region categories required; DINO is perceptual only'
                method = 'Reviewed region category comparison'
                if item.get('presence_evidence') is True:
                    reason = 'Reviewed occupancy of the reference content unavailable; detector failure is not region absence'
                    method = 'Region content missing fraction at fixed reference coordinates'
                    if (item.get('category') and other and other.get('occupancy_reviewed') is True and
                            other.get('occupancy_category') == item['category'] and 'element_occupancy' in other):
                        occupancy = area_mask({'mask': other['element_occupancy']}, shape)
                        value, reason = float(1-weighted(occupancy, mask)), None
                elif item.get('category') and other and other.get('category'):
                    value, reason = float(item['category'] != other['category']), None
            elif k == 'perceptual':
                value, reason = dino
                method = 'DINO multiscale perceptual features'
            else:
                value, reason, method = errors[k], None, detail['scope']
            metric_q = min(q, reliability(other)) if k == 'semantic' and other else q
            rows.append(record(k, level, key, value, metric_q, reason,
                               method=method))
        if level=='region' and item.get('layout_evidence') is True and 'spatial' in metrics:
            other = next((r for r in (rendered or {}).get('regions', []) if r['id']==key and reliability(r)), None)
            layout = None
            if other is not None:
                observed_mask = area_mask(other, shape) * (1-reference['anchor_exclusion'])
                layout = float(np.abs(coarse(area_mask(item,shape)*(1-reference['anchor_exclusion']),np.ones(shape),8)-
                                      coarse(observed_mask,np.ones(shape),8)).mean())
            rows.append(record('spatial','region',key+':occupancy',layout,q,
                               None if layout is not None else 'Reviewed rendered region occupancy unavailable',
                               method='Fixed-grid soft-mask occupancy error'))
        diagnostics.append(dict(id=key, level=level, reference_pixel_weight=float(mask.sum()), **detail))
    reference_complete = (reference.get('inventory_complete') is True and reference.get('reviewed') is True
                          and reference.get('evidence_scope', 'input_view') == 'input_view'
                          and not reference.get('unresolved_salient_candidates'))
    semantic, pairs, matches, extras, inventory = match_anchors(reference['anchors'], rendered, shape,
        reference_complete=reference_complete)
    anchors = {r['id']: r for r in reference['anchors']}
    trusted_anchors = [r for r in anchors.values() if reliability(r)]
    known_matches = [m for m in matches if m['status'] != 'unknown']
    if trusted_anchors or extras:
        known_anchors = [anchors[m['reference_id']] for m in known_matches]
        importance = [r['importance'] for r in known_anchors]
        q = float(np.average([m['q'] for m in known_matches], weights=importance)) if importance else 1.
        rows.append(record('semantic', 'anchor', 'instance_1_minus_f1', semantic, q,
                           None if semantic is not None else 'No verified Anchor correspondence or absence/extra conclusion',
                           aggregation_weight=sum(importance) or 1.,
                           method='Existing weighted instance F1 on verified conclusions; Unknown excluded and reported'))
    for match in matches:
        if match['status'] == 'unknown':
            ref = anchors[match['reference_id']]
            rows.append(record('semantic','anchor',ref['id']+':presence',None,reliability(ref),
                               match['reason'],aggregation_weight=ref['importance']))
    for key in inventory['unknown_extras'] + inventory['unknown_rendered_candidates']:
        rows.append(record('semantic','anchor',key+':extra',None,0.,
                           'Unverified rendered candidate/extra; reference extraction or visibility may be incomplete'))
    for ref in anchors.values():
        if not reliability(ref):
            rows += [record(k,'anchor',ref['id'],None,0.,'Unreviewed or unknown Anchor evidence',
                            aggregation_weight=ref['importance'])
                     for k in ('semantic','spatial','appearance','perceptual')]
    for match in matches:
        ref = anchors[match['reference_id']]
        if match['status'] == 'missing':
            rows += [record(k,'anchor',ref['id'],None,match['q'],
                            'Confirmed missing Anchor: absence is charged once in Semantic; object-level comparison unavailable',
                            aggregation_weight=ref['importance']) for k in ('appearance','perceptual','spatial')]
            continue
        # Anchor image evidence stays at reference coordinates; a relocated lookalike
        # cannot erase position errors. Region pixels already exclude this Anchor.
        anchor_mask = area_mask(ref if ref.get('mask_reviewed') is True else {'bbox':ref['bbox']}, shape)
        errors, _ = numerical_errors(a,b,anchor_mask)
        rows.append(record('appearance','anchor',ref['id'],errors['appearance'],reliability(ref),
                           aggregation_weight=ref['importance'],
                           method='RGB L1 at reference Anchor coordinates'))
        perceptual, reason = perceptual_error(a,b,anchor_mask,extract)
        rows.append(record('perceptual','anchor',ref['id'],perceptual,reliability(ref),reason,
                           aggregation_weight=ref['importance'],
                           method='DINO at reference Anchor coordinates'))
        other = pairs.get(ref['id'])
        if other is None:
            rows.append(record('spatial','anchor',ref['id'],None,reliability(ref),
                               'Unknown rendered Anchor correspondence',
                               aggregation_weight=ref['importance']))
        else:
            ca, cb = [(np.array(r['bbox'][:2])+r['bbox'][2:])/2 for r in [ref, other]]
            value = float(np.linalg.norm((ca-cb)/shape[::-1])/np.sqrt(2))
            rows.append(record('spatial','anchor',ref['id'],value,reliability(ref),
                               aggregation_weight=ref['importance'], method='Normalized center displacement'))
            if ref.get('mask_reviewed') is True and other.get('mask_reviewed') is True and 'mask' in ref and 'mask' in other:
                iou = mask_iou(area_mask(ref,shape) >= .5, area_mask(other,shape) >= .5)
                rows.append(record('spatial','anchor',ref['id']+':mask',1-iou if iou is not None else None,reliability(ref),
                                   aggregation_weight=ref['importance'],method='Reviewed mask IoU only'))
    # Relations may connect anchors and annotated regions. Regions keep reference coordinates;
    # rendered region positions must be independently supplied, never presumed equal.
    ref_items = {r['id']: r for r in reference['regions']+reference['anchors']}
    render_regions = {r['id']: r for r in (rendered or {}).get('regions', []) if reliability(r)}
    endpoints = dict(render_regions, **pairs)
    for fact in reference.get('relations', []):
        q = reliability(fact)
        value, reason = None, 'Unreviewed or unknown reference relation'
        s, o = fact['subject'], fact['object']
        pred = fact['predicate']
        # Endpoint reliability gates every relation, regardless of its own review flag.
        q = min(q, reliability(ref_items[s]), reliability(ref_items[o]))
        if q:
            missing = any(m['reference_id'] in {s,o} and m['status']=='missing' for m in matches)
            if missing:
                value, reason = None, 'Confirmed missing endpoint; absence charged in Semantic, relation cannot be compared separately'
            elif s in endpoints and o in endpoints:
                u, v = endpoints[s], endpoints[o]
                if pred in {'left_of','right_of','above','below'}:
                    axis = 0 if pred in {'left_of','right_of'} else 1
                    delta = ((np.array(u['bbox'][:2])+u['bbox'][2:])/2-(np.array(v['bbox'][:2])+v['bbox'][2:])/2)[axis]/shape[::-1][axis]
                    if abs(delta) <= POLICY['relation_margin']:
                        reason = 'Ambiguous projected relation within margin'
                    else:
                        value, reason = float((delta < 0) != (pred in {'left_of','above'})), None
                elif pred in {'in_front_of','behind'}:
                    depths = [p.get('relative_depth') for p in [u,v]]
                    if all(p.get('depth_reviewed') is True for p in [u,v]) and all(d is not None and np.isfinite(d) for d in depths) and abs(depths[0]-depths[1]) > .02:
                        value, reason = float((depths[0] < depths[1]) != (pred=='in_front_of')), None
                    else:
                        reason = 'Trusted relative depth unavailable; monocular depth is not GT'
                else:
                    verification = vlm_verify(f'Is {s} {pred} {o}?', a, b,
                                              dict(energy='spatial', fact=fact, error_range=[0,1]),vlm)
                    value, reason = verification['score'], verification['reason']
            else:
                reason = 'Relation endpoint correspondence unavailable'
        importance = np.sqrt(ref_items[s].get('importance',1.)*ref_items[o].get('importance',1.))
        rows.append(record('spatial','anchor',fact.get('id', fact.get('fact_id',f'{s}:{pred}:{o}')),value,q,reason,
                           aggregation_weight=importance))
    # Explicit ambiguous semantic/material questions live INSIDE their corresponding energies.
    # They are selected on reference evidence, not once per patch.
    for question in reference.get('verification_questions', []):
        energy = question['energy']
        if energy not in {'semantic','spatial','appearance','statistical'}:
            raise ValueError('VLM may only verify a concrete metric, never a perceptual/total score')
        q = reliability(question)
        out = vlm_verify(question['question'], a, b, question.get('criteria',{}),vlm) if q else dict(score=None,reason='Unreviewed question')
        rows.append(record(energy,question.get('level','global'),question['id'],out['score'],q,out['reason'],method='VLM metric verification'))
    return rows, dict(regions=diagnostics, anchor_matching=matches, extra_anchors=extras, inventory=inventory)


def aggregate(rows):
    """Reliability weights measurements, coverage describes gaps, policy weights energies."""
    results = {}
    for k in ENERGIES:
        planned = [r for r in rows if r['energy']==k]
        active = [r for r in planned if r['q']>0]
        valid = [r for r in active if r['value'] is not None]
        levels = []
        participating = []
        for level, weight in POLICY['levels'].items():
            selected = [r for r in valid if r['level']==level]
            if selected:
                internal = [r['q']*r.get('aggregation_weight',1.) for r in selected]
                levels.append((float(np.average([r['value'] for r in selected],weights=internal)),weight))
                participating += [dict(id=r['id'],level=level,q=r['q'],
                    aggregation_weight=r.get('aggregation_weight',1.),effective_weight=w,
                    within_energy_weight=weight*w/sum(internal)) for r,w in zip(selected,internal)]
        level_weight = sum(w for _,w in levels)
        for item in participating:
            item['within_energy_weight'] /= level_weight
        value = sum(v*w for v,w in levels)/sum(w for _,w in levels) if levels else None
        reliability = float(np.average([r['q'] for r in valid],
            weights=[r.get('aggregation_weight',1.) for r in valid])) if valid else None
        results[k] = dict(value=value, status='valid' if valid and len(valid)==len(planned) else 'partial' if valid else 'unavailable',
            m=int(bool(planned)), q=reliability, evidence_reliability=reliability,
            base_weight=POLICY['weights'][k], aggregation_weight=POLICY['weights'][k] if valid else 0.,
            valid_count=len(valid), applicable_count=len(planned), eligible_count=len(active),
            coverage=len(valid)/len(planned) if planned else None,
            eligible_coverage=len(valid)/len(active) if active else None,
            reason=None if valid else 'No usable evidence or required extractor unavailable',
            expected_metrics=[f"{r['level']}:{r['id']}" for r in planned],
            unavailable_metrics=[f"{r['level']}:{r['id']}" for r in planned if r['q']<=0 or r['value'] is None],
            participating_metrics=[f"{r['level']}:{r['id']}" for r in valid],participating_records=participating)
    denominator = sum(r['aggregation_weight'] for r in results.values())
    for item in results.values():
        item['normalized_aggregation_weight'] = item['aggregation_weight']/denominator if denominator else 0.
        for participant in item['participating_records']:
            participant['observation_weight'] = participant['within_energy_weight']*item['normalized_aggregation_weight']
    observation = sum(r['normalized_aggregation_weight']*r['value'] for r in results.values()
                      if r['value'] is not None) if denominator else None
    return results, observation
