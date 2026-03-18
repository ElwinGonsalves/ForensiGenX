#!/usr/bin/env python3
"""
Simple pipeline integrating Visual Scene Extraction (Stage 0),
semantic parsing (Stage 1-2), and spatial layout generation (Stage 3).

Usage examples:
  python build_pipeline.py --text "A living room: a sofa faces a television. A man lies on the floor between them. A kitchen knife lies nearby."

Outputs written to project root:
  - linguistic_features.json
  - scene_graph.json
  - layout.json
  - layout.png
"""
import json
import argparse
import re
import os

from semantic_module import normalizer
from semantic_module import semantic_parser
from semantic_module.validator import validate_scene
import spatial_layout


COMMON_OBJECTS = [
    # indoor/home objects
    'sofa', 'couch', 'table', 'coffee table', 'television', 'tv',
    'lamp', 'bookshelf', 'knife', 'kitchen knife', 'book', 'chair',
    'floor', 'bed', 'desk',
    # outdoor/parking-specific
    'car', 'black car', 'vehicle', 'parked car', 'police officer', 'officer', 'suspect',
    'gun', 'pistol', 'street light', 'streetlight', 'light', 'store', 'convenience store',
    'bicycle', 'bike', 'wall', 'parking lot'
]


def visual_scene_extraction(text):
    """Very small rule-based extractor that keeps visual info only.

    Returns a feature dict compatible with `semantic_parser.process_single_scene` input.
    """
    # lower for matching but keep original tokens when storing
    txt = text

    # find object mentions by looking for common object names
    objects_found = []
    attributes = {}
    relations = []

    # simple matching for common objects (multi-word first)
    sorted_objs = sorted(COMMON_OBJECTS, key=lambda s: -len(s))
    for obj in sorted_objs:
        pattern = re.compile(r"\b" + re.escape(obj) + r"\b", flags=re.IGNORECASE)
        if pattern.search(txt):
            objects_found.append(obj)

    # fallback: any capitalized nouns (proper names) as objects
    if not objects_found:
        caps = re.findall(r"\b([A-Z][a-z]{2,})\b", txt)
        for c in caps:
            objects_found.append(c.lower())

    # Normalize and deduplicate using the semantic normalizer
    seen = set()
    objects = []
    for o in objects_found:
        norm = normalizer.normalize_object(o)
        if norm is None:
            continue
        if norm not in seen:
            seen.add(norm)
            objects.append(norm)

    # extract relations by looking at proximity of normalized object mentions in text
    def add_relation(s, p, o):
        # endpoints are already normalized here, but ensure double-check
        sn = normalizer.normalize_object(s)
        on = normalizer.normalize_object(o)
        if sn is None or on is None:
            return
        relations.append(f"{sn} {p} {on}")

    lower_txt = txt.lower()
    positions = {}
    for o in objects:
        idx = lower_txt.find(o)
        positions[o] = idx if idx >= 0 else None

    # relation keywords and mapping
    # only consider object pairs that are reasonably close in text
    TEXT_WINDOW = 120
    for a in objects:
        for b in objects:
            if a == b:
                continue
            ia = positions.get(a)
            ib = positions.get(b)
            if ia is None or ib is None:
                continue
            if abs(ia - ib) > TEXT_WINDOW:
                continue
            start = min(ia, ib)
            end = max(ia, ib) + len(b)
            segment = lower_txt[start:end]
            if any(k in segment for k in (' near ', ' next to ', ' beside ', ' close to ')):
                add_relation(a, 'near', b)
            elif ' between ' in segment:
                add_relation(a, 'between', b)
            elif any(k in segment for k in (' lying on ', ' lies on ', ' is on ', ' on ')):
                add_relation(a, 'on', b)
            elif any(k in segment for k in (' in front of ', ' facing ', ' faces ')):
                add_relation(a, 'near', b)

    # heuristic fallback: if sentence contains 'between them' and objects exist, connect to nearest two
    if 'between them' in lower_txt and len(objects) >= 3:
        add_relation(objects[2], 'between', objects[0])
        add_relation(objects[2], 'between', objects[1])

    # attributes: adjectives preceding object (simple)
    for obj in objects:
        m = re.search(r"(\b[\w]{2,15}\b)\s+" + re.escape(obj), txt, flags=re.IGNORECASE)
        if m:
            attributes.setdefault(obj, []).append(m.group(1).lower())

    feature = {
        'id': 1,
        'objects': objects,
        'attributes': attributes,
        'relations': relations,
    }
    return feature


def to_spatial_inputs(scene_graph):
    """Convert scene_graph (objects+relationships) to inputs suitable for spatial_layout.solve_layout.

    scene_graph format from semantic_parser: objects list with 'id','name', relationships with 'subject_id','relation','object_id'
    We convert to objs list (id,name) and rels list of {'s': name, 'p': relation, 'o': name}
    """
    objs = [{'id': obj['id'], 'name': obj['name']} for obj in scene_graph['objects']]
    id_to_name = {obj['id']: obj['name'] for obj in scene_graph['objects']}
    rels = []
    for r in scene_graph.get('relationships', []):
        sname = id_to_name.get(r['subject_id'])
        oname = id_to_name.get(r['object_id'])
        if sname and oname:
            rels.append({'s': sname, 'p': r['relation'], 'o': oname})
    return objs, rels


def run(text=None, infile=None, out_prefix=''):
    project_root = os.path.dirname(os.path.abspath(__file__))

    if text is None and infile is None:
        raise SystemExit('Provide --text or --infile')

    if infile and infile.endswith('.txt'):
        with open(infile, 'r', encoding='utf-8') as f:
            text = f.read()

    # Stage 0: Visual Scene Extraction
    feature = visual_scene_extraction(text)
    ling_path = os.path.join(project_root, 'linguistic_features.json')
    with open(ling_path, 'w', encoding='utf-8') as f:
        json.dump(feature, f, indent=2, ensure_ascii=False)
    print('Wrote', ling_path)

    # Stage 1-2: Semantic parsing -> scene graph
    scene_graph = semantic_parser.process_single_scene(feature)
    # validate
    try:
        validate_scene(scene_graph)
    except ValueError as e:
        print('Scene validation failed:', e)
        return

    scene_path = os.path.join(project_root, 'scene_graph.json')
    with open(scene_path, 'w', encoding='utf-8') as f:
        json.dump(scene_graph, f, indent=2, ensure_ascii=False)
    print('Wrote', scene_path)

    # Stage 3: Spatial layout generation using spatial_layout.solve_layout + render
    objs, rels = to_spatial_inputs(scene_graph)
    layout = spatial_layout.solve_layout(objs, rels, canvas=(512, 512), box=(100, 100))
    out_layout = os.path.join(project_root, 'layout.json')
    with open(out_layout, 'w', encoding='utf-8') as f:
        json.dump({'objects': layout}, f, indent=2, ensure_ascii=False)
    out_img = os.path.join(project_root, 'layout.png')
    spatial_layout.render_layout(layout, out_img, canvas=(512, 512))
    print('Wrote', out_layout, 'and', out_img)


def main():
    parser = argparse.ArgumentParser(description='Build pipeline: Stage 0 (visual extraction) -> Stage1-3')
    parser.add_argument('--text', help='Raw narrative text (wrap in quotes)')
    parser.add_argument('--infile', help='Path to input .txt file')
    args = parser.parse_args()
    run(text=args.text, infile=args.infile)


if __name__ == '__main__':
    main()
