"""Trusted metadata reader. No render, save, text execution, or evaluated geometry."""
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

job = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text())
if (str(Path('/proc/self/ns/mnt').readlink()) == job['parent_mount_namespace'] or
        str(Path('/proc/self/ns/net').readlink()) == job['parent_net_namespace']):
    raise RuntimeError('Private mount and network namespaces required')
# Only this process namespace changes. Original artifacts and input copy are kernel read-only.
for target in (job['source_directory'], job['blend']):
    subprocess.run(['/usr/bin/mount','--bind',target,target],check=True)
    subprocess.run(['/usr/bin/mount','-o','remount,bind,ro',target],check=True)


def clear_handlers():
    counts = {}
    for name in dir(bpy.app.handlers):
        value = getattr(bpy.app.handlers,name)
        if isinstance(value,list):
            counts[name] = len(value)
            value.clear()
    return {k:v for k,v in counts.items() if v}


bpy.context.preferences.filepaths.use_scripts_auto_execute = False
before = clear_handlers()
bpy.ops.wm.open_mainfile(filepath=job['blend'],use_scripts=False,load_ui=False)
after = clear_handlers()
if bpy.context.preferences.filepaths.use_scripts_auto_execute:
    raise RuntimeError('Script execution preference unexpectedly enabled')
scene = bpy.context.scene
if len(bpy.data.objects)>5000 or sum(len(m.vertices) for m in bpy.data.meshes)>2000000:
    raise RuntimeError('Metadata scope exceeds small audit resource bounds')


def nums(values):
    return [round(float(v),7) for v in values]


def matrix(value):
    return [nums(row) for row in value]


resolution = [round(scene.render.resolution_x*scene.render.resolution_percentage/100),
              round(scene.render.resolution_y*scene.render.resolution_percentage/100)]
camera = scene.camera


def projection(corners):
    if camera is None or camera.data.type not in {'PERSP','ORTHO'}:
        return dict(status='unavailable',reason='No supported stored camera')
    points = [world_to_camera_view(scene,camera,p) for p in corners]
    if any(p.z<=0 for p in points):
        return dict(status='unavailable',reason='Bounds intersect/lie behind camera plane')
    x1,x2=min(p.x for p in points),max(p.x for p in points)
    y1,y2=1-max(p.y for p in points),1-min(p.y for p in points)
    return dict(status='geometric_bbox_only',xyxy_normalized=nums([x1,y1,x2,y2]),
        xyxy_render_pixels=nums([x1*resolution[0],y1*resolution[1],x2*resolution[0],y2*resolution[1]]),
        intersects_frame=bool(x2>0 and x1<1 and y2>0 and y1<1),
        actual_visibility='unknown; no occlusion test or historical Object-ID mask',
        includes_modifiers=False,reviewed=False)


focus = re.compile(r'vinyl|sleeve|record|books?|bookshelf|turntable|speaker|stereo|boombox|\bLP\b',re.I)
objects=[]
for obj in sorted(bpy.data.objects,key=lambda o:o.name):
    corners=[obj.matrix_world @ Vector(v) for v in obj.bound_box] if obj.type in {'MESH','CURVE','SURFACE','FONT','META'} else []
    bounds = [nums(min(p[i] for p in corners) for i in range(3)),
              nums(max(p[i] for p in corners) for i in range(3))] if corners else None
    row=dict(id=obj.name_full,name=obj.name,type=obj.type,data_id=obj.data.name_full if obj.data else None,
        collection_ids=sorted(c.name_full for c in obj.users_collection),
        parent_id=obj.parent.name_full if obj.parent else None,children_ids=sorted(o.name_full for o in obj.children),
        matrix_world=matrix(obj.matrix_world),world_origin=nums(obj.matrix_world.translation),
        object_dimensions=nums(obj.dimensions),world_aabb=bounds,
        hide_render=obj.hide_render,hide_viewport=obj.hide_viewport,
        visible_in_active_view_layer=bool(obj.visible_get()),pass_index=obj.pass_index,
        material_ids=[s.material.name_full for s in obj.material_slots if s.material],
        modifiers=[dict(type=m.type,viewport=m.show_viewport,render=m.show_render) for m in obj.modifiers],
        constraints=[c.type for c in obj.constraints],
        custom_property_keys=sorted(str(k) for k in obj.keys()),reviewed=False)
    if focus.search(obj.name):
        row['name_search_candidate']=True
        row['base_bounds_projection']=projection(corners) if corners else None
    objects.append(row)

meshes=[dict(id=m.name_full,users=m.users,vertex_count=len(m.vertices),edge_count=len(m.edges),
             polygon_count=len(m.polygons)) for m in sorted(bpy.data.meshes,key=lambda m:m.name)]
collections=[dict(id=c.name_full,object_ids=sorted(o.name_full for o in c.objects),
                  child_collection_ids=sorted(x.name_full for x in c.children),
                  hide_render=c.hide_render,hide_viewport=c.hide_viewport,instance_offset=nums(c.instance_offset))
             for c in sorted(bpy.data.collections,key=lambda c:c.name)]
cameras=[]
for obj in sorted((o for o in bpy.data.objects if o.type=='CAMERA'),key=lambda o:o.name):
    data=obj.data
    cameras.append(dict(object_id=obj.name_full,data_id=data.name_full,active=obj==camera,
        matrix_world=matrix(obj.matrix_world),type=data.type,lens_mm=data.lens,
        sensor_fit=data.sensor_fit,sensor_width_mm=data.sensor_width,sensor_height_mm=data.sensor_height,
        shift_xy=[data.shift_x,data.shift_y],clip_start=data.clip_start,clip_end=data.clip_end,
        ortho_scale=data.ortho_scale,dof_enabled=data.dof.use_dof))
drivers=[]
for name in ('objects','scenes','materials','worlds','meshes','cameras','node_groups'):
    for item in getattr(bpy.data,name):
        animation=getattr(item,'animation_data',None)
        if animation and animation.drivers:drivers.append(dict(data_type=name,id=item.name,count=len(animation.drivers)))
passes=[dict(name=l.name,enabled=l.use,object_index=l.use_pass_object_index,
             material_index=l.use_pass_material_index,cryptomatte_object=l.use_pass_cryptomatte_object)
        for l in scene.view_layers]
output=dict(status='metadata_extracted',source_blend=job['source_blend'],
    blender_build=bpy.app.version_string,objects=objects,meshes=meshes,collections=collections,cameras=cameras,
    scene=dict(name=scene.name,object_ids=sorted(o.name_full for o in scene.objects),
        root_collection=scene.collection.name_full,root_collection_children=sorted(c.name_full for c in scene.collection.children),
        frame=scene.frame_current,unit_system=scene.unit_settings.system,unit_scale_length=scene.unit_settings.scale_length,
        resolution=resolution,pixel_aspect=[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y],
        render_path=scene.render.filepath,render_engine=scene.render.engine,
        use_border=scene.render.use_border,use_crop_to_border=scene.render.use_crop_to_border),
    view_layer_passes=passes,external_libraries=[dict(name=l.name,filepath=l.filepath) for l in bpy.data.libraries],
    embedded_text_blocks=[dict(name=t.name,auto_module=t.use_module) for t in bpy.data.texts],drivers=drivers,
    safety=dict(autoexec_enabled=False,open_mainfile_use_scripts=False,load_ui=False,
        handlers_removed_before_load=before,handlers_removed_after_load=after,
        autoexec_fail=bool(bpy.app.autoexec_fail),source_directory_readonly_bind=True,input_copy_readonly_bind=True,
        render_calls=0,save_calls=0,historical_code_executed=False,evaluated_geometry_requested=False),
    object_id_mapping=dict(status='unavailable',reason='No existing Object-ID/segmentation pass found; pass_index is only declared metadata'),
    geometry_scope='Stored base-mesh bounds/transforms; modifiers, occlusion and actual visible surface not evaluated',
    semantic_names_are_gt=False,reviewed=False,usage='provisional/debug')
with Path(job['result']).open('x') as stream:
    json.dump(output,stream,ensure_ascii=False,indent=2,allow_nan=False)
print('READONLY_METADATA_COMPLETE',len(objects),'objects',len(meshes),'mesh datablocks')
