# 公開手順の例

選んだ方法の節だけを使う。ここでは手順を調査した。実際にアカウント設定やデプロイを行った記録ではない。

## 静的サイト: GitHub Pages

1. 公開するHTML・CSS・JSを用意し、`index.html` が入口になることを確認する。
2. GitHub Freeで行う場合は、公開してよいリポジトリを使う。対象repoのSettings → Pagesで、ブランチ公開なら対象ブランチとルートまたは`/docs`を選ぶ。
3. ViteやNext.jsなどビルドが必要なら、公式のGitHub Actions経由の公開手順を使い、配信する出力ディレクトリを指定する。
4. project siteのURLではリポジトリ名の下に置かれる場合がある。`/` から始まる画像・CSS・内部リンクが意図しないホスト直下を指していないか、公開URLで確かめる。

[公開元の指定](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) [H04]、[HTTPSと公開範囲](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https) [H05]。

## 静的サイト: Cloudflare Workers、既存Pages

Workers Static Assetsのプロジェクトを選び、HTMLなどを配置するディレクトリを指定する。ローカルでビルドする場合は生成された `dist/` などを対象にしてWranglerからデプロイできる。Git連携で更新する場合は、buildとdeployの各コマンド、作業ディレクトリ、出力先を揃える。[Workersの静的サイト手順](https://developers.cloudflare.com/workers/static-assets/get-started/) [H34]

最初は `workers.dev` の提供URLを使える。Cloudflareは業務上重要な本番用途にはカスタムドメインやWorkers routeを案内している。既存のPagesを維持する場合は、Pages側のGit連携またはDirect Upload手順とその枠を使う。[workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/) [H12]、[Pagesの開始方法](https://developers.cloudflare.com/pages/get-started/) [H11]

## 静的サイト: Netlify、Firebase Hosting、Render

| サービス | 手順の要点 | 公開先 |
| --- | --- | --- |
| Netlify | Git取込 → buildコマンド・publish directory → deploy → 公開可否を確認。新規Credit-based teamのprivate by defaultにも注意 | `netlify.app` または登録したドメイン |
| Firebase Hosting | Sparkで対象projectを選ぶ → Firebase CLIでHostingを初期化 → 公開ディレクトリを確認 → previewまたはliveへ配置 | `web.app`、`firebaseapp.com`、所有ドメイン |
| Render Static Site | Static SiteとしてGit repo・ブランチ・build・publish directoryを設定。サーバー処理が必要なWeb Serviceとは分ける | `onrender.com` または登録したドメイン |

[NetlifyのGit取込](https://docs.netlify.com/start/quickstarts/deploy-from-repository) [H19]、[Netlifyの本番URL](https://docs.netlify.com/deploy/deploy-types/production-deploy) [H37]、[Firebase Hosting](https://firebase.google.com/docs/hosting) [H25]、[Render Static Sites](https://render.com/docs/static-sites) [H23]。

## サーバー処理を使うNext.js

1. SSR、rewrites、Route Handler、Server Action、画像変換のうち、使う機能を洗い出す。静的出力へ変える場合は非対応機能を先に確認する。[Next.js 15 Static Exports](https://nextjs.org/docs/15/app/guides/static-exports) [H32]
2. Vercel等にリポジトリを取り込み、monorepoならNext.jsのあるルートを指定する。適切なNode版・lockfileと、環境別の変数を設定する。通常のNext.jsを実行する方式では、静的 `out/` だけを指定しない。[Next.js on Vercel](https://vercel.com/docs/frameworks/full-stack/nextjs) [H16]
3. Cloudflareを選ぶ場合は、現在の公式ガイドが案内するvinextと既存OpenNext向けの資料を区別する。ランタイム互換性、Node依存、画像最適化、SSRのCPU制限を対象アプリで確認する。[Cloudflare Next.jsガイド](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/) [H13]
4. previewで実際の画面とサーバー応答を確認してから、本番ブランチまたは本番deployへ進む。Vercelでは提供される `vercel.app` のURLでも確認できる。[Vercelの提供URL](https://vercel.com/docs/environment-variables/framework-environment-variables) [H35]

## 小さなPython API: Render Web Service

1. FastAPIの実行に必要な依存とPython版、health endpoint、開始コマンドを確認する。
2. New → Web Serviceでrepoを連携し、対象のルート・Python・compute planを指定する。
3. 公式の小さなアプリ例ではbuildに `pip install -r requirements.txt`、startに `uvicorn main:app --host 0.0.0.0 --port $PORT` を使う。実プロジェクトではモジュールパスと依存ファイルを合わせる。[FastAPI公開手順](https://render.com/docs/deploy-fastapi) [H22]
4. 接続先URLをフロントへ設定し、初回起動、正常応答、失敗、切断時の表示を確かめる。出力ファイルを長く保存するなら、Freeの一時ファイルに依存しない構成を別途選ぶ。[Freeの制限](https://render.com/docs/free) [H20]

Railwayの場合も、対象repoまたはコンテナ、開始コマンド、提供URL、状態保存の条件を先に決める。試用$5と継続Free $1/月は小さな実験向けの利用額であり、CPUやRAMの最大値まで常時無料で使える意味ではない。[Railway Free Trial](https://docs.railway.com/pricing/free-trial) [H28]、[プランと単価](https://docs.railway.com/pricing/plans) [H29]
