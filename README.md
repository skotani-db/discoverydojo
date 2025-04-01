# DiscoveryDojo

データスタックの現状調査と、Databricksへのマイグレーション計画を支援するStreamlitアプリケーション。

## 利用規約への同意
1. 規約をよく読んで[Google Form](https://forms.gle/BNKA2NErzTxNCvux8)から回答してください。
2. 承認等は行いませんので、回答を以て使用を開始できるものとします。

## 事前調査のポイント

### 調べたい点
* 中期経営計画等にデータ・AI関連の言及があるか
* データ基盤等を構築するための組織が社内にあるかどうか、またその部署やキーマン・意思決定者
* 上記のキーマン等が対外的に何か記事等があればその内容
* クラウドは何を使っているか、データ基盤には既存サービスとして何を活用しているか、またそれらのサービスはいつ頃いれていそうか。また、そのツールを選定した理由やツール導入後の成果から何を重視しているかが読み取れるケースがある
* 採用情報として、DS/DE/ML Engineer等の採用の有無とその要件。要件の中に利用サービスが記載されているケースは多い

### 調べるソース
* AWS等から出ている顧客事例
* 各種イベントのサイト (登壇しているものとかがあればそれを把握したいのと可能であれば登壇時の資料もみたい)
* (企業によっては)テックブログ

## セットアップ

### リポジトリの準備
DatabricksのRepos機能を使ってDiscoveryDojoリポジトリをインポートする

## 環境変数の設定

アプリケーションを実行するために以下の環境変数を設定する必要があります。app.yamlに以下の値を設定してください：

```yaml
env:
  - name: 'DATABRICKS_SERVER_HOSTNAME'
    value: 'sample-workspace.cloud.databricks.com'
  - name: 'DATABRICKS_HTTP_PATH'
    value: '/sql/1.0/warehouses/a1b2c3d4e5f6g7h8'
  - name: 'DATABRICKS_TOKEN'
    value: 'dapidxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
  - name: 'DATABRICKS_HOST'
    value: 'https://sample-workspace.cloud.databricks.com'
  - name: 'CATALOG_NAME'
    value: 'main'
  - name: 'SCHEMA_NAME'
    value: 'default'
```

### 環境変数の意味と設定方法

1. **DATABRICKS_SERVER_HOSTNAME**:
   - DatabricksワークスペースのDNSホスト名
   - ブラウザURLから確認（例: https://**sample-workspace.cloud.databricks.com**/ の太字部分）

2. **DATABRICKS_HTTP_PATH**:
   - SQL Warehouseに接続するためのHTTPパス
   - SQL WarehouseのConnection Detailsから確認
   - `/sql/1.0/warehouses/` の後にWarehouse IDが続く

3. **DATABRICKS_TOKEN**:
   - Databricks API認証用の個人アクセストークン
   - User Settings → Developer → Access tokensから新規作成
   - 生成時に一度だけ表示されるため必ず保存すること

4. **DATABRICKS_HOST**:
   - Databricksワークスペースの完全なURL（httpsプロトコル込み）
   - ブラウザのアドレスバーから確認

5. **CATALOG_NAME**:
   - Unity Catalogで使用するカタログ名
   - Data Explorerから確認（デフォルト: "main"）

6. **SCHEMA_NAME**:
   - 使用するスキーマ名
   - Data Explorerから確認（デフォルト: "default"）

## Databricksでのデプロイ

### Databricks Appsを使用したデプロイ
1. **アプリケーションのデプロイ設定**
   - Workspaceメニューから「Apps」を選択
   - 「Create New App」をクリック
   - アプリケーションのパスとして、プロジェクトのディレクトリを指定

2. **権限設定**
   - アプリケーションの公開範囲を設定（組織内、特定グループなど）
   - 必要に応じてサービスプリンシパルに権限を付与

## 活用例

1. 顧客ヒアリング前の準備
2. ヒアリング中のガイド付き調査
3. Databricksへのマイグレーション計画の作成

---

© 2025 Databricksマイグレーションツール