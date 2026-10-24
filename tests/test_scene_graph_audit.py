import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from scripts.audit_scene_graph import map_bounds, intersection, row_key, summary


class SceneGraphAuditTests(unittest.TestCase):
    def test_projection_respects_letterbox_not_warp(self):
        transform=dict(resized_size=[1258,852],offset_xy=[0,1])
        self.assertEqual(map_bounds([0,0,1,1],transform),[0,1,1258,853])
        self.assertEqual(map_bounds([.5,.5,.75,.75],transform),[629,427,943.5,640])

    def test_bbox_intersection_is_not_visibility(self):
        self.assertEqual(intersection([0,0,2,2],[1,1,3,3]),1)
        self.assertEqual(intersection([0,0,1,1],[1,0,2,1]),0)
        self.assertEqual(intersection([0,0,1,1],[2,2,3,3]),0)

    def test_component_names_not_all_counted_as_sleeve_bodies(self):
        self.assertEqual(row_key(dict(name='VINYL archival sleeve row 1.45 000.001')),'1.45')
        for name in ('LP colored paper narrow title','record library continuous shelf z1.42','black vinyl spinning platter 0'):
            self.assertIsNone(row_key(dict(name=name)))

    def test_geometry_cannot_create_semantic_gt_or_visible_mask(self):
        with TemporaryDirectory() as directory:
            png=Path(directory)/'image.png';Image.new('RGB',(10,10)).save(png)
            mask=Path(directory)/'mask.png';Image.new('L',(10,10),255).save(mask)
            body=dict(id='body',name='VINYL archival sleeve row 1.45 000',data_id='cube',
                matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],world_origin=[0,0,1.6],
                world_aabb=[[0,0,1.45],[.01,.3,1.8]],object_dimensions=[.01,.3,.35],
                collection_ids=['Collection'],parent_id=None,
                base_bounds_projection=dict(status='geometric_bbox_only',xyxy_normalized=[.1,.1,.2,.2]))
            label=dict(id='label',name='LP colored paper narrow title')
            graph=dict(objects=[body,label],meshes=[dict(id='cube',vertex_count=8,polygon_count=6)],
                cameras=[],scene=dict(resolution=[10,10],name='Scene',render_path='image.png'))
            result=summary(graph,dict(reference_group_id='g',group_source='frozen',roi=str(mask),render_rgb=str(png)),
                           dict(resized_size=[10,10],offset_xy=[0,0]))
            self.assertEqual(result['candidate_object_ids'],['body'])
            self.assertEqual(result['candidate_decoration_part_ids'],['label'])
            self.assertTrue(result['geometry']['counts_are_mesh_metadata_not_record_gt'])
            self.assertEqual(result['projection_summary']['actual_visible_mask'],'N/A')
            self.assertIsNone(result['projection_summary']['actual_visible_object_count'])
            self.assertFalse(result['reviewed']);self.assertFalse(result['scorable'])
            self.assertIsNone(result['formal_energy'])

    def test_trusted_reader_never_saves_renders_or_executes_text(self):
        path=Path(__file__).resolve().parents[1]/'scripts/scene_graph_readonly_blender.py'
        tree=ast.parse(path.read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        names={ast.unparse(n.func) for n in calls}
        self.assertFalse(names & {'exec','eval','runpy.run_path','bpy.ops.render.render','bpy.ops.wm.save_as_mainfile'})
        opens=[n for n in calls if ast.unparse(n.func)=='bpy.ops.wm.open_mainfile']
        self.assertEqual(len(opens),1)
        values={k.arg:k.value.value for k in opens[0].keywords if isinstance(k.value,ast.Constant)}
        self.assertIs(values['use_scripts'],False);self.assertIs(values['load_ui'],False)


if __name__=='__main__':unittest.main()
