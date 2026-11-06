"""Photo-lit PET v2 scenes with frozen CAD, clear liquids and ground-based cameras."""

import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector
import numpy as np

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
sys.path.insert(0,str(PARENT))
import render_scene as base
sys.path.insert(0,str(ROOT))
import appearance

CONFIG=json.loads((ROOT/"settings.json").read_text())
SIM=json.loads((PARENT/"simulation.json").read_text())
DATA=np.load(PARENT/"renders/trajectory.npz")["data"]
FPS=CONFIG["fps"]


def flight_time(t):
    if t<1.5:return 0.,0.
    if t<5.5:return (t-1.5)*.2,.2
    if t<11.:return .8+(t-5.5)*(DATA[-1,0]-.8)/5.5,(DATA[-1,0]-.8)/5.5
    return DATA[-1,0],0.


def state(t):
    return np.array([np.interp(t,DATA[:,0],DATA[:,i]) for i in range(DATA.shape[1])])


def photo_world(film):
    return appearance.photo_world(film, ROOT/"cache")


def surface_detail(mat, layered=False):
    return appearance.surface_detail(mat, layered)


def smooth_source(mesh):
    # Shared-coordinate normal averaging changes shading, never source vertex positions.
    vertices=np.array([v.co[:] for v in mesh.vertices])
    normals={}
    for p in mesh.polygons:
        weight=p.area
        for index in p.vertices:
            key=tuple(np.round(vertices[index],8))
            normals.setdefault(key,[]).append((Vector(p.normal),weight))
    result=[]
    for p in mesh.polygons:
        p.use_smooth=True
        for loop in p.loop_indices:
            index=mesh.loops[loop].vertex_index;key=tuple(np.round(vertices[index],8))
            normal=sum((n*w for n,w in normals[key] if n.dot(p.normal)>.65),Vector())
            result.append(normal.normalized()[:])
    mesh.normals_split_custom_set(result)


def asphalt():
    return appearance.asphalt(ROOT/"cache")


def bottle_geometry(pet,root):
    profile=[(.0148,0),(.0148,.034)]
    for z in np.linspace(.035,.1,32):
        blend=(z-.035)/.065
        r=.0148+(.055-.0148)*(.5-.5*math.cos(blend*math.pi))
        profile.append((r,float(z)))
    for z in np.linspace(.101,.28,80):
        r=.0549-.0014*math.sin((z-.1)/.18*math.pi)**2
        r-=.00018*math.sin((z-.1)*850)**8
        profile.append((r,float(z)))
    profile += [(.055*math.sqrt(max(0,1-(i/32)**2)),.280+.035*i/32) for i in range(1,33)]
    bottle=base.lathe("Detailed assumed PET envelope",profile,pet,192);bottle.parent=root
    solid=bottle.modifiers.new("Assumed 0.35mm PET wall","SOLIDIFY")
    solid.thickness=.00035;solid.offset=-1
    for z in (.009,.013,.017,.021,.025):
        bpy.ops.mesh.primitive_torus_add(major_segments=96,minor_segments=8,location=(0,0,z),major_radius=.0148,minor_radius=.0004)
        obj=base.assign(bpy.context.object,"Illustrative molded neck ring",pet);obj.parent=root
        for p in obj.data.polygons:p.use_smooth=True
    return profile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--film",choices=["design","launch"],required=True)
    parser.add_argument("--preview",type=int)
    parser.add_argument("--samples",type=int)
    parser.add_argument("--width",type=int)
    parser.add_argument("--start",type=int,default=1)
    parser.add_argument("--end",type=int)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.file_preview_type="NONE"
    scene=bpy.context.scene;scene.unit_settings.system="METRIC"
    scene.render.engine="CYCLES";scene.cycles.samples=args.samples or CONFIG["samples"]
    scene.cycles.use_denoising=True;scene.cycles.adaptive_threshold=.035
    scene.cycles.max_bounces=12;scene.cycles.transmission_bounces=10
    pref=bpy.context.preferences.addons["cycles"].preferences;pref.compute_device_type="OPTIX";pref.get_devices()
    for d in pref.devices:d.use=d.type=="OPTIX"
    scene.cycles.device="GPU";scene.cycles.seed=CONFIG["seed"]
    scene.render.resolution_x=args.width or CONFIG["width"]
    scene.render.resolution_y=round(scene.render.resolution_x*9/16)
    scene.render.resolution_percentage=100;scene.render.fps=FPS
    scene.render.image_settings.file_format="PNG"
    scene.view_settings.view_transform="AgX";scene.view_settings.exposure=.2
    photo_world(args.film)
    ivory=base.material("Unpainted ivory printed polymer",(.72,.72,.66),.3)
    graphite=base.material("Charcoal printed polymer",(.024,.035,.038),.34)
    surface_detail(ivory,True);surface_detail(graphite,True)
    pet=base.material("Clear thin PET",(.98,1,1),.04,transmission=1,ior=1.575);surface_detail(pet)
    water=base.material("Optically clear water",(1,1,1),.015,transmission=1,ior=1.333)
    steel=base.material("Brushed fixture steel",(.45,.48,.5),.28,.92)
    rubber=base.material("Matte black rubber",(.009,.012,.014),.7)
    root=bpy.data.objects.new("Frozen v2 assembly",None);scene.collection.objects.link(root)
    nose=base.stl("Exact source nose STL",PARENT/"assets/nose_cone.stl",ivory);nose.parent=root;nose.location.z=.262
    smooth_source(nose.data)
    fin=base.stl("Exact source fin STL 1",PARENT/"assets/fin_assembly.stl",graphite);fin.parent=root
    smooth_source(fin.data);fins=[fin]
    for i in (1,2):
        obj=fin.copy();obj.data=fin.data;scene.collection.objects.link(obj);obj.name=f"Exact source fin STL {i+1}";obj.parent=root;fins.append(obj)
    for i,obj in enumerate(fins):obj.location.z=.1;obj.rotation_euler.z=i*math.tau/3
    profile=bottle_geometry(pet,root)
    adapter=base.lathe("Assumed nozzle adapter",[(.0045,0),(.014,0),(.014,.006),(.0045,.006),(.0045,0)],rubber);adapter.parent=root
    zgrid=np.linspace(.003,.28,1000)
    inner=np.interp(zgrid,[z for r,z in profile],[r-.00036 for r,z in profile])
    volumes=np.r_[0,np.cumsum(.5*(inner[1:]**2+inner[:-1]**2)*math.pi*np.diff(zgrid))]
    liquid_mesh=bpy.data.meshes.new("Volume-driven water mesh")
    liquid=bpy.data.objects.new("Remaining water",liquid_mesh);scene.collection.objects.link(liquid);liquid.parent=root;liquid.data.materials.append(water)
    def update_water(volume):
        liquid.hide_render=bool(volume<1e-8)
        if liquid.hide_render:return
        level=float(np.interp(volume,volumes,zgrid));zs=np.linspace(.003,level,48)
        rs=np.interp(zs,zgrid,inner)-.00005
        rows=[(0,.003)]+list(zip(rs,zs))+[(0,level)]
        segments=128
        vs=[(r*math.cos(j*math.tau/segments),r*math.sin(j*math.tau/segments),z) for r,z in rows for j in range(segments)]
        fs=[(i*segments+j,i*segments+(j+1)%segments,(i+1)*segments+(j+1)%segments,(i+1)*segments+j) for i in range(len(rows)-1) for j in range(segments)]
        liquid_mesh.clear_geometry();liquid_mesh.from_pydata(vs,[],fs);liquid_mesh.update()
        for p in liquid_mesh.polygons:p.use_smooth=True
    if args.film=="design":
        height=.82
        base.box("Workbench top",(0,0,.78),(1.8,1.15,.08),steel,.008)
        mat=base.material("Cutting mat",(.025,.07,.061),.8)
        base.box("Cutting mat",(0,0,.821),(.7,.55,.002),mat,.002)
        pale=base.material("Mat grid ink",(.28,.4,.32),.8)
        for x in np.arange(-.34,.35,.02):base.box("Mat grid",(x,0,.8222),(.00025,.54,.0001),pale,0)
        for y in np.arange(-.26,.27,.02):base.box("Mat grid",(0,y,.8222),(.68,.00025,.0001),pale,0)
        base.box("Steel reference ruler",(.23,-.08,.824),(.027,.31,.001),steel,.0003)
        for i in range(61):
            base.box("Ruler tick",(.23-.009+(0 if i%10==0 else .003),-.23+i*.005,.8247),(.018 if i%10==0 else .012,.0002,.0001),rubber,0)
        base.cylinder("Illustrative nozzle rest",.018,.008,.827,rubber)
        height=.831
        base.area("Window fill",(-1,-.8,2.2),(0,0,1),25,1.1,(.88,.93,1))
    else:
        height=.18
        base.box("Photo-textured ground",(0,0,-.025),(20000,20000,.05),asphalt(),0)
        base.box("Illustrative launch base",(0,0,.038),(.42,.34,.076),steel,.004)
        for x in (-.18,.18):
            for y in (-.14,.14):
                bolt=base.cylinder("Base fastener",.007,.004,.078,steel,x,y)
                base.box("Fastener slot",(x,y,.0803),(.008,.0013,.0003),rubber,.0002)
        base.cylinder("Illustrative guide",.004,1.,.68,steel,x=-.12)
        base.lathe("Illustrative release collar",[(.0045,.076),(.019,.076),(.019,.18),(.0045,.18),(.0045,.076)],steel)
    camera_data=bpy.data.cameras.new("Grounded photographic camera")
    camera=bpy.data.objects.new("Grounded photographic camera",camera_data);scene.collection.objects.link(camera);scene.camera=camera
    camera_data.clip_start=.005;camera_data.clip_end=30000
    camera_data.dof.use_dof=True;camera_data.dof.aperture_fstop=8
    focus=bpy.data.objects.new("Focus point",None);scene.collection.objects.link(focus);camera_data.dof.focus_object=focus
    output=ROOT/"renders"/(args.film+"-frames");output.mkdir(parents=True,exist_ok=True)
    count=CONFIG[args.film+"_frames"]
    states={}
    # Water parcels are ballistic representations of the same discharged mass, not CFD.
    drops=None
    if args.film=="launch":
        amount=9000;mass=SIM["nominal"]["initial_water_mass_kg"]
        emission=np.interp(np.linspace(.00001,mass-.00001,amount),mass-DATA[:,4],DATA[:,0])
        emitted_z=np.interp(emission,DATA[:,0],DATA[:,1])+height
        emitted_v=np.interp(emission,DATA[:,0],DATA[:,2])-np.interp(emission,DATA[:,0],DATA[:,11])
        rng=np.random.default_rng(52);lateral=rng.normal(0,.18,(amount,2))
        radius=(3*mass/(4*math.pi*1000*amount))**(1/3)
        mesh=bpy.data.meshes.new("Discharged water points");mesh.from_pydata([(0,0,-10)]*amount,[],[])
        drops=bpy.data.objects.new("Discharged water",mesh);scene.collection.objects.link(drops)
        attr=mesh.attributes.new("parcel_radius","FLOAT","POINT")
        group=bpy.data.node_groups.new("Clear water parcel instances","GeometryNodeTree")
        group.interface.new_socket(name="Geometry",in_out="INPUT",socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry",in_out="OUTPUT",socket_type="NodeSocketGeometry")
        n=group.nodes;l=group.links;inp=n.new("NodeGroupInput");out=n.new("NodeGroupOutput")
        points=n.new("GeometryNodeMeshToPoints");sphere=n.new("GeometryNodeMeshIcoSphere");sphere.inputs["Radius"].default_value=1;sphere.inputs["Subdivisions"].default_value=2
        smooth=n.new("GeometryNodeSetShadeSmooth")
        material=n.new("GeometryNodeSetMaterial");material.inputs["Material"].default_value=water
        instance=n.new("GeometryNodeInstanceOnPoints");named=n.new("GeometryNodeInputNamedAttribute");named.data_type="FLOAT";named.inputs["Name"].default_value="parcel_radius"
        l.new(inp.outputs["Geometry"],points.inputs["Mesh"]);l.new(sphere.outputs["Mesh"],smooth.inputs["Geometry"]);l.new(smooth.outputs["Geometry"],material.inputs["Geometry"])
        l.new(material.outputs["Geometry"],instance.inputs["Instance"]);l.new(points.outputs["Points"],instance.inputs["Points"]);l.new(named.outputs["Attribute"],instance.inputs["Scale"]);l.new(instance.outputs["Instances"],out.inputs["Geometry"])
        drops.modifiers.new("Mass-representing water parcels","NODES").node_group=group
    def update(frame):
        t=(frame-1)/FPS;root.location=(0,0,height)
        nose.location=(0,0,.262)
        for obj in fins:obj.location=(0,0,.1)
        if args.film=="design":
            chapter=min(int(t//3),3);local=t%3
            if chapter==0:
                angle=-1.6+.10*local;camera.location=(1.15*math.cos(angle),1.15*math.sin(angle),height+.34);target=(0,0,height+.18);camera_data.lens=56
            elif chapter==1:
                a=min(local/.8,1);nose.location.z+=a*.045
                for i,obj in enumerate(fins):obj.location.x=.025*a*math.cos(i*math.tau/3);obj.location.y=.025*a*math.sin(i*math.tau/3)
                camera.location=(.65,-1.16,height+.32);target=(0,0,height+.19);camera_data.lens=56
            elif chapter==2:
                camera.location=(.23,-.24,height+.18+.003*local);target=(.055,0,height+.15);camera_data.lens=75
            else:
                camera.location=(.65,-1.05,height+.38);target=(0,0,height+.19);camera_data.lens=56
            update_water(.00066)
        else:
            physical,rate=flight_time(t);row=state(physical);root.location.z=height+row[1]
            if t<1.5:
                camera.location=(.58,-1.05,.41);target=(0,0,.36);camera_data.lens=54
            elif t<5.5:
                camera.location=(1.5,-4.2,.65);target=(0,0,root.location.z+.13);camera_data.lens=140
            else:
                camera.location=(4,-35,1.25);target=(0,0,root.location.z+.16);camera_data.lens=900
            update_water(row[4]/1000)
            age=physical-emission;positions=np.column_stack([lateral[:,0]*np.maximum(age,0),lateral[:,1]*np.maximum(age,0),emitted_z+emitted_v*age-.5*9.80665*age**2])
            active=(age>=0)&(age<.55)&(positions[:,2]>.008)
            active &= ~((abs(positions[:,0])<.21)&(abs(positions[:,1])<.17)&(positions[:,2]<.076))
            positions[~active]=[0,0,-10];mesh.vertices.foreach_set("co",positions.ravel());attr.data.foreach_set("value",np.where(active,radius,0));mesh.update()
            states[round(frame)]=[round(frame),t,physical,float(root.location.z),float(row[4]),float(row[6]),float(row[8] if t>=1.5 else 0),not liquid.hide_render,float(camera.location.z)]
        focus.location=target;base.aim(camera,target)
    def animate(scene,*unused):update(scene.frame_current+scene.frame_subframe)
    bpy.app.handlers.frame_change_pre.append(animate)
    scene.frame_start=args.start;scene.frame_end=args.end or count
    update(args.preview or 1)
    scene.frame_set(args.preview or 1)
    # Store relative asset paths so the scene can travel with the cache directory.
    for image in bpy.data.images:
        if image.source=="FILE":image.filepath="//../cache/"+Path(image.filepath).name
    scene.render.filepath="//"+output.name+"/frame_"
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"renders"/(args.film+".blend")))
    started=time.monotonic()
    if args.preview:
        scene.render.filepath=str(ROOT/"renders"/(args.film+f"-preview-{args.preview:04d}.png"));bpy.ops.render.render(write_still=True)
    else:
        scene.render.filepath=str(output/"frame_");bpy.ops.render.render(animation=True)
    if states:
        with (ROOT/"renders"/(args.film+"-state.csv")).open("w",newline="",encoding="utf-8") as file:
            writer=csv.writer(file);writer.writerow(["frame","film_time_s","simulation_time_s","nozzle_world_z_m","water_mass_kg","pressure_abs_pa","displayed_thrust_n","liquid_visible","camera_z_m"]);writer.writerows(states[k] for k in sorted(states))
    (ROOT/"renders"/(args.film+"-render.json")).write_text(json.dumps({"film":args.film,"width":scene.render.resolution_x,"height":scene.render.resolution_y,"samples":scene.cycles.samples,"frames":[scene.frame_start,scene.frame_end],"seconds":time.monotonic()-started,"method":"Cycles OptiX; exact source STL; photographic HDRI; original physics; illustrative bottle detail and fixture"},indent=2)+"\n")


if __name__=="__main__":main()
