import json,sys,os,numpy as np,collections
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from matplotlib.colors import rgb_to_hsv
out=sys.argv[1]; K=int(sys.argv[2])
rows=json.load(open(out+'/inventory.json')); T=np.load(out+'/thumbs64.npy')
drop=set(json.load(open(out+'/dup_extras.json')))
sel=[r for r in rows if r['status']=='ok' and '__files' not in r['path'] and r['path'] not in drop]
F=[]
for r in sel:
    a=T[r['idx']]/255.; h=rgb_to_hsv(a); H,S,V=h[...,0],h[...,1],h[...,2]
    hist=np.zeros(12)
    for b in range(12): hist[b]=((H*12).astype(int)%12==b).astype(float).__mul__(S*V).sum()
    hist/= hist.sum()+1e-6
    g=V.reshape(4,16,4,16).mean((1,3)).ravel()
    gy,gx=np.gradient(V); edge=np.hypot(gx,gy).mean()
    ar=r['w']/r['h']
    F.append(np.r_[V.mean(),V.std(),S.mean(),S.std(),hist*1.5,g*0.7,edge*5,min(ar,2.5)*0.5,(S<0.12).mean()])
F=np.array(F); X=StandardScaler().fit_transform(F); X=PCA(12,random_state=0).fit_transform(X)
km=KMeans(K,n_init=20,random_state=0).fit(X)
print('K',K,'sil',silhouette_score(X,km.labels_))
D=km.transform(X)
for r,l,d in zip(sel,km.labels_,D): r['cluster']=int(l); r['dist']=float(d[l])
json.dump(sel,open(out+f'/clusters_k{K}.json','w'))
for c in range(K):
    m=[r for r in sel if r['cluster']==c]
    fol=collections.Counter(r['path'].split(os.sep)[1] if r['path'].count(os.sep)>1 else '-' for r in m).most_common(4)
    print(c,len(m),fol)
