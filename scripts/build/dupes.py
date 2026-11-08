import json,sys,numpy as np,imagehash
rows=json.load(open(sys.argv[1])); ok=[r for r in rows if r['status']=='ok' and '__files' not in r['path']]
H=[imagehash.hex_to_hash(r['phash']) for r in ok]
n=len(ok); parent=list(range(n))
def f(x):
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
pairs=[]
for i in range(n):
    for j in range(i+1,n):
        d=H[i]-H[j]
        if d<=6: pairs.append((i,j,d)); parent[f(i)]=f(j)
g={}
for i in range(n): g.setdefault(f(i),[]).append(i)
groups=[v for v in g.values() if len(v)>1]
dist=lambda i,j:H[i]-H[j]
with open(sys.argv[2],'w',encoding='utf-8') as o:
    o.write(f'# Duplicate report\n\n{len(groups)} groups, {sum(len(v)-1 for v in groups)} removable extras (phash distance <= 6 of 64 bits). Nothing deleted. First file in each group = suggested keeper (highest resolution).\n\n')
    drop=set()
    for k,v in enumerate(sorted(groups,key=len,reverse=True),1):
        v=sorted(v,key=lambda i:-ok[i]['w']*ok[i]['h'])
        o.write(f'## Group {k}\n')
        for t,i in enumerate(v):
            o.write(f"- {'KEEP' if t==0 else 'dup '} {ok[i]['w']}x{ok[i]['h']} d={dist(v[0],i)}  `{ok[i]['path']}`\n")
            if t: drop.add(ok[i]['path'])
        o.write('\n')
json.dump(sorted(drop),open(sys.argv[3],'w'))
print(len(groups),len(drop),len(ok))
