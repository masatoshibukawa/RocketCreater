# 無料枠に収める実践方法

## 先に予算の単位を合わせる

| 見るもの | 試算に使う値 | 減らし方 |
| --- | --- | --- |
| 転送 | 1訪問で配る平均バイト × 訪問数 | 画像の寸法・品質、動画の初期取得、ブラウザキャッシュ |
| リクエスト | 1訪問のファイル/API要求 × 訪問数 | 不要なポーリングや読み込みを減らす |
| build・公開 | 1回の時間・成功回数 × 更新回数 | 対象外の変更でbuildしない設定、プレビューの活用 |
| 関数・サーバー | 呼び出し数、CPU、割当メモリ、稼働時間 | 静的化、実行箇所の分離、重複処理の抑制 |
| 保存・外部費用 | 写真・動画・DB、読取/書込、AI/API等 | 公開に必要な分だけ置く、保存期間と削除条件を決める |

例えば1訪問1.2 MBが8,000訪問なら単純計算で9.6 GB。16 MBの動画が1,000回すべて転送されるだけでも16 GBになる。これは十進単位での予算例。キャッシュや途中停止、bot、preview、再訪、CDNごとの計数で実測は変わる。

## Netlifyの300 creditsを試算する

Credit-basedプランの単価は、成功した本番deploy 1回15、転送1 GBあたり20、Web要求10,000件あたり2、compute 1 GB-hourあたり10 credits。これらを共有残高から引く。[課金FAQ](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/billing-faq-for-credit-based-plans/) [H33]

例: 本番1回、転送10 GB、要求100,000件、computeなしなら `15 + 200 + 20 = 235 credits`。残り65 creditsは他の利用がない場合の計算。無料の上限は帯域・回数それぞれの独立枠ではない。

試行はDeploy Previewで行い、採用時に本番更新すると、成功した本番deployの回数を抑えられる。previewを閲覧した際の転送・要求は残高を消費する。古いプランの利用者は、自分がLegacyかCredit-basedかを先に見る。[creditsの仕組み](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work) [H17]

## 節約の優先順位

1. **静的にできる範囲を先に決める。** 紹介、FAQ、公開済みの結果、サンプルデータは事前生成できる。すべての訪問でSSRや外部APIを動かす必要があるか見直す。
2. **提供URLで始める。** ドメインを買うのは必要になった段階で。ホスト名が提出条件に合うか、作業用の命名が受け手に見えないかは共有前に確認する。
3. **重い資産は実際の用途に合わせる。** レスポンシブ画像、適切な圧縮、画面外の遅延読み込み、クリック後に動画取得。大きなZIPや動画をすべて初期画面に読ませない。配信先を分ける場合は、そのサービスの利用条件と料金も数える。
4. **キャッシュは課金点を見て使う。** オリジン呼び出しを減らしてもCDNからの配信やリクエストが無料になるとは限らない。静的ファイル配信と、Workerが呼ばれる経路を確認する。[Workersの静的課金](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/) [H06]
5. **不用意なbuildと常時実行を減らす。** 本番変更をまとめ、文書など対象外の変更でアプリbuildしない。無料のsleepを避ける目的で無意味な定期アクセスを足さず、初回待ちを許容する構成を選ぶ。
6. **外部費用の入口を閉じる。** 試用では有料AI、SMS、メール、保存領域を使わない構成を優先し、必要なら明示的に枠を付ける。重い処理のデモは、同じ入力の承認済み結果を使う方法もある。

## 支出の上限と停止を決める

月額0円は、支出上限が0円であることを意味しない。プラン、支払方法、追加製品、自動追加購入、上限超過時の挙動を別々に確認する。例えばRenderではcomputeがFreeでも、条件により転送やbuildの追加料金が発生する。[Render Free](https://render.com/docs/free) [H20]

通知だけの予算設定と、実行を止めるhard limitを分ける。Railwayはsoft limitが通知、hard limitがworkload停止。Firebase App HostingはBlazeが必要で、関連製品の予算通知・上限設定を検討する。上限は配信や処理を止めることもあるため、復帰方法と代替URLを考えておく。[Railwayの支出設定](https://docs.railway.com/pricing/cost-control) [H31]、[App Hosting費用](https://firebase.google.com/docs/app-hosting/costs) [H26]

## 無料枠確認メモ

```text
目的・想定訪問数とピーク:
公開範囲・提供URLまたは所有ドメイン:
ホスト・プロジェクト・正確なプラン名:
無料枠の単位とリセット時期:
共有単位（アカウント / チーム / project / workspace）:
本番deploy回数・ページ転送・要求数・実行時間・保存量の見積り:
DB、外部API、動画、ドメインなど別費用:
超過時の停止・課金、自動追加購入、通知と実際の上限:
次に確認するusage画面・復旧手順:
```
