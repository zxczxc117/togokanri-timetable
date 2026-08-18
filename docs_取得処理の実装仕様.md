# 時刻表取得処理の実装仕様

## JR東海

1. `common/_api/time-schedule/list_station.json` から駅名を駅コードへ変換する。
2. `time-schedule/search/result.html?code=...&name=...&schedule=...` を取得する。
3. `line_keyword` と `direction_key`（`up`=上り、`down`=下り）に一致するPDFリンクだけを選ぶ。
4. PDFを座標解析し、時・分・種別・行先をTripへ変換する。
5. 公式の休日PDFは土曜・日曜・祝日共通としてSATURDAY/HOLIDAYへ保持する。

旧 `https://railway.jr-central.co.jp/timetable/` は使用しない。

## 名古屋市交通局

1. `timetable_list.html?name=駅名` を生成して駅別路線一覧へ進む。
2. `direction_keyword` と `direction_key` に一致する `timetable_dtl.html?code=...&direction=...` を選ぶ。
3. 詳細ページの平日列、土曜・日曜・休日列を分離する。
4. 「港」などセル内の行先記号を実際の行先名へ変換する。

## 名鉄

1. `start_id`、`link_id`、`direction_key`を1駅1方面で検証する。
2. `TrainDiagram`へ直接遷移する。
3. `direction=up/down`が設定と違う場合、またはIDが不足する場合は成功扱いにしない。
4. 時刻表の平日列と土・休日列を分離し、重複行を除去する。

## GitHub Actions

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
python build.py
```

外部サイトの構造変更・HTTPエラー・PDF解析失敗時は、誤った駅の時刻表を出力せず、`manual/`または前回の`public/index.json`へフォールバックする。ActionsのSummaryに失敗理由を記録する。

## オフライン検証

`tests/fixtures/`には添付された公式ページの保存HTMLを使用したテスト用資料を置いている。実サイトへ接続しなくても、地下鉄の平日/休日分離、JRの結果リンク選択、名鉄の方向URL検証を確認できる。
