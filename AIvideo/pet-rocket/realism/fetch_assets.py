"""Download the selected CC0 photo-based assets from the official Poly Haven API."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent
AGENT="RocketCreater PET video production"


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":AGENT}),timeout=60)


def main():
    targets=[("small_rural_road",["hdri","4k","exr"],"outdoor.exr"),
             ("artist_workshop",["hdri","4k","exr"],"workshop.exr"),
             ("asphalt_02",["diff","2k","jpg"],"ground-diff.jpg"),
             ("asphalt_02",["nor_gl","2k","jpg"],"ground-normal.jpg"),
             ("asphalt_02",["rough","2k","jpg"],"ground-rough.jpg")]
    metadata={};records=[]
    cache=ROOT/"cache";cache.mkdir(exist_ok=True)
    for asset,keys,name in targets:
        if asset not in metadata:
            with request("https://api.polyhaven.com/files/"+asset) as source:metadata[asset]=json.load(source)
        entry=metadata[asset]
        for key in keys:
            aliases={"diff":("diff","diffuse"),"rough":("rough","roughness")}.get(key,(key,))
            matched=next((candidate for candidate in entry if candidate.lower() in aliases),None)
            if matched is None:raise KeyError((key,list(entry)))
            entry=entry[matched]
        path=cache/name
        if not path.exists() or hashlib.md5(path.read_bytes()).hexdigest()!=entry["md5"]:
            with request(entry["url"]) as source:path.write_bytes(source.read())
        assert hashlib.md5(path.read_bytes()).hexdigest()==entry["md5"]
        records.append({"file":"cache/"+name,"asset":asset,"url":entry["url"],"source":"https://polyhaven.com/a/"+asset,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"license":"CC0-1.0"})
        print("Verified "+name,flush=True)
    (ROOT/"asset-manifest.json").write_text(json.dumps({"provider":"Poly Haven","license_url":"https://polyhaven.com/license","api_terms":"https://github.com/Poly-Haven/Public-API/blob/master/ToS.md","checked_date":"2026-11-05","files":records},indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":main()
