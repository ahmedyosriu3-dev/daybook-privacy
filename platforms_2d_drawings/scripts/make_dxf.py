"""Generate 2D DXF drawings (plan x2, elevation, side view) from the projected views."""
import os
import sys
import numpy as np
import ezdxf
from ezdxf.enums import TextEntityAlignment
from hlr import build, beam_edges, View, hlr

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
os.makedirs(OUT, exist_ok=True)
SCALE = 50           # drawing scale 1:50 (model units are mm, drawn 1:1)
TXT = 2.5 * SCALE    # 2.5 mm text on paper
TTL = 5.0 * SCALE    # 5 mm titles on paper
M = 1000.0           # model metres -> mm

LOWER_LEVELS = [31.5, 34.6, 34.85]
UPPER_LEVELS = [37.9, 41.555, 41.805]

# view name -> (screen right, screen up, platform filter, title, subtitle, axis labels)
VIEWS = {
    'PLAN_LOWER': ((0, 1, 0), (-1, 0, 0), 'L', 'PLAN VIEW - LOWER PLATFORM',
                   'VIEWED FROM ABOVE (LOOKING -Z), LOWER PLATFORM ONLY', ('+Y', '-X')),
    'PLAN_UPPER': ((0, 1, 0), (-1, 0, 0), 'U', 'PLAN VIEW - UPPER PLATFORM',
                   'VIEWED FROM ABOVE (LOOKING -Z), UPPER PLATFORM ONLY', ('+Y', '-X')),
    'ELEVATION': ((0, 1, 0), (0, 0, 1), None, 'ELEVATION',
                  'VIEWED FROM +X (LOOKING -X), BOTH PLATFORMS', ('+Y', '+Z')),
    'SIDE_VIEW': ((-1, 0, 0), (0, 0, 1), None, 'SIDE VIEW',
                  'VIEWED FROM +Y (LOOKING -Y), BOTH PLATFORMS', ('-X', '+Z')),
}


def compute_views():
    tris, tg, edges, bo = build()
    res = {}
    for name, (R, U, g, *_rest) in VIEWS.items():
        v = View(R, U)
        E = [e for e in edges + beam_edges(bo, v.F) if g is None or e[2] == g]
        TT = tris if g is None else tris[tg == g]
        vis, hid = hlr(v, TT, E)
        grp_of = {}
        # extents per platform (for dimensions) in screen coords, mm
        ext = {}
        for key in ('L', 'U'):
            pts = [np.array(e[:2]) for e in E if e[2] == key]
            if pts:
                P = np.vstack(pts)
                P2 = np.stack([P @ v.R, P @ v.U], 1) * M
                ext[key] = (P2.min(0), P2.max(0))
        res[name] = dict(vis=[(a * M, b * M, k) for a, b, k in vis],
                         hid=[(a * M, b * M, k) for a, b, k in hid], ext=ext)
        print(f'{name}: {len(vis)} visible / {len(hid)} hidden segments')
    return res


def new_doc():
    doc = ezdxf.new('R2018', setup=True, units=ezdxf.units.MM)
    doc.header['$MEASUREMENT'] = 1
    doc.header['$LTSCALE'] = 1.0
    doc.header['$PSLTSCALE'] = 0
    doc.linetypes.add('HIDDEN_50', pattern=[4.5 * SCALE, 3.0 * SCALE, -1.5 * SCALE],
                      description='Hidden 3/1.5 mm @1:50 __ __ __')
    L = doc.layers
    L.add('PLATE_VISIBLE', color=7, lineweight=35)
    L.add('PLATE_HIDDEN', color=8, linetype='HIDDEN_50', lineweight=18)
    L.add('PROFILE_VISIBLE', color=4, lineweight=25)
    L.add('PROFILE_HIDDEN', color=9, linetype='HIDDEN_50', lineweight=18)
    L.add('DIMENSIONS', color=3, lineweight=18)
    L.add('LEVELS', color=1, lineweight=18)
    L.add('TEXT', color=2, lineweight=25)
    L.add('AXES', color=6, lineweight=25)
    L.add('FRAME', color=7, lineweight=50)
    ds = doc.dimstyles.duplicate_entry('EZ_M_1_H25_CM', 'DIM_1_50') if 'EZ_M_1_H25_CM' in doc.dimstyles else doc.dimstyles.new('DIM_1_50')
    ds.dxf.dimscale = SCALE
    ds.dxf.dimtxt = 2.5
    ds.dxf.dimasz = 2.5
    ds.dxf.dimexo = 1.5
    ds.dxf.dimexe = 1.5
    ds.dxf.dimgap = 1.0
    ds.dxf.dimdec = 0
    ds.dxf.dimlfac = 1.0
    ds.dxf.dimblk = ''
    ds.dxf.dimtad = 1
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0
    ds.dxf.dimclrd = 3
    ds.dxf.dimclre = 3
    ds.dxf.dimclrt = 3
    return doc


def lvl(z):
    return f'EL. +{z * M:,.0f}'.replace(',', ' ')


def text(msp, s, x, y, h=TXT, align=TextEntityAlignment.LEFT, layer='TEXT', rot=0):
    t = msp.add_text(s, height=h, rotation=rot, dxfattribs={'layer': layer, 'style': 'OpenSans'
                                                            if 'OpenSans' in msp.doc.styles else 'Standard'})
    t.set_placement((x, y), align=align)
    return t


def arrow(msp, p, d, length, label, layer='AXES'):
    p = np.array(p, float)
    d = np.array(d, float)
    q = p + d * length
    n = np.array([-d[1], d[0]])
    msp.add_line(p, q, dxfattribs={'layer': layer})
    ah = 0.25 * length
    msp.add_solid([q, q - d * ah + n * ah * 0.3, q - d * ah - n * ah * 0.3], dxfattribs={'layer': layer})
    text(msp, label, *(q + d * 0.15 * length - np.array([0, TXT / 2])), h=TXT,
         align=TextEntityAlignment.LEFT if d[0] >= 0 else TextEntityAlignment.RIGHT, layer=layer)


def draw_view(msp, name, data, off):
    ox, oy = off
    R, U, g, title, sub, (hl, vl) = VIEWS[name]
    for segs, suffix in ((data['hid'], 'HIDDEN'), (data['vis'], 'VISIBLE')):
        for a, b, kind in segs:
            if np.hypot(*(b - a)) < 0.5:
                continue
            msp.add_line((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy),
                         dxfattribs={'layer': f'{kind}_{suffix}'})
    exts = data['ext']
    lo = np.min([e[0] for e in exts.values()], 0)
    hi = np.max([e[1] for e in exts.values()], 0)
    lo_o, hi_o = lo + (ox, oy), hi + (ox, oy)
    dim_gap = 12 * SCALE
    # overall dimensions
    msp.add_linear_dim(base=(lo_o[0], lo_o[1] - dim_gap), p1=(lo_o[0], lo_o[1]), p2=(hi_o[0], lo_o[1]),
                       dimstyle='DIM_1_50', dxfattribs={'layer': 'DIMENSIONS'}).render()
    msp.add_linear_dim(base=(lo_o[0] - dim_gap, lo_o[1]), p1=(lo_o[0], lo_o[1]), p2=(lo_o[0], hi_o[1]),
                       angle=90, dimstyle='DIM_1_50', dxfattribs={'layer': 'DIMENSIONS'}).render()
    # per-platform dimensions in the combined views
    if g is None:
        for k, (elo, ehi) in exts.items():
            elo_o, ehi_o = elo + (ox, oy), ehi + (ox, oy)
            msp.add_linear_dim(base=(elo_o[0], ehi_o[1] + 8 * SCALE), p1=(elo_o[0], ehi_o[1]),
                               p2=(ehi_o[0], ehi_o[1]), dimstyle='DIM_1_50',
                               dxfattribs={'layer': 'DIMENSIONS'}).render()
            msp.add_linear_dim(base=(hi_o[0] + 48 * SCALE, elo_o[1]), p1=(ehi_o[0], elo_o[1]),
                               p2=(ehi_o[0], ehi_o[1]), angle=90, dimstyle='DIM_1_50',
                               dxfattribs={'layer': 'DIMENSIONS'}).render()
        # level marks (Z is screen-up in these views; screen v == Z mm)
        for z in LOWER_LEVELS + UPPER_LEVELS:
            y = z * M + oy
            x0 = hi_o[0] + 4 * SCALE
            msp.add_line((x0, y), (x0 + 18 * SCALE, y), dxfattribs={'layer': 'LEVELS'})
            s = 2 * SCALE
            msp.add_lwpolyline([(x0 + 3 * SCALE, y), (x0 + 3 * SCALE - s, y + 1.6 * s),
                                (x0 + 3 * SCALE + s, y + 1.6 * s)], close=True, dxfattribs={'layer': 'LEVELS'})
            text(msp, lvl(z), x0 + 6 * SCALE, y + 0.6 * SCALE,
                 h=TXT, layer='LEVELS')
    else:
        # coordinate references for plan views: screen x == Y mm, screen y == -X mm
        text(msp, f'Y = {lo[0]:.0f}', lo_o[0], hi_o[1] + 3 * SCALE, layer='TEXT')
        text(msp, f'Y = {hi[0]:.0f}', hi_o[0], hi_o[1] + 3 * SCALE, align=TextEntityAlignment.RIGHT, layer='TEXT')
        text(msp, f'X = {-hi[1]:.0f}', hi_o[0] + 3 * SCALE, hi_o[1] - TXT, layer='TEXT')
        text(msp, f'X = {-lo[1]:.0f}', hi_o[0] + 3 * SCALE, lo_o[1], layer='TEXT')
        zs = LOWER_LEVELS if g == 'L' else UPPER_LEVELS
        text(msp, 'DECK / STRUCTURE LEVELS: ' + ',  '.join(lvl(z) for z in zs),
             (lo_o[0] + hi_o[0]) / 2, lo_o[1] - dim_gap - 12 * SCALE - TTL * 1.6 - TXT * 2.2,
             align=TextEntityAlignment.TOP_CENTER, layer='LEVELS')
    # axis triad (bottom-left)
    tp = (lo_o[0] - 30 * SCALE, lo_o[1] - 30 * SCALE)
    arrow(msp, tp, (1, 0), 12 * SCALE, hl)
    arrow(msp, tp, (0, 1), 12 * SCALE, vl)
    # title
    cx = (lo_o[0] + hi_o[0]) / 2
    ty = lo_o[1] - dim_gap - 12 * SCALE
    t = text(msp, title, cx, ty, h=TTL, align=TextEntityAlignment.TOP_CENTER)
    wtitle = len(title) * TTL * 0.85
    msp.add_line((cx - wtitle / 2, ty - TTL * 1.25), (cx + wtitle / 2, ty - TTL * 1.25),
                 dxfattribs={'layer': 'TEXT'})
    text(msp, f'{sub}   -   SCALE 1:{SCALE}', cx, ty - TTL * 1.6, h=TXT, align=TextEntityAlignment.TOP_CENTER)
    return lo_o, hi_o


NOTES = [
    'NOTES:',
    '1. 2D DRAWING GENERATED FROM 3D MODEL "platofrms.scdocx" (SPACECLAIM) - SURFACE BODIES + LINE BODIES WITH CROSS-SECTIONS.',
    '2. ALL DIMENSIONS AND LEVELS IN MILLIMETRES. GLOBAL AXES: Z UPWARD. LEVELS REFER TO MODEL Z = 0.',
    '3. THIRD-ANGLE ORTHOGRAPHIC PROJECTION. PLAN VIEWS SHOWN SEPARATELY FOR EACH PLATFORM (THEY OVERLAP IN PLAN).',
    '4. SURFACE BODIES (PLATES) ARE DRAWN AT THEIR MID/REFERENCE SURFACE - PLATE THICKNESS NOT DRAWN.',
    '5. LINE BODIES (STIFFENERS, FACE PLATES, PIPE BRACES) ARE DRAWN WITH THEIR TRUE CROSS-SECTION SWEPT ALONG THE LINE.',
    '6. LAYERS: PLATE_VISIBLE / PLATE_HIDDEN (DASHED), PROFILE_VISIBLE / PROFILE_HIDDEN (DASHED). FREEZE *_HIDDEN LAYERS FOR A CLEAN VIEW.',
]


def title_block(msp, x1, y0):
    w, h = 180 * SCALE, 60 * SCALE
    x0 = x1 - w
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y0 + h), (x0, y0 + h)], close=True, dxfattribs={'layer': 'FRAME'})
    rows = [('TITLE', 'PLATFORMS - GENERAL ARRANGEMENT (PLAN / ELEVATION / SIDE VIEW)'),
            ('SOURCE', '3D MODEL: platofrms.scdocx'),
            ('SCALE', f'1:{SCALE} @ A0        UNITS: mm'),
            ('PROJECTION', 'THIRD ANGLE, Z UP'),
            ('DATE', '2026-09-28')]
    rh = h / len(rows)
    for i, (k, v) in enumerate(rows):
        y = y0 + h - (i + 1) * rh
        if i:
            msp.add_line((x0, y + rh), (x1, y + rh), dxfattribs={'layer': 'FRAME'})
        text(msp, k, x0 + 3 * SCALE, y + rh / 2, h=TXT, align=TextEntityAlignment.MIDDLE_LEFT)
        text(msp, v, x0 + 38 * SCALE, y + rh / 2, h=TXT * 1.4 if i == 0 else TXT,
             align=TextEntityAlignment.MIDDLE_LEFT)
    msp.add_line((x0 + 35 * SCALE, y0), (x0 + 35 * SCALE, y0 + h), dxfattribs={'layer': 'FRAME'})


def main():
    res = compute_views()
    # ---------- individual files (true screen coordinates, no offset)
    for name in VIEWS:
        doc = new_doc()
        msp = doc.modelspace()
        lo, hi = draw_view(msp, name, res[name], (0, 0))
        doc.set_modelspace_vport(height=(hi[1] - lo[1]) * 1.8, center=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2))
        doc.saveas(os.path.join(OUT, f'{name}.dxf'))
    # ---------- combined A0 sheet (third-angle layout)
    doc = new_doc()
    msp = doc.modelspace()
    ext = {n: (np.min([e[0] for e in r['ext'].values()], 0), np.max([e[1] for e in r['ext'].values()], 0))
           for n, r in res.items()}
    gap = 70 * SCALE
    # elevation at true Y/Z coordinates, others offset around it
    e_lo, e_hi = ext['ELEVATION']
    off = {'ELEVATION': np.array([0.0, 0.0])}
    s_lo, s_hi = ext['SIDE_VIEW']
    off['SIDE_VIEW'] = np.array([e_hi[0] + gap + 20 * SCALE - s_lo[0], 0.0])
    pl_lo, pl_hi = ext['PLAN_LOWER']
    off['PLAN_LOWER'] = np.array([0.0, e_hi[1] + gap + 20 * SCALE - pl_lo[1]])
    pu_lo, pu_hi = ext['PLAN_UPPER']
    off['PLAN_UPPER'] = np.array([0.0, off['PLAN_LOWER'][1] + pl_hi[1] + gap - pu_lo[1]])
    boxes = []
    for name in ('ELEVATION', 'SIDE_VIEW', 'PLAN_LOWER', 'PLAN_UPPER'):
        boxes.append(draw_view(msp, name, res[name], off[name]))
    # projection link lines between plan and elevation are implied by alignment; draw frame
    allo = np.min([b[0] for b in boxes], 0) - (60 * SCALE, 75 * SCALE)
    alhi = np.max([b[1] for b in boxes], 0) + (60 * SCALE, 25 * SCALE)
    W, H = 1189 * SCALE, 841 * SCALE
    cx, cy = (allo + alhi) / 2
    fx0, fy0 = allo[0] - 25 * SCALE, cy - H / 2
    cx = fx0 + W / 2
    msp.add_lwpolyline([(fx0, fy0), (fx0 + W, fy0), (fx0 + W, fy0 + H), (fx0, fy0 + H)], close=True,
                       dxfattribs={'layer': 'FRAME'})
    m = 10 * SCALE
    msp.add_lwpolyline([(fx0 + m, fy0 + m), (fx0 + W - m, fy0 + m), (fx0 + W - m, fy0 + H - m),
                        (fx0 + m, fy0 + H - m)], close=True, dxfattribs={'layer': 'FRAME'})
    title_block(msp, fx0 + W - m, fy0 + m)
    ny = fy0 + H - m - 40 * SCALE
    nx = alhi[0] + 20 * SCALE
    for i, s in enumerate(NOTES):
        text(msp, s, nx, ny - i * TXT * 1.8, h=TXT)
    doc.set_modelspace_vport(height=H * 1.05, center=(cx, cy))
    doc.saveas(os.path.join(OUT, 'PLATFORMS_ALL_VIEWS_A0.dxf'))
    print('frame', fx0, fy0, W, H, 'content', allo, alhi)


if __name__ == '__main__':
    main()
