"""Check if dataset cameras can see the reference bowl's central floor."""
import argparse,json
from pathlib import Path
import numpy as np
import trimesh

parser=argparse.ArgumentParser(); parser.add_argument('source',type=Path); parser.add_argument('output',type=Path)
args=parser.parse_args(); mesh=trimesh.load(args.source/'metal_cups_1.obj',force='mesh',process=False)
t=np.asarray(mesh.vertices)[mesh.faces]; v0=t[:,0]; e1=t[:,1]-v0; e2=t[:,2]-v0
meta=json.loads((args.source/'metadata.json').read_text())
target=np.array([0.,1.3446241714188176,0.]); results=[]
for f in meta['frames']:
    if f['frame']==0: continue
    C=np.array([f['position_world'][k] for k in ('x','y','z')]); d=target-C; length=np.linalg.norm(d); d/=length
    h=np.cross(np.broadcast_to(d,e2.shape),e2); a=np.einsum('ij,ij->i',e1,h)
    valid=np.abs(a)>1e-10; inv=np.where(valid,1/np.where(valid,a,1),0)
    s=C-v0; u=inv*np.einsum('ij,ij->i',s,h); q=np.cross(s,e1)
    v=inv*(q@d); distance=inv*np.einsum('ij,ij->i',e2,q)
    hit=valid&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(distance>0)
    nearest=float(distance[hit].min()) if hit.any() else None
    results.append(dict(camera=f['camera'],frame=f['frame'],target_distance=float(length),
                        nearest_surface_distance=nearest,occluded=bool(nearest is not None and nearest<length-.02)))
report=dict(target=target.tolist(),tests=len(results),visible_count=sum(not x['occluded'] for x in results),
            occluded_count=sum(x['occluded'] for x in results),samples=results)
args.output.write_text(json.dumps(report,indent=2))
print({k:v for k,v in report.items() if k!='samples'})
print(results[0]); print(results[90])
