"""Decode both videos and verify CAD provenance and frame-by-frame physics synchronization."""

import csv
import hashlib
import json
from pathlib import Path
import wave

import av
import numpy as np
from PIL import Image,ImageDraw

from timeline import FPS,DESIGN_FRAMES,LAUNCH_FRAMES,physical_time
from cache_inputs import signature

ROOT=Path(__file__).resolve().parent


def main():
    reports=[]
    for kind,count,name in [("design",DESIGN_FRAMES,"pet_rocket_design.mp4"),("launch",LAUNCH_FRAMES,"pet_rocket_launch_prediction.mp4")]:
        path=ROOT/"renders"/name
        selection=[0,count//8,count//4,3*count//8,count//2,5*count//8,3*count//4,count-1]
        sheet=Image.new("RGB",(1280,408),"#09131c")
        draw=ImageDraw.Draw(sheet)
        means=[]
        with av.open(str(path)) as container:
            stream=container.streams.video[0]
            assert (stream.width,stream.height)==(1280,720)
            assert float(stream.average_rate)==FPS
            assert len(container.streams.audio)==1
            metadata=dict(container.metadata)
            frames=0
            for index,frame in enumerate(container.decode(stream)):
                image=frame.to_image()
                means.append(float(np.asarray(image.resize((32,18))).mean()))
                if index in selection:
                    place=selection.index(index)
                    x,y=place%4*320,place//4*204
                    sheet.paste(image.resize((320,180)),(x,y))
                    draw.text((x+7,y+185),f"{index/FPS:.2f}s",fill="white")
                frames+=1
        assert frames==count and min(means)>3
        serialized=json.dumps(metadata).lower()
        assert not any(term in serialized for term in ("c:\\users\\","chatgpt","codex","utm_"))
        with wave.open(str(ROOT/"renders"/(kind+"-sound.wav"))) as source:
            samples=np.frombuffer(source.readframes(source.getnframes()),dtype="<i2").astype(float)/32768
            assert source.getnchannels()==2 and source.getframerate()==48000
            peak=float(np.max(np.abs(samples)));rms=float(np.sqrt(np.mean(samples*samples)))
            assert 0<peak<.99 and rms>0
        sheet.save(ROOT/"renders"/(kind+"-contact.jpg"),quality=94)
        reports.append({"file":"renders/"+name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,"width":1280,"height":720,"fps":FPS,"frames":frames,"seconds":frames/FPS,"full_decode":"passed","audio":{"channels":2,"rate_hz":48000,"sample_peak":peak,"rms":rms,"source":"Original synthetic cues and flow-driven sound, not measured acoustics"},"metadata":metadata})
    simulated=np.load(ROOT/"renders/trajectory.npz")["data"]
    apex=json.loads((ROOT/"simulation.json").read_text())["nominal"]["apogee_time_s"]
    with (ROOT/"launch-frame-data.csv").open(encoding="utf-8") as source:ui=list(csv.DictReader(source))
    with (ROOT/"renders/launch-render-state.csv").open(encoding="utf-8") as source:render=list(csv.DictReader(source))
    by_frame={int(row["frame"]):row for row in render}
    assert len(ui)==LAUNCH_FRAMES and len(by_frame)==LAUNCH_FRAMES
    errors={"time_s":0.,"altitude_m":0.,"water_mass_kg":0.,"pressure_pa":0.,"displayed_thrust_n":0.}
    for row in ui:
        frame=int(row["frame"]); rendered=by_frame[frame]
        film_t=(frame-1)/FPS
        t,scale=physical_time(film_t,apex)
        expected=np.array([np.interp(t,simulated[:,0],simulated[:,i]) for i in range(simulated.shape[1])])
        errors["time_s"]=max(errors["time_s"],abs(float(row["simulation_time_s"])-t),abs(float(rendered["simulation_time_s"])-t))
        errors["altitude_m"]=max(errors["altitude_m"],abs(float(row["altitude_m"])-expected[1]),abs(float(rendered["nozzle_world_z_m"])-.18-expected[1]))
        errors["water_mass_kg"]=max(errors["water_mass_kg"],abs(float(row["water_mass_kg"])-float(rendered["water_mass_kg"])),abs(float(row["water_mass_kg"])-expected[4]))
        errors["pressure_pa"]=max(errors["pressure_pa"],abs(float(row["pressure_abs_pa"])-float(rendered["pressure_abs_pa"])))
        errors["displayed_thrust_n"]=max(errors["displayed_thrust_n"],abs(float(row["displayed_thrust_n"])-(expected[8] if film_t>=1.5 else 0)))
        assert (rendered["liquid_mesh_visible"]=="True")==bool(expected[4]/1000>=1e-8)
    assert errors["time_s"]<1e-10 and errors["altitude_m"]<5e-6
    assert errors["water_mass_kg"]<1e-10 and errors["pressure_pa"]<1e-6 and errors["displayed_thrust_n"]<1e-10
    provenance=json.loads((ROOT/"provenance.json").read_text())
    for item in provenance["files"]:
        assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest()==item["sha256"]
    geometry=json.loads((ROOT/"geometry-audit.json").read_text())
    assert geometry["checks"]=="passed"
    result={"videos":reports,"input_signature":signature(),"frame_sync_max_errors":errors,"source_hashes":"passed","geometry_audit":"passed","visual_review":"Timed contact sheets generated; record separate visual review.","full_real_time_playback_review":False,"audio_listening_review":False,"limitations":"Conditional still-air vertical ascent and assumed equipment/inputs. No stability, structural or recovery validation; water parcels are not CFD."}
    (ROOT/"verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"videos":[{key:r[key] for key in ("file","frames","seconds")} for r in reports],"frame_sync_max_errors":errors},indent=2))


if __name__=="__main__":main()
