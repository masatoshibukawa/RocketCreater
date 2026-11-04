# RocketWright fairing visualization

A project-adapted reconstruction of the user-supplied reference: an open fairing and upper-stage assembly in an industrial hangar, with a moving low-angle camera and cyan technical overlays.

## 日本語の概要

参照動画の尺、構図、カメラの傾き、HUDの配置、黒へのフェードを合わせ、RocketWrightのロゴと概念設計用の表示へ置き換える試作です。物理解析や構造検証の結果を示す映像ではありません。

参照は [LinkedInの公開投稿](https://www.linkedin.com/posts/isro-indian-space-hub_omspace-infinityone-indianspaceindustry-activity-7521055649573543937-gOV1)。Indian Space Hubが共有するOmspace Infinity Oneの映像です。取得した動画は640×360、30fps、310映像フレームで、音声を含むコンテナは約10.43秒でした。

## Reference analysis

[reference_spec.json](reference_spec.json) separates measured source properties, visual observations, and intentional project adaptations. The source video and extracted reference frames stay in the ignored `reference/` directory and are not redistributed with the project sources.

The reconstruction uses newly modeled geometry and original audio. It targets the observed presentation rather than claiming pixel-identical reproduction of different branding, geometry, and sound. At this checkpoint, reference analysis is complete and rendering is in progress.

## Tools

- Blender 5.2.2 LTS, already installed on the workstation.
- Pillow 13.0.0 and imageio-ffmpeg 0.8.1, installed only under the ignored `tools/python/` folder.
- [inspect_reference.py](tools/inspect_reference.py) reads public page metadata without browser credentials.
- [analyze_reference.py](tools/analyze_reference.py) decodes the local source and extracts timed reference frames.

The production approach is AI-assisted scene scripting and compositing. A text-to-video diffusion model is not used for the deterministic geometry or readable overlay text.
