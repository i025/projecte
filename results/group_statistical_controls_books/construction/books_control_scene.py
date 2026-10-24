"""Trusted synthetic book fixture: primitives only, CPU render, no external scene."""
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector

job=Path(sys.argv[sys.argv.index('--')+1])
cfg=json.loads(job.read_text())
started=time.monotonic()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene


def material(name,color,roughness=.5):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=color
    bsdf.inputs['Roughness'].default_value=roughness
    return mat


def cuboid(name,size,location,mat,parent=None,bevel=.003):
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0))
    obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.parent=parent;obj.location=location;obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('small rounded edges','BEVEL');mod.width=bevel;mod.segments=1
    return obj


shelf=cfg['shelf']
wood=material('shelf wood',shelf['wood_color'])
back=material('back panel',shelf['back_color'])
floor=material('studio floor',cfg['background_color'],.7)
width=shelf['width'];depth=shelf['depth'];thick=shelf['board_thickness']
levels=shelf['levels'];height=levels[-1]-levels[0]+thick
middle=(levels[-1]+levels[0])/2
for n,z in enumerate(levels):cuboid('fixed shelf board '+str(n),(width,depth,thick),(0,0,z),wood)
for x in (-width/2-thick/2,width/2+thick/2,0.):
    cuboid('fixed vertical support '+str(x),(thick,depth,height),(x,0,middle),wood)
cuboid('fixed back panel',(width+2*thick,.06,height),(0,shelf['back_y'],middle),back)
cuboid('studio floor',(200,200,.08),(0,0,.075),floor,bevel=0)
paper=material('constant cream page blocks',[.88,.84,.72,1.],.8)
trim=material('constant spine trim',[.80,.69,.42,1.],.55)
book_roots=[]
for book in cfg['books']:
    t,d,h=book['dimensions'];cover=.012
    root=bpy.data.objects.new(book['id'],None);scene.collection.objects.link(root)
    root.location=book['location'];root.rotation_euler=(0,book['rotation_y'],0)
    color=material(book['id']+' cover',book['cover_color'])
    cuboid(book['id']+' pages',(t-2*cover,d-.028,h-.034),(0,.006,0),paper,root,.001)
    for sign in (-1,1):
        cuboid(book['id']+' cover '+str(sign),(cover,d,h),(sign*(t-cover)/2,0,0),color,root,.002)
    cuboid(book['id']+' closed spine',(t,.016,h),(0,-d/2+.008,0),color,root,.002)
    for z in (-.28*h,.28*h):
        cuboid(book['id']+' decorative spine band '+str(z),(t+.001,.002,.007),(0,-d/2-.001,z),trim,root,0)
    book_roots.append(root)

lighting=cfg['lighting']
scene.world=bpy.data.worlds.new('constant studio world');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.8,.85,.92,1.)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=lighting['world_strength']
for key in ('key','fill'):
    data=bpy.data.lights.new(key,'AREA');data.energy=lighting[key+'_energy'];data.shape='DISK';data.size=lighting[key+'_size']
    obj=bpy.data.objects.new(key,data);scene.collection.objects.link(obj);obj.location=lighting[key+'_location']
    obj.rotation_euler=(Vector((0,0,1.))-obj.location).to_track_quat('-Z','Y').to_euler()
camera=bpy.data.cameras.new('fixed camera');obj=bpy.data.objects.new('fixed camera',camera)
scene.collection.objects.link(obj);obj.location=cfg['camera']['location']
obj.rotation_euler=(Vector(cfg['camera']['target'])-obj.location).to_track_quat('-Z','Y').to_euler()
camera.lens=cfg['camera']['lens_mm'];camera.sensor_width=cfg['camera']['sensor_width_mm'];scene.camera=obj
settings=cfg['rendering']
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=settings['samples']
scene.cycles.use_adaptive_sampling=False;scene.cycles.seed=settings['seed'];scene.cycles.max_bounces=settings['max_bounces']
scene.cycles.use_denoising=False;scene.cycles.denoising_use_gpu=False
scene.render.threads_mode='FIXED';scene.render.threads=2
scene.render.resolution_x,scene.render.resolution_y=settings['resolution'];scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
scene.render.use_stamp=False
scene.view_settings.view_transform=settings['view_transform'];scene.view_settings.exposure=settings['exposure'];scene.view_settings.gamma=settings['gamma']
scene.render.filepath=cfg['output']
bpy.context.view_layer.update()
render_start=time.monotonic();bpy.ops.render.render(write_still=True)
metadata=dict(engine=scene.render.engine,device=scene.cycles.device,threads=scene.render.threads,
    samples=scene.cycles.samples,seed=scene.cycles.seed,denoising=False,
    resolution=[scene.render.resolution_x,scene.render.resolution_y],
    camera_matrix=[list(row) for row in scene.camera.matrix_world],
    book_world_matrices={o.name:[list(row) for row in o.matrix_world] for o in book_roots},
    book_count=len(book_roots),text_objects=sum(o.type=='FONT' for o in scene.objects),
    render_seconds=time.monotonic()-render_start,total_seconds=time.monotonic()-started,
    external_assets=False,historical_agent_code=False,reviewed=False,labels_source='construction_expected')
with Path(cfg['metadata']).open('x') as stream:json.dump(metadata,stream,indent=2)
