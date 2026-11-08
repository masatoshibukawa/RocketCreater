# 動画の効果音

製品デモ、解説、短編映像に使う効果音の配置、制作、調達、ミックスを扱う。素材・モデル・サービスの条件は2026年11月8日確認。実際に使う音源、モデルの版、契約と提出先の条件を採用時に確認する。

## 役割とタイミングを決める

映像を一度通して見て、必要な箇所に「時刻またはフレーム／画面上の変化／視聴者に伝えること／実音か演出音か」を記す。以下の場面から該当するものを選ぶ。

| 役割 | 置き方 |
| --- | --- |
| 操作の受理や完了を伝える | 受理音は操作時、完了音は結果表示時に置く。待ち時間がある操作では二つの時点を区別する。 |
| 見落としやすい変化に注意を向ける | バッジや警告の表示に短い音の立ち上がりを合わせる。重要な状態は画面にも表示する。 |
| 切り替えを感じさせる | 文の切れ目に置き、スイッシュの山を画面の動きやカットに合わせる。 |
| 動きに手触りや距離感を与える | 足が着く、扉が閉まる、物が触れるフレームに打音を合わせ、必要に応じて距離と残響を調整する。 |

同期した短音が対象の発見を助けた視覚探索実験と、内容に無関係な音で学習成績が下がった教材実験がある。デモに応用するときは、音あり・なしを同じ映像で比べ、視線を向ける助けになった音を残す。製品の実際の出力音が証拠になる場面では実音を聞かせる。理解に必要な音は字幕にも含める。 [視覚探索の原著](https://pubmed.ncbi.nlm.nih.gov/18823194/) · [教材音声の原著](https://tecfa.unige.ch/tecfa/teaching/methodo/Moreno_Mayer00.pdf) · [W3Cの字幕ガイド](https://www.w3.org/WAI/media/av/captions/)

## 録る・合成する・探す

- **フォーリー**。静かな場所で紙、足音、机や留め具の音をマイクに近づけて録る。強さや材質を変えて数テイク作り、接触に波形の立ち上がりを合わせる。遠くで鳴る描写なら、画に合わせて音量や残響を調整する。 [ACMIのフォーリー教材](https://www.acmi.net.au/education/school-program-and-resources/foley-sound/) · [Adobeの効果音制作ガイド](https://www.adobe.com/creativecloud/video/discover/sfx-for-video)
- **合成**。完了音の試作なら Audacity の **Generate → Chirp** で正弦波を 550 Hz から 850 Hz へ 0.18 秒で上げ、末尾を短くフェードする。風切り音はノイズにフィルターとフェードを使って音の山を作る。衝撃音の立ち上がり、低い響き、残響は別素材にすると映像に合わせて動かしやすい。 [AudacityのChirp](https://www.audacityteam.org/manual/generators/chirp/) · [ジェネレーター一覧](https://www.audacityteam.org/manual/menu-bar/generate/) · [フェードの作り方](https://manual.audacityteam.org/man/creating_fades_with_the_envelope_tool.html)
- **既存素材**。`完了音 短い`、`soft UI confirmation chime`、`dry plastic latch click` のように、音源・動作・材質・長さ・残響で絞る。候補は単体と映像上の両方で試聴する。素材ごとに配布元とライセンスを確認できるものを選ぶ。 [効果音ラボ](https://soundeffect-lab.info/) · [Freesoundのライセンスと検索](https://freesound.org/help/faq/) · [YouTube Studioのカテゴリ・長さ検索](https://support.google.com/youtube/answer/3376882?hl=ja)

## ナレーションと混ぜる

1. 声、効果音、環境音、BGMを分け、声と必要な実音から決める。音の立ち上がりをマーカーに合わせ、声に重なる音は小さい状態から上げる。
2. 初回試聴の例として、近くの声のピークが −9 dBFS なら、重なる短い通知音を −21 dBFS 前後から試す。これはピークの仮置き。音色と長さによって聞こえ方が変わるため、数字・固有名詞・子音を聞き取れるかで調整する。
3. 声にかぶるときは、意味が変わらない範囲で文の切れ目に移す、短くする、クリップゲインを下げる。環境音やBGMが長く重なる場合は発話中だけ下げるダッキングも使う。
4. 書き出した動画をイヤホンと小音量のスマホスピーカーで聞く。短音の飛び出しやクリッピングはピーク、全体のラウドネスは統合LUFSで見て、納品仕様があればそれに合わせる。無音でも重要な状態が分かることを確認する。 [Adobeのダッキング](https://helpx.adobe.com/ph_en/premiere/desktop/add-audio-effects/adjust-volume-and-levels/automatically-duck-audio.html) · [EBUのラウドネス勧告](https://tech.ebu.ch/publications/r128)

WCAG 1.4.7（AAA）の 20 dB 差は、主に発話を含む収録済みの音声のみのコンテンツにおける選択肢の一つ。時折鳴る1〜2秒の音には例外がある。動画では声の明瞭さを守る参考として使う。 [W3Cの適用条件](https://www.w3.org/WAI/WCAG21/Understanding/low-or-no-background-audio)

## 公開・納品に使えるか確かめる

- **録音ファイルの権利**。日本で映画・ゲームなどの音を利用する場合、著作権や、該当する録音物に対するレコード製作者の複製権・送信可能化権などを確認する。短い抜粋、ピッチ変更、クレジットを付ける場合も、利用できる根拠を確認する。 [著作権法 第2条・第21条・第23条・第96条・第96条の2](https://laws.e-gov.go.jp/law/345AC0000000048)
- **CCライセンス**。CC0は通常表示不要。CC BY 4.0は商用利用・加工が可能で、作者、出典、ライセンス、変更の有無を表示する。CC BY-NCは非営利に限られるため、販促や顧客案件では商用可の素材を選ぶ。ND付きの録音を動画に同期して公開する場合は別途許諾を確認する。 [CC0](https://creativecommons.org/publicdomain/zero/1.0/deed.ja) · [CC BY](https://creativecommons.org/licenses/by/4.0/deed.ja) · [CC BY-NC](https://creativecommons.org/licenses/by-nc/4.0/deed.ja) · [Creative Commons FAQ](https://creativecommons.org/faq/)
- **配布形態と規約**。効果音ラボでは通常の動画での商用利用と加工が可能で、クレジットは任意。素材単体や加工済み素材の再配布、音源入りの配布用テンプレート、AI学習用データとしての利用は規約で制限される。完成動画、編集プロジェクト、公開リポジトリはそれぞれの形で配布可否を確認する。YouTubeのオーディオライブラリを他の公開先へ使う場合も、対象音源とその条件を確認する。 [効果音ラボの利用規約](https://soundeffect-lab.info/agreement/) · [YouTube公式ヘルプ](https://support.google.com/youtube/answer/3376882?hl=ja)

採用音源ごとに `使用箇所／音源名・作者／配布ページ／取得日／ライセンス・プラン／加工と表示内容／音源ファイルの再配布可否` を控える。採用先の規約が不明なら許諾が確認できる素材を選ぶ。細かい比較には [出典と利用条件](../../video-research-rights/SKILL.md) を参照する。

## AI生成を選ぶ

| 入力 | 使いどころ | 確認先 |
| --- | --- | --- |
| テキスト | 独立した通知音、機械音、環境音。単発とループを指定する。 | ElevenLabs Sound Effects は API で 0.5〜30秒を指定できる。無料生成物は非商用で、公開時は指定表記が必要。有料期間中の生成はベータ機能などを除き規約の範囲で商用可。 [生成仕様](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert) · [公開条件](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform) |
| 声のガイドとテキスト | 自分で「シュッ、カチッ」と鳴らし、間隔や強弱をガイドする。 | Adobe Firefly でガイドと音色の指示を組み合わせる。 [制作手順](https://helpx.adobe.com/firefly/web/work-with-audio-and-video/work-with-audio/voice-to-sound-effects.html) · [利用条件](https://helpx.adobe.com/firefly/web/get-started/learn-the-basics/adobe-firefly-faq.html) |
| 参照音声とテキスト | 自録りの打音を機械音にするなど、元のリズムや質感を使う。 | Stable Audio 3.0 の音声入力。モデル・プランの条件と参照音を外部サービスへ入力できるかを確認する。 [制作ガイド](https://stability.ai/guides/stable-audio-3-prompt-guide) · [利用条件](https://kb.stability.ai/knowledge-base/stable-audio-commerical-and-usage-licensing) |
| 映像 | 無音ショットへ足音や接触音をまとめて仮付けする。 | MMAudio の配布重みは CC BY-NC 4.0。生成結果の接触位置と余計な音を確認する。 [公式リポジトリ](https://github.com/hkchengrex/MMAudio) · [重みの条件](https://github.com/hkchengrex/MMAudio/releases) |

文章には音源、動作、回数、材質、距離、残響、余韻を必要に応じて書く。完了音の試作例は `A single soft electronic confirmation chime, two ascending notes, quick attack, dry, short decay, no music or voice.`。0.5 秒で数案作り、必要部分を切り出して末尾をフェードし、結果表示に同期させる。ループは継ぎ目をまたいで聞き、混入した声や音楽、音割れを確認する。 [ElevenLabsのプロンプトガイド](https://elevenlabs.io/docs/overview/capabilities/sound-effects)

既存作品の固有音を再現したい場合は、元の権利と許諾を先に確かめる。一般的な音なら材質や時間変化を指定する。生成物の利用規約、参照音源の権利、既存作品との類似性・依拠性を個別に確認する。生成物自体の著作物性は人の創作的寄与に応じた別の判断になる。モデル・生成日・プラン・プロンプト・採用テイク・編集内容を記録し、提出要項に応じてAI利用を申告する。 [文化庁「AIと著作権について」](https://www.bunka.go.jp/seisaku/chosakuken/aiandcopyright.html)
