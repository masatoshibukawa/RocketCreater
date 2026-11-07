# 実行基盤とデータサービスの比較

無料枠は2026-11-07の調査値。ここでは用途を選ぶための代表値を示す。詳細な数値・単位・集計範囲は [CSV](free-tier-quotas.csv)、出典番号は [台帳](sources.csv) で引ける。

## APIとworkerを動かす場所

| 選択肢 | 向く用途 | 無料枠・制約 |
| --- | --- | --- |
| Render Free | 小さなPython/Node APIの試作 | workspaceで750稼働時間/月。15分無通信でsleep。ローカル保存やDB期限にも制約。転送/buildの課金は前回調査を参照 [B10] |
| Railway Free | コンテナや小さなAPIの実験 | 継続無料は$1/月の利用額。最大RAM等の値を常時無料稼働の保証にしない。有料Hobbyは最低$5/月 [B11] |
| Cloudflare Workers Free | 短いedge API、D1等との連携 | 100,000要求/日、CPU 10 ms/HTTP要求、128 MB。CPU計算とネットワーク待ちを区別。一般的なVMやGPU実行環境とは異なる [B08] |
| Vercel Hobby Functions | 個人・非商用のサイトに近い短いAPI | 起動100万/月、Active CPU 4時間、Provisioned Memory 360 GB-hours等。Hobbyの表で最大実行時間300秒。対応設定を確認 [B09] |
| Cloud Run | 依存ライブラリを含むコンテナAPI、別Jobs | billingを有効にする従量課金サービス。request-basedは月200万要求等の無料使用量。region・課金方式・関連製品の費用を分ける [B04][B05] |

原資料: [Render](https://render.com/docs/free)、[Railway](https://docs.railway.com/pricing/plans)、[Workers](https://developers.cloudflare.com/workers/platform/limits/)、[Vercel](https://vercel.com/docs/plans/hobby)、[Cloud Run料金](https://docs.cloud.google.com/run/pricing)、[billing要件](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-service)。

Cloud Runのrequest-based無料使用量は、Tier 1 / us-central1基準の価格による割引で、月180,000 vCPU秒、360,000 GiB秒等をbilling accountで集計する。全regionで同じ量を個別に無料で使える意味ではない。build、コンテナ保存、DB、ログ、インターネット送信等の費用も確認する。[Cloud Run料金](https://docs.cloud.google.com/run/pricing) [B04]

無料の小規模APIが動くことと、大きなモデルやネイティブ解析を同時実行できることは別。依存ソフトの起動、メモリ、CPU/GPU、ファイルの寿命、プロセス実行可否を先に確認する。

## DB・認証・保存を任せる場所

| 選択肢 | データの形と機能 | 無料範囲と注意点 |
| --- | --- | --- |
| Supabase Free | Postgres、Auth、Data API、Storage等 | DB 500 MB/project。MAU 50,000、ファイル1 GB、uncached/cached egress各5 GB等はorganizationの使用量。低活動で1週間後に休止。既定SMTPは公開登録向けではない [B12][B13][B14][B17][B35][B36] |
| Neon Free | Postgres中心。現在はAuth等の追加サービスも提供 | 100 CU-hours/project/月、DB 1 GB/projectかつaccount合計20 GB、egress 5 GB/project/月。無操作5分でscale-to-zero。計算量やegress上限でcompute停止、容量上限では書込停止 [B19][B20] |
| Firestore Standardの無料枠 | ドキュメント型DB、リアルタイム参照 | project内の1 DBに保存1 GiB、読取50,000/日、書込20,000/日、削除20,000/日、送信10 GiB/月。日次は太平洋時間の深夜にreset [B21] |
| Cloudflare D1 Free | Workersから使うSQLite系DB | accountで読取500万行/日、書込10万行/日、合計5 GB。DBあたり500 MB、10 DBまで。API要求数やSQL文数と行数を混同しない [B25][B26] |
| R2 Standard | PDF、ZIP、画像、動画等のオブジェクト保存 | 10 GB-month/月、Class A 100万、Class B 1,000万操作/月を含む。直接のInternet egress無料でも、保存・操作・別経路の処理は別。月次課金サービス内の無料枠 [B29][B30] |

原資料: [Supabase料金](https://supabase.com/pricing)、[共有枠](https://supabase.com/docs/guides/platform/billing-faq)、[egress](https://supabase.com/docs/guides/platform/manage-your-usage/egress)、[MAU](https://supabase.com/docs/guides/platform/manage-your-usage/monthly-active-users)、[Storage](https://supabase.com/docs/guides/platform/manage-your-usage/storage-size)、[SMTP](https://supabase.com/docs/guides/auth/auth-smtp)、[Neonプラン](https://neon.com/docs/introduction/plans)、[Neon料金](https://neon.com/pricing)、[Firestore枠](https://firebase.google.com/docs/firestore/quotas)、[D1料金](https://developers.cloudflare.com/d1/platform/pricing/)、[D1制限](https://developers.cloudflare.com/d1/platform/limits/)、[R2料金](https://developers.cloudflare.com/r2/pricing/)、[R2開始条件](https://developers.cloudflare.com/r2/get-started/)。

## 無料の見積りで分けること

- SupabaseのDB容量はproject、MAUやファイル保存等はorganization。2つのactive Free project枠にはOwner/Adminの所属も関係する。[Billing FAQ](https://supabase.com/docs/guides/platform/billing-faq) [B13]
- Neonの100 CU-hoursは100時間の固定サーバーとは異なる。`CU × 稼働時間` であり、0.25 CUなら4時間で1 CU-hour。Freeはカード不要の継続プランと説明される。[Neon料金](https://neon.com/pricing) [B20]
- FirestoreのStandardとEnterpriseを分ける。バックアップ、PITR、TTL等には無料対象外のものがある。[Firestore枠](https://firebase.google.com/docs/firestore/quotas) [B21]
- Firebase Hostingの無料枠は、Cloud Storage for Firebaseの条件ではない。Cloud Storageは現在Blazeが必要で、課金契約内にno-cost usageがある。[Storageのbilling要件](https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024) [B23]
- DBやStorageの無料枠には、常時応答、復旧試験、バックアップ、メール到達性まで含まれるとは限らない。公開先の選定時に必要な機能を個別に確認する。
