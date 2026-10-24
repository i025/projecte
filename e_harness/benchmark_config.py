"""One benchmark policy; these weights and thresholds are provisional, not calibrated."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# Reuse the existing sibling evaluator without copying it or modifying its gates.
SCENE_BENCHMARK = ROOT.parent / 'scene-benchmark'
if str(SCENE_BENCHMARK) not in sys.path:
    sys.path.insert(0, str(SCENE_BENCHMARK))

ENERGIES = ('semantic', 'spatial', 'appearance', 'statistical', 'perceptual')
POLICY = {
    'weight_status': 'provisional',
    'weights': dict.fromkeys(ENERGIES, 1.0),
    'levels': {'global': .25, 'region': .5, 'anchor': .25},
    'structure_weights': {'penetration': 1., 'support': 1., 'degeneration': 1.},
    'grid': 2, 'min_pixels': 16, 'edge_threshold': .08,
    'match_max_cost': .85, 'relation_margin': .01,
    'multiscale': (1., .5), 'dino_size': 224, 'max_anchors': 12,
    'distribution_grids': {4: 1., 8: 1., 16: 1.},
    'statistical_components': {'texture': .5, 'distribution': .5},
    'misplaced_center_fraction': .05,  # max per-axis image fraction; diagnostic, not an energy weight
}
# Blender camera-to-world, right-handed Z-up; camera local -Z looks forward, +Y up.
FIXED_T0 = [[1., 0., 0., 0.], [0., 0., -1., -6.],
            [0., 1., 0., 2.], [0., 0., 0., 1.]]
RENDER = {'resolution': [128, 128], 'samples': 8,
          'matrix_world': FIXED_T0, 'color': 'Standard / None / exposure 0 / gamma 1',
          'device': 'CPU', 'threads': 2, 'timeout': 120}


def camera_pose(matrix, *, require_fixed=False):
    """Validate camera-to-world numerically; a rigid pose is not necessarily T0."""
    import numpy as np
    pose = np.asarray(matrix, dtype=float)
    if (pose.shape != (4, 4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3], [0, 0, 0, 1], rtol=0, atol=1e-6)
            or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), rtol=0, atol=1e-6)
            or not np.isclose(np.linalg.det(pose[:3, :3]), 1., rtol=0, atol=1e-6)):
        raise ValueError('Expected a finite rigid Blender camera-to-world matrix')
    if require_fixed and not np.allclose(pose, FIXED_T0, rtol=0, atol=1e-6):
        raise ValueError('Camera extrinsics differ from prescribed Project e T0')
    return pose


def camera_check(metadata=None):
    """External metadata can establish consistency, never trusted execution."""
    import numpy as np
    metadata = metadata or {}
    candidates = {}
    if isinstance(metadata.get('camera'), dict) and 'matrix_world' in metadata['camera']:
        candidates['camera.matrix_world'] = metadata['camera']['matrix_world']
    for key in ('T_c2w', 'matrix_world'):
        if key in metadata:
            candidates[key] = metadata[key]
    reasons, poses = [], {}
    for key, value in candidates.items():
        try:
            poses[key] = camera_pose(value).tolist()
        except (TypeError, ValueError) as exc:
            reasons.append(f'{key}: {exc}')
    matches = bool(poses) and len(poses) == len(candidates) and all(
        np.allclose(p, FIXED_T0, rtol=0, atol=1e-6) for p in poses.values())
    if poses and not matches:
        reasons.append('Recorded actual pose differs from prescribed T0 or conflicts with another pose')
    if not candidates:
        reasons.append('Actual camera pose unavailable; fixed_T0/boolean declarations are insufficient')
    reasons.append('Static RGB and external JSON do not attest trusted renderer execution or RGB/metadata binding')
    return dict(status='unverified', formal_eligible=False,
        camera_protocol='pose_consistent_unverified' if matches else 'historical_camera' if poses else 'unknown',
        pose_matches_T0=matches, actual_poses=poses, expected_T0=FIXED_T0,
        declared_fixed_extrinsics_enforced=metadata.get('fixed_extrinsics_enforced'),
        reason='; '.join(reasons), reasons=reasons)


def write_json(path, data):
    import json
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
