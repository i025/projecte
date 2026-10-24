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


def write_json(path, data):
    import json
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
