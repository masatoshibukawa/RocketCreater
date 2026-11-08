---
name: 3d-printer-bambu-x1-carbon
description: "Bambu Lab X1 CarbonのLidar校正、プレート・材料の制約、筐体冷却と接続を確認する。自動校正を印刷成功の証明にしない。"
---

# Bambu Lab X1 Carbon

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- X1系はLidarによる自動フローダイナミクスと、対応するFlow Rate校正を持つ。二つの目的を区別し、透明材料・校正線の接着不良等の制約を確認する。
- 実際のプレートとStudioの種類を一致させる。検出・校正が完了しても、細い初層が終盤の荷重まで保持するとは判断しない。
- 密閉条件とプレート温度に応じてPLAのheat creepを確認する。冷たいプレート向けの説明を、高温のPEI設定へ無条件に移さない。
- カメラや自動異常検出が全ての倒れ・接触を止めると仮定しない。失敗していた高さと終盤も観察する。

## 最小限の比較試行

校正に適合する材料・プレートで1個を試し、校正の結果と造形中の接地・熱・接触の結果を別々に記録する。

## 接続

Studioのネットワークプラグインでクラウド／LAN Onlyを設定する。ファーム更新で認証方式が変わる場合があるため、第三者ソフトの古い接続方法を固定しない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [フローダイナミクスと制約](https://wiki.bambulab.com/en/software/bambu-studio/calibration_pa)
- [Flow Rate校正](https://wiki.bambulab.com/en/software/bambu-studio/calibration_flow_rate)
- [Heat creep](https://wiki.bambulab.com/en/filament-acc/filament/heat-creep)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
