# MultiDeadline Timer マニュアル

## 1. 概要
`timer_app.py` は、複数タイマーを同時管理できる Tkinter 製のデスクトップアプリです。  
タイマー終了時は、画面中央に横長の帯メッセージを最前面表示します。

- 対応OS: macOS / Windows / Linux
- 使用ライブラリ: Python標準ライブラリのみ

## 2. 必要環境
- Python 3.x
- tkinter（通常の Python 配布に同梱）

## 3. 起動方法
ターミナルでプロジェクトフォルダに移動して実行します。

```bash
python3 timer_app.py
```

Windows では:

```powershell
python timer_app.py
```

## 4. 画面構成
- 上部入力欄
  - `Label`: タイマー名
  - `Time`: タイマー時間入力
  - `Add`: タイマー追加
- 一覧（スクロール可）
  - Label
  - Remaining（クリック編集可）
  - End Time（クリック編集可）
  - State（Running / Paused / Finished）
  - Start / Pause / Cancel

## 5. タイマーの追加
`Time` は以下形式で入力できます。

1. 絶対時刻指定: `HH:MM`
- 例: `07:20`
- 現在より過去時刻なら翌日扱い

2. 相対時間指定: `M:SS`
- 例: `0:55`（55秒）

3. 分のみ指定
- 例: `15`（15分）

`Add` または Enter で追加します。

## 6. 操作方法
- `Start`: Paused タイマーを再開
- `Pause`: 実行中タイマーを一時停止
- `Cancel`: タイマー削除
- `Label` 欄: 状態に関係なく直接編集可能

## 7. Remaining / End Time の再編集
- `Remaining` をクリック: 相対時間を再設定
- `End Time` をクリック: 絶対時刻を再設定

編集ダイアログには、そのタイマーの「前回設定値」が初期表示されます。

例:
- `0:55` で作成したタイマーは、Finished 後に Remaining に `0:55` を表示
- `00:55` で作成したタイマーは、Finished 後に End Time に `00:55` を表示

## 8. 終了アラート
タイマー満了時、画面中央に横長帯の `Time is up!` メッセージを表示します。

解除方法:
- `ESC`
- `Enter`
- マウスクリック

解除後は、上部の Label 入力欄へフォーカスが戻ります。

## 9. 自動復元（再起動時の継続）
アプリはタイマー状態を自動保存します。

- 保存ファイル: `timer_state.json`
- 保存タイミング:
  - 状態変更時（定期 autosave）
  - アプリ終了時
- 起動時に自動復元

これにより、誤ってアプリを閉じても、再起動時に進行状態を継続できます（絶対時刻ベースで再計算）。

## 10. OS別フォント
アプリはOSに応じてUIフォントを自動選択します。

- macOS: `Hiragino Sans` など
- Windows: `Yu Gothic UI` / `Meiryo UI` / `Segoe UI`
- Linux: `Noto Sans CJK JP` など

## 11. よくある問題
1. タイマーが追加できない
- `Time` の入力形式が正しいか確認してください（`HH:MM` / `M:SS` / 分）。

2. 前回状態が復元されない
- `timer_state.json` が存在するか、書き込み権限があるか確認してください。

3. 文字表示が崩れる
- OSに日本語フォントが不足している可能性があります。日本語フォントを導入してください。

## 12. ファイル構成
- `timer_app.py`: アプリ本体
- `timer_state.json`: 自動保存されるタイマー状態
- `readme.md`: 本マニュアル
