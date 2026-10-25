"""Experimental signed image-plane measurements; never an Energy score.

Object extents and correspondence must be supplied independently of this math.
All centres below are bbox centres, not visible-mask centroids or 3D positions.
"""
import numpy as np

from .benchmark_evidence import area_mask, reliability


def measure_pair(objects, image_size, *, allow_provisional=False, object_categories=None):
    """Measure the second object relative to the first on one common RGB grid.

    The default island/pendant contract stays backward compatible. Explicit
    object_categories supplies an ordered pair for other diagnostic objects.
    Unreviewed boxes can be inspected explicitly with allow_provisional=True.
    That opt-in does not validate a mask or make the result eligible for Energy.
    Unknown/missing/mismatched objects never receive a geometric penalty.
    """
    size = np.asarray(image_size, float)
    if (size.shape != (2,) or not np.isfinite(size).all() or
            (size <= 0).any() or (size != np.floor(size)).any()):
        raise ValueError('Expected positive integer image_size [width,height]')
    width, height = map(int, size)
    categories = ({'island':'island', 'pendant':'pendant light'}
                  if object_categories is None else object_categories)
    if (not isinstance(categories, dict) or len(categories) != 2 or
            not all(isinstance(k, str) and k and isinstance(v, str) and v
                    for k, v in categories.items())):
        raise ValueError('Exactly two ordered object IDs and explicit categories required')
    first, second = categories
    result = dict(image_size=[width, height], center_method='bbox_center',
                  extent_definition={k: (objects.get(k) or {}).get('extent_definition')
                                     for k in categories},
                  delta_x=None, delta_y=None, bbox_area_ratio_proxy=None,
                  visible_mask_area_ratio=None, normalized_centers={},
                  status='unavailable', reason=None, score=None,
                  participates_in_energy=False, allow_provisional=allow_provisional)
    areas, mask_areas, reasons = {}, {}, []
    for key, category in categories.items():
        row = objects.get(key)
        if row is None:
            reasons.append(f'{key}: localization unavailable')
            continue
        if row.get('status') not in ('matched', 'misplaced'):
            reasons.append(f'{key}: {row.get("status", "unknown")}')
            continue
        if row.get('category') != category:
            reasons.append(f'{key}: semantic mismatch')
            continue
        box = np.asarray(row.get('bbox'), float)
        if (box.shape != (4,) or not np.isfinite(box).all() or
                not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)):
            raise ValueError(f'{key}: invalid xyxy bbox on RGB grid')
        if not isinstance(row.get('extent_definition'), str) or not row['extent_definition'].strip():
            raise ValueError(f'{key}: explicit visible extent definition required')
        # Validate bbox even when an explicit mask is present: area_mask alone
        # intentionally accepts masks independently of their bbox metadata.
        mask_area = None
        if 'mask' in row:
            mask = area_mask(row, (height, width))
            if mask.sum() <= 0:
                raise ValueError(f'{key}: empty visible mask')
            if row.get('mask_reviewed') is True and row.get('mask_scope') == 'visible_object':
                mask_area = float(mask.sum())
        q = reliability(row)
        if not q and not allow_provisional:
            reasons.append(f'{key}: unreviewed/unreliable localization')
            continue
        if (row.get('conflicted') or row.get('visibility') in ('unknown', 'not_visible') or
                row.get('visible_in_input_view') is False or row.get('evidence_scope') == 'scene_objects'):
            reasons.append(f'{key}: conflicted or unobservable localization')
            continue
        result['normalized_centers'][key] = [float((box[0]+box[2])/2/width),
                                              float((box[1]+box[3])/2/height)]
        areas[key] = float((box[2]-box[0])*(box[3]-box[1]))
        if mask_area is not None:
            mask_areas[key] = mask_area
    if len(areas) == 2:
        a, b = (result['normalized_centers'][k] for k in categories)
        result.update(delta_x=b[0]-a[0], delta_y=b[1]-a[1],
                      bbox_area_ratio_proxy=areas[second]/areas[first],
                      status='conditional_debug' if allow_provisional else 'valid_geometry')
        if len(mask_areas) == 2:
            result['visible_mask_area_ratio'] = mask_areas[second]/mask_areas[first]
        else:
            reasons.append('Visible-object masks unavailable/unreviewed; bbox area remains a separate proxy')
    result['reason'] = '; '.join(reasons) or 'Known geometry; no Energy aggregation'
    return result


def compare_pairs(reference, rendered):
    """Signed render-minus-reference changes; never mix area definitions."""
    for key in ('image_size', 'center_method'):
        if reference[key] != rendered[key]:
            raise ValueError(f'Incompatible {key}; no implicit alignment or extent conversion')
    if list(reference['extent_definition']) != list(rendered['extent_definition']):
        raise ValueError('Incompatible ordered object IDs')
    for key in reference['extent_definition']:
        a, b = reference['extent_definition'][key], rendered['extent_definition'][key]
        if a is not None and b is not None and a != b:
            raise ValueError('Incompatible extent_definition; no implicit extent conversion')
    output = dict(direction='render_minus_reference', score=None, participates_in_energy=False)
    for key in ('delta_x', 'delta_y', 'bbox_area_ratio_proxy', 'visible_mask_area_ratio'):
        a, b = reference[key], rendered[key]
        output[key+'_change'] = None if a is None or b is None else float(b-a)
    return output


def measure_visible_pair(masks, image_size):
    """Diagnostic-only binary visible support for an ordered synthetic Oracle pair.

    Centres reuse measure_pair's visible-bbox centres. Boundary gap is the mean
    signed distance from the first mask's right pixel edge to the second mask's
    left edge, on rows with support for both; it is not a bbox envelope gap.
    Empty/unavailable support is not evidence of confirmed semantic absence.
    """
    categories = {key:'synthetic_component' for key in masks}
    # Reuse grid validation even when neither object can be localized.
    initial = measure_pair({}, image_size, allow_provisional=True, object_categories=categories)
    width, height = initial['image_size']
    objects, support, localizations = {}, {}, {}
    for key, raw in masks.items():
        objects[key] = None
        localizations[key] = dict(status='unavailable', bbox=None, visible_pixels=None,
                                  reason='No reliable visible pixel support; not confirmed missing')
        if raw is None:
            continue
        mask = np.asarray(raw)
        if mask.shape != (height, width) or not np.isin(mask, [0,1]).all():
            raise ValueError('Visible mask must be binary 0/1 on the declared RGB grid')
        ys, xs = np.nonzero(mask)
        if not len(xs):
            localizations[key]['visible_pixels'] = 0
            continue
        box = [int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]
        support[key] = mask.astype(bool)
        objects[key] = dict(category=categories[key], bbox=box, status='matched',
            reviewed=False, reliability=0., visibility='visible',
            extent_definition='bbox of binary visible Object-ID pixels, xyxy pixel edges')
        localizations[key] = dict(status='synthetic_oracle_visible',bbox=box,visible_pixels=len(xs),
                                  reviewed=False,source='supplied binary visible support')
    result = measure_pair(objects, image_size, allow_provisional=True, object_categories=categories)
    dx = result['delta_x']
    result.update(object_order=list(masks), localizations=localizations,
        left_of=None if dx is None else bool(dx>0), relative_distance=None if dx is None else abs(dx),
        boundary_gap=None, boundary_gap_pixels=None, boundary_rows=[],
        boundary_status='unavailable', boundary_reason='Both objects need visible support on common rows',
        localization_source='synthetic_oracle', reviewed=False, usage='provisional/debug',
        definitions=dict(left_of='First visible-bbox centre is left of second; discrete image-plane order',
            relative_distance='Absolute horizontal separation of visible-bbox centres divided by image width',
            boundary_gap='Mean [second left edge - first right edge] on shared rows, divided by width; signed',
            delta_y='Second minus first visible-bbox centre y divided by image height; down is positive'))
    if len(support) == 2:
        first,second = (support[k] for k in masks)
        for y in np.flatnonzero(first.any(axis=1) & second.any(axis=1)):
            right = int(np.flatnonzero(first[y])[-1])+1
            left = int(np.flatnonzero(second[y])[0])
            result['boundary_rows'].append(dict(y=int(y),first_right_edge=right,
                                                 second_left_edge=left,gap_pixels=left-right))
        if result['boundary_rows']:
            gaps = [row['gap_pixels'] for row in result['boundary_rows']]
            gap = float(np.mean(gaps))
            result.update(boundary_gap=gap/width, boundary_gap_pixels=gap,
                boundary_status='conditional_debug',boundary_reason=None,
                boundary_gap_pixels_min=int(min(gaps)),boundary_gap_pixels_max=int(max(gaps)))
    return result
