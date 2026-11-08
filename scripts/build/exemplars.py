import json,sys,os,shutil,collections
from PIL import Image
root,out=sys.argv[1],sys.argv[2]
rows=json.load(open(out+'/clusters_k5.json')); res={}
names={0:'neon-dusk',1:'deep-space-dark',2:'warm-interiors-japan',3:'bright-airy-minimal',4:'retro-sci-fi-painting'}
for c,n in names.items():
    m=sorted([r for r in rows if r['cluster']==c],key=lambda r:r['dist'])
    m=m[:max(8,int(len(m)*.5))]
    m=[r for r in m if max(r['w'],r['h'])>=1600 and r['w']>=r['h']*0.9 and r['w']*r['h']<40e6]
    m.sort(key=lambda r:-r['w']*r['h']); pick=[]; cnt=collections.Counter()
    for r in m:
        f=r['path'].split(os.sep)[1] if r['path'].count(os.sep)>1 else '-'
        if cnt[f]>=3: continue
        cnt[f]+=1; pick.append(r)
        if len(pick)==8: break
    d=f'{out}/exemplars/{n}'; os.makedirs(d,exist_ok=True)
    for r in pick:
        shutil.copy2(os.path.join(root,r['path']),os.path.join(d,f"{r['idx']:04d}_"+os.path.basename(r['path'])))
    res[n]=[r['path'] for r in pick]
    S=Image.new('RGB',(4*220,2*140),(20,20,20))
    for i,r in enumerate(pick):
        t=Image.open(f'{out}/thumbs/{r["idx"]}.jpg'); t.thumbnail((216,136)); S.paste(t,((i%4)*220,(i//4)*140))
    S.save(f'{out}/contact-sheets/exemplars-{n}.jpg',quality=80)
json.dump(res,open(out+'/exemplars.json','w'),indent=1); print({k:len(v) for k,v in res.items()})
