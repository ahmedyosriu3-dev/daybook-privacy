import struct, re
from collections import Counter, defaultdict
def load_facets(fn='sc/SpaceClaim/Graphics/facets.bin'):
    b=open(fn,'rb').read()
    st={'p':16}
    def I():
        v=struct.unpack_from('<i',b,st['p'])[0]; st['p']+=4; return v
    def al(): st['p']=(st['p']+3)&~3
    nb=struct.unpack_from('<i',b,12)[0]
    bodies={}
    for bi in range(nb):
        hdr=[I() for _ in range(7)]
        faces=[]
        for fi in range(hdr[6]):
            fh=[I() for _ in range(5)]; nv=fh[4]
            v=struct.unpack_from('<%df'%(8*nv),b,st['p']); st['p']+=32*nv
            nt=I(); tri=struct.unpack_from('<%dH'%nt,b,st['p']); st['p']+=2*nt; al()
            ns=I(); seg=struct.unpack_from('<%dH'%ns,b,st['p']); st['p']+=2*ns; al()
            ne=I(); ed=[(I(),I(),I()) for _ in range(ne)]
            pts=[v[i*8:i*8+3] for i in range(nv)]
            faces.append(dict(id='%d:%d'%(fh[0],fh[1]),pts=pts,tri=tri,seg=seg,edges=ed))
        ne=I(); et=[(I(),I(),I()) for _ in range(ne)]
        bodies['%d:%d'%(hdr[1],hdr[2])]=dict(us='%d:%d'%(hdr[3],hdr[4]),faces=faces,etab=et)
    return bodies
def load_renderlist(fn='sc/SpaceClaim/Graphics/renderlist.xml'):
    d=open(fn,encoding='utf-8-sig').read()
    views=d.split('<View ')[1:]
    items=[]
    for m in re.finditer(r'<Item ([^>]*?)(/?)>(.*?)(?:</Item>|(?=<Item)|(?=</View))',views[1],re.S):
        a=dict(re.findall(r'(\w+)="([^"]*)"',m.group(1)))
        bl=[dict(re.findall(r'(\w+)="([^"]*)"',x)) for x in re.findall(r'<Body ([^>]*)/>',m.group(3))]
        a['bodies']=bl; items.append(a)
    return items
