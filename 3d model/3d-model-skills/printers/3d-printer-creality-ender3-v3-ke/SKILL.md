---
name: 3d-printer-creality-ender3-v3-ke
description: "Ender-3 V3 KEの校正、ソフト版、可動ベッドとLAN/USB媒体接続を確認する。SEと異なる機種設定を保つ。"
---

# Creality Ender-3 V3 KE

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- KEのファームと対応するCreality Printプロファイルを使う。SEの設定や同名に近い別V3の開始コードを流用しない。
- CR-Touchの校正と実物の初層を確認する。ノズル付着物、材料変更後の供給、ベッド下の異物を点検する。
- 可動ベッドでの揺れと細い接地を、加速度・向き・補助接地と合わせて比較する。高速機の広告値を標準の試行値にしない。
- 画面とファームで校正・ネットワーク操作が変わり得る。旧手順のUI名より、実機と現行公式説明の一致を優先する。

## 最小限の比較試行

同じKE・材料・ノズルで初層と全高の1個を比較する。高速部だけ欠ける場合は流量、揺れる場合は動作条件を分ける。

## 接続

対応版のCreality Printで同一LANの実機を追加する。オフラインはUSBメモリー。クラウドとローカル送信、ファイル送信と実機開始を区別する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [KE公式マニュアル](https://wiki.creality.com/products/diy/ender%E7%B3%BB%E5%88%97/ender-3v3-ke/%E5%A4%9A%E8%AF%AD%E7%A7%8D%E8%AF%B4%E6%98%8E%E4%B9%A6/ender-3_v3_ke-sm-001__user_manual%EF%BC%88en%EF%BC%89.pdf)
- [KE保守](https://wiki.creality.com/en/ender-series/ender-3-v3-ke/maintenance)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
