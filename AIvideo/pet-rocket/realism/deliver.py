"""Package portable photographic videos, verified source CAD and photo assets."""

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import zipfile

from PIL import Image,ImageDraw
from render import signature

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent


def main():
    verification=json.loads((ROOT/"verification.json").read_text())
    assert verification["checks"]=="passed" and verification["input_signature"]==signature()
    assert json.loads((ROOT/"artifact-audit.json").read_text())["film_count"]==4
    for video in verification["videos"]:assert hashlib.sha256((ROOT/video["file"]).read_bytes()).hexdigest()==video["sha256"]
    references=[(PARENT/"renders"/("design-frames" if film=="design" else "launch-frames-refined")/"frame_0001.png",ROOT/"renders"/(film+"-frames")/"frame_0001.png") for film in ("design","launch")]
    if all(path.is_file() for pair in references for path in pair):
        comparison=Image.new("RGB",(1280,780),"#101719");draw=ImageDraw.Draw(comparison)
        for row,(film,paths) in enumerate(zip(("design","launch"),references)):
            draw.text((14,row*390+8),"Previous / "+film,fill="white")
            draw.text((654,row*390+8),"Photographic revision / "+film,fill="white")
            for column,path in enumerate(paths):
                with Image.open(path) as source:comparison.paste(source.convert("RGB").resize((640,360)),(column*640,row*390+30))
        comparison.save(ROOT/"renders/comparison.jpg",quality=95)
    else:
        # The portable archive retains the reviewed comparison, not old frame caches.
        assert (ROOT/"renders/comparison.jpg").is_file()
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PET Rocket v2 — 写真素材による改良版</title><style>body{margin:0;background:#101719;color:#edf1ef;font:16px 'Yu Gothic',system-ui}main{max-width:1200px;margin:auto;padding:28px}section{margin:28px 0;padding:20px;background:#1c2528;border-radius:10px}video,img{width:100%;background:#000}p{line-height:1.8}a{color:#b6e1d2}</style><main><h1>PET ROCKET v2</h1><p>写真由来の環境光・地面、薄いPETと透明な水、地上カメラへ作り直したCGです。原寸STLと計算軌道を維持し、ボトル細部・重量・圧力などの未実測値は仮定として扱います。</p><section><h2>設計紹介 / 16秒</h2><video controls preload="metadata" src="pet_rocket_design_cinematic.mp4" poster="design-cinematic-poster.png"></video><p><a href="pet_rocket_design_cinematic.mp4" download>映像版を保存</a> · <a href="pet_rocket_design.mp4">寸法・質量の注釈付き版</a></p></section><section><h2>打ち上げ予測 / 12秒</h2><video controls preload="metadata" src="pet_rocket_launch_cinematic.mp4" poster="launch-cinematic-poster.png"></video><p><a href="pet_rocket_launch_cinematic.mp4" download>映像版を保存</a> · <a href="pet_rocket_launch_prediction.mp4">時刻・高度・残水量の注釈付き版</a></p></section><section><h2>前版との比較</h2><img src="comparison.jpg" alt="上段は設計紹介、下段は打ち上げ。左が前版、右が改良版。"></section><p>無風・鉛直、水0.66L、初期ゲージ圧300kPa、9mmノズル等の条件付き計算で、名目最高点28.34m、到達2.602秒。映像は低速再生・静止を含みます。実飛行、姿勢安定性、保持・回収の検証結果ではありません。水滴はCFDではなく弾道表現、音は独自合成です。</p><p>環境光・地面：Poly Haven CC0（Andreas Mischok、Oliksiy Yakovlyev、Rob Tuytel）。制作：AI支援によるシーン記述、原寸CAD、数値計算、ローカルの物理ベース描画。</p></main></html>'''
    (ROOT/"renders/index.html").write_text(page,encoding="utf-8")
    common=["LICENSE","requirements.txt","scenario.json","simulation.json","simulate.py","render_scene.py","timeline.py","render-settings.json","provenance.json","audit_metadata.py","sanitize_scenes.py","test_physics.py"]
    files=[PARENT/name for name in common]+sorted((PARENT/"source-data").glob("*.json"))+sorted((PARENT/"assets").glob("*.stl"))+[PARENT/"renders/trajectory.npz"]
    files += sorted(p for p in ROOT.iterdir() if p.is_file() and p.name not in (".gitignore","delivery-manifest.json","archive-check.json"))
    files += sorted((ROOT/"cache").iterdir())
    for pattern in ("*.mp4","*-poster.png","*-contact.jpg","*-sound.wav","*-state.csv","*-render.json"):
        files += sorted((ROOT/"renders").glob(pattern))
    files += [ROOT/"renders/index.html",ROOT/"renders/comparison.jpg",ROOT/"renders/design.blend",ROOT/"renders/launch.blend"]
    files=sorted(set(files))
    assert all(path.is_file() for path in files)
    manifest={"files":[{"path":p.relative_to(PARENT).as_posix(),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],"self_excluded_from_hashes":True,"photo_assets":"Poly Haven CC0; original URLs and hashes in realism/asset-manifest.json"}
    manifest_path=ROOT/"delivery-manifest.json";manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8");files.append(manifest_path)
    archive=ROOT/"renders/pet_rocket_v2_photographic.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in files:bundle.write(path,path.relative_to(PARENT).as_posix())
    with tempfile.TemporaryDirectory(prefix="delivery-check-",dir=ROOT/"renders") as folder:
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in bundle.namelist())
            bundle.extractall(folder)
        for path in files:
            assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256((Path(folder)/path.relative_to(PARENT)).read_bytes()).digest()
        class Links(HTMLParser):
            def handle_starttag(self,tag,attrs):
                for key,value in attrs:
                    if key in ("src","href","poster") and value:assert (Path(folder)/"realism/renders"/value).is_file(),value
        Links().feed((Path(folder)/"realism/renders/index.html").read_text(encoding="utf-8"))
    report={"archive":"renders/"+archive.name,"bytes":archive.stat().st_size,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"files":len(files),"extraction_and_hashes":"passed","extracted_page_links":"passed","excluded":["raw frame caches","render logs","runtime binaries","system fonts","backup blend files"]}
    (ROOT/"archive-check.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
