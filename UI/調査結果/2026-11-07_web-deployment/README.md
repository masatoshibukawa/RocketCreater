# Webサイトのデプロイ・公開と無料枠

調査日: 2026-11-07。静的サイト、Next.jsなどのサーバー処理、Python APIを分け、7サービスの公式資料を確認した。CloudflareのWorkers / Pages、FirebaseのHosting / App Hostingは別製品として比較する。

## 最初に選ぶ方向

| 作りたいもの | 出発点の候補 | 先に確認する条件 |
| --- | --- | --- |
| 紹介ページ、作品集、ドキュメント | Cloudflare Workers Static Assets、GitHub Pages | 静的出力、ファイル制限、利用目的 |
| Next.jsで動的な画面・APIを使う | Vercel、Netlify、Cloudflare Workers | 非商用条件、計算量、対応ランタイム |
| Pythonの小さなAPIを試す | Render Free、Railway Free | sleep、メモリ、保存領域、無料枠の小ささ |
| Firebaseを既に使っている静的アプリ | Firebase Hosting Spark | プロジェクト単位の保存量・転送量 |
| 停止や復帰待ちを許容しにくいサービス | 用途に合う有料構成も比較 | 無料枠での停止、復帰時間、運用・復旧条件 |

これは用途に応じた本資料の提案。最安値ランキングや、無料で全機能が動く保証ではない。独自ドメインを買わず、提供サブドメインと静的配信を使う構成は、費用を抑える出発点になる。

Cloudflareは現在、新規プロジェクトにWorkersを案内している。Pagesの500 builds/月と、Workers Buildsの3,000分/月を混同しない。[Pagesの案内](https://developers.cloudflare.com/pages/get-started/) [H11]、[Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/) [H08]

## 資料

- [構成と公開の流れ](01_architecture-and-publishing.md): 静的・サーバー・保存、DNS、HTTPS、プレビュー
- [無料プランの比較](02_free-tiers.md): 使える処理、代表的な上限、停止・課金、利用条件
- [無料枠に収める方法](03_free-cost-tips.md): 転送量・クレジットの計算例、超過時の設定、記録用テンプレート
- [公開手順の例](04_deployment-playbooks.md): Git連携、静的サイト、Next.js、FastAPI
- [RocketWrightへの適用案](05_project-fit.md): 紹介・デモ・実行環境、公開と最終提出
- [無料枠の数値表](free-tier-quotas.csv): 単位・周期・集計範囲・超過時の扱い
- [出典台帳](sources.csv): 公式資料37件と、実際に確認した範囲

## 調査の読み方

継続的な無料プラン、期間限定の試用、従量課金契約内の無料枠を区別した。金額は原資料のUSD表記。税、為替、ドメイン更新、外部API、データベース、動画保存・配信などは別に考える。

公式本文または公式検索抜粋を参照した文献調査であり、登録・カード入力・実デプロイ・請求の実験は行っていない。取得サービスの本文キャッシュを含むため、調査日は全ページの更新日やリアルタイムの契約確認を意味しない。採用時に自分のダッシュボードのプランと現行原資料を確認する。

関連: [Webデザイン調査](../2026-11-04_web-design/README.md)、[Webデザインskills](../../web-design-skills/SKILL.md)。
