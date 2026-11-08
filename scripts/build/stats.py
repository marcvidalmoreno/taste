import json,sys,collections
rows=json.load(open(sys.argv[1]))
ok=[r for r in rows if r['status']=='ok']
print('bad:',[(r['path'][-60:],r['status'][:30]) for r in rows if r['status']!='ok'])
print('fmt',collections.Counter(r['fmt'] for r in ok))
tot=sum(r['bytes'] for r in rows)/1e6; print('MB',tot)
mp=sorted(r['w']*r['h']/1e6 for r in ok); import numpy as np
print('MP pct',np.percentile(mp,[0,10,50,90,100]))
print('tiny <1000px long edge:',sum(1 for r in ok if max(r['w'],r['h'])<1000),' <1920:',sum(1 for r in ok if max(r['w'],r['h'])<1920))
print('portrait',sum(1 for r in ok if r['h']>r['w']*1.1),'landscape',sum(1 for r in ok if r['w']>r['h']*1.1))
print('web assets (__files):',sum('__files' in r['path'] for r in ok))
import os;c=collections.Counter(r['path'].split(os.sep)[1] if r['path'].count(os.sep)>1 else '-' for r in ok); print(c)
