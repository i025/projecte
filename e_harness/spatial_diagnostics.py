"""Experimental signed image-plane measurements; never an Energy score.

Object extents and correspondence must be supplied independently of this math.
All centres below are bbox centres, not visible-mask centroids or 3D positions.
"""
import numpy as np

from .benchmark_evidence import area_mask, reliability


def measure_pair(objects, image_size, *, allow_provisional=False):
    """Measure pendant relative to island on one common RGB grid.

    Unreviewed boxes can be inspected explicitly with allow_provisional=True.
    That opt-in does not validate a mask or make the result eligible for Energy.
    Unknown/missing/mismatched objects never receive a geometric penalty.
    """
    size = np.asarray(image_size, float)
    if (size.shape != (2,) or not np.isfinite(size).all() or
            (size <= 0).any() or (size != np.floor(size)).any()):
        raise ValueError('Expected positive integer image_size [width,height]')
    width, height = map(int, size)
    result = dict(image_size=[width, height], center_method='bbox_center',
                  extent_definition={k: (objects.get(k) or {}).get('extent_definition')
                                     for k in ('island', 'pendant')},
                  delta_x=None, delta_y=None, bbox_area_ratio_proxy=None,
                  visible_mask_area_ratio=None, normalized_centers={},
                  status='unavailable', reason=None, score=None,
                  participates_in_energy=False, allow_provisional=allow_provisional)
    areas, mask_areas, reasons = {}, {}, []
    for key, category in (('island', 'island'), ('pendant', 'pendant light')):
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
        a, b = (result['normalized_centers'][k] for k in ('island', 'pendant'))
        result.update(delta_x=b[0]-a[0], delta_y=b[1]-a[1],
                      bbox_area_ratio_proxy=areas['pendant']/areas['island'],
                      status='conditional_debug' if allow_provisional else 'valid_geometry')
        if len(mask_areas) == 2:
            result['visible_mask_area_ratio'] = mask_areas['pendant']/mask_areas['island']
        else:
            reasons.append('Visible-object masks unavailable/unreviewed; bbox area remains a separate proxy')
    result['reason'] = '; '.join(reasons) or 'Known geometry; no Energy aggregation'
    return result


def compare_pairs(reference, rendered):
    """Signed render-minus-reference changes; never mix area definitions."""
    for key in ('image_size', 'center_method'):
        if reference[key] != rendered[key]:
            raise ValueError(f'Incompatible {key}; no implicit alignment or extent conversion')
    for key in ('island', 'pendant'):
        a, b = reference['extent_definition'][key], rendered['extent_definition'][key]
        if a is not None and b is not None and a != b:
            raise ValueError('Incompatible extent_definition; no implicit extent conversion')
    output = dict(direction='render_minus_reference', score=None, participates_in_energy=False)
    for key in ('delta_x', 'delta_y', 'bbox_area_ratio_proxy', 'visible_mask_area_ratio'):
        a, b = reference[key], rendered[key]
        output[key+'_change'] = None if a is None or b is None else float(b-a)
    return output
