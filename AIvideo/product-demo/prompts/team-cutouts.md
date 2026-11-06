# チーム写真の切り抜きプロンプト

組み込み画像編集ツールによる背景除去。画像は人物紹介用の候補で、元写真を保持する。顔・服・ポーズの画素単位の一致を保証する手法ではない。合成の文字・緑の発光は別レイヤーで加える。

## Taichi Uchida / 内田 大智

入力：本人の公開ポートフォリオの`assets/images/portrait.webp`。表示名と組み合わせは本人が確認済み。

```text
Use case: background-extraction.
Asset type: a transparent photographic portrait cutout for a spaceship cockpit team-introduction screen.
Input image 1 is the exact edit target: Taichi Uchida's publicly provided portrait.
Remove ONLY the plain gray background. Keep the original person exactly unchanged: face, facial proportions, open-mouth expression, eyes, hair, skin texture, blue suit, red tie, both hands and every finger, pose, lighting and photographic colors. Preserve the existing cropped boundaries at the top, left, right and bottom; do not invent missing hair, fingers or body. Preserve fine hair and clean suit edges without a gray halo.
Deliver a single real RGBA PNG with genuinely transparent background, matching the source framing. No checkerboard or colored background rendered into the image. No new costume, relighting, beautification, text, logos, border, drop shadow, glow or watermark. Do not redraw the face or change identity. Only background extraction.
```

## Masato Shibukawa / 渋川 雅人

入力：本人のSlackプロフィール写真。表示名と組み合わせは本人が確認済み。

```text
Use case: background-extraction.
Asset type: a transparent photographic portrait cutout for a spaceship cockpit team-introduction screen.
Input image 1 is the exact edit target: Masato Shibukawa's Slack profile photo.
Remove ONLY the beige wall background. Preserve the original man exactly: same face, facial proportions, skin details and mole, glasses and transparent lenses, hairstyle and fine hair, neutral expression, dark suit, striped shirt, blue striped tie, pose, original lighting and natural photographic colors. Keep the original square crop and existing shoulder/bottom boundaries. Do not invent missing hair or body. Carefully preserve glass frame and hair boundaries with no beige halo.
Deliver a single real RGBA PNG with genuinely transparent background. No checkerboard painted into the image. No relighting, restyling, beautification, face redraw, new clothes, text, logos, border, shadow, glow or watermark. Only background extraction; preserve identity and expression.
```
