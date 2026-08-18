# togokanri-timetable（時刻表配信サーバ）

GitHub Actionsで公式時刻表を取得し、駅・方面ごとの時刻を`public/index.json`としてGitHub Pagesへ公開する。

## 取得経路

* JR東海: `https://railway.jr-central.co.jp/time-schedule/search/index.html` の駅コードAPIで駅名をコード化し、`result.html?code=...`の検索結果から「路線名・平日/休日・上り/下り」に一致するPDFリンクを選び、PDFを解析する。旧URL `https://railway.jr-central.co.jp/timetable/`は使用しない。
* 名古屋市交通局: `timetable_list.html?name=駅名`を取得し、設定した方面文字列と`direction_key`に一致する`code`/`direction`リンクを選び、`timetable_dtl.html`の平日・土曜/休日列を解析する。駅名を単に入力欄へ入れるだけで最終ページを固定表示する処理ではない。
* 名鉄: `start_id`・`link_id`・`direction_key(up/down)`を駅・方面ごとに検証し、`TrainDiagram`へ遷移する。いずれかが未設定または不一致の場合は取得NGとしてmanualへフォールバックする。別駅・逆方向のIDを推測して流用しない。

## 重要な設定

`stations.yaml`の1項目が1駅1方面を表す。以下は同時に一致している必要がある。

* JR: `name`, `line_keyword`, `direction_key(up/down)`
* 地下鉄: `name`, `direction_keyword`, `direction_key(詳細ページのdirection値)`
* 名鉄: `start_id`, `link_id`, `direction_key(up/down)`

公式サイトのURLやHTMLが変更され、対象リンクを特定できない場合は、誤った駅のデータを成功扱いにせず、前回データまたは`manual/`へフォールバックする。GitHub ActionsのSummaryに失敗理由を残す。

## ローカル確認

```bash
pip install -r requirements.txt
python build.py --force-manual
python -m py_compile build.py adapters/*.py lib/*.py
```

実サイト取得はネットワークとPlaywright/PDF依存のため、ローカルで上記の机上確認を実施した後、GitHub Actionsの手動実行で公式ページからの取得を確認する。
