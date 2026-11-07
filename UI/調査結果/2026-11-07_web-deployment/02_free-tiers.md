# 無料プランの比較

数値は2026-11-07の調査で確認した代表値。すべての制限を網羅する表ではない。実際の枠は [数値表](free-tier-quotas.csv) と各行の原資料で確認する。

## 配信と実行の違い

| サービス・プラン | 主な用途と無料範囲 | 上限で起こること・条件 |
| --- | --- | --- |
| GitHub Pages / GitHub Free | 静的サイト。公開サイト1 GB以下、転送100 GB/月はsoft limit | 配信制限やサポートからの連絡の可能性。Freeではpublicリポジトリ。ECや商用SaaSを営む無料ホストとしての利用には制限 [H02][H03] |
| Cloudflare Workers Free + Static Assets | 静的assetへの要求は無料・無制限。20,000ファイル、各25 MiB。Worker処理は100,000要求/日、CPU 10 ms/要求 | 静的配信とWorker起動を区別。CPU・要求数超過はエラーになりうる。DBなど他製品には別枠 [H06][H07] |
| Cloudflare Pages Free | 静的配信。500 builds/月、同時1、20,000ファイル。FunctionsはWorkersの枠を使用 | 静的な要求だけを無制限と呼ぶ。新規案件の案内はWorkersへ [H09][H10][H11] |
| Vercel Hobby | 個人・非商用のNext.js等。Fast Data Transfer 100 GB、CDN要求100万、Function起動100万を月次で含む | 多くの機能は超過後に利用待ち。商用はPro等が必要。Hobbyは共同開発機能にも制限 [H14][H15] |
| Netlify Free / Credit-based | チーム全体で300 credits/月。配信、production deploy、関数等が同じ残高を使用 | 残高終了で全プロジェクト停止。Freeはhard limitで自動追加購入なし。旧Legacyプランとは別 [H17][H18] |
| Render Free Web Service / Hobby workspace | Python/Node等。512 MB RAM、workspace合計750稼働時間/月。Hobbyの転送5 GB/月、標準build 500分/月 | 15分無通信でsleep、復帰約1分。時間枠超過は翌月まで停止。転送/buildは支払方法の有無で追加課金または停止 [H20][H21] |
| Firebase Hosting / Spark | 静的・SPA。Hosting保存10 GB、CDN転送10 GB/月。project全体で共有 | 保存超過は新規deploy不可。転送超過は猶予後に翌月まで配信停止。Sparkは支払方法不要 [H24][H27] |
| Firebase App Hosting / Blaze | サーバー描画等。Blaze契約が必要で、送信10 GiB/月など関連製品の無料枠あり | 無料枠を超えると従量課金。SparkのHostingと同じ無課金方式ではない [H26] |
| Railway Trial → Free | 試用は最長30日・一度だけ$5。その後は$1/月の継続無料クレジット。Freeは最大0.5 GB RAM/サービス | 試用と継続枠を分ける。小さなクレジットを資源で消費する方式で、常時稼働時間の保証ではない。Hobbyは最低$5/月 [H28][H29][H30] |

原資料: [GitHub制限](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)、[GitHubプラン](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)、[Workers static assets](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)、[Workers制限](https://developers.cloudflare.com/workers/platform/limits/)、[Pages制限](https://developers.cloudflare.com/pages/platform/limits/)、[Pages Functions料金](https://developers.cloudflare.com/pages/functions/pricing/)、[Pages新規案内](https://developers.cloudflare.com/pages/get-started/)、[Vercel Hobby](https://vercel.com/docs/plans/hobby)、[Vercel利用条件](https://vercel.com/docs/limits/fair-use-guidelines)、[Netlify credits](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work)、[Netlify Free](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans)、[Render Free](https://render.com/docs/free)、[Render料金](https://render.com/pricing)、[Firebase Hosting枠](https://firebase.google.com/docs/hosting/usage-quotas-pricing)、[Firebase料金](https://firebase.google.com/pricing)、[App Hosting費用](https://firebase.google.com/docs/app-hosting/costs)、[Railway試用](https://docs.railway.com/pricing/free-trial)、[Railwayプラン](https://docs.railway.com/pricing/plans)、[Railway料金](https://railway.com/pricing)。

## 読み違えやすい条件

### GitHub Pages

10 builds/時はsoft limitで、独自Actions workflowによるbuild・publishにはその制限が適用されない。Actions自体の料金・runner条件は別に確認する。サイト配信でPythonやNodeサーバーを動かすサービスではない。[制限](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) [H02]、[サービス概要](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages) [H01]

オンライン事業・商取引・商用SaaSへの制限を、すべての企業紹介や作品集の可否へ雑に拡大解釈しない。対象の用途を原文と照合する。Vercel Hobbyの個人・非商用限定とも別の条件である。

### Cloudflare

Workersを先に実行する設定では、静的ファイルへのアクセスもWorkerの枠を使うことがある。`run_worker_first` の対象ではFreeの要求上限超過時に429となり、単純な静的配信へ戻る保証はない。[static assetsの課金](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/) [H06]

CPU 10 msはネットワーク応答を待つ実時間とは別である。SSR、認証、大きなJSON処理が枠内に収まるかは実測する。静的assetへの要求数が無制限でも、計算・ファイル・build・各ストレージまで無制限にはならない。[Workers制限](https://developers.cloudflare.com/workers/platform/limits/) [H07]

### Vercel

HobbyはActive CPU 4時間、Provisioned Memory 360 GB-hours等も別に数える。帯域100 GBだけを見て選ばない。超過時の停止期間は機能ごとに異なり、原資料は多くの場合30日待つと説明する。すべての機能が暦月1日に一斉回復するという説明にはしない。[Hobbyの枠](https://vercel.com/docs/plans/hobby) [H14]

業務・広告・報酬のある案件などはcommercial usageの原文を先に確認する。少ないアクセス数だからHobbyで商用利用できる、という判断にはしない。[Fair Use](https://vercel.com/docs/limits/fair-use-guidelines) [H15]

### Netlify

2025-09-04より前に作られた対象アカウントのLegacyプランと、現在のCredit-basedプランを分ける。新規Freeに昔の100 GB帯域等を流用しない。Deploy Previewのdeploy自体は0 creditsでも、そのURLへの要求・転送やcomputeは別に消費する。[creditsの仕組み](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work) [H17]

Freeの上限はプロジェクトごと300ではなく、teamの残高である。ひとつのサイトの消費によって他サイトも停止しうる。Freeは追加購入できないため、必要なら次の周期まで待つかプランの変更を検討する。[Freeプラン](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans) [H18]

### Render

無料のworkspaceプランと各サービスのcompute planは別である。Hobbyを選ぶだけで、有料computeや追加機能が無料になるわけではない。Free Web Serviceのファイル変更は永続保存の前提にできず、persistent diskも使えない。無料Postgresは30日で失効するため、継続無料のDBとして扱わない。[Freeの制約](https://render.com/docs/free) [H20]

転送・build枠を使い切った際、支払方法があれば追加分が課金される場合がある。未登録なら配信停止または新規build停止になる。課金を避けたい場合はcomputeだけでなくworkspaceのusageと支払設定を見る。[Freeの超過時の挙動](https://render.com/docs/free) [H20]

### FirebaseとRailway

Firebase Hostingの容量には保存された過去のreleaseも含まれる。Cloud StorageやFirestoreとは別の枠。App HostingではCloud Run等の関連費用も見る。[Hosting](https://firebase.google.com/docs/hosting/usage-quotas-pricing) [H24]、[App Hosting](https://firebase.google.com/docs/app-hosting/costs) [H26]

Railway Freeはカード不要と料金ページに明記される一方、現在の表では試用終了後の独自ドメイン枠は0である。提供ドメインで試す場合と独自ドメインを使う場合を分ける。資源の上限値は無料でもらえる量ではなく、クレジットを使って稼働できる最大構成である。[料金・ネットワーク枠](https://railway.com/pricing) [H30]

## 商用・カード・独自ドメイン

無料プランの名前だけで用途の可否を決めない。非商用条件、共同開発者、private organization repo、認証、データの扱いなどは別の制約になりうる。本調査は全サービスの商用利用を一括で許可する解釈をしない。

カード不要を明示確認できた例はFirebase SparkとRailway Free。その他のサービスの登録・本人確認画面は実地確認していない。無料枠の数値とカード登録の要否を同じ意味にしない。[Firebase料金](https://firebase.google.com/pricing) [H27]、[Railway料金](https://railway.com/pricing) [H30]

独自ドメインへの接続機能と、ドメインの新規取得・毎年の更新は別の費用。RenderはHobbyに独自ドメイン2件を含み、それを超えると月額が発生する。Railway Freeのように接続自体にプラン制限がある例もある。[Render料金](https://render.com/pricing) [H21]、[Railway料金](https://railway.com/pricing) [H30]
