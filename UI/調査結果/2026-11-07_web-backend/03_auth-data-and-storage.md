# 認証・データ・ファイル保存の設計

## ログインとアクセス権を分ける

ログインできた利用者でも、他人の設計、ファイル、ジョブを読めるとは限らない。対象の所有者や所属を、認証済みの利用者情報と照合する。読む、作る、更新する、消す、ダウンロードする、再実行する操作を個別に扱う。[OWASPの対象別認可](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) [B31]

| 構成 | 認可を置く場所 | 確認すること |
| --- | --- | --- |
| 自作APIからDBに接続 | APIの認証・認可とDB権限 | 利用者から受けたIDを、所有者条件付きで扱う |
| Supabase Data API | PostgresのgrantsとRLS | `anon` / `authenticated` の役割、対象行、操作別ポリシー |
| FirebaseのクライアントSDK | Security Rules | ドキュメント・ファイルの所有者、許可する操作、未ログイン時 |
| 署名URLで保存先へアクセス | URLを発行するAPIと保存先の設定 | 発行対象の所有者、期限、権限、他ユーザーとの分離 |

Supabaseのブラウザ向けキーは `publishable`。利用者本人の認証と、grants・RLSによる認可が別に必要になる。`secret` はRLSを迂回する強い権限を持つため、信頼できるサーバーだけで使い、そのAPIで認可する。旧 `anon` / `service_role` の例は現行のキー案内と照合する。[APIキー](https://supabase.com/docs/guides/api/api-keys) [B16]、[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) [B15]

Firebaseも、開発用に開いたルールをそのまま公開しない。書込条件にログインだけを使うと、全ログイン利用者が同じ対象を編集できる場合がある。所有者や公開範囲に沿った許可と拒否を、別アカウントでも確認する。[Security Rules](https://firebase.google.com/docs/rules/basics) [B24]

CORSはブラウザに別originへの通信を許すための設定で、APIの本人確認・認可ではない。必要なoriginだけを許可し、Cookie等を伴うリクエストではcredentialsの設定を確認する。APIキー、DBパスワード、署名キーを公開bundleやログへ含めない。[FastAPI CORS](https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/cors.md) [B03]

## 無料のログイン機能とメール配送

- SupabaseのFreeには50,000 MAUの枠があるが、既定SMTPはチームの許可済みアドレス向けで、調査時点で2通/時。一般利用者の登録、確認、回復メールを使う場合は、custom SMTPの設定・配送枠・費用も確認する。[MAU](https://supabase.com/docs/guides/platform/manage-your-usage/monthly-active-users) [B35]、[SMTP](https://supabase.com/docs/guides/auth/auth-smtp) [B17]
- Firebase AuthのSparkでは、メールリンクでのログイン送信は5通/日と明記される。メールアドレス確認やパスワード再設定には別枠があり、電話認証のSMSはBlazeが必要。登録数・MAU・実際の送信通数を分ける。[Firebase Auth制限](https://firebase.google.com/docs/auth/limits) [B22]

試作では、実際に使うログイン方法を一つ選び、登録・再ログイン・期限切れ・回復を通す。メールが届くまでを要件に含める。無料枠の大きさだけで公開登録に適合すると判断しない。

## DBの設計と接続

関連するデータを一緒に検索・更新し、参照整合性が必要ならPostgresなどのリレーショナルDBが候補。決まった画面単位でドキュメントを読み、リアルタイム参照を使うならFirestoreの形も検討する。想定クエリを先に書き、データの重複、更新時の一貫性、検索・読み取り課金を比較する。

サーバーレスが同時に増えるとDB接続も増えやすい。例えばSupabaseは短命な環境にtransaction pooler、永続バックエンドにはネットワーク条件に合ったdirectまたはsession modeを案内している。poolerモードとドライバ機能の互換性を確認する。[Postgres接続](https://supabase.com/docs/guides/database/connecting-to-postgres) [B18]

利用者、設計、設計版、ジョブ、成果物の関係を明示する。更新が複数行にまたがる場合は、一部だけ成功して不整合にならない方法を選ぶ。マイグレーションを版管理し、古いデータを含む復元を試す。Supabase Freeは自動バックアップ・PITRが含まれず、Firestoreも管理バックアップなどは無料対象外。保存できることと、戻せることを別に確認する。[Supabase料金](https://supabase.com/pricing) [B12]、[Firestore無料枠](https://firebase.google.com/docs/firestore/quotas) [B21]

## 生成ファイルを分けて保存する

DBには所有者、入力版、状態、保存先のキー、サイズ、ハッシュ、作成時刻を置き、大きなPDF・動画・ZIPはオブジェクト保存を検討する。公開見本と個人の成果物は分離し、アップロード、一覧、取得、削除の権限を確認する。Supabase Storageは `storage.objects` のポリシーで各操作を制御できる。[Storage access control](https://supabase.com/docs/guides/storage/security/access-control) [B32]

アップロードの容量・型を検証し、アクセスに必要な時間だけ取得URLを発行する。期限付きURLの発行前にも所有者を確認する。ファイルを配信する経路ごとに、保存量、ダウンロード、CDN、リクエスト・操作課金を見積もる。
