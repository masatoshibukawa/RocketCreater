# Local video generation

ComfyUIとWan2.2 TI2V-5Bを、このディレクトリの`runtime/`へ分離して導入する。サービスへの生成課金や、サービスのロゴを合成する処理は使わない。電力、保存容量、生成時間は必要になる。

## Install

WindowsのPython 3.11以降で実行する。

```powershell
python AIvideo/local-runtime/bootstrap.py --install
```

公式ComfyUIリリース、PyTorchのCUDA 13.0用wheel、ComfyOrgが再配布する公式Wan2.2ワークフロー用の重みを取得する。モデルはHugging Faceが公開するLFSのSHA-256とサイズで照合する。仮想環境、モデル、キャッシュは`runtime/`へ保存し、Gitには含めない。

ComfyUIの起動と短い生成の検証は別の工程として記録する。導入記録がない段階では、導入・生成成功を意味しない。

## Sources

- [ComfyUI manual installation](https://docs.comfy.org/installation/manual_install)
- [Official Wan2.2 workflow](https://docs.comfy.org/tutorials/video/wan/wan2_2)
- [Wan2.2 model and license](https://github.com/Wan-Video/Wan2.2)
- [ComfyOrg model repackaging](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged)
