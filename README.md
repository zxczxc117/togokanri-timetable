# togokanri-timetable（時刻表配信サーバ）

名鉄瀬戸線・JR中央本線・名古屋市営地下鉄（名城線／東山線）の駅時刻表を、
GitHub Actions で毎日自動生成し、GitHub Pages で配信する仕組み。
統合管理アプリの「電車 → データ取得 → 配信」タブから取り込む。

## 仕組み（C兼A方式）

```
GitHub Actions（毎日JST04:00）
  └ build.py
      ├ ① 各社サイトを Playwright で取得（自動取得）
      └ ② 失敗したら manual/ の手貼りデータへフォールバック（安全網）
  → public/index.json を生成（変わった駅だけ updatedDate を更新）
  → GitHub Pages で公開
        ↓
アプリが Wi-Fi 接続時に1日1回だけ index.json を確認し、更新があれば取り込む
```

- **A（自動取得）**: `adapters/{meitetsu,jrcentral,nagoya_subway}.py` が公式サイトを描画して表を抽出。
- **保険**: 公式が取れないときは `adapters/yahoo.py`（Yahoo!路線情報）。
- **C（確実な土台）**: それも駄目なら `manual/<駅id>/*.txt` の手貼りデータを使う。
  取得が全滅しても前回の `index.json` を維持するので配信は止まらない。

## フォルダ構成

| パス | 役割 |
|---|---|
| `stations.yaml` | 配信する駅の定義（adapter/url/方面/フォールバック） |
| `build.py` | 生成本体。自己テスト→取得→差分検知→`public/index.json` |
| `adapters/` | 取得方法（meitetsu / jrcentral / nagoya_subway / yahoo / manual） |
| `lib/model.py` | JSONスキーマ（アプリの StationEntry / Departure に対応） |
| `lib/textparse.py` | 時刻テキスト/表の解析（25時超・記号・全角対応、自己テスト付き） |
| `manual/<駅id>/` | 手貼り時刻表（WEEKDAY / SATURDAY / HOLIDAY .txt） |
| `tools/inspect.py` | 取れなくなった時の調査ツール |
| `public/index.json` | 公開される成果物（アプリ取得対象） |
| `.github/workflows/build.yml` | 毎日1回の自動実行 |

> 同梱の manual データは**代表値のサンプル**です。運用前に必ず公式時刻表で置き換えてください。
> 公開までの詳しい手順は同梱の「配信サーバ構築手順.md」を参照。

## ローカルで試す

```bash
pip install -r requirements.txt
python build.py --force-manual   # スクレイピング無しで manual から生成
python build.py                  # 通常（自動取得→失敗はフォールバック）
python build.py --check          # 差分の有無だけ確認
```
