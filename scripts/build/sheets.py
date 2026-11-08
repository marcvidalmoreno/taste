import json,sys,os,random
from PIL import Image
out=sys.argv[1]; K=int(sys.argv[2]); rows=json.load(open(f'{out}/clusters_k{K}.json'))
os.makedirs(out+'/contact-sheets',exist_ok=True)
for c in range(K):
    m=[r for r in rows if r['cluster']==c]; random.Random(1).shuffle(m); m=m[:48]
    cols,cell=8,150; rs=(len(m)+cols-1)//cols
    S=Image.new('RGB',(cols*cell,rs*cell),(20,20,20))
    for i,r in enumerate(m):
        t=Image.open(f'{out}/thumbs/{r["idx"]}.jpg'); t.thumbnail((cell-4,cell-4))
        S.paste(t,((i%cols)*cell+2+(cell-4-t.width)//2,(i//cols)*cell+2+(cell-4-t.height)//2))
    S.save(f'{out}/contact-sheets/cluster{c}.jpg',quality=80)
