"""Decode the refined films and check their actual render states against the ODE."""

import csv
import hashlib
import json
from pathlib import Path
import wave

import av
import numpy as np
from PIL import Image,ImageDraw

from render import signature

ROOT=Path(__file__).resolve().parent
DATA=np.load(ROOT.parent/"renders/trajectory.npz")["data"]


def main():
    geometry=json.loads((ROOT/"geometry-audit.json").read_text())
    assert geometry["checks"]=="passed"
    assert all((s["width"],s["height"])==(1920,1080) for s in geometry["scenes"])
    reports=[]
    for kind,count,name in [("design",384,"pet_rocket_design.mp4"),("launch",288,"pet_rocket_launch_prediction.mp4"),("design",384,"pet_rocket_design_cinematic.mp4"),("launch",288,"pet_rocket_launch_cinematic.mp4")]:
        path=ROOT/"renders"/name
        selected=[0,count//8,count//4,3*count//8,count//2,5*count//8,3*count//4,count-1]
        sheet=Image.new("RGB",(1920,588),"#151819");draw=ImageDraw.Draw(sheet)
        with av.open(str(path)) as source:
            stream=source.streams.video[0]
            assert (stream.width,stream.height)==(1920,1080) and float(stream.average_rate)==24
            assert len(source.streams.audio)==1
            metadata={"container":dict(source.metadata),"streams":[dict(s.metadata) for s in source.streams]}
            total=0
            for i,frame in enumerate(source.decode(stream)):
                image=frame.to_image()
                assert float(np.asarray(image.resize((32,18))).mean())>3
                if i in selected:
                    slot=selected.index(i);x=slot%4*480;y=slot//4*294
                    sheet.paste(image.resize((480,270)),(x,y))
                    draw.text((x+8,y+277),f"{i/24:.2f}s",fill="white")
                total+=1
        assert total==count
        with wave.open(str(ROOT/"renders"/(kind+"-sound.wav"))) as sound:
            assert sound.getframerate()==48000 and sound.getnchannels()==2
            seconds=sound.getnframes()/sound.getframerate()
            samples=np.frombuffer(sound.readframes(sound.getnframes()),dtype="<i2").astype(float)/32768
            peak=float(np.max(abs(samples)));rms=float(np.sqrt(np.mean(samples*samples)))
            assert abs(seconds-count/24)<1e-6 and 0<peak<.99
        sheet.save(ROOT/"renders"/(kind+("-cinematic" if "cinematic" in name else "")+"-contact.jpg"),quality=95)
        reports.append({"file":"renders/"+name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,"width":1920,"height":1080,"fps":24,"frames":total,"seconds":count/24,"decode":"passed","metadata":metadata,"audio":{"seconds":seconds,"sample_peak":peak,"rms":rms,"listening_review":False}})
    with (ROOT/"renders/launch-state.csv").open(encoding="utf-8") as source:rows=list(csv.DictReader(source))
    assert len(rows)==288 and {int(r["frame"]) for r in rows}==set(range(1,289))
    error={"time_s":0.,"altitude_m":0.,"water_mass_kg":0.,"pressure_pa":0.,"displayed_thrust_n":0.}
    for row in rows:
        frame=int(row["frame"]);film=(frame-1)/24
        expected_t=0 if film<1.5 else (film-1.5)*.2 if film<5.5 else .8+(film-5.5)*(DATA[-1,0]-.8)/5.5 if film<11 else DATA[-1,0]
        t=float(row["simulation_time_s"])
        expected=[np.interp(t,DATA[:,0],DATA[:,i]) for i in range(DATA.shape[1])]
        error["time_s"]=max(error["time_s"],abs(t-expected_t))
        error["altitude_m"]=max(error["altitude_m"],abs(float(row["nozzle_world_z_m"])-.18-expected[1]))
        error["water_mass_kg"]=max(error["water_mass_kg"],abs(float(row["water_mass_kg"])-expected[4]))
        error["pressure_pa"]=max(error["pressure_pa"],abs(float(row["pressure_abs_pa"])-expected[6]))
        error["displayed_thrust_n"]=max(error["displayed_thrust_n"],abs(float(row["displayed_thrust_n"])-(expected[8] if film>=1.5 else 0)))
        assert (row["liquid_visible"]=="True")==bool(expected[4]/1000>=1e-8)
        assert abs(float(row["camera_z_m"])-(.41 if film<1.5 else .65 if film<5.5 else 1.25))<1e-6
    assert error["time_s"]<1e-10 and error["altitude_m"]<5e-6
    assert error["water_mass_kg"]<1e-10 and error["pressure_pa"]<1e-6 and error["displayed_thrust_n"]<1e-10
    manifest=json.loads((ROOT/"asset-manifest.json").read_text())
    for item in manifest["files"]:assert hashlib.sha256((ROOT/item["file"]).read_bytes()).hexdigest()==item["sha256"]
    for film in ("design","launch"):
        assert (ROOT/"renders"/(film+"-frames")/"input-signature.txt").read_text()==signature()
        log=(ROOT/"renders"/(film+"-render.log")).read_text(encoding="utf-8")
        assert "Traceback (most recent call last)" not in log
    result={"checks":"passed","input_signature":signature(),"videos":reports,"frame_sync_max_error":error,"camera":"All rendered launch camera heights remain fixed at ground-based shot positions","source_geometry":"passed","photo_asset_hashes":"passed","real_time_full_playback":False,"actual_audio_listening":False,"method":"Exact CAD and conditional physics with photographic environment maps; not actual flight footage"}
    (ROOT/"verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"checks":"passed","videos":[{k:r[k] for k in ("file","frames","seconds")} for r in reports],"frame_sync_max_error":error},indent=2))


if __name__=="__main__":main()
