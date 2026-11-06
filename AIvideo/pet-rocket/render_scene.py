"""Render the frozen PET v2 meshes and a trajectory-driven ascent in Blender."""

import argparse
import csv
import json
import math
from pathlib import Path
import struct
import sys
import time

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from timeline import physical_time
PARAM = json.loads((ROOT / "source-data/parameters.json").read_text())
SIM = json.loads((ROOT / "simulation.json").read_text())
SETTINGS=json.loads((ROOT/"render-settings.json").read_text())
DATA = np.load(ROOT / "renders/trajectory.npz")["data"]
FPS = 24


def material(name, color, roughness=.3, metallic=0, transmission=0, ior=1.45):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    for key, value in {"Base Color":(*color,1), "Roughness":roughness, "Metallic":metallic, "Transmission Weight":transmission, "IOR":ior}.items():
        shader.inputs[key].default_value = value
    return result


def assign(obj, name, mat):
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def box(name, location, dimensions, mat, bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = assign(bpy.context.object, name, mat)
    obj.scale = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge", "BEVEL")
        modifier.width, modifier.segments = bevel, 3
    return obj


def cylinder(name, radius, depth, z, mat, x=0, y=0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth, location=(x,y,z))
    obj = assign(bpy.context.object, name, mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def lathe(name, profile, mat, segments=96):
    verts = [(r*math.cos(2*math.pi*j/segments),r*math.sin(2*math.pi*j/segments),z) for r,z in profile for j in range(segments)]
    faces = [(i*segments+j,i*segments+(j+1)%segments,(i+1)*segments+(j+1)%segments,(i+1)*segments+j) for i in range(len(profile)-1) for j in range(segments)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign(obj,name,mat)
    for polygon in mesh.polygons:
        polygon.use_smooth=True
    return obj


def stl(name, path, mat):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    verts, faces = [], []
    for index in range(count):
        numbers = struct.unpack_from("<12fH",data,84+50*index)
        offset = len(verts)
        verts.extend(tuple(numbers[3+3*j+k]*.001 for k in range(3)) for j in range(3))
        faces.append((offset,offset+1,offset+2))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    assign(obj,name,mat)
    return obj


def aim(camera, target):
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat("-Z","Y").to_euler()


def area(name, location, target, watts, size, color):
    light=bpy.data.lights.new(name,"AREA")
    light.energy,light.shape,light.size,light.color=watts,"DISK",size,color
    obj=bpy.data.objects.new(name,light)
    bpy.context.collection.objects.link(obj)
    obj.location=location
    aim(obj,target)


def sample(t):
    return np.array([np.interp(t,DATA[:,0],DATA[:,i]) for i in range(DATA.shape[1])])


def launch_time(film_t):
    return physical_time(film_t,SIM["nominal"]["apogee_time_s"])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--film",choices=["design","launch"],required=True)
    parser.add_argument("--preview",type=int)
    parser.add_argument("--samples",type=int,default=24)
    parser.add_argument("--start",type=int,default=1)
    parser.add_argument("--end",type=int)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.file_preview_type="NONE"
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC"
    scene.render.engine="CYCLES"
    scene.cycles.samples=args.samples
    scene.cycles.use_denoising=True
    scene.cycles.max_bounces=7
    scene.cycles.transmission_bounces=6
    preferences=bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type="OPTIX"
    preferences.get_devices()
    for device in preferences.devices: device.use=device.type=="OPTIX"
    scene.cycles.device="GPU"
    scene.render.resolution_x,scene.render.resolution_y=1280,720
    scene.render.resolution_percentage=100
    scene.render.fps=FPS
    scene.render.image_settings.file_format="PNG"
    scene.render.film_transparent=False
    scene.view_settings.view_transform="AgX"
    scene.view_settings.exposure=-2.0
    scene.world=bpy.data.worlds.new("Environment")
    scene.world.use_nodes=True
    nodes=scene.world.node_tree.nodes
    sky=nodes.new("ShaderNodeTexSky")
    sky.sky_type="MULTIPLE_SCATTERING"
    sky.sun_elevation=math.radians(28)
    sky.sun_rotation=math.radians(140)
    scene.world.node_tree.links.new(sky.outputs["Color"],nodes["Background"].inputs["Color"])
    nodes["Background"].inputs["Strength"].default_value=.35 if args.film=="design" else .5
    if args.film=="design":
        for link in list(scene.world.node_tree.links):
            scene.world.node_tree.links.remove(link)
        nodes["Background"].inputs["Color"].default_value=(.025,.035,.05,1)
        nodes["Background"].inputs["Strength"].default_value=.3
        scene.view_settings.exposure=0
    white=material("Ivory printed shell",(.75,.78,.73),.28)
    finmat=material("Graphite printed fins",(.035,.10,.12),.30)
    pet=material("Unmeasured PET envelope",(.89,.98,.97),.07,transmission=1,ior=1.575)
    water=material("Water",(.83,.96,.99),.035,transmission=1,ior=1.333)
    metal=material("Brushed aluminium",(.4,.46,.5),.23,.85)
    rubber=material("Dark fixture",(.025,.03,.035),.65)
    orange=material("Assumed nozzle adapter",(.82,.28,.035),.3)
    ground=material("Concrete",(.35,.37,.35),.85)
    n=ground.node_tree.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value=130
    bump=ground.node_tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value=.3
    bump.inputs["Distance"].default_value=.001
    ground.node_tree.links.new(n.outputs["Fac"],bump.inputs["Height"])
    ground.node_tree.links.new(bump.outputs["Normal"],ground.node_tree.nodes.get("Principled BSDF").inputs["Normal"])
    root=bpy.data.objects.new("Frozen v2 assembly",None)
    scene.collection.objects.link(root)
    nose=stl("Exact source nose STL",ROOT/"assets/nose_cone.stl",white)
    nose.parent=root
    nose.location.z=.262
    fin=stl("Exact source fin STL 1",ROOT/"assets/fin_assembly.stl",finmat)
    fin.parent=root
    fins=[fin]
    for index in (1,2):
        obj=fin.copy()
        obj.data=fin.data
        scene.collection.objects.link(obj)
        obj.name=f"Exact source fin STL {index+1}"
        fins.append(obj)
    for i,obj in enumerate(fins):
        obj.parent=root
        obj.location.z=.1
        obj.rotation_euler.z=2*math.pi*i/3
    bottle_profile=[(.015,0),(.015,.035),(.055,.100),(.055,.280)]
    bottle_profile += [(.055*math.sqrt(max(0,1-(i/20)**2)),.280+.035*i/20) for i in range(1,21)]
    bottle=lathe("Assumed bottle envelope",bottle_profile,pet)
    bottle.parent=root
    solid=bottle.modifiers.new("Assumed PET wall thickness","SOLIDIFY")
    solid.thickness,solid.offset=.00035,-1
    nozzle=lathe("Assumed 9mm insert",[(.0045,0),(.013,0),(.014,.008),(.0045,.008),(.0045,0)],orange)
    nozzle.parent=root
    # Internal liquid volume is integrated in SI units inside the assumed envelope.
    zgrid=np.linspace(.008,.280,700)
    rgrid=np.interp(zgrid,[0,.035,.1,.280],[.01465,.01465,.05465,.05465])
    volumes=np.r_[0,np.cumsum(.5*(rgrid[1:]**2+rgrid[:-1]**2)*math.pi*np.diff(zgrid))]
    liquid=cylinder("Remaining water",.04,.02,.02,water)
    liquid.parent=root
    # The liquid lathe is rebuilt from the physical remaining water volume; no liquid persists after depletion.
    bpy.data.objects.remove(liquid,do_unlink=True)
    liquid_mesh=bpy.data.meshes.new("Liquid surface")
    liquid=bpy.data.objects.new("Remaining water",liquid_mesh)
    scene.collection.objects.link(liquid)
    liquid.parent=root
    liquid.data.materials.append(water)
    def update_water(volume):
        if volume<1e-8:
            liquid.hide_render=True
            return
        liquid.hide_render=False
        level=float(np.interp(volume,volumes,zgrid))
        levels=np.linspace(.008,level,24)
        radii=np.interp(levels,zgrid,rgrid)
        profile=[(0,.008)]+list(zip(radii,levels))+[(0,level)]
        segments=64
        verts=[(r*math.cos(2*math.pi*j/segments),r*math.sin(2*math.pi*j/segments),z) for r,z in profile for j in range(segments)]
        faces=[(i*segments+j,i*segments+(j+1)%segments,(i+1)*segments+(j+1)%segments,(i+1)*segments+j) for i in range(len(profile)-1) for j in range(segments)]
        liquid_mesh.clear_geometry()
        liquid_mesh.from_pydata(verts,[],faces)
        liquid_mesh.update()
    floor=box("Ground slab",(0,0,-.025),(20000,20000,.05),ground,.0)
    if args.film=="design":
        box("Inspection bench",(0,0,.76),(1.4,.8,.08),rubber,.008)
        cylinder("Presentation pad",.18,.025,.8125,metal)
        base=.825
        area("Large softbox",(.6,-.4,1.6),(0,0,1),95,.6,(.83,.93,1))
        area("Rim softbox",(-.4,.3,1.4),(0,0,1),65,.45,(1,.86,.67))
        for x in (-.55,.55):
            box("Bench leg",(x,.25,.36),(.035,.04,.72),metal)
    else:
        base=.18
        box("Concept launch base",(0,0,.04),(.45,.36,.08),metal,.01)
        guide_length=SIM["scenario"]["guide_length_m"]
        cylinder("Concept guide",.005,guide_length,base+guide_length/2,metal,x=-.15)
        lathe("Concept release support",[(.0045,.08),(.022,.08),(.018,base),(.0045,base),(.0045,.08)],metal)
        for z in (.18,.75): box("Guide support",(-.20,0,z),(.1,.03,.025),metal)
        grass=material("Dry grass",(.13,.20,.055),.94)
        coords=grass.node_tree.nodes.new("ShaderNodeTexCoord")
        noise=grass.node_tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value=7
        ramp=grass.node_tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color=(.025,.055,.009,1)
        ramp.color_ramp.elements[1].color=(.15,.21,.055,1)
        grass.node_tree.links.new(coords.outputs["Object"],noise.inputs["Vector"])
        grass.node_tree.links.new(noise.outputs["Fac"],ramp.inputs[0])
        grass.node_tree.links.new(ramp.outputs["Color"],grass.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])
        floor.data.materials.clear()
        floor.data.materials.append(grass)
        rng=np.random.default_rng(41)
        vertices=[]; faces=[]
        for i in range(45000):
            x,y=rng.uniform(-6,6,2)
            if abs(x)<.6 and abs(y)<.6: continue
            height=rng.uniform(.035,.12); width=.005
            a=len(vertices)
            vertices.extend([(x-width,y,0),(x+width,y,0),(x+rng.uniform(-.025,.025),y,height)])
            faces.append((a,a+1,a+2))
        mesh=bpy.data.meshes.new("Field blades")
        mesh.from_pydata(vertices,[],faces)
        obj=bpy.data.objects.new("Field blades",mesh)
        scene.collection.objects.link(obj)
        assign(obj,"Field blades",grass)
        for i in range(28):
            angle=i*math.tau/28
            x,y=65*math.cos(angle),65*math.sin(angle)
            cylinder("Distant tree trunk",.18,5,2.5,ground,x=x,y=y)
            for cluster in range(14):
                dx,dy,dz=rng.normal(0,1.0,3)
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=rng.uniform(.7,1.4),location=(x+dx,y+dy,4.5+abs(dz)))
                leaf=assign(bpy.context.object,"Distant foliage cluster",grass)
                for polygon in leaf.data.polygons: polygon.use_smooth=True
        # Finite-size ballistic water parcels. Their total represented volume equals the expelled water.
        count=3000
        emission=np.interp(np.linspace(.00001,.65999,count),SIM["nominal"]["initial_water_mass_kg"]-DATA[:,4],DATA[:,0])
        emission=np.clip(emission,0,SIM["nominal"]["phase_ends"]["water"])
        emission_z=np.interp(emission,DATA[:,0],DATA[:,1])+base
        emission_v=np.interp(emission,DATA[:,0],DATA[:,2])-np.interp(emission,DATA[:,0],DATA[:,11])
        rng=np.random.default_rng(12)
        lateral=rng.normal(0,.12,(count,2))
        radius=(3*SIM["nominal"]["initial_water_mass_kg"]/(4*math.pi*1000*count))**(1/3)
        drop_mesh=bpy.data.meshes.new("Water parcel points")
        drop_mesh.from_pydata([(0,0,-10)]*count,[],[])
        drops=bpy.data.objects.new("Ballistic water parcels",drop_mesh)
        scene.collection.objects.link(drops)
        attr=drop_mesh.attributes.new("parcel_radius","FLOAT","POINT")
        group=bpy.data.node_groups.new("Water parcel instancing","GeometryNodeTree")
        group.interface.new_socket(name="Geometry",in_out="INPUT",socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry",in_out="OUTPUT",socket_type="NodeSocketGeometry")
        ns,links=group.nodes,group.links
        inp=ns.new("NodeGroupInput"); out=ns.new("NodeGroupOutput")
        points=ns.new("GeometryNodeMeshToPoints")
        sphere=ns.new("GeometryNodeMeshIcoSphere"); sphere.inputs["Radius"].default_value=1; sphere.inputs[" subdivisions" if " subdivisions" in sphere.inputs else "Subdivisions"].default_value=1
        sm=ns.new("GeometryNodeSetMaterial"); sm.inputs["Material"].default_value=water
        inst=ns.new("GeometryNodeInstanceOnPoints")
        named=ns.new("GeometryNodeInputNamedAttribute"); named.data_type="FLOAT"; named.inputs["Name"].default_value="parcel_radius"
        links.new(inp.outputs["Geometry"],points.inputs["Mesh"])
        links.new(sphere.outputs["Mesh"],sm.inputs["Geometry"])
        links.new(sm.outputs["Geometry"],inst.inputs["Instance"])
        links.new(points.outputs["Points"],inst.inputs["Points"])
        links.new(named.outputs["Attribute"],inst.inputs["Scale"])
        links.new(inst.outputs["Instances"],out.inputs["Geometry"])
        drops.modifiers.new("Represented water parcels","NODES").node_group=group
    camera_data=bpy.data.cameras.new("Cinematography")
    camera=bpy.data.objects.new("Cinematography",camera_data)
    scene.collection.objects.link(camera)
    scene.camera=camera
    camera_data.lens=52
    camera_data.clip_start=.005
    camera_data.clip_end=20000
    focus=bpy.data.objects.new("Assembly focus",None)
    scene.collection.objects.link(focus)
    focus.parent=root
    focus.location=(0,0,.18)
    camera_data.dof.use_dof=True
    camera_data.dof.focus_object=focus
    camera_data.dof.aperture_fstop=8 if args.film=="design" else 5.6
    frames=384 if args.film=="design" else 336
    output=ROOT/"renders"/SETTINGS[args.film+"_frames"]
    output.mkdir(parents=True,exist_ok=True)
    frame_states={}
    @persistent
    def animate(_scene,*_):
        film_t=(_scene.frame_current-1)/FPS
        root.location=(0,0,base)
        nose.location=(0,0,.262)
        for i,obj in enumerate(fins): obj.location=(0,0,.1)
        if args.film=="design":
            if film_t<4:
                angle=-math.pi/2+.25*film_t
                camera.location=(1.15*math.cos(angle),1.15*math.sin(angle),base+.35)
                target=(0,0,base+.18)
            elif film_t<8:
                amount=min(1,(film_t-4)/.8)
                nose.location.z+=amount*.065
                for i,obj in enumerate(fins):
                    angle=2*math.pi*i/3
                    obj.location.x=amount*.04*math.cos(angle)
                    obj.location.y=amount*.04*math.sin(angle)
                camera.location=(.65,-1.1,base+.42); target=(0,0,base+.19)
            elif film_t<12:
                camera.location=(.32,-.30,base+.20); target=(.064,0,base+.15)
                camera_data.lens=62
            else:
                camera_data.lens=52
                camera.location=(.55,-.95,base+.47); target=(0,0,base+.23)
            update_water(SIM["scenario"]["volume_m3"]*SIM["scenario"]["fill_fraction"])
        else:
            t,scale=launch_time(film_t)
            row=sample(t)
            root.location.z=base+row[1]
            distance=1.1 if film_t<1.5 else 1.3
            camera.location=(distance*.55,-distance,root.location.z+.28)
            target=(0,0,root.location.z+.16)
            update_water(row[4]/1000)
            frame_states[_scene.frame_current]=[_scene.frame_current,film_t,t,float(root.location.z),float(row[4]),float(row[6]),float(row[8]),bool(not liquid.hide_render)]
            age=t-emission
            active=(age>=0)&(age<.42)
            z=emission_z+emission_v*age-0.5*9.80665*age**2
            active &= z>.006
            positions=np.column_stack([lateral[:,0]*np.maximum(age,0),lateral[:,1]*np.maximum(age,0),z])
            active &= ~((np.abs(positions[:,0])<.225)&(np.abs(positions[:,1])<.18)&(positions[:,2]<=.08))
            positions[~active]=[0,0,-10]
            drop_mesh.vertices.foreach_set("co",positions.ravel())
            attr.data.foreach_set("value",np.where(active,radius,0))
            drop_mesh.update()
        aim(camera,target)
    bpy.app.handlers.frame_change_pre.append(animate)
    scene.frame_start=args.start
    scene.frame_end=args.end or frames
    scene.render.filepath="//"+output.name+"/frame_"
    scene.frame_set(args.preview or 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"renders"/(args.film+".blend")))
    scene.render.filepath=str(output/"frame_")
    started=time.monotonic()
    if args.preview:
        scene.render.filepath=str(ROOT/"renders"/(args.film+f"-preview-{args.preview:04d}.png"))
        bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)
    report={"film":args.film,"frames_requested":[scene.frame_start,scene.frame_end],"fps":FPS,"width":1280,"height":720,"samples":args.samples,"engine":"Cycles/OptiX","seconds":time.monotonic()-started,"geometry":"Frozen original v2 STL meshes, scaled from mm to m; no generative mesh changes.","bottle_and_launcher":"Unmeasured envelope and illustrative equipment.","water_visualization":"Remaining liquid volume from ODE; ballistic finite-size parcels, not CFD. Internal bottle base/air-space geometry is not measured."}
    (ROOT/"renders"/(args.film+"-render.json")).write_text(json.dumps(report,indent=2)+"\n")
    if frame_states:
        with (ROOT/"renders/launch-render-state.csv").open("w",newline="",encoding="utf-8") as target:
            writer=csv.writer(target)
            writer.writerow(["frame","film_time_s","simulation_time_s","nozzle_world_z_m","water_mass_kg","pressure_abs_pa","predicted_thrust_n","liquid_mesh_visible"])
            writer.writerows(frame_states[key] for key in sorted(frame_states))


if __name__=="__main__": main()
