"""Conservative structural aggregation; raw intersections never imply semantic errors."""
from copy import deepcopy
import numpy as np

from .benchmark_config import POLICY


def structural_report(geometry=None, triage=None, rules=None):
    geometry, triage, rules = geometry or {}, triage or {}, rules or {}
    checks = {k: [] for k in POLICY['structure_weights']}
    diagnostics = []
    if geometry.get('status')=='unavailable':
        diagnostics.append(dict(kind='structural_evidence_unavailable',reason=geometry.get('reason')))
    annotations = {tuple(sorted(r['unit_ids'])): deepcopy(r) for r in triage.get('pairs', [])}
    for previous in triage.get('legacy_records', []):
        key = tuple(sorted(previous['unit_ids']))
        if key not in annotations:
            annotations[key] = dict(reviewed=False, classification=None, historical_proposals=[])
        annotations[key].setdefault('historical_proposals', []).append(previous)
    for pair in geometry.get('collisions', []):
        review = annotations.get(tuple(sorted(pair['unit_ids'])), {})
        label = review.get('classification')
        confirmed = review.get('reviewed') is True
        value, reason = None, 'Candidate only: semantic triage unavailable or unreviewed'
        if confirmed and label in {'normal_connection','same_entity'}:
            reason = 'Reviewed normal connection or same semantic entity; excluded'
        elif confirmed and label == 'implausible_penetration' and pair['status']=='penetration':
            value, reason = 1., None
        elif confirmed and label == 'independent_objects' and pair['status'] in {'separate','no_penetration_detected','contact'}:
            value, reason = 0., None
        checks['penetration'].append(dict(unit_ids=pair['unit_ids'], value=value, reason=reason,
                                          classification=label, reviewed=confirmed))
        if pair['status'] in {'penetration','uncertain'}:
            diagnostics.append(dict(kind='penetration_candidate', geometry=pair, semantic_review=review,
                                    confirmed_error=value==1.))
    by_id = {r['unit_id']: r for r in geometry.get('objects', [])}
    for rule in rules.get('support', []):
        value, reason = None, 'Requires reviewed support expectation, Z-up and known absent alternative attachment'
        unit = by_id.get(rule['unit_id'])
        if (rule.get('reviewed') is True and rules.get('up_axis') == '+Z' and
                rule.get('expected') is True and unit and rule.get('attachment_known_absent') is True):
            contact = unit.get('support', {})
            receivers = {s['receiver'] for s in contact.get('supports', []) if s.get('value') == 1.}
            allowed = set(rule.get('receivers', []))
            if allowed and receivers & allowed:
                value, reason = 0., None
            elif (geometry.get('support_receivers_complete') is True and
                  unit.get('floating', {}).get('status') == 'floating'):
                value, reason = 1., None
            else:
                reason = 'Incomplete contacts, unspecified receiver, penetration, or possible missed support'
        checks['support'].append(dict(unit_id=rule['unit_id'],value=value,reason=reason))
    components = {c['name']: c for c in geometry.get('components', [])}
    for rule in rules.get('degeneration', []):
        value, reason = None, 'Requires reviewed volumetric expectation and complete evaluated geometry'
        parts = [components.get(name) for name in rule.get('components', [])]
        if (rule.get('reviewed') is True and rule.get('must_enclose_volume') is True and
                parts and all(p is not None for p in parts)):
            # Exact planar rank plus explicit volumetric expectation is stronger than thinness.
            # Nonflat geometry is not automatically declared a valid complete 3D reconstruction.
            unit = by_id.get(rule['unit_id'], {})
            if len(parts)==1:
                planar = parts[0].get('affine_rank',3)<=2
            else:
                # Several flat faces can form a sound 3D object; test their joint span.
                planar = (set(unit.get('component_names',[]))==set(rule['components']) and
                          unit.get('affine_rank',3)<=2)
            if planar:
                value, reason = 1., 'Planar evaluated geometry violates reviewed volumetric expectation'
            elif rule.get('reviewed_structure_valid') is True:
                value, reason = 0., None
            else:
                reason = 'Non-planarity alone cannot verify structural fidelity'
        checks['degeneration'].append(dict(unit_id=rule['unit_id'],value=value,reason=reason))
    for c in geometry.get('components', []):
        if c.get('affine_rank',3) <= 2:
            diagnostics.append(dict(kind='planar_geometry_candidate',component=c['name'],
                                    reason='No penalty without reviewed category/volumetric expectation'))
    energies = {}
    for key, rows in checks.items():
        valid = [r['value'] for r in rows if r['value'] is not None]
        energies[key] = dict(value=float(np.mean(valid)) if valid else None,
            status='valid' if valid and len(valid)==len(rows) else 'partial' if valid else 'unavailable',
            valid_count=len(valid), check_count=len(rows), coverage=len(valid)/len(rows) if rows else None,
            reason=None if valid else 'No reliable reviewed structural checks')
    usable = [(k,e['value']) for k,e in energies.items() if e['value'] is not None]
    total = sum(POLICY['structure_weights'][k]*v for k,v in usable)/sum(POLICY['structure_weights'][k] for k,_ in usable) if usable else None
    count = sum(e['check_count'] for e in energies.values())
    covered = sum(e['valid_count'] for e in energies.values())
    return dict(energy=total, energies=energies, check_coverage=covered/count if count else None,
        checks=checks, diagnostics=diagnostics, raw_geometry=geometry,
        existing_triage=triage, rules=rules, weight_status='provisional',
        limitations=['E_3D is conditional on available reviewed checks, not a completeness certificate.',
                     'BVH witnesses are sampled candidates; normal assemblies are not penalized.',
                     'Support is static Z-up geometry, not physical stability; thinness alone is not degeneration.'])
