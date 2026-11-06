# PCごとの導入・検出・転送の確認

2026-11-06。OS名だけでなく、CPU、ソフトの版、送信モジュール、物理接続を組み合わせる。以下は公式資料に基づく判断手順で、全環境の接続実験ではない。

## Windows

- x64とARMを先に確認し、対応する配布を使う。x64ソフトがエミュレーションで起動しても、同梱のプラグイン・USBドライバーまで動くとは断定しない。PreFormの確認した要件ではWindows ARMは非対応。
- 信頼する研究室／家庭のLANと、公衆・ゲストネットワークを区別する。Windowsのdomain/private/publicで適用規則が異なる。対象アプリの必要な通信条件を確認し、全ファイアウォールの無効化を初手にしない。[Microsoft：Firewallとプロファイル](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/)
- ネットワーク検出、実機のIPへの到達、アプリ側の認証を分ける。検出されないからといってWindowsの紙用プリンタードライバーへ3Dプリンターを登録しない。該当スライサー／管理ソフトから登録する。
- USBケーブル方式の対応機では、充電専用ケーブルやUSBハブ、認識されたデバイスと必要な機種用ドライバーを確認する。S5／UM3のUSBメモリー経路へ、シリアルCOMの設定を追加しない。

## macOS：IntelとApple Silicon

- 実際のCPUとmacOS版に対応するIntel／Apple Silicon／Universal配布を選び、必要なネットワークモジュールもそろえる。旧Intelプラグインをそのまま使えると仮定しない。
- 該当macOSでは「システム設定→プライバシーとセキュリティ→ローカルネットワーク」で、使用するアプリの許可を確認する。アプリ更新や初回導入後の検出失敗では、ルーターより先にこの状態を確認できる。[Apple：Local Networkのアクセス設定](https://support.apple.com/guide/mac-help/control-access-to-your-local-network-on-mac-mchla4f49138/mac)
- アプリは見つかるが媒体保存ができない場合、外部ボリュームの権限・空き容量・ファイルシステムを別に調べる。MacBookのUSB-Cは形状であり、媒体・データケーブル・Ethernetアダプターは異なる役割である。
- 未確認ソフトのためにOSの保護を一括無効化せず、公式署名・配布元と該当する必要権限を確認する。

## Linux

- CPUとディストリビューション、OpenGL、公式の配布形態を確認する。x86_64向けのLinux版からLinux ARM対応を推定しない。プリンター側のLinuxとPC側のLinuxも別である。
- AppImageやFlatpak等では、起動の依存、保存先、リムーバブル媒体、ネットワークの権限を分ける。PrusaSlicer／OrcaSlicerは版別に配布方法が変わるので、古い導入コマンドを固定しない。[PrusaSlicer公式リリース](https://github.com/prusa3d/PrusaSlicer/releases)、[OrcaSlicer公式リリース](https://github.com/OrcaSlicer/OrcaSlicer/releases)
- スライサー本体とネットワークプラグインの両方を確認する。ChituManagerのOS別配布と、Basicのスライス対応は別条件。Anycubic Next／Photon Workshopは、参照したQuick StartだけでLinux対応を断言できない。
- Form 4をLinux PCから扱いたい場合、PreFormの公式対応PCへスライス・転送を分担するか、機種対応のWeb管理の範囲を調べる。LinuxネイティブのPreFormがあるとして導入手順を作らない。

## ノート・デスクトップ・リモートPC

ノートPCのドック切替、Wi-Fi切断、スリープ中の挙動を確認する。USBシリアルで逐次送る方式と、先に全ファイルを本体へ転送する方式は異なるため、PCをいつ切り離せるかも機種資料に従う。媒体経路は書出し完了・安全な取り外し後、本体側でジョブを選ぶ。

リモートデスクトップではGPUや検出用ネットワークが別条件になる。Curaの公式説明ではRDP・仮想環境等は対応外。全ソフトが同じ制限とはせず、実行しているPCと手元の画面、プリンターが存在するLANを明確にする。[Curaの対応OSと環境](https://support.ultimaker.com/s/article/1667337917781)

## ソフトとCPUを照合する表

「版別確認」は対応の保証ではない。導入する版の配布物と要件を調べる。

| ソフト | 公式資料で確認したOSの範囲 | CPU／接続モジュールで残る確認 |
| --- | --- | --- |
| Cura | Windows 64-bit、macOS Intel/M系、Linux 64-bit | Windows ARMは版別配布。USB-cable機能も版・機種別 |
| Bambu Studio | Windows、macOS、Linux | CPU別配布とBambu Networkプラグイン |
| OrcaSlicer | Windows、macOS、Linuxの公式配布 | CPU／パッケージ、ホストAPI、Bambu等の認証方式 |
| PrusaSlicer | Windows、macOS、Linuxの公式配布 | Linuxの配布形態と物理プリンターの送信先 |
| Creality Print | 公式説明とリリースにWindows／macOS／Linuxの記載 | 古い最低要件より、その版の配布・CPU・機種対応を優先 |
| Anycubic Slicer Next | Quick StartはWindows／macOS | Linux・ARMはこの資料だけでは未確認。旧Slicerと区別 |
| CHITUBOX／ChituManager | Windows／macOS／UbuntuのOS欄 | 本体と管理モジュールを別々に版・機種と照合 |
| Photon Workshop | 参照マニュアルはWindows／macOS、Intel/M1の条件 | Linux／Windows ARMはこの資料だけでは未確認 |
| PreForm | Windows 64-bit（ARM非対応）、macOS | Linuxは公式対応OSに含まれない |

一次資料：[Cura](https://support.ultimaker.com/s/article/1667337917781)、[Bambu Studio](https://wiki.bambulab.com/en/software/bambu-studio/studio-quick-start)、[Creality Print公式リリース](https://github.com/CrealityOfficial/CrealityPrint/releases)、[Next](https://wiki.anycubic.com/en/software-and-app/new-page-anycubic-slicer-beta%28orca-version%29/anycubic-slicer-next-slicing-software-quick-start-guide)、[CHITUBOX導入](https://docs.chitubox.com/en-US/chitubox-basic/latest/installation)、[ChituManager](https://docs.chitubox.com/en-US/chitu-manager/latest/introduction)、[Photon Workshop](https://wiki.anycubic.com/photon-mono-m7-pro/anycubic_photon_workshop-en-v0.2.0-b.pdf)、[PreForm](https://formlabs.com/support/What-are-the-system-requirements-to-run-PreForm)

## 記録する状態

機種と構成／ソフトと版／OSとCPU／経路、検出結果、認証結果、転送結果、実機開始の有無、止まった段階と根拠を記録する。ローカルIP、APIキー、パスワード、アクセスコード、機器固有番号は共有資料に埋め込まない。[未実施状態の記録例](connection-record.example.json)を必要に応じてコピーする。
