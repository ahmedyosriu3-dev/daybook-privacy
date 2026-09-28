import pickle, re, numpy as np
B,it=pickle.load(open('cache.pkl','rb'))
d=open('sc/SpaceClaim/document.xml',encoding='utf-8-sig').read()
def T_of(a): return np.array([float(x) for x in a['Transform'].split(',')]).reshape(4,4)
item_by_id={a['Id']:a for a in it}
# surfaces
surf=[]  # list of dict(body, faces:[(pts,tri,seg)])
for a in it:
    T=T_of(a)
    for bb in a['bodies']:
        if bb['Visible']!='1': continue
        fl=[]
        for f in B[bb['Id']]['faces']:
            p=np.array(f['pts'])@T[:3,:3].T+T[:3,3]
            fl.append(dict(pts=p,tri=np.array(f['tri']).reshape(-1,3),seg=np.array(f['seg']).reshape(-1,2),fid=f['id']))
        surf.append(dict(id=bb['Id'],item=a['Id'],faces=fl,color=bb['Color']))
# profiles
def profile(pid):
    i=d.find('<PartDef Id="%s"'%pid)
    if i<0: pid='15111:125'; i=d.find('<PartDef Id="%s"'%pid)
    bid=re.search(r'<NominalBodyDef Id="([^"]+)"',d[i:i+5000]).group(1)
    for f in B[bid]['faces']:
        p=np.array(f['pts'])
        if np.ptp(p[:,2])<1e-6 and abs(p[0,2])<1e-6:
            return dict(pts=p[:,:2],tri=np.array(f['tri']).reshape(-1,3),seg=np.array(f['seg']).reshape(-1,2),pid=pid)
# sketch curves -> part
parts=[(m.start(),m.group(1)) for m in re.finditer(r'<PartDef Id="([^"]+)"',d)]
import bisect
starts=[s for s,_ in parts]
sk={}
for m in re.finditer(r'<SketchCurveDef Id="([^"]+)">(.*?)</SketchCurveDef>',d,re.S):
    g=re.search(r'<origin>(.*?)</origin><dir>(.*?)</dir></curve><interval><start>(.*?)</start><end>(.*?)</end>',m.group(2))
    o=np.array(g.group(1).split(),float); dr=np.array(g.group(2).split(),float); s0,s1=float(g.group(3)),float(g.group(4))
    part=parts[bisect.bisect(starts,m.start())-1][1]
    T=T_of(item_by_id[part])
    p0=T[:3,:3]@(o+s0*dr)+T[:3,3]; p1=T[:3,:3]@(o+s1*dr)+T[:3,3]
    sk[m.group(1).split(':')[1]]=(m.group(1),p0,p1,part)
beams=[]
for m in re.finditer(r'<BeamDef Id="([^"]+)".*?refId="([^"]+)".*?<sectionSource>(.*?)</sectionSource><reversed>(.*?)</reversed><orientation>(.*?)</orientation><anchor>(.*?)</anchor>(.*?)<beamType>.*?<yDirection>(.*?)</yDirection></BeamDef>',d,re.S):
    loc=re.search(r'<u>(.*?)</u><v>(.*?)</v>',m.group(7))
    skid,p0,p1,part=sk[m.group(2).split(':')[1]]
    beams.append(dict(id=m.group(1),sk=skid,p0=p0,p1=p1,prof=profile(m.group(3)),rev=m.group(4)=='True',ang=float(m.group(5)),anchor=m.group(6),
        uv=(float(loc.group(1)),float(loc.group(2))) if loc else None,ydir=np.array(m.group(8).split(),float),part=part))
