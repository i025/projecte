"""Trusted fixed-camera renderer/fixture, executed by the bounded CPU launcher only."""
import json
from itertools import combinations
from pathlib import Path
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from e_harness.benchmark_config import RENDER, SCENE_BENCHMARK, write_json
from e_harness.runtime.blender_entry import render_settings
from benchmark.render import metadata, export
from benchmark.geometry import (semantic_unit, collision, support,
                                floating_check, reject_penetrating_support)
from examples.multilevel_blender import evaluated

INTRINSICS = ('type','lens','sensor_fit','sensor_width','sensor_height','shift_x','shift_y',
              'ortho_scale','clip_start','clip_end')


def benchmark_camera(scene, config, intrinsics=None):
    """Fresh unparented camera removes Agent constraints, animation and transform edits."""
    submitted = scene.camera
    if intrinsics is None and submitted is None:
        raise ValueError('Agent must submit camera intrinsics or an active camera')
    values = intrinsics or {k:getattr(submitted.data,k) for k in INTRINSICS}
    if values.get('type','PERSP') not in {'PERSP','ORTHO'}:
        raise ValueError('Only perspective and orthographic intrinsics are supported')
    cam = bpy.data.cameras.new('BenchmarkCamera')
    for key in INTRINSICS:
        if key in values:
            setattr(cam, key, values[key])
    nums = [getattr(cam,k) for k in INTRINSICS if k not in {'type','sensor_fit'}]
    if not np.isfinite(nums).all() or not (cam.sensor_width>0 and cam.sensor_height>0
            and (cam.type!='PERSP' or 1<=cam.lens<=300) and (cam.type!='ORTHO' or cam.ortho_scale>0)
            and 0<cam.clip_start<cam.clip_end and abs(cam.shift_x)<=2 and abs(cam.shift_y)<=2):
        raise ValueError('Illegal Agent intrinsics')
    # Reject Blender property clamping instead of silently changing submitted K.
    for key in values:
        if key not in INTRINSICS:
            raise ValueError('Unexpected intrinsic parameter: '+key)
        if isinstance(values[key], (float,int)) and not np.isclose(getattr(cam,key),values[key],rtol=1e-6,atol=1e-7):
            raise ValueError('Blender clamped intrinsic parameter: '+key)
    t0 = np.asarray(config['matrix_world'],float)
    if (t0.shape!=(4,4) or not np.isfinite(t0).all() or not np.allclose(t0[3],[0,0,0,1])
            or not np.allclose(t0[:3,:3].T@t0[:3,:3],np.eye(3),atol=1e-6)
            or not np.isclose(np.linalg.det(t0[:3,:3]),1.)):
        raise ValueError('T0 must be a finite rigid camera-to-world matrix')
    obj = bpy.data.objects.new('BenchmarkCamera',cam)
    scene.collection.objects.link(obj)
    obj.matrix_world = Matrix(t0.tolist())
    scene.camera = obj
    bpy.context.view_layer.update()
    return obj


def configure(scene, config):
    render_settings(dict(samples=config['samples'],resolution=config['resolution']))
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1.
    scene.render.use_border=scene.render.use_crop_to_border=False
    scene.render.use_motion_blur=False
    scene.render.film_transparent=False
    scene.render.use_sequencer=False
    for index, layer in enumerate(scene.view_layers):
        layer.use = index==0
    scene.display_settings.display_device='sRGB'
    scene.view_settings.view_transform='Standard'
    scene.view_settings.look='None'
    scene.view_settings.exposure=0.
    scene.view_settings.gamma=1.
    scene.view_settings.use_curve_mapping=False
    scene.camera.data.dof.use_dof=False
    scene.cycles.use_denoising=False


def geometry_evidence(scene, groups, rules):
    parts = {}
    surfaces = [o for o in scene.objects if o.type in {'MESH','CURVE'} and not o.hide_render]
    if len(surfaces)>150:
        raise ValueError('Structural inspection limited to 150 components')
    for obj in surfaces:
        c = evaluated(obj)
        if len(c['triangles'])>50000:
            raise ValueError('Structural inspection limited to 50000 triangles/component')
        parts[obj.name]=c
    rows = groups or [dict(unit_id=name,scene_ids=[name],reviewed=False) for name in parts]
    owned = [p for r in rows for p in r['scene_ids']]
    if len(owned)!=len(set(owned)) or set(owned)-parts.keys():
        raise ValueError('Geometry groups must have unique existing components')
    units = [semantic_unit(r['unit_id'],[parts[p] for p in r['scene_ids']]) for r in rows]
    if len(units)>50:
        raise ValueError('Structural inspection limited to 50 semantic/candidate units')
    pairs=[dict(unit_ids=[u['unit_id'],v['unit_id']],**collision(u,v)) for u,v in combinations(units,2)]
    objects=[]
    for u in units:
        contact=reject_penetrating_support(u['unit_id'],support(u,units),pairs)
        rule=next((r for r in rules.get('support',[]) if r['unit_id']==u['unit_id']),{})
        floating=floating_check(contact,attachment_known_absent=(rule.get('reviewed') is True and
            rule.get('attachment_known_absent') is True and rules.get('up_axis')=='+Z'))
        objects.append(dict(unit_id=u['unit_id'],bounds=u['bounds'].tolist(),support=contact,floating=floating,
            component_names=[c['name'] for c in u['components']],
            affine_rank=int(np.linalg.matrix_rank(u['vertices']-u['vertices'].mean(0)))))
    return dict(collisions=pairs,objects=objects,semantic_grouping_reviewed=all(r.get('reviewed') is True for r in rows),
        support_receivers_complete=rules.get('support_receivers_complete') is True,
        components=[dict(name=n,closed=c['closed'],bounds=c['bounds'].tolist(),volume_estimate=c['volume_estimate'],
            affine_rank=int(np.linalg.matrix_rank(c['vertices']-c['vertices'].mean(0))),
            vertex_count=len(c['vertices']),triangle_count=len(c['triangles'])) for n,c in parts.items()],
        scope='Evaluated scene coordinates; +Z up; geometry-only candidates, semantic triage required')


def fixture(variant):
    """Small source-controlled primitives. No external code or assets are accepted."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.world=bpy.data.worlds.new('FixtureWorld');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.6,.6,.6,1)
    def cube(name, location, scale, color):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object;obj.name=name;obj.scale=scale
        mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
        mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
        obj.data.materials.append(mat)
        return obj
    cube('floor',(0,0,-.15),(7,5,.3),(.22,.5,.22) if variant!='color' else (.55,.1,.1))
    if variant!='deleted':
        if variant=='billboard':
            bpy.ops.mesh.primitive_plane_add(size=1,location=(-1,0,1),rotation=(np.pi/2,0,0))
            bpy.context.object.name='anchor';bpy.context.object.scale=(1,1.5,1)
        else:
            cube('anchor',(-1 if variant!='moved' else -.1,0,.75),(1,1,1.5),(.8,.12,.08))
    cube('other',(1 if variant!='penetration' else -.7,0,.5),(1,1,1),(.1,.2,.8))
    for i in range(6):
        cube('repeat_'+str(i),(-2+i*.8,1.3 if variant!='distribution' else (-1.4 if i%2 else 1.8),.12),(.25,.25,.24),(.9,.8,.2))
    bpy.ops.object.light_add(type='AREA',location=(0,-3,5));bpy.context.object.data.energy=450
    bpy.context.object.data.shape='DISK';bpy.context.object.data.size=4
    bpy.ops.object.camera_add(location=(50,50,50))
    scene.camera=bpy.context.object
    scene.camera.data.lens=42;scene.camera.data.sensor_fit='HORIZONTAL'
    scene.camera.data.shift_x=.05
    if variant=='ortho':
        scene.camera.data.type='ORTHO'
        scene.camera.data.ortho_scale=7.
    # A malicious/mistaken source transform must not survive benchmark_camera().
    scene.camera.rotation_euler=(1.,2.,3.)
    bpy.context.view_layer.update()
    return scene


def main():
    job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text())
    out=Path(job['output']);config=job.get('render',RENDER)
    if job.get('fixture'):
        scene=fixture(job['fixture'])
    else:
        bpy.context.preferences.filepaths.use_scripts_auto_execute=False
        bpy.ops.wm.open_mainfile(filepath=job['blend'],use_scripts=False)
        scene=bpy.context.scene
    benchmark_camera(scene,config,job.get('intrinsics'))
    configure(scene,config)
    rows=job.get('groups',[])
    # Component IDs are observations; they are not semantic Anchor identities.
    mappings=rows or [dict(unit_id=f'component_{i:04}',scene_ids=[o.name],reviewed=False)
                     for i,o in enumerate(scene.objects) if o.type in {'MESH','CURVE'}]
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',r['unit_id']) or r['unit_id'] in {'.','..'} for r in mappings):
        raise ValueError('Unsafe geometry unit ID')
    export(scene,metadata(scene),{'mappings':mappings},out,[],image_size=tuple(config['resolution']),include_normals=True)
    exported=json.loads((out/'export_metadata.json').read_text())
    exported.update(fixed_T0=config['matrix_world'],ortho_scale=scene.camera.data.ortho_scale,
                    fixed_extrinsics_enforced=True,color_management=metadata(scene)['color_management'],
                    component_identity_is_semantics=False)
    write_json(out/'export_metadata.json',exported)
    try:
        geometry=geometry_evidence(scene,rows,job.get('rules',{}))
    except (ValueError,RuntimeError) as exc:
        geometry=dict(status='unavailable',reason=f'{type(exc).__name__}: {exc}',
                      scope='RGB export succeeded; structural evidence is unavailable, not a zero error')
    write_json(out/'geometry.json',geometry)
    write_json(out/'result.json',dict(success=True,scene_validity='valid',source_saved=False,
                                    structural_status=geometry.get('status','candidates_available')))


if __name__=='__main__':
    main()
