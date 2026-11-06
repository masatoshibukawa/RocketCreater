# 機種・ソフト・PCごとの接続経路

調査日：2026-11-06。接続できること、ファイルを送れること、ジョブを開始したこと、実物が完成したことを区別する。今回の調査では実機の設定変更・送信・印刷開始はしていない。実際の送信前には型番・材料・ノズル・空のプレート等を照合する。

## 機種から経路を選ぶ

「LAN」はIP通信の経路で、有線Ethernet端子を意味するとは限らない。「USB」も媒体とケーブルでは別である。SD／USBメモリーの対応形式・容量・ファイルシステムは該当機種の手順を使い、読めないからといって使用中の媒体を初手で初期化しない。

| 機種 | 基準になるソフト | 確認した主な転送経路 | 取り違えやすい点 |
| --- | --- | --- | --- |
| UltiMaker S5 / Ultimaker 3 | Cura | 本体のEthernet／Wi-Fiを使うローカル接続、対応クラウド、USBメモリー | USB媒体とPC直結ケーブル。UM3は新機種と対応ファームが異なる |
| Bambu A1 / A1 mini / P1S / X1 Carbon | Bambu Studio | Wi-Fi側のクラウドまたはLAN Only、対応カード | 初期プラグイン導入、アクセスコード、第三者ソフトとファームの認証差 |
| Prusa MK4S / CORE One | PrusaSlicer | PrusaLink（LAN）、Prusa Connect（クラウド）、対応USB媒体 | USB-CとUSBメモリー、ローカルIPとクラウドアカウント |
| Ender-3 V3 SE | 対応するCreality Print等 | 機種の対応メモリーカード | KE向けの標準ネットワーク機能を前提にしない |
| Ender-3 V3 KE / K1C | Creality Print | 対応LAN送信、クラウド、USBメモリー | K1Cの世代、LAN表記と有線端子の区別 |
| Anycubic Kobra 3 | Anycubic Slicer Next | 対応ファームのLAN Mode、クラウド、対応媒体 | 旧Anycubic SlicerとNext。LAN Modeでクラウド機能が切れる |
| ELEGOO Neptune 4 Pro | 対応スライサー＋ブラウザー／Orca | **標準は有線Ethernet**、USB媒体 | Plus/MaxのWi-Fiを4 Proの標準機能と混同しない |
| Mars 5 Ultra / Saturn 4 Ultra 12K | CHITUBOX＋ChituManager | 対応Wi-Fi／LAN転送、USBメモリー | スライサーと送信モジュールの対応OSは別確認 |
| Photon Mono M7 Pro | Photon Workshop | 対応USB媒体、公式Wi-Fi／クラウド経路 | Wi-Fi対応だけでオフラインLAN印刷を保証しない |
| Formlabs Form 4 | PreForm | **USBケーブル**、Ethernet、Wi-Fi | Dashboard接続とローカル転送、対応OSの区別 |

機種固有の根拠は[機種別スキル](../3d-model-skills/printers/3d-printer-profiles/SKILL.md)にも記載する。以下は接続判断の一次資料。

- [UltiMaker：USB媒体・ローカル・Digital Factoryの違い](https://support.ultimaker.com/s/article/1667412724591)
- [Bambu：アクセスコードでLAN接続](https://wiki.bambulab.com/en/knowledge-sharing/access-code-connect)
- [Prusa：PrusaLinkの接続設定](https://help.prusa3d.com/wp-content/uploads/generated/prusa-connect-prusalink_1636_guide_413293_en_2026-05-13.pdf)
- [Creality：K1Cの転送方式](https://www.creality.com/support/k1c-carbon-3d-printer)
- [Anycubic：Kobra 3のLAN Mode](https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/kobra-3-series-lan-connection-guide)
- [ELEGOO：Neptune 4系の有線／無線差](https://wiki.elegoo.com/neptune/neptune-4-series-web-page-control)
- [ELEGOO：Saturn 4 UltraのNetwork Sending](https://wiki.elegoo.com/saturn/saturn-4-ultra-how-to-enable-remote-printing-via-network-connection)
- [Anycubic：M7 Proの初回と媒体](https://wiki.anycubic.com/en/resin-3d-printer/photon-mono-m7-pro/-quick-start-guide-page-contents)
- [Formlabs：USB／LAN／インターネットの区別](https://formlabs.com/support/Connectivity-and-Security/)

## PCの種類を合わせる

| PC | 導入・接続の確認 |
| --- | --- |
| Windows x64 | その版のOS要件とインストーラーを確認。信頼するLANのネットワーク区分、アプリ単位の通信許可を点検。USBケーブル方式ではデータ対応ケーブルと機種用ドライバーも確認 |
| Windows ARM | x64向けソフトが起動しても、ネットワークプラグインやUSBドライバーが対応するとは限らない。版別のARM配布を照合。PreFormは確認した公式要件でARM非対応 |
| macOS Intel | 対応するmacOSとIntelビルドを選ぶ。外部ストレージ、ローカルネットワーク、プラグインの権限を必要なものだけ確認 |
| macOS Apple Silicon | Apple Silicon／Universalの配布を優先。Intel版のエミュレーションで全機能が動くと決めず、プラグインまで版を照合 |
| Linux x86_64 | 公式の配布形態・ディストリビューション条件・GPUを確認。AppImage／Flatpak等のストレージ・ネットワーク権限と、スライサー・送信モジュールの提供を別確認 |
| Linux ARM / ChromeOS / 仮想PC | x86_64 Linux対応から推定しない。Curaは公式にChromeOS・仮想環境等を非対応としている。対応PCでスライスし、機種が対応するWeb画面／媒体を使えるか別途検討 |

最低OS版・配布CPU・プラグインは更新される。古いマニュアルの最低値を現行版へ固定せず、導入時に公式配布と照合する。スライス可能なOSと、送信・カメラまで対応するOSを分ける。

- [Cura：対応OSと非対応環境](https://support.ultimaker.com/s/article/1667337917781)、[版別配布](https://github.com/Ultimaker/Cura/releases)
- [Bambu Studio：OSとネットワークプラグイン](https://wiki.bambulab.com/en/software/bambu-studio/studio-quick-start)
- [PrusaSlicer：版別配布](https://github.com/prusa3d/PrusaSlicer/releases)、[OrcaSlicer：版別配布](https://github.com/OrcaSlicer/OrcaSlicer/releases)
- [ChituManager：OS別要件](https://docs.chitubox.com/en-US/chitu-manager/latest/introduction)
- [PreForm：Windows/macOS、ARM非対応の要件](https://formlabs.com/support/What-are-the-system-requirements-to-run-PreForm)

## 見つからない・つながらない場合

1. 実機の電源、正しい型番、接続表示、IPの取得を確認する。保存済みのアドレスが現在も有効とは限らない。
2. PCと実機のLAN到達性を確認する。同じSSIDでもゲスト分離・VLANで遮断され得る。有線PCと無線プリンターでも、同じLANで通信が許可されれば使える。プリンターが対応する無線帯域と、PCの帯域は同じ問題ではない。
3. 自動検出と直接IP指定を分ける。検出用マルチキャストが届かない場合、公式の手動IP追加を試す。IPの総当たり探索や不要なネットワーク変更を行わない。
4. 本体側の認証・アクセスコード・APIキー、クラウドのアカウント／地域、LAN Onlyの切替状態を確認する。接続済みでも送信の権限が別の場合がある。
5. OSのアプリ通信許可、対応プラグイン、VPN／ゲストネットワーク等の経路を確認する。ファイアウォール・ウイルス対策を一括無効化して解決しない。必要な例外はメーカーのネットワーク要件で特定する。
6. ネットワーク機能がその構成で未対応なら、適合する媒体経路を案内する。送信テストは、印刷開始を含まない機能を選び、転送と実機開始を分けて確認する。

[UltiMaker：ネットワーク診断](https://support.ultimaker.com/s/article/1667337573408)、[必要な通信条件](https://support.ultimaker.com/s/article/1667337958118)、[Formlabs：接続と通信条件](https://formlabs.com/support/Connectivity-and-Security/)
