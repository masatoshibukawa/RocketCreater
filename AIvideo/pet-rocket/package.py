"""Package the two videos with source data and verify the extracted delivery."""

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import zipfile
from cache_inputs import signature

ROOT=Path(__file__).resolve().parent


def main():
    verification=json.loads((ROOT/"verification.json").read_text())
    assert verification["input_signature"]==signature(),"Verify the current inputs before packaging"
    assert json.loads((ROOT/"artifact-audit.json").read_text())["checks"]=="passed"
    for video in verification["videos"]:
        assert hashlib.sha256((ROOT/video["file"]).read_bytes()).hexdigest()==video["sha256"]
    summary=json.loads((ROOT/"simulation.json").read_text())
    apex=summary["nominal"]["apogee_m"]
    page=f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PET Rocket v2 — 設計と上昇予測</title><style>body{{margin:0;background:#08131c;color:#e5eef1;font:16px 'Yu Gothic',system-ui}}main{{max-width:1300px;margin:auto;padding:32px}}h1{{color:#66dfc8}}section{{background:#12232e;padding:22px;border-radius:12px;margin:24px 0}}video{{width:100%;background:#000}}p{{line-height:1.8}}a{{color:#80d7ee}}.note{{color:#f0c376}}</style><main><h1>PET Rocket v2</h1><p>既存2L試作v2の原寸STLと設計記録を使用。ボトル外形や初期条件は未実測の仮定として明示しています。</p><section><h2>詳細設計の紹介 / 24秒</h2><video controls preload="metadata" poster="design-poster.png" src="pet_rocket_design.mp4"></video><p>全体寸法、分解配置、フィン取付部、CAD材料質量と未検証項目を紹介します。各章に説明を読む静止時間を設けています。</p><a href="pet_rocket_design.mp4" download>動画を保存</a></section><section><h2>条件付き打ち上げ予測 / 14秒</h2><video controls preload="metadata" poster="launch-poster.png" src="pet_rocket_launch_prediction.mp4"></video><p>水噴射・空気噴射・慣性上昇を連続計算。計算時間は約2.60秒、名目最高点は{apex:.2f}mです。映像は低速再生と最高点での静止を含み、時刻・再生倍率を表示します。</p><a href="pet_rocket_launch_prediction.mp4" download>動画を保存</a></section><p class="note">無風・鉛直、初期圧力300kPa、水0.66L、9mmノズル等の仮定条件です。実飛行の結果、飛行安全、姿勢安定性、保持・回収の成立を示す映像ではありません。音は独自の合成音で、実測音響ではありません。</p><p>制作方式：AI支援のシーン記述、原寸STL、数値積分、物理ベース3Dレンダリング。機体や軌道を拡散モデルで再生成していません。</p></main></html>'''
    (ROOT/"renders/index.html").write_text(page,encoding="utf-8")
    files=[p for p in ROOT.iterdir() if p.is_file() and p.name not in ("delivery-manifest.json","archive-check.json",".gitignore")]
    files += sorted((ROOT/"assets").glob("*.stl"))
    files += sorted((ROOT/"source-data").glob("*.json"))
    names=["pet_rocket_design.mp4","pet_rocket_launch_prediction.mp4","design-poster.png","launch-poster.png","design-contact.jpg","launch-contact.jpg","design.blend","launch.blend","design-sound.wav","launch-sound.wav","trajectory.npz","launch-render-state.csv","design-render.json","launch-render.json","index.html"]
    files += [ROOT/"renders"/name for name in names]
    for path in files:
        if not path.is_file():raise FileNotFoundError(path.name)
    manifest={"files":[{"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],"self_excluded_from_hashes":True,"excluded":["frame caches","runtime binaries","raw render logs","backup Blender files","system font files"]}
    manifest_path=ROOT/"delivery-manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    files.append(manifest_path)
    archive=ROOT/"renders/pet_rocket_v2_video_project.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for path in files:output.write(path,path.relative_to(ROOT).as_posix())
    with tempfile.TemporaryDirectory(prefix="delivery-check-",dir=ROOT/"renders") as folder:
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            assert all(".." not in Path(name).parts and not name.startswith(("runtime/","source-reference/")) for name in bundle.namelist())
            bundle.extractall(folder)
        for source in files:
            extracted=Path(folder)/source.relative_to(ROOT)
            assert hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(extracted.read_bytes()).digest()
        class Links(HTMLParser):
            def handle_starttag(self,tag,attrs):
                for key,value in attrs:
                    if key in ("src","href","poster") and value:
                        assert (Path(folder)/"renders"/value).is_file(),value
        Links().feed((Path(folder)/"renders/index.html").read_text(encoding="utf-8"))
    report={"archive":"renders/"+archive.name,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"bytes":archive.stat().st_size,"files":[p.relative_to(ROOT).as_posix() for p in files],"extraction_and_hash_verification":"passed","extracted_page_links":"passed","excluded":manifest["excluded"]}
    (ROOT/"archive-check.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"archive":report["archive"],"bytes":report["bytes"],"files":len(files),"checks":report["extraction_and_hash_verification"]},indent=2))


if __name__=="__main__":main()
