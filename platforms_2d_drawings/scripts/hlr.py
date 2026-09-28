"""Build world geometry (surfaces + swept beams) and project with hidden-line removal."""
import numpy as np
from geom import surf, beams

Z_SPLIT = 36.2  # lower platform below, upper platform above


def rot(v, k, a):
    k = k / np.linalg.norm(k)
    return v * np.cos(a) + np.cross(k, v) * np.sin(a) + k * (k @ v) * (1 - np.cos(a))


def loops_of(seg):
    """Group segment pairs into closed loops (lists of vertex indices)."""
    nb = {}
    for a, b in seg:
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
    seen, loops = set(), []
    for s in nb:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [n for n in nb[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops


def poly_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1))


def build():
    tris, tri_grp = [], []
    edges = []  # (p0, p1, grp, kind)
    beam_objs = []
    # ---- surfaces
    for s in surf:
        zc = np.mean(np.vstack([f['pts'] for f in s['faces']])[:, 2])
        grp = 'U' if zc > Z_SPLIT else 'L'
        s['grp'] = grp
        seen = set()
        for f in s['faces']:
            P = f['pts']
            tris.append(P[f['tri']])
            tri_grp += [grp] * len(f['tri'])
            for a, b in f['seg']:
                k = tuple(sorted([tuple(np.round(P[a], 4)), tuple(np.round(P[b], 4))]))
                if k in seen or k[0] == k[1]:
                    continue
                seen.add(k)
                edges.append((P[a], P[b], grp, 'PLATE'))
    # ---- beams
    for bm in beams:
        pr = bm['prof']
        p0, p1 = bm['p0'], bm['p1']
        T = (p1 - p0) / np.linalg.norm(p1 - p0)
        Tl = -T if bm['rev'] else T
        Y = rot(bm['ydir'] / np.linalg.norm(bm['ydir']), Tl, bm['ang'])
        Y = Y - (Y @ Tl) * Tl
        Y /= np.linalg.norm(Y)
        X = np.cross(Y, Tl)
        sp = pr['pts']
        if bm['anchor'] == 'Centroid':
            t = sp[pr['tri']]
            ar = 0.5 * np.abs(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]))
            anc = (t.mean(1) * ar[:, None]).sum(0) / ar.sum()
        else:
            anc = np.array(bm['uv'])
        loc = sp - anc
        off = loc[:, :1] * X + loc[:, 1:2] * Y
        W0, W1 = p0 + off, p1 + off
        grp = 'U' if (p0[2] + p1[2]) / 2 > Z_SPLIT else 'L'
        bm['grp'] = grp
        loops = loops_of(pr['seg'])
        areas = [abs(poly_area(sp[l])) for l in loops]
        outer = int(np.argmax(areas))
        # caps
        for W in (W0, W1):
            for a, b in pr['seg']:
                edges.append((W[a], W[b], grp, 'PROFILE'))
            tris.append(W[pr['tri']])
            tri_grp += [grp] * len(pr['tri'])
        # side faces
        lp = []
        for li, l in enumerate(loops):
            n = len(l)
            idx = np.array(l)
            q0, q1 = W0[idx], W1[idx]
            r0, r1 = np.roll(q0, -1, 0), np.roll(q1, -1, 0)
            tris.append(np.stack([q0, r0, r1], 1))
            tris.append(np.stack([q0, r1, q1], 1))
            tri_grp += [grp] * (2 * n)
            # side-face normals (for silhouettes) and corner sharpness
            d2 = sp[np.roll(idx, -1)] - sp[idx]
            d2n = d2 / np.linalg.norm(d2, axis=1)[:, None]
            prev = np.roll(d2n, 1, 0)
            turn = np.degrees(np.arccos(np.clip((prev * d2n).sum(1), -1, 1)))
            n3 = np.cross(d2[:, :1] * X + d2[:, 1:2] * Y, Tl)
            lp.append(dict(q0=q0, q1=q1, turn=turn, n3=n3, outer=li == outer))
        beam_objs.append(dict(loops=lp, grp=grp, T=Tl))
    tris = np.concatenate(tris)
    return tris, np.array(tri_grp), edges, beam_objs


def beam_edges(beam_objs, F):
    """Longitudinal beam lines: sharp corners always, smooth vertices only on silhouette."""
    out = []
    for bo in beam_objs:
        for lp in bo['loops']:
            s = np.sign(lp['n3'] @ F)
            sil = s != np.roll(s, 1)
            sharp = lp['turn'] > 25
            for i in np.nonzero(sharp | (sil & lp['outer']))[0]:
                out.append((lp['q0'][i], lp['q1'][i], bo['grp'], 'PROFILE'))
    return out


class View:
    def __init__(self, R, U):
        self.R, self.U = np.array(R, float), np.array(U, float)
        self.F = np.cross(self.U, self.R)  # direction the viewer looks
        # right-handed screen: R x U points toward viewer => F = U x R

    def proj(self, p):
        return np.stack([p @ self.R, p @ self.U, p @ self.F], -1)


def hlr(view, tris, edges, step=0.01, eps=0.004, cell=0.25):
    Pt = view.proj(tris)  # (n,3,3)
    a, b, c = Pt[:, 0], Pt[:, 1], Pt[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ok = np.abs(area) > 1e-7
    Pt, area = Pt[ok], area[ok]
    lo = Pt[:, :, :2].min(1)
    hi = Pt[:, :, :2].max(1)
    org = lo.min(0) - 1
    grid = {}
    i0 = np.floor((lo - org) / cell).astype(int)
    i1 = np.floor((hi - org) / cell).astype(int)
    for t in range(len(Pt)):
        for i in range(i0[t, 0], i1[t, 0] + 1):
            for j in range(i0[t, 1], i1[t, 1] + 1):
                grid.setdefault((i, j), []).append(t)
    grid = {k: np.array(v) for k, v in grid.items()}

    # sample all edges
    E0 = view.proj(np.array([e[0] for e in edges]))
    E1 = view.proj(np.array([e[1] for e in edges]))
    L = np.linalg.norm((E1 - E0)[:, :2], axis=1)
    L3 = np.linalg.norm(E1 - E0, axis=1)
    ns = np.maximum(2, np.ceil(L / step).astype(int) + 1)
    ns[L < 1e-6] = 0  # edges viewed end-on vanish
    eid = np.repeat(np.arange(len(edges)), ns)
    tpar = np.concatenate([np.linspace(0, 1, n) for n in ns]) if ns.sum() else np.zeros(0)
    Q = E0[eid] + (E1[eid] - E0[eid]) * tpar[:, None]
    hidden = np.zeros(len(Q), bool)
    qc = np.floor((Q[:, :2] - org) / cell).astype(int)
    key = qc[:, 0] * 100000 + qc[:, 1]
    order = np.argsort(key)
    ks, starts = np.unique(key[order], return_index=True)
    ends = np.append(starts[1:], len(order))
    for k, s0, s1 in zip(ks, starts, ends):
        cellk = (k // 100000, k % 100000)
        tl = grid.get(cellk)
        if tl is None:
            continue
        qi = order[s0:s1]
        q = Q[qi]
        T = Pt[tl]
        A, Bv, C = T[:, 0], T[:, 1], T[:, 2]
        ar = area[tl]
        # barycentric
        w0 = ((Bv[None, :, 0] - q[:, None, 0]) * (C[None, :, 1] - q[:, None, 1]) -
              (Bv[None, :, 1] - q[:, None, 1]) * (C[None, :, 0] - q[:, None, 0])) / ar
        w1 = ((C[None, :, 0] - q[:, None, 0]) * (A[None, :, 1] - q[:, None, 1]) -
              (C[None, :, 1] - q[:, None, 1]) * (A[None, :, 0] - q[:, None, 0])) / ar
        w2 = 1 - w0 - w1
        # inside with small margin (in model units) so coincident outlines stay visible
        m = 1e-9
        inside = (w0 > m) & (w1 > m) & (w2 > m)
        # reject points within ~1 mm of the triangle boundary in 2D
        dep = w0 * A[None, :, 2] + w1 * Bv[None, :, 2] + w2 * C[None, :, 2]
        occ = inside & (dep < q[:, None, 2] - eps)
        if occ.any():
            # boundary tolerance: distance to each triangle edge must exceed 1 mm
            rows, cols = np.nonzero(occ)
            P2 = q[rows, :2]
            TT = T[cols][:, :, :2]
            dmin = np.full(len(rows), np.inf)
            for e in range(3):
                pa, pb = TT[:, e], TT[:, (e + 1) % 3]
                d = pb - pa
                ll = np.maximum((d * d).sum(1), 1e-18)
                tt = np.clip(((P2 - pa) * d).sum(1) / ll, 0, 1)
                dmin = np.minimum(dmin, np.linalg.norm(P2 - (pa + d * tt[:, None]), axis=1))
            good = dmin > 0.001
            hid = np.zeros(len(qi), bool)
            np.logical_or.at(hid, rows[good], True)
            hidden[qi] = hid
    # rebuild runs per edge
    vis_out, hid_out = [], []
    pos = 0
    for e, n in enumerate(ns):
        if n == 0:
            continue
        h = hidden[pos:pos + n]
        q = Q[pos:pos + n, :2]
        pos += n
        # clean isolated single-sample flips
        if n >= 3:
            hh = h.copy()
            for i in range(1, n - 1):
                if h[i] != h[i - 1] and h[i] != h[i + 1]:
                    hh[i] = h[i - 1]
            h = hh
        brk = np.nonzero(h[1:] != h[:-1])[0]
        cuts = [0.0] + [(i + 0.5) / (n - 1) for i in brk] + [1.0]
        p0, p1 = q[0], q[-1]
        state = h[0]
        for c0, c1 in zip(cuts[:-1], cuts[1:]):
            seg = (p0 + (p1 - p0) * c0, p0 + (p1 - p0) * c1, edges[e][3])
            (hid_out if state else vis_out).append(seg)
            state = not state
    return vis_out, hid_out
