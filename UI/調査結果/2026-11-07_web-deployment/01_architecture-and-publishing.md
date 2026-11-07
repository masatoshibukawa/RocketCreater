# サイトの構成と公開までの流れ

デプロイは、指定した版のファイルやサーバーをホストへ配置する作業。公開は、その版を利用者がアクセスできるURLで配信すること。プレビューURL、公開用URL、最終提出で渡すURLは区別する。

## 何を置くかでサービスを選ぶ

| 構成 | ホストが必要なもの | 例 |
| --- | --- | --- |
| 静的 | HTML、CSS、JS、画像などを配信する場所 | 紹介、作品集、ドキュメント、ブラウザ内だけで動くUI |
| サーバー描画・短いAPI | 対応するNode/edgeランタイム、実行時間、環境変数 | SSR、Server Actions、フォーム送信、ログイン |
| API・長時間処理 | APIサーバー、worker、保存領域、再開やキューの仕組み | FastAPI、ストリーム、PDF生成、シミュレーション |
| データベース・動画 | 保存、転送、読み書き、バックアップ | ユーザーデータ、動画・ZIPの配布 |

ReactやNext.jsを使うだけでは動的サーバーが必要とは限らない。公開時にサーバーで何をするかを確認する。Next.js 15では `output: 'export'` の対応構成を `next build` すると通常 `out/` ができる。リクエスト依存の機能やrewritesなどはこの方式で使えない。[Next.js 15 Static Exports](https://nextjs.org/docs/15/app/guides/static-exports) [H32]

## 公開の順序

1. **範囲を決める。** 共有相手、商用か、必要な操作、保存するデータ、無料枠超過時に停止してよいかを決める。
2. **出力を作る。** 素のHTMLなら `index.html` のあるディレクトリ。ビルド型ならルートディレクトリ、lockfile、ビルドコマンド、実際の出力先を確認する。よくある `dist/` や `out/` はプロジェクトに合わせて選ぶ。
3. **ホストへ置く。** 単発なら完成ファイルのアップロード、更新を続けるならGit連携が候補。Git連携では本番ブランチを確認し、pushが本番更新を起こすか把握する。公開対象は成果物に絞る。
4. **プレビューを確認する。** 別の設定・データで試す。URLを知っているだけで見える状態と、アクセス制御のある状態を区別する。個人情報や本番の秘密を載せない。
5. **本番URLを選ぶ。** 提供サブドメインか、所有する独自ドメイン。HTTPS、目的のURLへのリダイレクト、ルートと深いURLの直接アクセスを確認する。
6. **外部から開く。** ログアウト状態や別端末で主操作、API、ファイル、エラー時の挙動を確認する。公開commit・設定・戻せる版を記録する。公開済みという表示だけでは、利用者が見られるかは分からない。

GitHub Pagesのブランチ/Actions選択、NetlifyのGit取込と初期非公開設定、VercelのGitプレビューを確認した。[GitHubの公開元](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) [H04]、[Netlifyの取込手順](https://docs.netlify.com/start/quickstarts/deploy-from-repository) [H19]、[Next.js on Vercel](https://vercel.com/docs/frameworks/full-stack/nextjs) [H16]

## URL・DNS・HTTPSを分ける

提供URLで始めれば、自分のドメイン取得を省ける。独自ドメインを使うときは登録・更新料金と、ホスト側の接続枠を別に見る。

1. ホストの設定に、公開したいホスト名を登録する。
2. 指示されたDNSレコードを所有するDNS管理画面へ設定する。ルートドメインと `www` の設定を同じと仮定しない。すでに使っているメール用のレコードを誤って置き換えない。
3. 所有確認と証明書の発行を待ち、両URLのHTTPS表示を確認する。片方を正規URLにするならリダイレクトも確認する。

サブドメインとTLSの例: [GitHub PagesのHTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https) [H05]、[Cloudflareのworkers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/) [H12]、[Firebase Hosting](https://firebase.google.com/docs/hosting) [H25]。

## 公開設定で見落としやすい点

- privateリポジトリやpreviewという名称だけで、公開URLも非公開とは判断しない。実際の閲覧権限を確かめる。
- APIキーはサーバー側のsecretに置く。Next.jsの `NEXT_PUBLIC_` を付けた値はビルド時にブラウザ用JSへ含まれうる。静的出力のファイルは取得される前提で扱う。[Next.js 15環境変数](https://nextjs.org/docs/15/app/guides/environment-variables.md) [H36]
- `localhost` は接続元から見た自分自身を指す。公開先のブラウザやクラウドホストから開発PCへ自動ではつながらない。
- 別originのAPIにはHTTPS、CORSと認証の両方を確認する。CORSはアクセス権限の代わりにならない。クライアントのルーティングとサーバーの404対応も別に確認する。
- ロールバックでページを戻しても、DB更新や外部送信が自動で戻るとは限らない。データを扱うサイトは復旧範囲を決める。
