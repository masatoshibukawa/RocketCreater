---
name: 3d-printer-elegoo-neptune4-pro
description: "Neptune 4 Proの補助手動調整とメッシュ、金属PEI、補助冷却、EthernetとWeb接続を確認する。Plus/MaxのWi-Fiと混同しない。"
---

# ELEGOO Neptune 4 Pro

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- 純正の金属PEIシートとセンサーの前提を保持する。ガラスへ交換して同じ検出が働くと考えない。
- 公式説明の中心調整→四隅の補助手動調整→自動レベリング→初層確認を実機版に合わせる。温度とZ補正の保持、ベッドやガントリーの緩みも調べる。
- Klipper系の機種・画面・ファームの対応を確認する。メッシュ不良に対して無関係なファームを混在させたり、全設定を書き換えたりしない。
- ヘッド冷却と補助ファンを区別し、細い部品の反りと冷却不足を比較する。入力整形と高速表示は初層や接地の保証ではない。

## 最小限の比較試行

同じシートと温度で接触域の初層を確認し、全高の薄い部品1個へ進む。調整後のZとメッシュを保存して比較する。

## 接続

標準の4/4 Proは有線Ethernet。Plus/Max向けWi-Fi手順を移さない。同一LANの本体IPをブラウザーで開くか、対応版Orcaの物理プリンターで接続する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [Neptune4Pro公式マニュアル](https://elegoo-downloads.oss-us-west-1.aliyuncs.com/download.elegoo.com/06%20FDM%20Printer/02%20ELEGOO%20Neptune%20Series%20Files/Neptune%204%20Pro/3.%20User%27s%20Guide/1.User%20Manual/V1.5-2/NEPTUNE%204%20RPO%20User%20Manual-English-V1.5.pdf)
- [レベリング再発](https://wiki.elegoo.com/machines/neptune/troubleshooting/neptune-4-4-pro/why-i-need-to-re-level-the-neptune-4-pro-every-time)
- [接続と機種差](https://wiki.elegoo.com/neptune/neptune-4-series-web-page-control)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
