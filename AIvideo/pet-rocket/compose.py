"""Add legible data-driven Japanese annotations and original synthetic sound."""

import argparse
import csv
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from timeline import physical_time,design_source_frame,DESIGN_FRAMES

ROOT=Path(__file__).resolve().parent
REPORT=json.loads((ROOT/"simulation.json").read_text())
PARAM=json.loads((ROOT/"source-data/parameters.json").read_text())
SETTINGS=json.loads((ROOT/"render-settings.json").read_text())
DATA=np.load(ROOT/"renders/trajectory.npz")["data"]
FPS=24
W,H=1280,720
TEAL=(95,228,203)
AMBER=(255,198,105)


@lru_cache(maxsize=20)
def font(size):
    paths=[Path("C:/Windows/Fonts")/name for name in ("YuGothM.ttc","meiryo.ttc","msgothic.ttc")]
    path=next((path for path in paths if path.is_file()),None)
    if not path: raise FileNotFoundError("A Japanese system font is required")
    return ImageFont.truetype(str(path),size)


def time_map(t):
    return physical_time(t,REPORT["nominal"]["apogee_time_s"])


def state(t):
    return np.array([np.interp(t,DATA[:,0],DATA[:,i]) for i in range(DATA.shape[1])])


def text(draw,xy,value,size=22,fill="white"):
    draw.text(xy,value,font=font(size),fill=fill,stroke_width=0)


def panel(draw,title,rows):
    draw.rounded_rectangle((900,115,1255,598),radius=12,fill=(8,19,27,223),outline=(86,132,144,200),width=1)
    text(draw,(924,134),title,25,TEAL)
    draw.line((924,178,1230,178),fill=(*TEAL,140),width=1)
    for i,(label,value,status) in enumerate(rows):
        y=195+i*62
        text(draw,(924,y),label,17,(176,193,202))
        text(draw,(924,y+23),value,23)
        if status:text(draw,(1181,y+28),status,14,AMBER)


def overlay(kind,t):
    result=Image.new("RGBA",(W,H))
    draw=ImageDraw.Draw(result)
    draw.rectangle((0,0,W,93),fill=(6,16,23,220))
    text(draw,(30,14),"PET ROCKET / v2",32,TEAL)
    text(draw,(32,57),"詳細設計の紹介" if kind=="design" else "条件付き打ち上げ予測 / 上昇のみ",21)
    text(draw,(1040,31),"RocketWright",23,(203,220,226))
    draw.rectangle((0,638,W,H),fill=(6,16,23,226))
    if kind=="design":
        phase=min(int(t//4),3)
        d=REPORT["design"]
        chapters=[
            ("01  全体と原寸配置",[("全長 / STL組立包絡",f"{d['height_m']*1000:.1f} mm","CAD"),("ボトル外形径",f"{d['bottle_diameter_m']*1000:.0f} mm","仮定"),("最大幅 / フィンを含む",f"{d['span_m']*1000:.1f} mm","CAD"),("フィン配置",f"{d['fin_count']}枚 / 120°","設計"),("ノーズ基部",f"z = {d['nose_base_z_m']*1000:.0f} mm","設計"),("単位とモデル","mm → m で描画","原寸")]),
            ("02  分解して見る",[("ノーズ外径 × 高さ","114 × 103.9 mm","CAD"),("ノーズの法線肉厚",f"{PARAM['nose']['wall']:.1f} mm","設計"),("フィン板厚",f"{PARAM['fin']['thickness']:.1f} mm","設計"),("根元の補強ウェブ",f"{PARAM['fin']['root_web']:.0f} mm","設計"),("フィン後端位置",f"z = {PARAM['fin']['mount_tail_z']:.0f} mm","設計"),("分解表示","移動のみ / 形状は保持","")]),
            ("03  フィン取付部",[("翼根長 × 翼幅","100 × 50 mm","設計"),("帯用スロット","3.6 × 8.0 mm","設計"),("スロット中心 / 部品内","z = 20 / 78 mm","設計"),("サドル幅",f"{PARAM['fin']['saddle_width']:.0f} mm","設計"),("片側の名目すきま","0.4 mm","設計"),("現物適合・保持","未確認","未検証")]),
            ("04  質量と残課題",[("ノーズのCAD材料質量",f"{d['nose_mass_kg']*1000:.2f} g","計算"),("フィン / 1枚 × 3",f"{d['one_fin_mass_kg']*1000:.2f} g × 3","計算"),("ノーズ + フィン3枚",f"{d['cad_parts_mass_kg']*1000:.2f} g","計算"),("密度の仮定","1.24 g/cm³","仮定"),("軟質キャップ・回収","未供給 / 未設計",""),("実重量・全機安定性","未確認","未検証")])
        ]
        panel(draw,*chapters[phase])
        text(draw,(30,651),"設計値を表示。ボトル外形・印刷重量・固定・回収・飛行安定性は未実測／未検証。",19,AMBER)
        text(draw,(30,682),"原寸STLを使用した物理ベースCG / 分解表示は説明用の移動です。",17,(185,202,210))
    else:
        draw.rounded_rectangle((16,103,588,190),radius=9,fill=(8,19,27,190))
        sim_t,scale=time_map(t)
        row=state(sim_t)
        phase="開始条件" if t<1.5 else "水噴射" if sim_t<REPORT["nominal"]["phase_ends"]["water"] else "空気噴射" if sim_t<REPORT["nominal"]["phase_ends"]["air"] else "慣性上昇" if scale else "最高点で表示を停止"
        text(draw,(30,112),phase,28,TEAL)
        text(draw,(30,151),f"計算時刻 {sim_t:.3f} s   /   再生速度 {scale:.2f}×",20)
        thrust=0 if t<1.5 else row[8]
        rows=[("打上点からの高度",f"{row[1]:.2f} m","予測"),("鉛直速度",f"{max(0,row[2]):.2f} m/s","予測"),("残水量",f"{row[4]*1000:.0f} mL","計算"),("内圧 / ゲージ圧",f"{max(0,row[6]-REPORT['scenario']['ambient_pressure_pa'])/1000:.1f} kPa","計算"),("軸方向推力",f"{thrust:.2f} N","計算"),("乾燥質量 / 仮定を含む",f"{REPORT['nominal']['dry_mass_kg']*1000:.2f} g","")]
        if t>=11.5:
            low,high=REPORT["sensitivity_apogee_range_m"]
            rows=[("名目最高点",f"{REPORT['nominal']['apogee_m']:.2f} m","予測"),("到達時刻",f"{REPORT['nominal']['apogee_time_s']:.3f} s","予測"),("条件を変えた最高点",f"{low:.1f} ～ {high:.1f} m","") ,("変えた条件","圧力±15% / Cd 0.35–0.70","") ,("範囲の意味","統計的な信頼区間ではない","") ,("回収・姿勢安定性","計算対象外 / 未検証","")]
        panel(draw,"予測状態" if t<11.5 else "予測結果と範囲",rows)
        chart=(30,398,351,601)
        draw.rounded_rectangle(chart,radius=10,fill=(8,19,27,220),outline=(86,132,144,180))
        text(draw,(46,409),"高度履歴 / m",18,TEAL)
        x0,y0=60,570; cw,ch=265,120
        for height in (0,10,20,30):
            y=y0-height/32*ch
            draw.line((x0,y,x0+cw,y),fill=(80,103,116,150))
            text(draw,(37,y-9),str(height),13,(172,190,201))
        pts=[(x0+r[0]/DATA[-1,0]*cw,y0-r[1]/32*ch) for r in DATA[::max(1,len(DATA)//160)]]
        draw.line(pts,fill=(109,137,149,180),width=2)
        live=[p for p,r in zip(pts,DATA[::max(1,len(DATA)//160)]) if r[0]<=sim_t]
        if len(live)>1:draw.line(live,fill=TEAL,width=3)
        px,py=x0+sim_t/DATA[-1,0]*cw,y0-row[1]/32*ch
        draw.ellipse((px-4,py-4,px+4,py+4),fill=TEAL)
        text(draw,(68,579),"0 s                      2.60 s",13,(172,190,201))
        text(draw,(30,649),"仮定：2L / 水0.66L / 初期300kPa / 9mmノズル / 無風・鉛直。実測・飛行検証ではありません。",18,AMBER)
        text(draw,(30,681),"水滴は計算流量に対応した弾道表現（CFDではありません）。姿勢・固定・回収の成立は未検証。",17,(185,202,210))
    return result


def base_frame(kind,path):
    image=Image.open(path).convert("RGBA")
    if kind=="design":
        canvas=Image.new("RGBA",(W,H),(6,16,23,255))
        image=image.crop((160,0,1120,720)).resize((720,540),Image.Resampling.LANCZOS)
        canvas.paste(image,(84,96))
        return canvas
    return image


def audio(kind,seconds,path):
    rate=48000
    t=np.arange(round(seconds*rate))/rate
    rng=np.random.default_rng(20261105)
    noise=rng.standard_normal(len(t))
    filtered=np.convolve(noise,np.ones(5)/5,mode="same")
    signal=.0015*filtered
    if kind=="design":
        for event,pitch in [(0.25,650),(6.15,800),(12.15,950),(18.15,700)]:
            dt=t-event
            signal+=.025*np.sin(2*np.pi*pitch*dt)*np.exp(-np.maximum(dt,0)*16)*(dt>=0)*(dt<.35)
    else:
        apex=REPORT["nominal"]["apogee_time_s"]
        sim=np.where(t<1.5,0,np.where(t<5.5,(t-1.5)*.2,np.where(t<11.5,.8+(t-5.5)*(apex-.8)/6,apex)))
        q=np.interp(sim,DATA[:,0],DATA[:,9])*(t>=1.5)
        qa=np.interp(sim,DATA[:,0],DATA[:,10])*(t>=1.5)
        signal+=filtered*(.13*np.sqrt(q/max(DATA[:,9].max(),1e-9))+.05*np.sqrt(qa/max(DATA[:,10].max(),1e-9)))
    signal*=np.minimum(t/.15,1)*np.minimum((seconds-t)/.3,1)
    stereo=np.column_stack([signal,signal*.98]).clip(-.9,.9)
    with wave.open(str(path),"wb") as target:
        target.setnchannels(2);target.setsampwidth(2);target.setframerate(rate)
        target.writeframes((stereo*32767).astype("<i2").tobytes())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--film",choices=["design","launch","both"],default="both")
    parser.add_argument("--poster",action="store_true")
    args=parser.parse_args()
    films=["design","launch"] if args.film=="both" else [args.film]
    for kind in films:
        count=DESIGN_FRAMES if kind=="design" else 336
        output=ROOT/"renders"
        if args.poster:
            frame=48 if kind=="design" else 80
            image=base_frame(kind,output/f"{kind}-preview-{frame:04d}.png")
            Image.alpha_composite(image,overlay(kind,(frame-1)/FPS)).convert("RGB").save(output/f"{kind}-poster.png")
            continue
        source_count=384 if kind=="design" else count
        missing=[i for i in range(1,source_count+1) if not (output/SETTINGS[kind+"_frames"]/f"frame_{i:04d}.png").exists()]
        if missing:raise FileNotFoundError(f"Missing {len(missing)} frames for {kind}")
        wav=output/f"{kind}-sound.wav"
        audio(kind,count/FPS,wav)
        filename="pet_rocket_design.mp4" if kind=="design" else "pet_rocket_launch_prediction.mp4"
        process=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),"-y","-hide_banner","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(wav),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-t",str(count/FPS),"-map_metadata","-1","-metadata",f"title=PET Rocket v2 {'Design Introduction' if kind=='design' else 'Conditional Ascent Prediction'}","-metadata","comment=AI-assisted physically based visualization using frozen CAD; assumed inputs; not measured or flight-validated","-movflags","+faststart",str(output/filename)],stdin=subprocess.PIPE)
        timeline=[]
        for frame in range(1,count+1):
            film_t=(frame-1)/FPS
            source_frame=design_source_frame(frame) if kind=="design" else frame
            annotation_t=(source_frame-1)/FPS if kind=="design" else film_t
            image=base_frame(kind,output/SETTINGS[kind+"_frames"]/f"frame_{source_frame:04d}.png")
            image=Image.alpha_composite(image,overlay(kind,annotation_t)).convert("RGB")
            if frame==(48 if kind=="design" else 80):image.save(output/f"{kind}-poster.png")
            process.stdin.write(image.tobytes())
            if kind=="launch":
                sim_t,scale=time_map(film_t); row=state(sim_t)
                timeline.append([frame,film_t,sim_t,scale,row[1],row[2],row[4],row[6],row[8] if film_t>=1.5 else 0])
        process.stdin.close()
        if process.wait():raise RuntimeError("Encoder failed")
        if timeline:
            with (ROOT/"launch-frame-data.csv").open("w",newline="",encoding="utf-8") as target:
                writer=csv.writer(target);writer.writerow(["frame","film_time_s","simulation_time_s","playback_scale","altitude_m","velocity_m_s","water_mass_kg","pressure_abs_pa","displayed_thrust_n"]);writer.writerows(timeline)
        print(f"Encoded {filename}",flush=True)


if __name__=="__main__":main()
