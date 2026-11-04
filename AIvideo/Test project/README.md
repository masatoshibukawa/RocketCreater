# RocketWright fairing visualization

A project-adapted reconstruction of the user-supplied reference: an open fairing and upper-stage assembly in an industrial hangar, with a moving low-angle camera and cyan technical overlays.

## 日本語の概要

参照動画の尺、構図、カメラの傾き、HUDの配置、黒へのフェードを合わせ、RocketWrightのロゴと概念設計用の表示へ置き換える試作です。物理解析や構造検証の結果を示す映像ではありません。

参照は [LinkedInの公開投稿](https://www.linkedin.com/posts/isro-indian-space-hub_omspace-infinityone-indianspaceindustry-activity-7521055649573543937-gOV1)。Indian Space Hubが共有するOmspace Infinity Oneの映像です。取得した動画は640×360、30fps、310映像フレームで、音声を含むコンテナは約10.43秒でした。

## Reference analysis

[reference_spec.json](reference_spec.json) separates measured source properties, visual observations, and intentional project adaptations. The source video and extracted reference frames stay in the ignored `reference/` directory and are not redistributed with the project sources.

The reconstruction uses newly modeled geometry and original audio. It targets the observed presentation rather than claiming pixel-identical reproduction of different branding, geometry, and sound. See [the reconstruction review](reconstruction_review.md) for the matched elements and remaining differences.

## Generated deliverables

Generated media is saved locally under `renders/` and excluded from Git. Rebuild it from the committed scripts or use the delivered project archive.

| Local file | Content |
| --- | --- |
| `renders/rocketwright_fairing.mp4` | 1280×720, 30fps, 310 frames, approximately 10.43 seconds including original stereo audio |
| `renders/rocketwright_fairing_poster.png` | A frame from the finished composite |
| `renders/rocketwright_fairing.blend` | Editable geometry, materials, lighting, camera, and animation |
| `renders/original_sound.wav` | Original synthesized ambient sound and interface tones |
| `renders/rocketwright_fairing_project.zip` | Video, scene, original sound, source scripts, dependency pins, and review records |

The Blender file contains the 3D scene; readable HUD text and audio are added by the compositing script. The source material is not included in the archive.

## Rebuild

Run from this directory using Python 3.11 or later and a compatible Blender installation:

```powershell
python -m pip install --target tools/python -r requirements.txt
python tools/render_project.py
python tools/package_project.py
```

Use `--blender` to specify another Blender executable. The tested installation is Blender 5.2.2 LTS. The scene selects OptiX when available, with a CPU fallback. After a successful scene render, `python tools/render_project.py --skip-render` recomposites and verifies the existing frames.

## Validation and provenance

[verification.json](verification.json) records the output hash, stream properties, full video decode, expected frame count, black endpoints, synthesized-audio peak/RMS, and metadata inspection. The extracted contact sheet was visually reviewed for composition, camera movement, HUD, and fades. Audio was checked as a digital signal; a listening review has not been performed.

The production files were checked for unwanted assistant working labels and embedded user-directory paths. The export retains the meaningful concept label. The ZIP is extracted and its files compared by SHA-256 before handoff. This is a development prototype, not a final competition submission or an audit of the repository's entire shared history.

## Tools

- Blender 5.2.2 LTS, already installed on the workstation.
- Pillow 13.0.0 and imageio-ffmpeg 0.8.1, installed only under the ignored `tools/python/` folder.
- [inspect_reference.py](tools/inspect_reference.py) reads public page metadata without browser credentials.
- [analyze_reference.py](tools/analyze_reference.py) decodes the local source and extracts timed reference frames.
- [build_scene.py](tools/build_scene.py) creates the editable Blender scene and renders the visible 3D portion.
- [compose_video.py](tools/compose_video.py) adds the HUD, fades, original sound, and MP4 encoding.
- [render_project.py](tools/render_project.py), [verify_video.py](tools/verify_video.py), and [package_project.py](tools/package_project.py) rebuild, verify, and package the project.

The production approach is AI-assisted scene scripting and compositing. A text-to-video diffusion model is not used for the deterministic geometry or readable overlay text.

New code and concept geometry follow the repository's MIT license. Original reference footage remains attributable to its creators; Indian Space Hub is the observed sharing account, and the subject is Omspace Infinity One. No third-party footage or soundtrack is redistributed in the export or archive. System fonts are used to rasterize overlay text; font files and downloaded dependency binaries are not included in the archive.
