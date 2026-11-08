# 光造形で失敗を減らす

調査日：2026-11-06。FDMの接地・速度と、レジンの底層接着・支持・剥離を区別する。全機種共通の露光秒数や固定の45°は設定しない。

| 症状 | 分けて調べること | 次の比較 |
| --- | --- | --- |
| プレートに何も付かない | 底露光、プレート固定・校正、レジン温度、光学系、膜と異物 | 対応する既知の小試験を、同じ材料と温度で確認 |
| 底層だけ残る | 底から通常層への遷移、通常露光、剥離、急な断面 | どの層で分離したかを記録 |
| 支持だけ残る | 接点、支持の偏り、通常露光、重量、大断面・カップ | 問題の接点と断面変化を保った試験 |
| 穴が閉じる・合わない | 露光、光の回り込み、設計寸法、洗浄・硬化後の収縮 | 同じ処理後の穴とピンを実測 |
| 途中に欠け・剥離が出る | 孤立した層、薄い接続、膜・異物、剥離と補給 | 層画像で最初に成立しなくなる箇所を確認 |
| 中空部から液体が出る | 独立空洞、排液・通気・洗浄・乾燥できる経路 | 未処理の空洞を残さず開口や分割を見直す |

## 本体の方式と材料を固定する

Mars 5 Ultraと元のSaturn 4 Ultra 12Kはティルト剥離を持つ。従来のZリフトの値をそのまま移さない。Saturn 4 Ultra 16Kなど後発機の加温機能を、12K版が持つとは仮定しない。[ELEGOO：Mars 5系の差](https://us.elegoo.com/pages/elegoo-mars-5-series)、[Saturn 4 Ultra 12K](https://us.elegoo.com/products/saturn-4-ultra-12k-10inch-monochrome-lcd-resin-3d-printer)

M7 Proは温調タンク、供給・排液等の構成を持つが、温度設定だけで樹脂の状態が一定と判断しない。標準／高速レジン、層高、温度に適合する設定を使う。失敗後の硬化片を残したまま自動排液しない。[Anycubic：M7 Pro公式マニュアル](https://wiki.anycubic.com/photon-mono-m7-pro/Photon%20Mono%20M7%20Pro-EN-V0.1.0.pdf)

Form 4は対応材料・タンク・PreFormを組み合わせる。自動支持後も断面の合流とカップを確認する。空洞の向き、穴、洗浄と硬化までを設計に含める。[Formlabs：Form 4向けの配置](https://formlabs.com/support/Best-practices-for-printing-with-Form-4-generation-printers?language=en_US)、[PreFormのカップ](https://support.formlabs.com/support/Preventing-suction-cups-in-PreForm/)

## 診断用の数値を通常設定へ写さない

ELEGOOの特殊な手動レベリング手順にある底露光60/90秒は、調整する時間を確保するための値。M7 Proの不着診断にある80秒も条件付きの診断案である。これらを通常露光や全レジンの初回値として保存しない。危険な特殊手順を短い抜粋だけで実行せず、必要な場合だけ機種・版・故障条件をそろえて全文へ戻る。[ELEGOO：調整用手順](https://wiki.elegoo.com/en/mars/mars-5-u-manual-leveling-tutorial)、[Anycubic：不着の診断](https://wiki.anycubic.com/en/resin-3d-printer/photon-mono-m7-pro/model-non-stick-printing-platform)

露光の比較は材料・温度・層高を固定して底層と通常層を分ける。大きなラフトや支持増量だけでカップと剥離を解消したとみなさない。タンク内の異物、膜の損傷、漏れを確認し、材料SDSと機種手順に合う洗浄・乾燥・硬化後に合否を判定する。
