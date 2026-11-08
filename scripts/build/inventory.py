import sys, os, json, colorsys
import numpy as np
from PIL import Image
import imagehash
try:
    import pillow_avif  # noqa
except Exception: pass
Image.MAX_IMAGE_PIXELS = 300_000_000
root, out = sys.argv[1], sys.argv[2]
exts = {'.jpg','.jpeg','.png','.webp','.gif','.avif','.download'}
rows=[]; thumbs=[]
for dp, dn, fn in os.walk(root):
    if '_taste-work' in dp: continue
    for f in sorted(fn):
        p=os.path.join(dp,f); e=os.path.splitext(f)[1].lower()
        rel=os.path.relpath(p,root)
        r={'path':rel,'ext':e,'bytes':os.path.getsize(p)}
        if e not in exts: r['status']='non-image'; rows.append(r); continue
        try:
            im=Image.open(p); r['fmt']=im.format; r['w'],r['h']=im.size
            im.draft('RGB',(256,256)); im=im.convert('RGB')
            t=im.copy(); t.thumbnail((128,128)); 
            r['phash']=str(imagehash.phash(t,hash_size=8)); r['dhash']=str(imagehash.dhash(t,hash_size=8))
            r['idx']=len(thumbs)
            c=Image.new('RGB',(128,128)); c.paste(t,((128-t.width)//2,(128-t.height)//2)); 
            thumbs.append(np.asarray(t.resize((64,64))))
            t.save(os.path.join(out,'thumbs',f'{r["idx"]}.jpg'),quality=85)
            r['status']='ok'
        except Exception as ex:
            r['status']='broken: '+str(ex)[:80]
        rows.append(r)
np.save(os.path.join(out,'thumbs64.npy'),np.stack(thumbs))
json.dump(rows,open(os.path.join(out,'inventory.json'),'w'),indent=1)
print(len(rows),len(thumbs))
