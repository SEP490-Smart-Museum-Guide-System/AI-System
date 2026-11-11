"""Compare reconstructed geometry silhouettes with source images before texture."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import trimesh
from trimesh.transformations import quaternion_matrix


def top_profile(mesh, axis):
    triangles=np.asarray(mesh.vertices)[mesh.faces]
    x=triangles[:,:,0]; z=triangles[:,:,2]; y=triangles[:,:,1]
    denominator=(z[:,1]-z[:,2])*(x[:,0]-x[:,2])+(x[:,2]-x[:,1])*(z[:,0]-z[:,2])
    valid=np.abs(denominator)>1e-12
    denominator=np.where(valid,denominator,1)
    result=[]
    for value in np.linspace(-2.8,2.8,81):
        px,pz=(value,0) if axis=='x' else (0,value)
        a=((z[:,1]-z[:,2])*(px-x[:,2])+(x[:,2]-x[:,1])*(pz-z[:,2]))/denominator
        b=((z[:,2]-z[:,0])*(px-x[:,2])+(x[:,0]-x[:,2])*(pz-z[:,2]))/denominator
        c=1-a-b
        hit=valid&(a>=-1e-8)&(b>=-1e-8)&(c>=-1e-8)
        height=a*y[:,0]+b*y[:,1]+c*y[:,2]
        result.append(dict(coordinate=float(value),height=float(height[hit].max()) if hit.any() else None))
    return result


def assess(mesh_path, poses_path, images, output, reference=None):
    mesh=trimesh.load(mesh_path,force='mesh',process=False)
    poses=json.loads(poses_path.read_text())
    edges=np.sort(mesh.edges,axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    report=dict(vertices=len(mesh.vertices), faces=len(mesh.faces), watertight=bool(mesh.is_watertight),
                winding_consistent=bool(mesh.is_winding_consistent), boundary_edges=int(np.sum(counts==1)),
                nonmanifold_edges=int(np.sum(counts>2)), degenerate_faces=int(np.sum(mesh.area_faces<1e-12)),
                normals_finite=bool(np.isfinite(mesh.face_normals).all()),bounds=mesh.bounds.tolist(),views=[])
    output.mkdir(parents=True,exist_ok=True)
    if reference:
        original=trimesh.load(reference,force='mesh',process=False)
        report['top_down_profiles']={axis:dict(reference=top_profile(original,axis),reconstruction=top_profile(mesh,axis)) for axis in ('x','z')}
        errors=[]
        missing=0; reference_hits=0
        for profiles in report['top_down_profiles'].values():
            for a,b in zip(profiles['reference'],profiles['reconstruction']):
                reference_hits += int(a['height'] is not None)
                missing += int(a['height'] is not None and b['height'] is None)
                if a['height'] is not None and b['height'] is not None:
                    errors.append(abs(a['height']-b['height']))
        report['top_down_profile_mean_absolute_error']=float(np.mean(errors)) if errors else None
        report['top_down_profile_missing_hits']=missing
        report['top_down_profile_reference_hits']=reference_hits
    for name,p in poses.items():
        frame=int(Path(name).stem.split('.')[-1])
        if frame not in (1,23,46,68,90):
            continue
        R=quaternion_matrix(p['qvec'])[:3,:3]
        xyz=np.asarray(mesh.vertices)@R.T+np.asarray(p['tvec'])
        uv=xyz[:,:2]/xyz[:,2:]*[p['fx'],p['fy']]+[p['cx'],p['cy']]
        mask=Image.new('1',(p['width'],p['height'])); draw=ImageDraw.Draw(mask)
        for face in mesh.faces:
            if np.all(xyz[face,2]>0):
                draw.polygon([tuple(v) for v in uv[face]],fill=1)
        rendered=np.asarray(mask,dtype=bool)
        a=np.asarray(Image.open(images/name).convert('RGB')).astype(float)
        foreground=np.max(np.abs(a-a[0,0]),axis=2)>18
        iou=float(np.logical_and(foreground,rendered).sum()/np.logical_or(foreground,rendered).sum())
        report['views'].append(dict(image=name,silhouette_iou=iou))
        overlay=np.uint8(np.stack([foreground*255,rendered*255,np.zeros_like(foreground)],axis=-1))
        Image.fromarray(overlay).save(output/(Path(name).stem+'-mesh-mask.png'))
    (output/'mesh-audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for field in ('mesh','poses','images','output'): parser.add_argument(field,type=Path)
    parser.add_argument('--reference',type=Path)
    args=parser.parse_args(); assess(args.mesh,args.poses,args.images,args.output,args.reference)
