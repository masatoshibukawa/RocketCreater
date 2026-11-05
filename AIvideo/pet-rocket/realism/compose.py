"""Finish the photographic scenes with restrained captions and state-driven sound."""

import csv
import argparse
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/"settings.json").read_text())
SIM=json.loads((ROOT.parent/"simulation.json").read_text())
DATA=np.load(ROOT.parent/"renders/trajectory.npz")["data"]
FPS=CONFIG["fps"]
W,H=CONFIG["width"],CONFIG["height"]


@lru_cache(maxsize=16)
def font(size):
    path=next((Path("C:/Windows/Fonts")/name for name in ("YuGothM.ttc","meiryo.ttc","msgothic.ttc") if (Path("C:/Windows/Fonts")/name).is_file()),None)
    if path is None:raise FileNotFoundError("Japanese system font required")
    return ImageFont.truetype(str(path),size)


def source_frame(frame):
    index=frame-1
    return min(index//96,3)*72+min(index%96,71)+1


def read_states():
    with (ROOT/"renders/launch-state.csv").open(encoding="utf-8") as file:
        return {int(row["frame"]):row for row in csv.DictReader(file)}


def overlay(kind,frame,states,clean=False):
    layer=Image.new("RGBA",(W,H));draw=ImageDraw.Draw(layer)
    def text(x,y,value,size=29,color=(243,245,243)):
        draw.text((x,y),value,font=font(size),fill=color,stroke_width=1,stroke_fill=(7,12,14,180))
    if clean:
        text(43,1037,"CG / 設計の可視化・条件付きシミュレーション（未実測値を含む）",21)
        return layer
    if kind=="design":
        chapter=min((frame-1)//96,3)
        titles=["01 / 原寸設計","02 / 分解して確認","03 / 取付部の接写","04 / 質量と残課題"]
        rows=[
            ["全長365.9mm / 最大幅214.4mm","ノーズ・フィンは元STLを保持","ボトル外径110mmは未実測の仮定"],
            ["ノーズ外径114mm / 高さ103.9mm","法線肉厚1.6mm / フィン3枚・120°","分解表示は説明用の移動"],
            ["フィン板厚2.4mm / 翼根長100mm","帯用スロット3.6×8.0mm","現物への適合・保持は未検証"],
            ["ノーズ＋フィンのCAD材料質量102.94g","仮定密度1.24g/cm³。印刷重量は未実測","固定・回収・姿勢安定性は未検証"]
        ]
        draw.rounded_rectangle((43,43,793,260),radius=8,fill=(12,17,19,185))
        text(65,55,"PET ROCKET v2",28,(207,224,218))
        text(65,96,titles[chapter],36)
        for i,value in enumerate(rows[chapter]):text(65,152+i*31,value,24)
    else:
        row=states[frame];t=float(row["simulation_time_s"]);film_t=(frame-1)/FPS
        times=np.array([float(states[i]["simulation_time_s"]) for i in sorted(states)])
        scale=0 if film_t<1.5 or film_t>=11 else .2 if film_t<5.5 else (DATA[-1,0]-.8)/5.5
        phase="開始条件" if film_t<1.5 else "水噴射" if t<SIM["nominal"]["phase_ends"]["water"] else "空気噴射" if t<SIM["nominal"]["phase_ends"]["air"] else "慣性上昇" if scale else "最高点 / 静止表示"
        draw.rounded_rectangle((43,43,653,183),radius=8,fill=(12,17,19,168))
        text(65,57,"PET ROCKET v2 / 条件付き上昇予測",27)
        text(65,98,phase,34)
        text(65,143,f"計算 {t:.3f}s   再生速度 {scale:.2f}×",22)
        altitude=float(row["nozzle_world_z_m"])-.18
        velocity=max(0,float(np.interp(t,DATA[:,0],DATA[:,2])))
        water=float(row["water_mass_kg"])*1000
        pressure=max(0,float(row["pressure_abs_pa"])-101325)/1000
        draw.rounded_rectangle((43,915,833,1017),radius=8,fill=(12,17,19,182))
        text(65,925,f"高度 {altitude:.2f}m   速度 {velocity:.2f}m/s",31)
        text(65,971,f"残水 {water:.0f}mL   内圧 {pressure:.1f}kPa（ゲージ）",23)
    text(43,1037,"原寸CAD＋計算によるCG / ボトル外形・重量・圧力等は未実測の仮定。実飛行ではありません。",20)
    return layer


def audio(kind,seconds,states,path):
    rate=48000;t=np.arange(round(seconds*rate))/rate
    rng=np.random.default_rng(8162)
    noise=np.convolve(rng.standard_normal(len(t)),np.ones(7)/7,mode="same")
    signal=.001*noise
    if kind=="launch":
        film=np.array([float(states[i]["film_time_s"]) for i in sorted(states)])
        physical=np.array([float(states[i]["simulation_time_s"]) for i in sorted(states)])
        clock=np.interp(t,film,physical)
        q=np.interp(clock,DATA[:,0],DATA[:,9])*(t>=1.5)
        air=np.interp(clock,DATA[:,0],DATA[:,10])*(t>=1.5)
        signal += noise*(.15*np.sqrt(q/max(DATA[:,9].max(),1e-9))+.045*np.sqrt(air/max(DATA[:,10].max(),1e-9)))
    signal *= np.minimum(t/.15,1)*np.minimum((seconds-t)/.3,1)
    stereo=np.column_stack([signal,signal*.97]).clip(-.9,.9)
    with wave.open(str(path),"wb") as file:
        file.setnchannels(2);file.setsampwidth(2);file.setframerate(rate)
        file.writeframes((stereo*32767).astype("<i2").tobytes())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--clean-only",action="store_true")
    args=parser.parse_args()
    states=read_states()
    assert set(states)==set(range(1,CONFIG["launch_frames"]+1))
    tasks=[] if args.clean_only else [("design",384,"pet_rocket_design.mp4",False),("launch",288,"pet_rocket_launch_prediction.mp4",False)]
    tasks += [("design",384,"pet_rocket_design_cinematic.mp4",True),("launch",288,"pet_rocket_launch_cinematic.mp4",True)]
    for kind,count,name,clean in tasks:
        wav=ROOT/"renders"/(kind+"-sound.wav");audio(kind,count/FPS,states,wav)
        output=ROOT/"renders"/name
        process=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),"-y","-hide_banner","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(wav),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","17","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-t",str(count/FPS),"-map_metadata","-1","-metadata",f"title=PET Rocket v2 Photographic {'Design' if kind=='design' else 'Conditional Ascent'}","-metadata","comment=AI-assisted physically based CG; frozen source CAD; assumed bottle detail and inputs; not actual footage; photo assets from Poly Haven CC0","-movflags","+faststart",str(output)],stdin=subprocess.PIPE)
        for frame in range(1,count+1):
            source=source_frame(frame) if kind=="design" else frame
            image=Image.open(ROOT/"renders"/(kind+"-frames")/f"frame_{source:04d}.png").convert("RGBA")
            assert image.size==(W,H)
            image=Image.alpha_composite(image,overlay(kind,frame,states,clean)).convert("RGB")
            if frame==(28 if kind=="design" else 80):image.save(ROOT/"renders"/(kind+("-cinematic" if clean else "")+"-poster.png"))
            process.stdin.write(image.tobytes())
        process.stdin.close()
        if process.wait():raise RuntimeError("Video encoding failed")
        print("Encoded "+name,flush=True)


if __name__=="__main__":main()
