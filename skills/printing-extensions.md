# 3Dプリント拡張のスキル索引（未統合）

[全体索引へ戻る](README.md)

[PR #53](https://github.com/masatoshibukawa/RocketCreater/pull/53) の追加85件です。確認日：2026-11-07、参照コミット：[`da2667e`](https://github.com/masatoshibukawa/RocketCreater/commit/da2667e0f5b78756807ee8d49c6b957ebbd72f95)。このPRの3Dスキルは、[mainの既存9件](README.md#3dモデル制作9件)と合わせて94件です。

スキル名は確認コミット内のファイルへリンクしています。利用する際は、その版のスキルと同じ版の参照資料を使ってください。

| 分類 | 追加件数 | 内容 |
| --- | ---: | --- |
| 接地と速度 | 2 | 倒れ・反り、特徴別速度・流量・冷却 |
| PCとソフトの接続 | 10 | 接続案内と各スライサーの検出・認証・転送 |
| 機種別 | 18 | 家庭・業務向けFDMと光造形、プロファイル案内 |
| 材料と組み合わせ | 28 | 樹脂・レジン・支持材・合金、適合と置き換え |
| カーボン・金属の工程 | 7 | 繊維、LPBF、EB-PBF、結合材、DED |
| カーボン・金属の機種 | 12 | 工業機の構成、専用材料、周辺設備と後処理 |
| キャラクターフィギュア | 5 | 参照・形状、分割・嵌合、印刷確認と塗装 |
| 品質と結果の引き継ぎ | 3 | 最終出力、ツールパス、条件付きの改善知見 |

## 接地と速度（2件）

| スキル | 使う場面 |
| --- | --- |
| [3d-print-bed-stability](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/categories/3d-print-bed-stability/SKILL.md) | FDMで接地面が小さい、高い薄い部品が倒れる、反る、支持が倒れる問題を、向き・接地接続・ブリム・揺れ・衝突へ切り分けて改善する。 |
| [3d-print-speed-calibration](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/categories/3d-print-speed-calibration/SKILL.md) | FDMの速すぎる造形、揺れ、高速部の欠け、短い層の熱変形を、特徴別速度・加速度・最大体積流量・冷却へ分けて校正する。 |

## PCとソフトの接続（10件）

| スキル | 使う場面 |
| --- | --- |
| [3d-print-connect-anycubic-next](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-anycubic-next/SKILL.md) | 元のKobra3をAnycubic Slicer Nextへ接続し、LAN Modeとクラウドを分ける。旧SlicerやPhoton Workshopの接続と混同しない。 |
| [3d-print-connect-bambu-studio](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-bambu-studio/SKILL.md) | Bambu Studioのネットワークプラグイン、クラウドとLAN Only、IPとアクセスコード、PC別の導入・検出・認証を確認する。 |
| [3d-print-connect-chitubox](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-chitubox/SKILL.md) | CHITUBOXとChituManagerで対応レジン機へLAN送信する。OS別のスライス機能と管理モジュール、機種別形式を分けて確認する。 |
| [3d-print-connect-creality](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-creality/SKILL.md) | Creality PrintでSE/KE/K1Cの対応転送方式とOSを選び、LAN追加、認証、クラウドと媒体を切り分ける。 |
| [3d-print-connect-cura](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-cura/SKILL.md) | UltiMaker CuraからS5/Ultimaker3等へLAN・Digital Factory・媒体で接続する。検出失敗やPC差を調べ、対応機種だけのUSBケーブル機能と区別する。 |
| [3d-print-connect-orca](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-orca/SKILL.md) | OrcaSlicerの物理プリンター、Moonraker/Octo系ホスト、Bambuプラグインを機種と版で選ぶ。モデル用プロファイルと通信対応を区別する。 |
| [3d-print-connect-photon-workshop](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-photon-workshop/SKILL.md) | Photon WorkshopでM7Pro等の機種用データを生成し、対応USB媒体または公式Wi-Fi経路で渡す。Kobra用LAN機能とは区別する。 |
| [3d-print-connect-preform](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-preform/SKILL.md) | PreFormとForm4のUSBケーブル・Ethernet・Wi-Fi接続、Dashboardとローカルの差、Windows/macOSのPC要件を確認する。 |
| [3d-print-connect-prusa](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-print-connect-prusa/SKILL.md) | PrusaSlicerからPrusaLinkローカルまたはPrusa Connectクラウドへ送る。MK4S/COREOneの接続、USB媒体とPC差を確認する。 |
| [3d-printer-connection](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/connections/3d-printer-connection/SKILL.md) | 機種・ソフト・PCのOS/CPUから接続経路を選び、検出・認証・転送・開始を切り分ける。USB媒体・ケーブル、LAN・クラウドを取り違えない。 |

## 機種別（18件）

| スキル | 使う場面 |
| --- | --- |
| [3d-printer-anycubic-kobra3](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-anycubic-kobra3/SKILL.md) | 元のAnycubic Kobra 3のレベリング、材料供給、Slicer NextとLAN接続を確認する。V2/MaxやS1の設定を混同しない。 |
| [3d-printer-anycubic-m7-pro](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-anycubic-m7-pro/SKILL.md) | Photon Mono M7 Proの温調タンク、レジン・露光・支持・供給とPhoton Workshop接続を確認する。非Proの構成と区別する。 |
| [3d-printer-bambu-a1-mini](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-bambu-a1-mini/SKILL.md) | Bambu Lab A1 miniの造形範囲、可動ベッド、校正とネットワーク接続を確認する。A1向け配置やブリムを自動縮小して移さない。 |
| [3d-printer-bambu-a1](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-bambu-a1/SKILL.md) | Bambu Lab A1の可動ベッド、プレート、フローダイナミクスとBambu Studio接続を調整する。A1 miniの造形域とは区別する。 |
| [3d-printer-bambu-p1s](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-bambu-p1s/SKILL.md) | Bambu Lab P1Sの密閉環境、補助ファン、手動流量校正と接続を確認する。P1PやX1の自動校正機能と区別する。 |
| [3d-printer-bambu-x1-carbon](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-bambu-x1-carbon/SKILL.md) | Bambu Lab X1 CarbonのLidar校正、プレート・材料の制約、筐体冷却と接続を確認する。自動校正を印刷成功の証明にしない。 |
| [3d-printer-creality-ender3-v3-ke](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-creality-ender3-v3-ke/SKILL.md) | Ender-3 V3 KEの校正、ソフト版、可動ベッドとLAN/USB媒体接続を確認する。SEと異なる機種設定を保つ。 |
| [3d-printer-creality-ender3-v3-se](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-creality-ender3-v3-se/SKILL.md) | Ender-3 V3 SEの専用プロファイル、初層、機械状態と媒体接続を確認する。KEや無印V3の高速・ネットワーク設定を移さない。 |
| [3d-printer-creality-k1c](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-creality-k1c/SKILL.md) | Creality K1Cの材料プロファイル、校正、筐体とネットワークを確認する。K1/K1 Max/K1C 2025の構成差を先に照合する。 |
| [3d-printer-elegoo-mars5-ultra](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-elegoo-mars5-ultra/SKILL.md) | Mars 5 Ultraのティルト剥離、自動レベリング、露光・支持とCHITUBOX接続を確認する。Mars5や他機種の動作・露光値をコピーしない。 |
| [3d-printer-elegoo-neptune4-pro](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-elegoo-neptune4-pro/SKILL.md) | Neptune 4 Proの補助手動調整とメッシュ、金属PEI、補助冷却、EthernetとWeb接続を確認する。Plus/MaxのWi-Fiと混同しない。 |
| [3d-printer-elegoo-saturn4-ultra-12k](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-elegoo-saturn4-ultra-12k/SKILL.md) | 元のSaturn 4 Ultra 12Kのティルト剥離、レベリング、レジンとLAN送信を確認する。16K世代の機能・露光・加温を前提にしない。 |
| [3d-printer-formlabs-form4](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-formlabs-form4/SKILL.md) | Formlabs Form4の材料・タンク・PreForm、向き・支持・カップとPC接続を確認する。Form3等の設定を流用しない。 |
| [3d-printer-profiles](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-profiles/SKILL.md) | 正確な型番・世代から機種別の印刷・校正・接続スキルを選ぶ。似た機種やスライサー間の設定の取り違えを防ぐ。 |
| [3d-printer-prusa-core-one](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-prusa-core-one/SKILL.md) | 元のPrusa CORE Oneの筐体・ノズル・ロードセル・ネットワーク条件を確認する。CORE One+、Gen2、L、INDXの機能を混同しない。 |
| [3d-printer-prusa-mk4s](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-prusa-mk4s/SKILL.md) | Prusa MK4Sのロードセル初層、高流量ノズルとプロファイル、可動ベッド、PrusaLink/Connect接続を確認する。MK4やCORE Oneと区別する。 |
| [3d-printer-ultimaker-3](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-ultimaker-3/SKILL.md) | Ultimaker 3のAA/BBコア、active leveling、CuraとLAN接続を確認する。S5やExtendedの設定をそのまま移さない。 |
| [3d-printer-ultimaker-s5](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/printers/3d-printer-ultimaker-s5/SKILL.md) | S5のガラス・2.85 mm材料・AA/BBコアとCuraで、接地、速度、終盤転倒、接続を点検する。S6/S7や汎用1.75 mm設定へ転用しない。 |

## 材料と組み合わせ（28件）

| スキル | 使う場面 |
| --- | --- |
| [3d-material-abs](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-abs/SKILL.md) | ABSの反り・層割れ・収縮と、必要な熱環境・排気・機械対応を確認する。ABS-likeレジンは対象外で、レジンの専用スキルを使う。 |
| [3d-material-asa](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-asa/SKILL.md) | ASAの屋外用途、反り、収縮、層割れと機械の熱環境を評価する。耐候性の訴求を、今回の荷重・使用温度・寿命の確認と分ける。 |
| [3d-material-breakaway-support](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-breakaway-support/SKILL.md) | UltiMaker Breakaway等の剥離用支持材を製品別に扱い、本体/コアの対応・界面・機械的除去経路を確認する。同材支持や水溶性支持とは分ける。 |
| [3d-material-engineering-resin](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-engineering-resin/SKILL.md) | Tough/ABS-like、柔軟、耐熱等の工学用レジンを用途と製品別に選ぶ。試験条件、専用プロファイル、洗浄・硬化と混合の可否を扱う。 |
| [3d-material-fiber-filled](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-fiber-filled/SKILL.md) | CF/GF等の繊維充填フィラメントを基材ポリマーに重ねて評価する。ノズル・給材の摩耗、詰まり、熱条件、異方性と層間性能を確認する。 |
| [3d-material-foaming-pla](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-foaming-pla/SKILL.md) | LW-PLA等の能動発泡/既発泡材料を区別し、温度・滞留時間・流量・壁厚と実効密度を校正する。軽量部品への置き換えや質量見積りに使う。 |
| [3d-material-machine-match](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-machine-match/SKILL.md) | 3Dプリンターと材料製品の適合を、径・コア/ノズル・温度・囲い・送り装置・プレート・乾燥まで照合する。新材料導入や周辺品交換時に使う。 |
| [3d-material-nylon](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-nylon/SKILL.md) | PA6/PA12/PA11や共重合ナイロン等を製品別に選び、吸湿・乾燥・給材・反り・寸法と層間強度を評価する。繊維入りPAは複合材スキルを併用する。 |
| [3d-material-pairing](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pairing/SKILL.md) | 複数色・異種ポリマー・本体と支持材の同時造形やレジン混合を評価する。接合強度、支持の離型、パージ、熱条件、メーカー指定の混合範囲を分けて扱う。 |
| [3d-material-pc](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pc/SKILL.md) | PC/PC Blendの吸湿・高温条件・反り・層割れ・プレート損傷を製品別に扱う。耐熱部品への採用や他材料からの置き換えに使う。 |
| [3d-material-pet](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pet/SKILL.md) | PET系とPET CFをPETGと区別し、製品・機種/コア・吸湿・反り・熱処理前後の寸法と強度を確認する。繊維入りでは摩耗条件も併用する。 |
| [3d-material-petg](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-petg/SKILL.md) | PETGの糸引き、ブリッジ、プレート過剰密着、寸法と支持除去を扱う。PETやPET-CF、PETG高速用等の製品差にも注意して選定・印刷条件を整える。 |
| [3d-material-pla](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pla/SKILL.md) | 未充填PLAの選定・初層・冷却・薄肉・熱変形を扱う。外観試作やPLAの印刷不良に使い、Tough/PLA+、繊維入り、発泡品は専用スキルを併用する。 |
| [3d-material-pp](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pp/SKILL.md) | PPの低い接地性、反り、専用シート/接着剤、柔らかさと嵌合を扱う。支持材の接着不足や他材料からの置き換えも製品別に確認する。 |
| [3d-material-pps](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-pps/SKILL.md) | PPS系とPPS CFの製品別熱環境、機械・耐摩耗コア、支持、乾燥と層間/熱処理条件を確認する。高耐熱という名称だけで汎用機へ採用しない。 |
| [3d-material-soluble-support](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-soluble-support/SKILL.md) | PVA/BVOHの乾燥・機種/コア・本体との界面・パージ・除去を確認する。複雑形状や内部支持を水で除くFDM造形に使う。水洗いレジンとは別。 |
| [3d-material-standard-resin](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-standard-resin/SKILL.md) | 標準/模型用レジンの機種・製品世代・色・露光・支持・洗浄/硬化を合わせる。細部の再現、支持欠損、寸法試作を行う光造形に使う。 |
| [3d-material-substitution](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-substitution/SKILL.md) | 既存モデルを別の材料・ブランド・充填材・発泡材・レジンへ置き換える際に、機械適合、寸法、剛性、層間強度、質量と重心を再評価する。 |
| [3d-material-tough-pla](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-tough-pla/SKILL.md) | Tough PLA、PLA+等の改質PLAを製品別に扱う。通常PLAとの置き換え、実際のS5/Tough PLA Gray/AA0.4の試行、靱性と耐熱の混同を確認する。 |
| [3d-material-tpu](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-tpu/SKILL.md) | TPU/TPEの硬度・送り経路・巻き付き・糸引き・過剰密着を扱う。柔軟部品の設計、Bowden/直接給材、AMS等との適合を確認するときに使う。 |
| [3d-material-water-wash-resin](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-material-water-wash-resin/SKILL.md) | 水洗いレジンの製品世代・洗浄槽・浸漬時間・乾燥・二次硬化・中空部と廃液を扱う。水洗いABS-like等は工学用レジンも併用する。 |
| [3d-metal-aluminum](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-aluminum/SKILL.md) | AlSi10Mg等の金属AM用アルミ合金を製品と方式別に選び、熱処理・熱/電気伝導・疲労・支持・粉末取り扱いを評価する。 |
| [3d-metal-copper](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-copper/SKILL.md) | 純銅やCuCrZr等の金属AM用銅系を熱/電気伝導と強度から選ぶ。光学系・供給形態・後処理・密度/欠陥と最終伝導性を確認する。 |
| [3d-metal-nickel-alloy](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-nickel-alloy/SKILL.md) | IN625/IN718等の金属AM用ニッケル合金を熱・腐食・荷重から選定する。機種・供給形態・熱処理状態と、割れ/変形・加工・検査を評価する。 |
| [3d-metal-stainless-steel](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-stainless-steel/SKILL.md) | 316Lと17-4PH等の金属AM用ステンレスを選定する。合金規格・供給形態・機種/世代・焼結や熱処理状態・耐食と強度を確認する。 |
| [3d-metal-titanium](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-titanium/SKILL.md) | Ti6Al4V Grade 5/23や工業用純チタンの金属AMを選定し、供給形態・装置/PDS・酸素管理・熱処理/HIP・表面と疲労を評価する。 |
| [3d-metal-tool-steel](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-metal-tool-steel/SKILL.md) | H13、A2、D2等の金属AM用工具鋼を用途・製品世代と熱処理状態から選ぶ。焼結/造形後の硬度、割れ・反り、加工と検査を評価する。 |
| [3d-print-materials](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/materials/3d-print-materials/SKILL.md) | 3Dプリントの材料選定、製品別設定、機種との適合、複数材料の併用、材料変更を整理して専門スキルへ案内する。材料が既知なら該当する材料スキルと機種スキルを併用する。 |

## カーボン・金属の工程（7件）

| スキル | 使う場面 |
| --- | --- |
| [3d-carbon-metal-printing](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-carbon-metal-printing/SKILL.md) | カーボン系と金属の3Dプリンター、材料、造形方式、周辺設備、後処理を整理して専門スキルへ案内する。短繊維と連続繊維、金属風樹脂と実金属を区別する。 |
| [3d-print-continuous-fiber](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-continuous-fiber/SKILL.md) | 連続カーボン・ガラス・アラミドと樹脂マトリックスの造形を評価する。繊維経路、曲率、切断、配置可能層、層間と荷重を確認し、短繊維入りFDMと区別する。 |
| [3d-print-metal-binder-jet](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-metal-binder-jet/SKILL.md) | 金属粉末床へバインダーを噴射し、硬化・粉抜き・脱脂/焼結で完成させる方式を計画する。造形中の支持と焼結治具、グリーン品の保持・収縮を確認する。 |
| [3d-print-metal-bound](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-metal-bound/SKILL.md) | 金属粉末を結合材に含むFFF/Bound Powder Extrusionの機械・材料・脱脂・焼結を計画する。金属風樹脂、グリーン品、最終金属を区別する。 |
| [3d-print-metal-ded](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-metal-ded/SKILL.md) | レーザーDEDのワイヤー/粉末、アーク方式WAAMを材料・熱入力・基板・加工代から比較する。大型造形、肉盛り、補修、異材界面を計画するときに使う。 |
| [3d-print-metal-eb-pbf](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-metal-eb-pbf/SKILL.md) | EB-PBFの真空・予熱された粉末床、材料/パラメーター、支持と粉末ケーキからの取り出しを評価する。LPBFの条件を流用せず、機種・版と後処理を照合する。 |
| [3d-print-metal-lpbf](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/3d-print-metal-lpbf/SKILL.md) | 金属LPBF（DMLS/SLM等）の機械・粉末・パラメーター・配置・熱と支持・粉抜き・後加工を計画する。粉末床の支持と最終検査を確認するときに使う。 |

## カーボン・金属の機種（12件）

| スキル | 使う場面 |
| --- | --- |
| [3d-printer-anisoprint-composer](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-anisoprint-composer/SKILL.md) | Composer A4/A3のCFC、専用繊維・マトリックス/外周用樹脂、切断・給材・Zオフセットを確認し、経路と荷重を評価する。 |
| [3d-printer-colibrium-spectra-l](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-colibrium-spectra-l/SKILL.md) | Spectra LのEB-PBF、Ti6Al4V Grade5/23、ソフト/Point Meltと粉末回収・後処理を照合する。Spectra H等とは個別に扱う。 |
| [3d-printer-dmg-lasertec-65-ded](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-dmg-lasertec-65-ded/SKILL.md) | LASERTEC 65 DED hybrid第2世代の粉末DEDと5軸切削を計画し、母材/粉末・ノズル校正・到達性・熱履歴・加工順を評価する。 |
| [3d-printer-eos-m290](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-eos-m290/SKILL.md) | EOS M 290の金属LPBFを粉末製品・層厚・パラメーターID・ソフト、粉末/ガス・支持・後処理の組で確認する。他EOS機の条件を移さない。 |
| [3d-printer-hp-metal-jet-s100](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-hp-metal-jet-s100/SKILL.md) | S100 Platformの構成別の硬化・有効造形域・粉末/材料検証区分と、粉抜き・焼結・工程能力を確認する。旧仕様と現行構成を分ける。 |
| [3d-printer-markforged-fx10](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-markforged-fx10/SKILL.md) | FX10の複合材/Metal Kit構成、製品世代別材料、シート・ヘッド・校正とWash/Sinterを照合する。同一部品の任意の金属/繊維混在とは分ける。 |
| [3d-printer-markforged-mark-two](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-markforged-mark-two/SKILL.md) | Mark Twoの樹脂/連続繊維とGen1/2・旧構成を照合し、繊維配置と層間、給材・校正を評価する。Onyx Pro等の機能を推定で補わない。 |
| [3d-printer-markforged-metal-x](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-markforged-metal-x/SKILL.md) | Metal Xの金属FFF・製品世代別材料、Wash-1/Sinter-1/2、界面材と脱脂判定を確認する。FX10の316L対応を流用しない。 |
| [3d-printer-meltio-m600](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-meltio-m600/SKILL.md) | M600のワイヤーレーザーDEDを材料パラメーター・基板・経路・冷却/ガスと加工代で確認する。M450や開発中の合金条件を移さない。 |
| [3d-printer-raise3d-e2cf](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-raise3d-e2cf/SKILL.md) | Raise3D E2CFの短繊維材、耐摩耗給材、IDEX、ドライボックスと専用支持材を照合する。E2/連続繊維機との違いを扱う。 |
| [3d-printer-raise3d-forge1](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-raise3d-forge1/SKILL.md) | Forge1の金属FFFとMetalFuseの触媒脱脂・焼結、ideaMaker Metal、材料供給/受託先の条件を確認する。造形域と最終金属寸法を分ける。 |
| [3d-printer-ultimaker-factor](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/industrial/printers/3d-printer-ultimaker-factor/SKILL.md) | Factor 4とFactor 4+の短繊維材・PPS CF/PET CFとHT/CC/CC+コアの世代差を照合する。S5の耐摩耗化と同一視しない。 |

## キャラクターフィギュア（5件）

| スキル | 使う場面 |
| --- | --- |
| [3d-character-figurines](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/figurines/3d-character-figurines/SKILL.md) | ポケモン等のキャラクターをプラスチックの展示用フィギュアへ仕上げる工程を整理する。参照と形状、分割/台座、FDM/光造形、配色と塗装をつなぎ、専用スキルへ案内する。 |
| [3d-figurine-finishing](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/figurines/3d-figurine-finishing/SKILL.md) | プラスチックのフィギュアを支持除去・洗浄/硬化から仮組み、接着、表面処理、塗装と完成確認へつなぐ。細部・嵌合を塗膜や研磨で失わないよう製品別に扱う。 |
| [3d-figurine-print-review](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/figurines/3d-figurine-print-review/SKILL.md) | FDM/光造形フィギュアを最終サイズで確認し、顔と薄部、支持痕、接地、中空の排液、色の経路を評価する。多色変換や自動修復後の検証にも使う。 |
| [3d-figurine-reference](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/figurines/3d-figurine-reference/SKILL.md) | キャラクターフィギュアの参照を揃え、AI生成/彫刻で顔・輪郭・背面・凹凸を評価する。テクスチャの似姿と実際の形状、生成された見えない部分を区別する。 |
| [3d-figurine-split-fit](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/figurines/3d-figurine-split-fit/SKILL.md) | フィギュアの耳・尻尾・足の根元、隠せる切断面、ダボ/キー、接着と塗装の隙間、展示台座と印刷用接地を設計する。縮小や自動分割後の再評価にも使う。 |

## 品質と結果の引き継ぎ（3件）

| スキル | 使う場面 |
| --- | --- |
| [3d-model-export-verification](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/quality/3d-model-export-verification/SKILL.md) | 編集・修復・縮尺変更後の3D出力を再読込し、単位、姿勢、実寸、部品と意図した形状差分を確認する。STL/3MFの受け渡しや自動修復の評価に使う。 |
| [3d-print-outcome-learning](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/quality/3d-print-outcome-learning/SKILL.md) | 3Dプリントの成功・失敗を試行IDと条件付きの改善知見に整理し、次回に適用できる範囲を判断する。接地・速度・支持・嵌合の再試行と結果の引継ぎに使う。 |
| [3d-print-toolpath-review](https://github.com/masatoshibukawa/RocketCreater/blob/da2667e0f5b78756807ee8d49c6b957ebbd72f95/3d%20model/3d-model-skills/quality/3d-print-toolpath-review/SKILL.md) | スライス後の層画像・G-code・機種別データから、実際の接地、支持、部品、速度指令とプロファイルの対応を確認する。設定だけでは判断できない印刷前検証に使う。 |
