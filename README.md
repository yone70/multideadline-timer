# MultiDeadline Timer マニュアル

## 1. 概要
`timer_app.py` は、複数タイマーを同時管理できる Tkinter 製デスクトップアプリです。  
タイマー終了時には、画面中央に横長の全画面アラートを表示します。

- 対応OS: macOS / Windows / Linux
- 依存: Python 標準ライブラリのみ

## 2. 必要環境
- Python 3.x
- tkinter（通常の Python 配布に同梱）

## 3. 起動方法
```bash
python3 timer_app.py
```

Windows:
```powershell
python timer_app.py
```

## 4. 画面構成
### Mainビュー
- 上部入力
  - `Label`
  - `Time (HH:MM / M:SS / Minutes)`
  - `Add`
  - `Trash`
- タイマー一覧
  - Label
  - Remaining  
    `(Click to edit)`
  - End Time  
    `(Click to edit)`
  - Actions（`▶/⏸`, `⏹`, `ⓧ`）

### Trashビュー
- 上部は `← Mainに戻る` と `Empty Trash` のみ表示
- 一覧は削除済みタイマー
- 各行で `↩`（復元）/ `🗑`（完全削除）

## 5. 入力形式
`Time` は以下を受け付けます。

1. 絶対時刻: `HH:MM`（例 `07:20`）
2. 相対時間: `M:SS`（例 `0:55`）
3. 分のみ: `15`（15分）

絶対時刻が現在より前なら翌日扱いです。

## 6. タイマー動作
### absolute（`HH:MM`）
- ソース: `target time`
- 実行中は `⏸` 表示だが押せません（Pauseなし）
- `⏹` は停止（Remaining を `--:--` 表示）
- 00:00 到達時
  1. Alert表示
  2. Alert後、Remaining は `--:--`
  3. `▶` で同じ `HH:MM` の次回時刻へ再開
  4. 完了後の `⏹` は無視

### relative（`M:SS` / 分）
- ソース: `remaining_seconds` と `initial_seconds`
- `⏸` で一時停止、`▶` で再開
- `⏹` は停止 + `initial_seconds` にリセット
- 00:00 到達時
  1. Alert表示
  2. Alert後、Remaining は最後に設定した値（例: `00:30`）
  3. `▶` で新規カウントダウン開始
  4. 完了後の `⏹` は無視

## 7. 編集
- Remaining をクリック: 相対時間として再設定
- End Time をクリック: 絶対時刻として再設定
- Label は各行で直接編集可能

## 8. 削除と復元
- `ⓧ`: ソフト削除（Trashへ移動）
- Trashビュー `↩`: 復元
- Trashビュー `🗑`: その項目を完全削除
- `Empty Trash`: Trashを全削除

## 9. 終了アラート
満了時に `Time is up!` を全画面帯で表示。

解除:
- `ESC`
- `Enter`
- クリック

## 10. 自動保存/復元
- 保存先: `timer_state.json`
- 形式: `timers`（現役）と `trash`（ゴミ箱）
- タイミング: 状態変更後のautosave + 終了時
- 起動時に自動復元（旧形式ファイルも互換読込）

## 11. ファイル
- `timer_app.py`: アプリ本体
- `timer_state.json`: 保存状態
- `README.md`: 日本語マニュアル
- `README_EN.md`: English manual
