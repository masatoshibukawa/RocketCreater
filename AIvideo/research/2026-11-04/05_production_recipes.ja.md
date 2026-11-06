# 動画制作の実践手順

以下は調査結果を組み合わせた制作案である。秒数やカット構成は作例の設計値で、モデルの性能測定ではない。最初は一本の短いショットを完成させ、映像と音を編集できることを確認してから作品を長くする。

## このPCで最初の一場面を作る

**目標:** 雨の屋上で人物が光を見上げる、短い写実ショット。

1. [Comfy DesktopのWindows公式手順](https://docs.comfy.org/installation/desktop/windows)でローカル実行環境を用意する。既存のRocketCreater用環境とは分離する。
2. [Wan2.2の公式テンプレート](https://docs.comfy.org/tutorials/video/wan/wan2_2)から5Bを選ぶ。必要なモデルは、テンプレートの種類と一致させる。
3. 人物の顔、衣装、雨、主光源を固定した基準画像を用意する。
4. テンプレート既定のサイズと長さで、次の動作を指定する。
5. 出力を確認し、一度に一項目だけ変えて候補を比較する。
6. 採用ショットに日本語のナレーションと環境音を付け、動画ファイルとして書き出す。

```text
The subject slowly looks up toward a distant light.
Rain beads slide down the jacket. The camera gently moves closer.
```

完成の判断は、顔が別人にならない、手や衣装の輪郭が途中で変わらない、背景の直線が大きく歪まない、声の冒頭と末尾が切れない、という観点で行う。

## 音付き動画をGUIで試す

LTX Desktopを使う場合は、アプリのText to VideoまたはImage to Videoから短い場面を作る。音を中心に設計したい場合はAudio to Videoを比較する。2.5の重み等は取得時にHugging Face側での条件確認を要する。[LTX Desktop公式](https://github.com/Lightricks/LTX-Desktop)。

映像と音が同時に出ても、セリフの正確な読み、声の一貫性、効果音のタイミングは別に評価する。日本語ナレーションを確実に読ませたい場面では、TTSの別素材も残して比較する。

## オリジナルSF予告編の構成案

**作品案:** 停止した観測基地に信号が戻り、一人の技師が巨大な光のゲートへ向かう。合計30秒を目標に、6カットで構成する。

| 時間 | 画面 | 動きとカメラ | 音 | 制作候補 |
| --- | --- | --- | --- | --- |
| 0〜5秒 | 荒れた観測基地の遠景 | ゆっくり前進 | 風、遠い機械音 | I2Vまたは3D |
| 5〜10秒 | 技師の顔 | 一度だけ光を見上げる | 「信号が、戻った。」 | 同一基準画像のI2VとTTS |
| 10〜15秒 | 装置に触れる手元 | 接触と小さな発光 | 起動音、短い低音 | 実写または3Dと合成 |
| 15〜20秒 | 空に開くゲート | 人物は小さく、ゲートが広がる | 予兆、衝撃、残響 | 生成背景とFX合成 |
| 20〜25秒 | ゲートへ向かう背中 | ゆっくり歩き出す | 「今度は、私たちが迎えに行く。」 | I2V、別録りの声 |
| 25〜30秒 | 基地と光、タイトル | 余韻を残して止める | 主題と余韻 | 編集、文字は後付け |

ショットごとに別々の生成を行い、編集で必要な部分を切り出す。生成尺と最終採用尺は同じでなくてよい。

**ゲートの背景用プロンプト案**

```text
A vast abandoned observatory stands beneath heavy storm clouds.
A distant circular energy aperture slowly opens above the horizon.
Its pale blue light spreads across the wet structures and low clouds.
A lone engineer appears small in the foreground.
Slow, restrained camera movement. Heavy atmosphere and believable scale.
```

人物の基準は毎回同じ画像を使い、衣装、髪、照明、機材の形をショット表に残す。精密な手の接触が必要なカットは、実写や3Dを比較する。

## PC内のLLMを使う構成

LLMには次のような指示で、生成前のショット表を作らせる。既存モデルがどこにあるかは今回の限定確認では特定できていないため、まず使用するローカルサーバーとモデルIDを確認する。

```text
あなたは映像の構成を整理する担当です。
30秒のSF予告編を、6つの独立したショットへ分解してください。
各ショットに、目的、日本語説明、英語の動作プロンプト、
参照画像、カメラ、光、セリフ、効果音、連続性の条件を付けてください。
未確定のモデル設定や生成時間は推測せず、未設定としてください。
```

1. ローカルLLMで台本とショット案を作る。
2. 人間が内容と連続性を確認し、参照画像を決める。
3. 必要ならLLMをGPUから外し、動画モデルで映像を生成する。
4. TTSと効果音を生成し、編集する。
5. 実際の結果をLLMへ渡し、次の修正案を作らせる。動画を見る機能のないLLMには、確認した問題を文章で渡す。

OllamaのローカルAPI基点は `http://localhost:11434/api`、LM Studioの互換API例は `http://localhost:1234/v1`。これらは会話モデルを呼ぶ接続先であり、動画生成APIへ自動的に変わるものではない。Ollamaにはクラウドモデルの経路もあるため、完全ローカルを意図する場合は実際の選択モデルと接続先を確認する。[Ollama公式API](https://docs.ollama.com/api/introduction)、[LM Studio公式API](https://lmstudio.ai/docs/developer/openai-compat)。

## 保存と比較のテンプレート

- [shot_plan.example.json](templates/shot_plan.example.json) は作品設計用。ComfyUIへ直接読み込むワークフローJSONではない。
- [generation_record.example.json](templates/generation_record.example.json) は生成条件と評価の記録用。未測定値は `null` のままにする。

実際に制作するときの保存構成例:

```text
project/
  script/
  references/
  shots/SH010/
    input/
    workflow/
    takes/
    selected/
  audio/voice/
  audio/sfx/
  audio/music/
  edit/
  exports/
```

モデル重み、元録音、大きな中間動画は作品用ストレージで管理し、Gitには台本、出典、設定、ワークフロー、短い評価記録を入れる案とする。参照ファイルのハッシュとモデルのrevisionを記録すると比較対象を追いやすい。

## 実験の順序

| 試す順 | 比較する内容 | 次へ進む条件 |
| --- | --- | --- |
| 1 | Wan5Bの公式テンプレートと同じ入力での候補生成 | 動画を出力して再生できる |
| 2 | 同一画像で動作とカメラ指示を一つずつ変更 | 意図した動きを持つテイクを選べる |
| 3 | Qwen3-TTSまたはStyle-Bert-VITS2の日本語 | 固有名詞と語尾を確認できる |
| 4 | 声と環境音を編集で合成 | ずれ、音割れ、欠けを解消できる |
| 5 | LTX、Hunyuan、A14B等との比較 | 同じ条件で結果と費用を記録できる |
| 6 | 30秒の構成へ展開 | 人物、光、進行方向がつながる |

費用比較では、採用した動画だけでなく、失敗・再生成も含める。クラウドの秒単価を固定して資料に埋めず、実行時の見積りと請求を記録する。ローカルも処理時間、ストレージ、電力を含めて判断する。
