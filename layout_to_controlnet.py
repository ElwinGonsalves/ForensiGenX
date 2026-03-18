#!/usr/bin/env python3
import json
import math
import argparse
from PIL import Image, ImageDraw


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Accept either top-level list or dict with 'objects'
    if isinstance(data, dict) and 'objects' in data:
        objs = data['objects']
    elif isinstance(data, list):
        objs = data
    else:
        raise ValueError('Input JSON must contain an "objects" list or be a list of objects')
    # normalize required fields
    norm = []
    for o in objs:
        norm.append({'id': o.get('id'), 'name': o.get('name'), 'x': int(o.get('x', 0)), 'y': int(o.get('y', 0)), 'w': int(o.get('w', 0)), 'h': int(o.get('h', 0))})
    return norm


# color mapping by keywords -> (name, (R,G,B))
BASE_COLOR_MAP = {
    'sofa': ('red', (255, 0, 0)),
    'television': ('green', (0, 255, 0)),
    'tv': ('green', (0, 255, 0)),
    'coffee_table': ('blue', (0, 0, 255)),
    'coffee': ('blue', (0, 0, 255)),
    'floor_lamp': ('yellow', (255, 255, 0)),
    'lamp': ('yellow', (255, 255, 0)),
    'bookshelf': ('purple', (128, 0, 128)),
    'book': ('purple', (128, 0, 128)),
    'victim': ('cyan', (0, 255, 255)),
    'knife': ('gray', (128, 128, 128)),
    'blood_pool': ('dark red', (139, 0, 0)),
    'blood': ('dark red', (139, 0, 0)),
}


def choose_color_for_object(obj_name):
    lname = (obj_name or '').lower()
    for k, v in BASE_COLOR_MAP.items():
        if k in lname:
            return v
    # fallback deterministic color based on name hash
    h = abs(hash(lname))
    r = 80 + (h % 176)
    g = 80 + ((h >> 8) % 176)
    b = 80 + ((h >> 16) % 176)
    return (None, (r, g, b))


def generate_layout_image(objects, outpath='layout_map.png', size=(1024, 1024), margin=16):
    W, H = size
    # compute bounding box of input coords
    if not objects:
        raise ValueError('No objects provided')
    xmin = min(o['x'] for o in objects)
    ymin = min(o['y'] for o in objects)
    xmax = max(o['x'] + o['w'] for o in objects)
    ymax = max(o['y'] + o['h'] for o in objects)
    spanx = xmax - xmin if (xmax - xmin) > 0 else 1
    spany = ymax - ymin if (ymax - ymin) > 0 else 1
    scale = min((W - 2 * margin) / spanx, (H - 2 * margin) / spany)

    img = Image.new('RGB', (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # draw rectangles without text, consistent colors
    for o in objects:
        cname, col = choose_color_for_object(o.get('id') or o.get('name') or '')
        x = int((o['x'] - xmin) * scale + margin)
        y = int((o['y'] - ymin) * scale + margin)
        w = int(o['w'] * scale)
        h = int(o['h'] * scale)
        # ensure within bounds
        x2 = max(0, min(W, x + w))
        y2 = max(0, min(H, y + h))
        x1 = max(0, min(W, x))
        y1 = max(0, min(H, y))
        draw.rectangle([x1, y1, x2, y2], fill=col)
    img.save(outpath)
    return outpath


def _compass_direction(cx, cy, W, H):
    # cx, cy are centers in image coords
    nx = cx / W
    ny = cy / H
    horiz = ''
    vert = ''
    if nx < 0.33:
        horiz = 'west'
    elif nx > 0.66:
        horiz = 'east'
    else:
        horiz = ''
    if ny < 0.33:
        vert = 'north'
    elif ny > 0.66:
        vert = 'south'
    else:
        vert = ''
    if vert and horiz:
        return f"{vert}-{horiz}"
    if vert:
        return vert
    if horiz:
        return horiz
    return 'center'


def generate_prompt(objects, image_size=(1024, 1024)):
    # build mapping sentences
    used = {}
    mapping_phrases = []
    for o in objects:
        key = (o.get('id') or o.get('name') or '').lower()
        cname, col = choose_color_for_object(key)
        # ensure we mention each color only once for the primary keyword
        primary = None
        for k in BASE_COLOR_MAP.keys():
            if k in key:
                primary = k
                break
        label = o.get('name') or o.get('id')
        if cname is None:
            # derive a readable color name from RGB
            cname = f"rgb({col[0]},{col[1]},{col[2]})"
        if cname not in used:
            # pick a short descriptive object type from the name
            typ = label
            mapping_phrases.append(f"a {cname} region represents a {typ}")
            used[cname] = typ

    mapping_sentence = ', '.join(mapping_phrases)
    if mapping_sentence:
        mapping_sentence = mapping_sentence[0].upper() + mapping_sentence[1:] + '.'

    # describe positions
    W, H = image_size
    desc_items = []
    # compute centers in image coords using same scaling logic as image generator
    xmin = min(o['x'] for o in objects)
    ymin = min(o['y'] for o in objects)
    xmax = max(o['x'] + o['w'] for o in objects)
    ymax = max(o['y'] + o['h'] for o in objects)
    spanx = xmax - xmin if (xmax - xmin) > 0 else 1
    spany = ymax - ymin if (ymax - ymin) > 0 else 1
    scale = min((W - 2 * 16) / spanx, (H - 2 * 16) / spany)

    center_coords = {}
    for o in objects:
        cx = (o['x'] - xmin + o['w'] / 2.0) * scale + 16
        cy = (o['y'] - ymin + o['h'] / 2.0) * scale + 16
        center_coords[o.get('id') or o.get('name')] = (cx, cy)
        loc = _compass_direction(cx, cy, W, H)
        desc_items.append(f"the {o.get('name')} is located at the {loc}")

    scene_desc = ' '.join(desc_items)

    # optional relations: note if knife is near victim (pixel threshold)
    extra = ''
    # find victim and knife keys if present
    vic = None
    kn = None
    for o in objects:
        k = (o.get('id') or o.get('name') or '').lower()
        if 'victim' in k or 'body' in k or 'victim' in (o.get('name') or '').lower():
            vic = o
        if 'knife' in k or 'knife' in (o.get('name') or '').lower():
            kn = o
    if vic and kn:
        vkey = vic.get('id') or vic.get('name')
        kkey = kn.get('id') or kn.get('name')
        vc = center_coords.get(vkey)
        kc = center_coords.get(kkey)
        if vc and kc:
            dist = math.hypot(vc[0] - kc[0], vc[1] - kc[1])
            if dist < 200:
                extra = f" The map also shows the {kkey} positioned near the {vkey}, suggesting proximity between the weapon and the victim." 

    prompt = f"A spatial layout map of a crime scene. {mapping_sentence} {scene_desc}.{extra} Generate a realistic photorealistic living-room scene following this layout with objects placed in the corresponding colored regions, using the color mapping described above."
    return prompt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='layout JSON input (objects with id,name,x,y,w,h)')
    parser.add_argument('--out-img', default='layout_map.png', help='output image file (1024x1024)')
    parser.add_argument('--size', type=int, nargs=2, default=(1024, 1024))
    args = parser.parse_args()

    objects = load_json(args.input)
    imgpath = generate_layout_image(objects, outpath=args.out_img, size=tuple(args.size))
    prompt = generate_prompt(objects, image_size=tuple(args.size))
    print(prompt)


if __name__ == '__main__':
    main()
