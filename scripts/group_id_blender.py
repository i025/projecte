"""One CPU IndexOB render, using only a reviewed helper and an unchanged camera."""
import json
from pathlib import Path
import subprocess
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text())
if any(str(Path('/proc/self/ns/'+kind).readlink())==job['parent_'+kind+'_namespace'] for kind in ('mnt','net')):
    raise RuntimeError('Private namespaces required')
for path in (job['source_directory'],job['blend']):
    subprocess.run(['/usr/bin/mount','--bind',path,path],check=True)
    subprocess.run(['/usr/bin/mount','-o','remount,bind,ro',path],check=True)


def clear_handlers():
    for name in dir(bpy.app.handlers):
        value=getattr(bpy.app.handlers,name)
        if isinstance(value,list):value.clear()


bpy.context.preferences.filepaths.use_scripts_auto_execute=False
clear_handlers()
bpy.ops.wm.open_mainfile(filepath=job['blend'],use_scripts=False,load_ui=False)
clear_handlers()
if bpy.context.preferences.filepaths.use_scripts_auto_execute or bpy.data.libraries or bpy.data.texts:
    raise RuntimeError('Unexpected scripts or external dependencies; stop')
scene=bpy.context.scene;camera=scene.camera;expected=job['expected_camera']
if not camera or camera.name_full!=expected['object_id']:
    raise RuntimeError('Saved camera identity mismatch')
if (not np.allclose(np.array(camera.matrix_world),expected['matrix_world'],atol=1e-6,rtol=0)
        or camera.data.type!=expected['type'] or abs(camera.data.lens-expected['lens_mm'])>1e-6
        or abs(camera.data.sensor_width-expected['sensor_width_mm'])>1e-6
        or abs(camera.data.sensor_height-expected['sensor_height_mm'])>1e-6
        or camera.data.sensor_fit!=expected['sensor_fit']
        or not np.allclose([camera.data.shift_x,camera.data.shift_y],expected['shift_xy'],atol=1e-6)):
    raise RuntimeError('Saved camera numerical parameters differ')
old=job['expected_scene']
if (scene.render.engine!='CYCLES' or scene.name!=old['name'] or scene.frame_current!=old['frame']
        or [scene.render.resolution_x,scene.render.resolution_y]!=old['resolution']
        or scene.render.resolution_percentage!=100 or scene.render.use_border
        or scene.render.use_crop_to_border or scene.render.use_motion_blur
        or camera.data.dof.use_dof):
    raise RuntimeError('Scene/render state differs or unsupported projection effects')
for obj in bpy.data.objects:
    if obj.animation_data and obj.animation_data.drivers:raise RuntimeError('Unexpected object driver')
    obj.pass_index=0
mapping=[]
for row in job['mapping']:
    obj=bpy.data.objects.get(row['object_id'])
    if obj is None or obj.type!='MESH' or not np.allclose(np.array(obj.matrix_world),row['matrix_world'],atol=1e-6,rtol=0):
        raise RuntimeError('Candidate geometry missing/changed')
    bottom=min((obj.matrix_world@Vector(v)).z for v in obj.bound_box)
    if abs(bottom-float(row['row_hint']))>.01:raise RuntimeError('Layer ownership not supported by geometry')
    obj.pass_index=row['index'];mapping.append(dict(index=row['index'],object_id=row['object_id'],row_hint=row['row_hint']))

native=[scene.render.resolution_x,scene.render.resolution_y]
aspect=[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y]
w=512;h=round(native[1]*w/native[0])
# Compensate integer resolution rounding in pixel aspect, preserving the saved camera frame.
desired=native[0]*aspect[0]/(native[1]*aspect[1]);ratio=desired/(w/h)
new_aspect=[ratio,1.] if ratio>=1 else [1.,1./ratio]
scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.resolution_percentage=100
scene.render.pixel_aspect_x,scene.render.pixel_aspect_y=new_aspect
scene.render.threads_mode='FIXED';scene.render.threads=2
scene.cycles.device='CPU';scene.cycles.samples=1
scene.cycles.use_adaptive_sampling=False;scene.cycles.use_denoising=False
scene.cycles.denoising_use_gpu=False
scene.render.use_persistent_data=False;scene.render.use_sequencer=False;scene.render.use_compositing=True
if hasattr(scene.render,'compositor_device'):scene.render.compositor_device='CPU'
for layer in scene.view_layers:
    layer.use=layer==bpy.context.view_layer
    layer.cycles.use_denoising=False
layer=bpy.context.view_layer;layer.use_pass_object_index=True
if hasattr(layer,'update_render_passes'):layer.update_render_passes()
scene.use_nodes=True;tree=scene.node_tree;tree.nodes.clear()
rl=tree.nodes.new('CompositorNodeRLayers');rl.layer=layer.name
if rl.outputs.get('IndexOB') is None:raise RuntimeError('IndexOB socket unavailable; no render')
folder=Path(job['pass_directory']);folder.mkdir(exist_ok=False)
node=tree.nodes.new('CompositorNodeOutputFile');node.base_path=str(folder)
node.format.file_format='OPEN_EXR';node.format.color_mode='RGB';node.format.color_depth='32';node.format.exr_codec='ZIP'
node.file_slots[0].path='object_ids_';tree.links.new(rl.outputs['IndexOB'],node.inputs[0])
beauty=tree.nodes.new('CompositorNodeOutputFile');beauty.base_path=str(folder)
beauty.format.file_format='PNG';beauty.format.color_mode='RGB';beauty.format.color_depth='8'
beauty.file_slots[0].path='low_rgb_';tree.links.new(rl.outputs['Image'],beauty.inputs[0])
settings=dict(pass_type='Cycles IndexOB',resolution=[w,h],original_resolution=native,
    original_pixel_aspect=aspect,pixel_aspect=[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y],
    saved_camera_frame_preserved=True,alpha_threshold=layer.pass_alpha_threshold,
    samples=1,threads=2,device=scene.cycles.device,denoising=False,
    camera_unchanged=True,materials_lights_and_occluders_preserved=True,
    title_parts_included=False,index_zero_includes_all_nonbody_objects=True,
    autoexec=False,source_saved=False,reviewed=False)
Path(job['settings']).write_text(json.dumps(settings,indent=2))
# Exactly one render call. No fallback, retry, engine switch, or second pass render.
started=time.monotonic()
bpy.ops.render.render(write_still=False)
seconds=time.monotonic()-started
files=list(folder.glob('object_ids_*.exr'))
if len(files)!=1:raise RuntimeError('Expected one raw IndexOB EXR')
image=bpy.data.images.load(str(files[0]),check_existing=False)
iw,ih=image.size;channels=image.channels
pixels=np.array(image.pixels[:],dtype=np.float32).reshape(ih,iw,channels)
if (iw,ih)!=(w,h) or channels<3:raise RuntimeError('ID pass shape/channels invalid')
pixels=np.flipud(pixels)
raw=pixels[:,:,0]
if not np.isfinite(raw).all() or not np.allclose(pixels[:,:,1:3],raw[:,:,None],atol=1e-5):
    raise RuntimeError('ID channels disagree/nonfinite')
rounded=np.rint(raw)
if np.max(np.abs(raw-rounded))>1e-4 or not set(np.unique(rounded))<=set(range(len(mapping)+1)):
    raise RuntimeError('Nonintegral/unexpected IndexOB values; no reliable mask')
ids=rounded.astype(np.uint16)
np.save(job['ids'],ids,allow_pickle=False)
Path(job['result']).write_text(json.dumps(dict(status='id_pass_extracted',settings=settings,
    render_calls=1,render_seconds=seconds,index_values=np.unique(ids).tolist(),mapping=mapping,
    raw_exr=str(files[0]),id_array=job['ids'],source_blend_saved=False,
    reviewed=False,usage='provisional/debug'),indent=2))
print('SINGLE_CPU_ID_PASS_COMPLETE',w,h,len(np.unique(ids))-1,'body IDs sampled')
