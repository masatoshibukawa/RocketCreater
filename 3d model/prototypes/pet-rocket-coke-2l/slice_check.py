"""Reproducible geometric slice review. Never use the temporary G-code on a printer."""
import argparse
from collections import defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

PROTOTYPE = Path(__file__).resolve().parent
OUT = None
SOURCE = None
PARTS = ('nose_cone', 'fin', 'fit_ring', 'mount_gauge')
MODEL_TYPES = {'WALL-INNER','WALL-OUTER','SKIN','FILL','GAP-FILL'}
COLORS = {'WALL-INNER':'#2474b5','WALL-OUTER':'#e67316','SKIN':'#8b5bb4','FILL':'#1c9c66','SKIRT':'#aab2bd'}


def stl(path):
    data=path.read_bytes()
    count,=struct.unpack_from('<I',data,80)
    result=[]
    for i in range(count):
        f=struct.unpack_from('<12fH',data,84+50*i)
        result.append([f[3:6],f[6:9],f[9:12]])
    return result


def geometry(tris):
    points=[p for t in tris for p in t]
    low=[min(p[i] for p in points) for i in range(3)]
    high=[max(p[i] for p in points) for i in range(3)]
    contact=0.0
    downward=defaultdict(float)
    volume=0.0
    for a,b,c in tris:
        u=[b[i]-a[i] for i in range(3)]
        v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        cross=[b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0]]
        volume+=sum(a[i]*cross[i] for i in range(3))/6
        if max(abs(p[2]-low[2]) for p in (a,b,c))<1e-5:
            contact+=length/2
        if length and n[2]<0 and min(p[2] for p in (a,b,c))>low[2]+1e-5:
            slope=math.degrees(math.acos(min(1,max(-1,-n[2]/length))))
            for limit in (20,30,40,45):
                if slope<limit-1e-5:downward[str(limit)]+=length/2
    slices=[]
    for z in (.1,.3,.5,.7,.9,1.1,1.3,1.5,1.7,1.9,2.1):
        cut=[]
        for tri in tris:
            for a,b in zip(tri,tri[1:]+tri[:1]):
                if (a[2]<=z<b[2])or(b[2]<=z<a[2]):
                    f=(z-a[2])/(b[2]-a[2])
                    cut.append([a[i]+f*(b[i]-a[i]) for i in range(2)])
        if cut:slices.append({'slice_z_mm':z,'xy_bounds_mm':[[min(p[i] for p in cut),max(p[i] for p in cut)] for i in range(2)]})
    return {'stl_bounds_mm':[low,high],'stl_dimensions_mm':[high[i]-low[i] for i in range(3)],'signed_volume_mm3':volume,'flat_contact_area_mm2':contact,'downward_surface_area_with_slope_below_degrees_from_bed_mm2':dict(downward),'early_stl_cross_section_bounds':slices}


def ranges(values):
    out=[]
    for v in sorted(values):
        if out and v==out[-1][1]+1:out[-1][1]=v
        else:out.append([v,v])
    return out


def parse_gcode(path):
    layers=defaultdict(list)
    layer=-1
    typ=''
    x=y=z=e=0.0
    filament_area=math.pi*1.75**2/4
    layer_count=None
    run=0
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith(';TYPE:'):
            typ=line[6:]
            run+=1
        if line.startswith(';LAYER:'):layer=int(line[7:])
        if line.startswith(';LAYER_COUNT:'):layer_count=int(line[13:])
        if line.startswith('G92 '):
            vals={k:float(v) for k,v in re.findall(r'([XYZE])(-?[0-9.]+)',line)}
            e=vals.get('E',e)
        if not line.startswith(('G0 ','G1 ')):continue
        vals={k:float(v) for k,v in re.findall(r'([XYZE])(-?[0-9.]+)',line)}
        nx,ny,nz,ne=vals.get('X',x),vals.get('Y',y),vals.get('Z',z),vals.get('E',e)
        distance=math.hypot(nx-x,ny-y)
        if line.startswith('G0 ') and distance>.0001:run+=1
        if ne>e and distance>.0001 and layer>=0:
            volume=(ne-e)*filament_area
            width=volume/(distance*.2)
            layers[layer].append({'a':(x,y),'b':(nx,ny),'z':nz,'type':typ,'length':distance,'extrusion_volume_mm3':volume,'width':width,'run':run})
        x,y,z,e=nx,ny,nz,ne
    return layers,layer_count


def sampled(segment,step=.4):
    n=max(1,math.ceil(segment['length']/step))
    for i in range(n+1):
        f=i/n
        yield (segment['a'][0]+f*(segment['b'][0]-segment['a'][0]),segment['a'][1]+f*(segment['b'][1]-segment['a'][1]))


def prior_index(segments):
    grid=defaultdict(list)
    for s in segments:
        for x,y in sampled(s):grid[(math.floor(x/.5),math.floor(y/.5))].append((x,y,min(.9,max(.1,s['width']))/2))
    return grid


def support_screen(layers):
    """Conservative point-sampled bead-overlap screen; not a mechanics solver.

    A sample counts as overlapped if previous bead center samples are within
    the sum of the two bead half-widths plus 0.08 mm numeric/sample allowance.
    Current bead widths derive from extrusion volume, using 0.2 mm layer height.
    Near-gap ratios are screening data, not unsupported *area* measurements.
    """
    reports=[]
    prev=[]
    for layer,segs in sorted(layers.items()):
        model=[s for s in segs if s['type'] in MODEL_TYPES]
        if layer==0:
            prev=segs
            continue
        grid=prior_index(prev)
        total=unsupported=0.0
        worst=0.0
        runs=defaultdict(lambda:{'length':0.0,'all_no_overlap':True})
        for s in model:
            samples=list(sampled(s))
            count=0
            for x,y in samples:
                ix,iy=math.floor(x/.5),math.floor(y/.5)
                supported=False
                half=min(.9,max(.1,s['width']))/2
                for dx in (-2,-1,0,1,2):
                    if supported:break
                    for dy in (-2,-1,0,1,2):
                        if any((x-px)**2+(y-py)**2<=(half+ph+.08)**2 for px,py,ph in grid.get((ix+dx,iy+dy),())):
                            supported=True
                            break
                if not supported:count+=1
            fraction=count/len(samples)
            s['unsupported_sample_fraction']=fraction
            runs[s['run']]['length']+=s['length']
            runs[s['run']]['all_no_overlap'] &= count==len(samples)
            total+=s['length']
            unsupported+=s['length']*fraction
            if fraction>.8:worst=max(worst,s['length'])
        reports.append({'layer_zero_based':layer,'print_z_mm':model[0]['z'] if model else None,'model_path_length_mm':round(total,3),'no_prior_bead_overlap_sampled_path_mm':round(unsupported,3),'no_prior_overlap_fraction':round(unsupported/total,5) if total else 0,'longest_segment_with_over_80percent_no_prior_overlap_mm':round(worst,3),'extrusion_runs_with_no_prior_overlap_lengths_mm':[round(v['length'],3) for v in runs.values() if v['all_no_overlap']]})
        prev=segs
    return reports


def metrics(layers,reported_count):
    types=defaultdict(lambda:{'path_length_mm':0.0,'volume_mm3':0.0,'segments':0,'layers':set()})
    bounds=[[float('inf'),float('-inf')] for _ in range(3)]
    model_layers=[]
    brim_paths=[]
    for layer,segs in layers.items():
        if any(s['type'] in MODEL_TYPES for s in segs):model_layers.append(layer)
        for s in segs:
            r=min(.9,max(.1,s['width']))/2
            for p in (s['a'],s['b']):
                for i in (0,1):bounds[i]=[min(bounds[i][0],p[i]-r),max(bounds[i][1],p[i]+r)]
            bounds[2]=[min(bounds[2][0],s['z']-.2),max(bounds[2][1],s['z'])]
            d=types[s['type']]
            d['path_length_mm']+=s['length'];d['volume_mm3']+=s['extrusion_volume_mm3'];d['segments']+=1;d['layers'].add(layer)
            if s['type']=='SKIRT':brim_paths.append(s)
    for d in types.values():
        d['layer_ranges_zero_based']=ranges(d.pop('layers'))
        d['path_length_mm']=round(d['path_length_mm'],3);d['volume_mm3']=round(d['volume_mm3'],3)
    absent=sorted(set(range(reported_count))-set(model_layers))
    internal=sorted(set(range(max(model_layers)+1))-set(model_layers))
    return {'reported_layer_count':reported_count,'actual_model_layer_count':len(model_layers),'model_layer_ranges_zero_based':ranges(model_layers),'reported_layers_without_model_paths':absent,'internal_missing_model_layers':internal,'all_model_layers_continuous':not internal,'swept_extrusion_bounds_including_brim_mm':bounds,'each_part_fits_bed_with_brim':bounds[0][0]>=0 and bounds[1][0]>=0 and bounds[0][1]<=220 and bounds[1][1]<=220 and bounds[2][1]<=250,'path_types':dict(types),'support_path_present':any(k.startswith('SUPPORT') for k in types)}


def svg(name,layers,selected):
    ncol=3;panel=310
    height=math.ceil(len(selected)/ncol)*panel
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" width="930" height="{height}" viewBox="0 0 930 {height}"><rect width="100%" height="100%" fill="#f7f9fc"/>']
    allpts=[p for segs in layers.values() for s in segs for p in (s['a'],s['b'])]
    lo=[min(p[i] for p in allpts)-2 for i in (0,1)];hi=[max(p[i] for p in allpts)+2 for i in (0,1)]
    scale=min(280/(hi[0]-lo[0]),245/(hi[1]-lo[1]))
    for idx,layer in enumerate(selected):
        segs=layers[layer]
        ox=(idx%ncol)*panel+15;oy=(idx//ncol)*panel+42
        result.append(f'<text x="{ox}" y="{oy-18}" font-family="sans-serif" font-size="14">{html.escape(name)} layer {layer}, Z={segs[0]["z"]:.1f} mm</text>')
        result.append(f'<rect x="{ox}" y="{oy}" width="280" height="245" fill="white" stroke="#d5dce5"/>')
        for s in segs:
            color='#dc2626' if s.get('unsupported_sample_fraction',0)>.8 else COLORS.get(s['type'],'#252d3a')
            (x1,y1),(x2,y2)=s['a'],s['b']
            x1=ox+(x1-lo[0])*scale;y1=oy+245-(y1-lo[1])*scale
            x2=ox+(x2-lo[0])*scale;y2=oy+245-(y2-lo[1])*scale
            result.append(f'<path d="M{x1:.3f},{y1:.3f} L{x2:.3f},{y2:.3f}" fill="none" stroke="{color}" stroke-width="{max(.3,s["width"]*scale):.3f}"/>')
        result.append(f'<text x="{ox}" y="{oy+262}" font-family="sans-serif" font-size="10">orange outer; blue inner; gray brim; red overlap concern</text>')
    result.append('</svg>')
    (OUT/(name+'_paths.svg')).write_text('\n'.join(result),encoding='utf-8')


def main():
    global OUT, SOURCE
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--source-dir',type=Path,default=PROTOTYPE/'improved')
    parser.add_argument('--settings',type=Path,default=PROTOTYPE/'reports/printing/settings.json')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    OUT=args.out.resolve()
    SOURCE=args.source_dir.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    args.engine=args.engine.resolve()
    defs=args.engine.parent/'share/cura/resources/definitions'
    settings=json.loads(args.settings.read_text())
    if (settings['machine_width'],settings['machine_depth'],settings['machine_height'],settings['layer_height'],settings['material_diameter']) != (220,220,250,.2,1.75):
        parser.error('Analyzer is calibrated for the supplied 220x220x250, 0.2 mm layer, 1.75 mm filament trial only')
    (OUT/'settings.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
    version=subprocess.run([str(args.engine),'help'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    engine_match=re.search(r'Cura(?:_Steam)?Engine version[^\r\n]*',version.stdout+'\n'+version.stderr)
    summary={'engine':engine_match.group(0) if engine_match else 'CuraEngine (see engine executable hash)','engine_sha256':hashlib.sha256(args.engine.read_bytes()).hexdigest(),'definition_sha256':{name:hashlib.sha256((defs/name).read_bytes()).hexdigest() for name in ('fdmprinter.def.json','fdmextruder.def.json')},'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'purpose':'Geometric trial only; no physical-printer or flight validation','settings_file':'settings.json','one_part_per_slice':True,'parts':{},'overlap_screen':{'method':'sampled toolpath bead overlap with preceding layer, step <=0.4 mm; 0.08 mm allowance','limitations':'Not a proof of successful bridging or strength; low fractions can still hide local defects. SVG red means >80% of segment samples lack prior-layer bead overlap.'},'gcode_retained':False}
    for name in PARTS:
        path=SOURCE/(name+'.stl')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        outg=OUT/(name+'_temporary.gcode')
        cmd=[str(args.engine),'slice','-j',str(defs/'fdmprinter.def.json')]
        for k,v in settings.items():cmd+=['-s',f'{k}={str(v).lower() if isinstance(v,bool) else v}']
        cmd+=['-e0','-j',str(defs/'fdmextruder.def.json')]
        for k,v in settings.items():cmd+=['-s',f'{k}={str(v).lower() if isinstance(v,bool) else v}']
        cmd+=['-l',str(path),'-o',str(outg)]
        process=subprocess.run(cmd,cwd=OUT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        log=(process.stdout+'\n'+process.stderr).replace(str(SOURCE),'<source>').replace(str(OUT),'<output>').replace(str(args.engine.parent),'<Cura-install>')
        (OUT/(name+'.log')).write_text(log,encoding='utf-8')
        if process.returncode:
            raise RuntimeError(f'{name}: Cura exit {process.returncode}. See {name}.log')
        layers,count=parse_gcode(outg)
        geo=geometry(stl(path))
        met=metrics(layers,count)
        print(name,'sliced',count,'layers; screening overlap',flush=True)
        screen=support_screen(layers)
        selected={'nose_cone':[0,1,2,135,140,400,count-1],'fin':[0,1,2,3,4,15,40,60,68,245,270,273,350,count-1],'fit_ring':[0,1,2,45,count-1],'mount_gauge':list(range(min(8,count)))+[count-2,count-1]}[name]
        selected=sorted(set(i for i in selected if i in layers))
        svg(name,layers,selected)
        opening=None
        if name in ('nose_cone','fit_ring'):
            last=max(layers)
            model=[s for s in layers[last] if s['type'] in MODEL_TYPES]
            opening=2*min(math.hypot(p[0]-110,p[1]-110)-s['width']/2 for s in model for p in (s['a'],s['b']))
        summary['parts'][name]={'source_stl_relative_path':'improved/'+path.name,'source_sha256':digest,'source_unchanged_during_run':digest==hashlib.sha256(path.read_bytes()).hexdigest(),'geometry':geo,'slice':met,'last_layer_bore_diameter_from_bead_edges_mm':opening,'layer_overlap_screen':screen,'selected_path_svg':name+'_paths.svg'}
        (OUT/'measurements.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        outg.unlink()
        print(name,'complete; concerning layers',[(s['layer_zero_based'],s['no_prior_overlap_fraction']) for s in screen if s['no_prior_overlap_fraction']>.05][:15],flush=True)
    print('Saved measurements.json and four path SVGs. Temporary G-code removed.',flush=True)


if __name__=='__main__':main()
