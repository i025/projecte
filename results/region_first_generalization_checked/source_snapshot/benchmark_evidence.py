"""Reference-only hierarchical evidence. Candidate review flags are never upgraded."""
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image

from .benchmark_config import POLICY
from benchmark.metrics import mask_iou, bbox_iou, local_dino_extractor  # reused public APIs
from benchmark.evidence import sam2_box_masks, relateanything_candidates, local_vqa


REGION_FIRST_SCHEMA = {
    'type':'object', 'additionalProperties':False, 'required':['regions'],
    'properties':{'regions':{
        'type':'array', 'minItems':2, 'maxItems':5,
        'items':{'type':'object', 'additionalProperties':False,
                 'required':['id','name','location','content'],
                 'properties':{
                     'id':{'type':'string','pattern':'^R[1-5]$'},
                     'name':{'type':'string','minLength':1,'maxLength':80},
                     'location':{'type':'string','minLength':1,'maxLength':160},
                     'content':{'type':'string','minLength':1,'maxLength':400}}}}}}


def validate_region_first_plan(answer):
    """Small exact-schema check; uniqueness/whitespace are additional constraints.

    This checks structure, not semantic correctness or pixel localization.
    No object vocabulary, expected Region names or automatic review decisions.
    """
    import re
    if not isinstance(answer,dict) or set(answer)!={'regions'}:
        raise ValueError('Expected only the regions field')
    schema=REGION_FIRST_SCHEMA['properties']['regions']
    rows=answer['regions']
    if not isinstance(rows,list) or not schema['minItems']<=len(rows)<=schema['maxItems']:
        raise ValueError('Expected 2–5 Regions')
    seen=set();clean=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!=set(schema['items']['required']):
            raise ValueError('Each Region requires only id, name, location, content')
        for key,rule in schema['items']['properties'].items():
            value=row[key]
            if not isinstance(value,str) or not value.strip() or len(value)>rule.get('maxLength',10):
                raise ValueError('Invalid Region text: '+key)
            if 'pattern' in rule and re.fullmatch(rule['pattern'],value) is None:
                raise ValueError('Expected Region ID R1–R5')
        if row['id'] in seen: raise ValueError('Duplicate Region ID')
        seen.add(row['id']);clean.append({key:row[key].strip() for key in row})
    return {'regions':clean}


# Small shared noun translations, used only on actual descriptions/candidate
# metadata. No scene/Region IDs, coordinates, expected partitions or priorities.
GROUNDING_CONCEPTS = {
    'bookshelf':('bookshelf','bookcase','书架','书柜'),
    'books collection':('books','books group','book collection','书籍'),
    'vinyl records':('vinyl records','records group','record collection','唱片'),
    'desk':('desk','书桌'), 'monitor':('monitor','显示器'),
    'lamp':('lamp','台灯'), 'chair':('chair','transparent chair','椅子','椅'),
    'sofa':('sofa','couch','沙发'), 'globe':('globe','地球仪'),
    'aquarium':('aquarium','水族箱','鱼缸'), 'boombox':('boombox','收录机'),
    'turntable':('turntable','唱盘'), 'audio equipment':('audio equipment','音响'),
    'cushions':('cushion','cushions','靠垫'), 'pillows':('pillow','pillows','抱枕'),
    'decorative objects':('decorative objects','摆件'), 'picture':('picture','图片'),
    'table':('table','桌子','圆桌'), 'refrigerator':('refrigerator','fridge','冰箱'),
    'potted plant':('potted plant','盆栽'), 'wall':('wall','墙壁','墙面'),
    'ceiling':('ceiling','顶棚','天花板'), 'floor':('floor','地板'),
}


def grounding_concepts(text):
    import re
    text=text.lower()
    found=set()
    for concept,aliases in GROUNDING_CONCEPTS.items():
        for alias in aliases:
            matched=(alias in text) if not alias.isascii() else bool(re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',text))
            if matched:found.add(concept);break
    return found


def region_sam3_prompts(regions, limit=6):
    """Bounded prompts from the supplied plan only; no object-instance enumeration."""
    import re
    rows=[]
    for region in regions:
        concepts=grounding_concepts(region['name'])|grounding_concepts(region['content'])
        prompts=sorted(concepts)[:limit]
        if not prompts:
            prompts=[x.strip() for x in re.split('[、，,;；]',region['content']) if x.strip()][:limit]
        rows.append(dict(region_id=region['id'],prompts=prompts,location=region['location'],
                         source='Plan-derived noun translation; no per-instance prompts',reviewed=False))
    return rows


def ground_region_candidates(regions, candidates, shape, *, specific=False):
    """Associate existing SAM masks by plan nouns; model scores never become q.

    Returns overlapping candidate unions and separate heuristic support scores.
    A named concept outranks an incidental mention of that same concept in a
    different Region. Contains no image-specific boxes or Region-ID ordering.
    """
    from scipy import ndimage
    names=[grounding_concepts(r['name']) for r in regions]
    contents=[grounding_concepts(r['content']) for r in regions]
    masks=np.zeros((len(regions),*shape),bool)
    scores=np.zeros(masks.shape,np.float32)
    associations=[]
    yy,xx=np.indices(shape,dtype=np.float32)
    xx=(xx+.5)/shape[1];yy=(yy+.5)/shape[0]
    for candidate in candidates:
        mask=np.asarray(candidate['mask'],bool)
        if mask.shape!=shape:raise ValueError('Candidate mask grid differs from original RGB')
        if not mask.any():continue
        concepts=grounding_concepts(candidate.get('category',''))
        if not concepts:continue
        primary=[bool(concepts&n) for n in names]
        area=float(mask.mean())
        distance=ndimage.distance_transform_edt(mask)
        interior=np.minimum(distance/max(1.,float(np.percentile(distance[mask],95))),1.)
        for index,region in enumerate(regions):
            mention=bool(concepts&contents[index])
            if not primary[index] and not mention:continue
            suppressed=specific and any(primary) and not primary[index]
            associations.append(dict(region_id=region['id'],candidate_id=candidate['id'],category=candidate['category'],
                 name_match=primary[index],content_match=mention,suppressed_incidental_mention=suppressed,
                 raw_score_used_as_reliability=False,reviewed=False))
            if suppressed:continue
            masks[index]|=mask
            semantic=.9 if primary[index] else .85
            location=region.get('location','').lower()
            prior=np.full(shape,.5,np.float32)
            # Soft positional evidence, with no scene-specific coordinate cutoffs.
            parts=[]
            left=('左' in location or 'left' in location);right=('右' in location or 'right' in location)
            top=('上' in location or 'top' in location or 'upper' in location)
            bottom=('下' in location or '前景' in location or 'bottom' in location or 'foreground' in location)
            if left!=right:parts.append(1-xx if left else xx)
            if top!=bottom:parts.append(1-yy if top else yy)
            if parts:prior=np.mean(parts,axis=0)
            # Area is a weak specificity cue; boundary interiors do not fabricate
            # pixels outside candidate masks. All weights are uncalibrated.
            value=semantic*(1-.5*area)+.04*interior+.04*prior
            scores[index]=np.maximum(scores[index],np.where(mask,value,0.))
    return dict(region_ids=[r['id'] for r in regions],masks=masks,scores=scores,associations=associations,
                score_definition='Uncalibrated semantic/area-specificity + SAM-boundary interior + soft location; not reliability',
                reviewed=False)


def consensus_sam_candidates(candidates):
    """Within-source union, cross-source intersection for the same concept.

    This is a conservative diagnostic, not calibrated agreement or GT. A missing
    source prediction is not evidence of absence: single-source masks stay
    candidates and remain explicitly single-source. No Region IDs are consulted.
    """
    import re
    groups={}
    for row in candidates:
        concepts=tuple(sorted(grounding_concepts(row.get('category',''))))
        if not concepts:continue
        source=row.get('method','unknown_source')
        group=groups.setdefault(concepts,{})
        mask=np.asarray(row['mask'],bool)
        if source in group:group[source]|=mask
        else:group[source]=mask.copy()
    result=[]
    for concepts,by_source in sorted(groups.items()):
        sources=sorted(by_source)
        stack=np.stack([by_source[source] for source in sources])
        mask=stack.all(axis=0) if len(sources)>1 else stack[0]
        result.append(dict(id='consensus_'+re.sub('[^a-z0-9]+','_', '_'.join(concepts)),
             category=' / '.join(concepts),mask=mask,source_methods=sources,source_count=len(sources),
             source_union_pixels=int(stack.any(axis=0).sum()),consensus_pixels=int(mask.sum()),
             status='cross_source_candidate' if len(sources)>1 else 'single_source_unverified',
             reviewed=False,mask_reviewed=False,reliability=0.))
    return result


def resolve_region_conflicts(masks, scores=None, *, margin=.08):
    """Disjoint support; ties/weak differences abstain. No Region-order priority.

    reason: 0=no support, 1=single supported Region, 2=separated winner,
    3=ambiguous conflict left Unassigned. Unsupported pixels are never filled.
    """
    masks=np.asarray(masks,bool)
    if masks.ndim!=3 or not len(masks):raise ValueError('Expected nonempty RxHxW masks')
    if not np.isfinite(margin) or not 0<margin<=1:raise ValueError('Positive finite conflict margin required')
    count=masks.sum(axis=0)
    reason=np.zeros(count.shape,np.uint8);reason[count==1]=1
    output=masks&(count==1)
    if scores is not None:
        scores=np.asarray(scores,float)
        if scores.shape!=masks.shape or not np.isfinite(scores).all() or (scores<0).any():
            raise ValueError('Finite nonnegative RxHxW association scores required')
        supported=np.where(masks,scores,-np.inf)
        best=supported.max(axis=0)
        if len(masks)>1:
            second=np.partition(supported,-2,axis=0)[-2]
            difference=np.zeros(count.shape,float)
            np.subtract(best,second,out=difference,where=count>1)
            resolved=(count>1)&(difference>=margin)
            output|=masks&(supported==best)&resolved
            reason[resolved]=2
    reason[(count>1)&(reason!=2)]=3
    if (output.sum(axis=0)>1).any():raise AssertionError('Conflict resolver left overlapping masks')
    return dict(masks=output,unassigned=~output.any(axis=0),conflict=count>1,reason=reason,
                unresolved_conflict=reason==3,reviewed=False,margin=margin)


def rgb(path):
    return np.asarray(Image.open(path).convert('RGB'))


def reliability(row):
    # Inferred evidence needs an explicit reviewed reliability rule; model confidence
    # is deliberately not used as a probability or an automatic weight.
    q = float(row.get('reliability', 0. if row.get('status') == 'inferred' else 1.))
    if not np.isfinite(q) or not 0 <= q <= 1:
        raise ValueError('Evidence reliability must be finite in [0,1]')
    return q if row.get('reviewed') is True and row.get('status') != 'unknown' and not row.get('conflicted') else 0.


def area_mask(row, shape):
    """Coordinates are xyxy pixels on the original grid; soft masks stay soft."""
    height, width = shape
    if 'mask' in row:
        mask = np.asarray(row['mask'], float)
        if mask.shape != shape or not np.isfinite(mask).all() or (mask < 0).any() or (mask > 1).any():
            raise ValueError('Expected a finite HxW mask in [0,1] on the RGB grid')
        return mask
    x0, y0, x1, y1 = row['bbox']
    if not np.isfinite([x0, y0, x1, y1]).all() or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError('Invalid xyxy pixel bbox on original RGB grid')
    result = np.zeros(shape, float)
    result[int(y0):int(np.ceil(y1)), int(x0):int(np.ceil(x1))] = 1.
    return result


def load_document(path, *, levels=None):
    import json
    path = Path(path)
    doc = json.loads(path.read_text())
    if levels is not None:
        # Optional construction/review subset; scoring callers retain the old API.
        for kind in ('regions','anchors'):
            doc[kind] = [r for r in doc.get(kind,[]) if r.get('level') in levels]
    label_maps = {}
    archive = np.load(path.parent / doc['mask_archive'], allow_pickle=False) if doc.get('mask_archive') else None
    for row in doc.get('regions', []) + doc.get('anchors', []):
        if archive is not None and row['id'] in archive:
            row['mask'] = archive[row['id']]
        if 'label_map' in row:
            name = row['label_map']
            if name not in label_maps:
                label_maps[name] = np.asarray(Image.open(path.parent / name))
            labels = label_maps[name]
            value = row['label_value']
            if (labels.ndim != 2 or ('image_size' in doc and list(labels.shape[::-1]) != doc['image_size'])
                    or isinstance(value,bool) or not isinstance(value,int) or value < 0):
                raise ValueError('Invalid original-grid label selector')
            row['mask'] = (labels == value).astype(np.uint8)
            if not row['mask'].any():
                raise ValueError('Unknown label value')
        for field in ('mask', 'element_occupancy'):
            if isinstance(row.get(field), str):
                p = path.parent / row[field]
                row[field+'_source'] = str(p.resolve())
                row[field] = np.asarray(Image.open(p).convert('L'), float) / 255.
    if archive is not None:
        archive.close()
    return doc


def coverage_audit(regions, shape, dense_labels=None):
    """Pixel unions, not sums of mask areas; candidate labels never imply review.

    A nonnegative dense label assigns a pixel even when its semantic category is
    unknown. Soft masks retain their values; coverage counts positive support.
    This audit does not call build_reference or change any candidate review flag.
    """
    count = np.zeros(shape, np.uint32)
    semantic = np.zeros(shape, bool)
    reviewed_semantic = np.zeros(shape, bool)
    for row in regions:
        support = area_mask(row, shape) > 0
        count += support
        if row.get('category'):
            semantic |= support
            if reliability(row):
                reviewed_semantic |= support
    if dense_labels is None:
        dense = count > 0
    else:
        labels = np.asarray(dense_labels)
        if labels.shape != shape or not np.isfinite(labels).all():
            raise ValueError('Dense partition must use the original finite RGB grid')
        dense = labels >= 0
    return dict(dense_pixel_coverage=float(dense.mean()), candidate_region_coverage=float((count>0).mean()),
                candidate_semantic_coverage=float(semantic.mean()), reviewed_semantic_coverage=float(reviewed_semantic.mean()),
                unassigned_pixels=int((count==0).sum()), unclassified_pixels=int((~semantic).sum()),
                overlap_pixels=int((count>1).sum()), overlap_fraction=float((count>1).mean()),
                max_mask_multiplicity=int(count.max()), region_count=len(regions),
                definition='Positive mask support unions on original grid; dense assignment is not semantic correctness')


def merge_slic_regions(image, labels, *, features=None, anchor_masks=(),
                       thresholds=(.075, .14)):
    """Deterministic adjacent-only visual merging; no semantic or review decisions.

    Lab distances use delta-E / 100, feature distances use cosine / 2, and
    boundaries use RGB Sobel magnitude. Cluster means are area weighted and
    recomputed after every merge. Original-cell colour radius and the maximum
    original shared-boundary mean prevent a chain of weak edges crossing a
    strong one. Unreviewed Anchor masks provide a conservative *candidate*
    boundary guard, never a correctness label.
    """
    import heapq
    from scipy import ndimage

    image = np.asarray(image, float) / 255.
    labels = np.asarray(labels)
    if (image.ndim != 3 or image.shape[2] != 3 or labels.shape != image.shape[:2]
            or not np.issubdtype(labels.dtype, np.integer) or (labels < 0).any()
            or not np.isfinite(image).all() or image.min() < 0 or image.max() > 1):
        raise ValueError('Expected RGB uint8-range image and nonnegative integer labels')
    if len(thresholds) != 2 or not 0 < thresholds[0] < thresholds[1] < 1:
        raise ValueError('Expected increasing Medium and Coarse thresholds')
    ids, inverse = np.unique(labels.ravel(), return_inverse=True)
    fine = inverse.reshape(labels.shape).astype(np.int32)
    n = len(ids)
    # Standard sRGB -> D65 CIE Lab; avoids a new colour-library dependency.
    linear = np.where(image <= .04045, image / 12.92, ((image + .055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[.4124564,.3575761,.1804375],
                            [.2126729,.7151522,.0721750],
                            [.0193339,.1191920,.9503041]]).T
    xyz /= [.95047, 1., 1.08883]
    f = np.where(xyz > (6/29)**3, np.cbrt(xyz), xyz/(3*(6/29)**2)+4/29)
    lab = np.stack([116*f[:,:,1]-16, 500*(f[:,:,0]-f[:,:,1]),
                    200*(f[:,:,1]-f[:,:,2])], axis=-1)
    area = np.bincount(inverse, minlength=n).astype(float)
    colours = np.stack([np.bincount(inverse, weights=lab[:,:,k].ravel(), minlength=n)/area
                        for k in range(3)], axis=1)
    feature = None if features is None else np.array(features, float, copy=True)
    if feature is not None and (feature.ndim != 2 or len(feature) != n or
            not np.isfinite(feature).all() or (np.linalg.norm(feature, axis=1) == 0).any()):
        raise ValueError('Expected one finite nonzero DINO feature per sorted original label')
    gray = image @ [.299,.587,.114]
    gradient = np.hypot(ndimage.sobel(gray, axis=0)/4, ndimage.sobel(gray, axis=1)/4)
    rag = {}
    for a,b,g in [(fine[:,:-1],fine[:,1:],np.maximum(gradient[:,:-1],gradient[:,1:])),
                  (fine[:-1,:],fine[1:,:],np.maximum(gradient[:-1,:],gradient[1:,:]))]:
        keep = a != b
        pairs = np.sort(np.stack([a[keep],b[keep]],axis=1),axis=1)
        for (i,j), value in zip(pairs, g[keep]):
            key = (int(i),int(j))
            total,count = rag.get(key,(0.,0))
            rag[key] = (total+float(value),count+1)
    original_edges = {key: total/count for key,(total,count) in rag.items()}
    neighbours = {i:{} for i in range(n)}
    for (i,j),value in original_edges.items():
        neighbours[i][j] = neighbours[j][i] = value
    inside, outside = [0]*n, [0]*n
    for index,mask in enumerate(anchor_masks):
        mask = np.asarray(mask, bool)
        if mask.shape != fine.shape:
            raise ValueError('Anchor guard must use the SLIC grid')
        fraction = np.bincount(inverse, weights=mask.ravel(), minlength=n)/area
        for i in range(n):
            if fraction[i] >= .65: inside[i] |= 1 << index
            if fraction[i] <= .35: outside[i] |= 1 << index
    original_colours = colours.copy()
    members = {i:[i] for i in range(n)}
    generation = [0]*n
    weights = (.65,0.,.35) if feature is None else (.45,.25,.30)
    heap, events, rejected = [], [], dict(anchor_guard=0,boundary_guard=0,colour_radius=0)

    def terms(i,j):
        colour = float(np.linalg.norm(colours[i]-colours[j])/100)
        dino = 0.
        if feature is not None:
            dino = float(np.clip(1-np.dot(feature[i],feature[j]) /
                                 (np.linalg.norm(feature[i])*np.linalg.norm(feature[j])),0,2)/2)
        edge = neighbours[i][j]
        return colour,dino,edge

    def push(i,j):
        i,j = sorted((i,j))
        cost = float(np.dot(weights,terms(i,j)))
        heapq.heappush(heap,(cost,i,j,generation[i],generation[j]))

    for i,j in sorted(original_edges): push(i,j)
    levels = {'fine':fine.copy()}
    level_events = {}
    for name,threshold in zip(('medium','coarse'),thresholds):
        while heap and heap[0][0] <= threshold:
            cost,i,j,gi,gj = heapq.heappop(heap)
            if i not in members or j not in members or gi != generation[i] or gj != generation[j]:
                continue
            colour,dino,edge = terms(i,j)
            if (inside[i]&outside[j]) or (inside[j]&outside[i]):
                rejected['anchor_guard'] += 1
                continue
            if edge > .22:
                rejected['boundary_guard'] += 1
                continue
            combined = members[i]+members[j]
            mean = (area[i]*colours[i]+area[j]*colours[j])/(area[i]+area[j])
            radius = float(np.linalg.norm(original_colours[combined]-mean,axis=1).max()/100)
            if radius > min(.34,threshold*2.5):
                rejected['colour_radius'] += 1
                continue
            events.append(dict(left=list(members[i]),right=list(members[j]),cost=cost,
                               color=colour,feature=dino,boundary=edge,colour_radius=radius,stage=name))
            colours[i] = mean
            if feature is not None:
                feature[i] = (area[i]*feature[i]+area[j]*feature[j])/(area[i]+area[j])
            area[i] += area[j]
            inside[i] |= inside[j]; outside[i] |= outside[j]
            members[i] = combined
            del members[j]
            generation[i] += 1
            for k,value in list(neighbours[j].items()):
                neighbours[k].pop(j,None)
                if k == i: continue
                # Strong constituent boundaries cannot be diluted by merging.
                value = max(value,neighbours[i].get(k,0.))
                neighbours[i][k] = neighbours[k][i] = value
            neighbours[i].pop(j,None)
            del neighbours[j]
            for k in sorted(neighbours[i]): push(i,k)
        mapping = np.empty(n,np.int32)
        for index,root in enumerate(sorted(members)):
            mapping[members[root]] = index
        levels[name] = mapping[fine]
        level_events[name] = len(events)
        # Radius rejects at Medium may become eligible at Coarse.
        heap = []
        for i in sorted(members):
            for j in sorted(neighbours[i]):
                if i < j: push(i,j)
    return dict(levels=levels,original_label_ids=ids.tolist(),events=events,
                level_event_counts=level_events,rejected=rejected,
                parameters=dict(weights=dict(color=weights[0],feature=weights[1],boundary=weights[2]),
                                thresholds=list(thresholds),max_original_boundary=.22,
                                max_colour_radius='min(0.34, threshold * 2.5)',
                                anchor_inside=.65,anchor_outside=.35),
                rag=[dict(left=i,right=j,boundary=v) for (i,j),v in sorted(original_edges.items())])


def validate_region_hierarchy(nodes):
    """Validate organization independently of scoring and of semantic correctness."""
    ids = [n['id'] for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate hierarchy ID')
    by_id = {n['id']:n for n in nodes}
    for row in nodes:
        if row.get('reviewed') is not False:
            raise ValueError('Automatic hierarchy must remain unreviewed')
        for key in ('parent_ids','child_ids','region_ids'):
            if any(v not in by_id for v in row.get(key,[])):
                raise ValueError('Unknown hierarchy reference')
        for child in row.get('child_ids',[]):
            if row['id'] not in by_id[child].get('parent_ids',[]):
                raise ValueError('Nonreciprocal hierarchy link')
        for parent in row.get('parent_ids',[]):
            if row['id'] not in by_id[parent].get('child_ids',[]):
                raise ValueError('Nonreciprocal hierarchy link')
    active,complete = set(),set()
    def visit(key):
        if key in active: raise ValueError('Cyclic hierarchy')
        if key in complete: return
        active.add(key)
        for child in set(by_id[key].get('child_ids',[])+by_id[key].get('region_ids',[])):
            visit(child)
        active.remove(key); complete.add(key)
    for key in ids: visit(key)
    return dict(node_count=len(nodes),acyclic=True,all_unreviewed=True)


def validate_vlm_region_response(answer, stage, region_ids=()):
    """Strict bounded contracts: invalid references fail instead of being repaired."""
    from benchmark.vlm import RELATIONS
    if not isinstance(answer, dict): raise ValueError('Expected JSON object')
    def text(row,key,required=True):
        if not isinstance(row,dict): raise ValueError('Expected object item')
        value = row.get(key,'' if not required else None)
        if not isinstance(value,str) or len(value)>500 or (required and not value.strip()):
            raise ValueError('Invalid text field: '+key)
        return value.strip()
    if stage == 'plan':
        cleaned = dict(regions=[],anchors=[],relations=[],uncertain=answer.get('uncertain',[]))
        if (not isinstance(cleaned['uncertain'],list) or len(cleaned['uncertain'])>24 or
                not all(isinstance(x,str) and len(x)<=500 for x in cleaned['uncertain'])):
            raise ValueError('Invalid uncertain descriptions')
        seen = set()
        for kind in ('regions','anchors'):
            rows = answer.get(kind)
            if not isinstance(rows,list) or len(rows)>12: raise ValueError('Expected at most 12 '+kind)
            for row in rows:
                if not isinstance(row,dict): raise ValueError('Expected object item')
                key = text(row,'id')
                if key in seen: raise ValueError('Duplicate VLM ID')
                seen.add(key)
                item = dict(id=key,name=text(row,'name'),location=text(row,'location'),
                            reason=text(row,'reason',False),reviewed=False,reliability=0.)
                if kind=='regions':
                    item['kind']=text(row,'kind')
                    if item['kind'] not in {'continuous','collection','unknown'}: raise ValueError('Invalid Region kind')
                else:
                    if not isinstance(row.get('need_mask'),bool): raise ValueError('Expected boolean need_mask')
                    item['need_mask']=row['need_mask']
                cleaned[kind].append(item)
        relations = answer.get('relations',[])
        if not isinstance(relations,list) or len(relations)>40: raise ValueError('Invalid relations list')
        triples=set(); inverse={'left_of':'right_of','right_of':'left_of','above':'below','below':'above',
                               'in_front_of':'behind','behind':'in_front_of','contains':'inside','inside':'contains'}
        for row in relations:
            subject,predicate,obj=(text(row,k) for k in ('subject','predicate','object'))
            if subject not in seen or obj not in seen or subject==obj or predicate not in RELATIONS:
                raise ValueError('Invalid relation reference or predicate')
            triple=(subject,predicate,obj)
            if (subject,inverse.get(predicate),obj) in triples or (obj,predicate,subject) in triples:
                if predicate in inverse: raise ValueError('Contradictory relations')
            if triple in triples: raise ValueError('Duplicate relation')
            triples.add(triple)
            cleaned['relations'].append(dict(subject=subject,predicate=predicate,object=obj,reviewed=False,reliability=0.))
        # Containment is the only relation interpreted as a hierarchy edge.
        nodes={key:dict(id=key,parent_ids=[],child_ids=[],reviewed=False) for key in seen}
        for subject,predicate,obj in triples:
            if predicate in {'contains','inside'}:
                parent,child=(subject,obj) if predicate=='contains' else (obj,subject)
                if child not in nodes[parent]['child_ids']:
                    nodes[parent]['child_ids'].append(child); nodes[child]['parent_ids'].append(parent)
        validate_region_hierarchy(list(nodes.values()))
    elif stage == 'group':
        groups=answer.get('groups')
        uncertain=answer.get('uncertain_region_ids',[])
        if not isinstance(groups,list) or len(groups)>12 or not isinstance(uncertain,list):
            raise ValueError('Invalid grouping list')
        allowed=set(region_ids)
        if not all(isinstance(x,str) and x in allowed for x in uncertain): raise ValueError('Invalid uncertain ID')
        cleaned=dict(groups=[],uncertain_region_ids=sorted(set(uncertain)))
        names=set()
        for row in groups:
            name=text(row,'name'); members=row.get('region_ids')
            if (name in names or not isinstance(members,list) or not members or
                    not all(isinstance(x,str) and x in allowed for x in members) or len(members)!=len(set(members))):
                raise ValueError('Invalid or duplicate group reference')
            if set(members)&set(uncertain): raise ValueError('Group includes an explicitly uncertain Region')
            names.add(name)
            cleaned['groups'].append(dict(name=name,region_ids=members,reviewed=False,reliability=0.))
    else:
        raise ValueError('Unknown VLM stage')
    return cleaned


def build_reference(image, supplied=None, *, grid=None):
    """Accept no rendered argument: reference selection cannot depend on Agent output."""
    supplied = deepcopy(supplied or {})
    h, w = image.shape[:2]
    if supplied.get('image_size', [w, h]) != [w, h]:
        raise ValueError('Reference evidence grid differs from input RGB')
    anchors = supplied.get('anchors', [])
    if len(anchors) > POLICY['max_anchors']:
        raise ValueError('Select at most 12 salient anchors in the reference evidence')
    for row in anchors:
        row.setdefault('importance', 1.)
        if not np.isfinite(row['importance']) or row['importance'] <= 0:
            raise ValueError('Anchor importance must be positive and finite')
        row.setdefault('position', ((np.array(row['bbox'][:2]) + row['bbox'][2:]) / 2).tolist())
        reliability(row)
        area_mask(row, (h, w))
    regions = supplied.get('regions', [])
    for row in regions:
        row.setdefault('description', 'Independently annotated reference region')
        row.setdefault('metrics', ['appearance','spatial','statistical','perceptual'])
        row.setdefault('reliability', 1.)
        reliability(row)
        area_mask(row, (h, w))
        if 'element_occupancy' in row:
            area_mask({'mask': row['element_occupancy']}, (h, w))
    # Grid tiles fill only uncovered reference pixels, avoiding overlap with named regions.
    occupied = np.zeros((h, w), float)
    for row in regions:
        if reliability(row):
            occupied = np.maximum(occupied, area_mask(row, (h, w)))
    grid = POLICY['grid'] if grid is None else grid
    if not isinstance(grid, int) or grid < 1 or grid > min(w, h):
        raise ValueError('Grid must be a positive integer within image dimensions')
    for iy in range(grid):
        for ix in range(grid):
            box = [ix*w//grid, iy*h//grid, (ix+1)*w//grid, (iy+1)*h//grid]
            row = dict(id=f'patch_{iy}_{ix}', bbox=box,
                       description='Reference-coordinate fallback patch; no semantic category claimed',
                       metrics=list(('appearance', 'spatial', 'statistical', 'perceptual')),
                       reviewed=True, reliability=1., source='deterministic RGB grid', status='observable')
            if any(r['id']==row['id'] for r in regions):
                continue
            row['mask'] = area_mask(row, (h, w)) * (1 - occupied)
            if row['mask'].sum() >= POLICY['min_pixels']:
                regions.append(row)
    ids = [r['id'] for r in regions + anchors]
    if len(ids) != len(set(ids)):
        raise ValueError('Region and Anchor IDs must be unique')
    for fact in supplied.get('relations', []):
        if fact['subject'] not in ids or fact['object'] not in ids:
            raise ValueError('Unknown relation endpoint')
        reliability(fact)
    # Statistical region pixels exclude reliable anchors. Without a reliable mask,
    # the bbox is a conservative exclusion, and is explicitly recorded.
    exclusion = np.zeros((h, w), float)
    for row in anchors:
        if reliability(row):
            geometry = row if row.get('mask_reviewed') is True else {'bbox': row['bbox']}
            exclusion = np.maximum(exclusion, area_mask(geometry, (h, w)))
    result = dict(supplied, image_size=[w, h], global_evidence={
        'description': 'Complete reference RGB', 'reviewed': True, 'reliability': 1.},
        regions=regions, anchors=anchors, anchor_exclusion=exclusion,
        overlap_policy='Exclude reviewed Anchor mask or conservative bbox from all Region statistics; Global retained; fixed level weights',
        source='reference RGB and independently supplied annotations only')
    return result


def candidate_reference(path):
    """Thin adapter for existing contrast24 input candidates; no render/name lookup."""
    import json
    path = Path(path)
    doc = json.loads(path.read_text())
    result = dict(image_size=doc['image_size'], anchors=[], regions=[], relations=[],
                  candidate_source=str(path), reviewed=doc.get('reviewed', False))
    for obj in doc.get('objects', []):
        if obj.get('evaluate', True):
            row = deepcopy(obj)
            row.update(id=obj['object_id'], importance=1., reliability=1.)
            if isinstance(row.get('mask'), str):
                row['mask_source'] = str(path.parent / row.pop('mask'))
                # Known candidate SAM masks are deliberately not used for scoring/exclusion.
            result['anchors'].append(row)
    relpath = path.with_name('candidate_relations.json')
    if relpath.exists():
        result['relations'] = json.loads(relpath.read_text()).get('relations', [])
    return result


def vlm_verify(question, reference_evidence, rendered_evidence, criteria, infer=None):
    """Local/explicitly authorized callback only. Never discovers keys or calls APIs."""
    if infer is None:
        return dict(score=None, status='unavailable', reason='No authorized verified VLM configured')
    try:
        import json
        def answer(a, b, q):
            result = infer(q, a, b, criteria)
            return (json.dumps(result) if isinstance(result,dict) else result), None
        # The established local_vqa gateway validates the question and answer contract.
        result = local_vqa(reference_evidence, rendered_evidence, question,
                           infer=answer)
        answer = json.loads(result['answer'])
        status, score = answer['status'], answer.get('score')
        if status not in {'valid', 'uncertain', 'unavailable'}:
            raise ValueError('Invalid VLM status')
        if status == 'valid' and (score is None or not np.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('VLM score must be a finite normalized error')
        return dict(score=float(score) if status == 'valid' else None,
                    status=status, reason=str(answer['reason']))
    except Exception as exc:
        return dict(score=None, status='unavailable', reason=f'VLM failed: {type(exc).__name__}: {exc}')
