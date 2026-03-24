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
### タブ列
- 左端にシステムタブ `General`
- その右にユーザー作成タブ
- さらに右に `+` ボタン
- 右端にシステムタブ `Trash`

### 通常タブ (`General` / ユーザータブ)
- 上部入力
  - `Label`
  - `Time (HH:MM / M:SS / Minutes)`
  - `Add`
  - `Delete Tab`
- タイマー一覧
  - Label
  - Remaining  
    `(Click to edit)`
  - End Time  
    `(Click to edit)`
  - Actions（`▶/⏸`, `⏹`, `⚙`, `ⓧ`）

### Trash タブ
- 新規タイマー作成なし
- 設定ダイアログなし
- 通常の直接編集なし
- `Empty Trash` を表示
- 各行で `↩`（復元）/ `🗑`（完全削除）

## 5. タブ操作
### 作成
- `+` を押すと新しいユーザータブを作成します。
- 初期名は `New Tab` です。
- 同名タブは作成可能です。

### 選択
- タブをシングルクリックすると、そのタブを表示します。
- 起動時に選ばれるタブは常に `General` です。

### 名前変更
- 選択中のユーザータブをダブルクリックすると rename できます。
- `General` と `Trash` は rename できません。

### 並べ替え
- 並べ替えできるのはユーザー作成タブだけです。
- `General` は左固定、`Trash` は右固定、`+` はその手前に固定です。
- ユーザータブをドラッグすると、ユーザータブ領域内で順序を変更できます。

### 削除
- `Delete Tab` で選択中のユーザータブを削除できます。
- 空でないタブは削除できません。
- `General` と `Trash` は削除できません。

## 6. タイマー入力形式
`Time` は以下を受け付けます。

1. 絶対時刻: `HH:MM`（例 `07:20`）
2. 相対時間: `M:SS`（例 `0:55`）
3. 分のみ: `15`

## 7. タイマーの配置とドラッグ
- 各タイマーは必ず 1 つのタブに属します。
- 同一タブ内では縦ドラッグで並べ替えできます。
- 別タブへドラッグすると、そのタブへ移動します。
- タブ上で少し hover すると、そのタブを開いて任意位置へ drop できます。
- `Trash` へのドラッグは soft delete と同じです。
- `Trash` から通常タブへドラッグした場合は、drop 先のタブがそのまま新しい所属先になります。

## 8. タイマー動作
### absolute（`HH:MM`）
- ソース: 設定した壁時計時刻 `HH:MM`
- End Time は常に設定した `HH:MM` をそのまま表示します。
- 内部時刻の丸めや残り秒逆算で `07:20` が `07:19` と表示されることはありません。
- 実行中は `⏸` 表示だが押せません（Pauseなし）
- `⏹` は停止（Remaining を `--:--` 表示）
- 完了後、未解除アラート中は `00:00`、解除後は `--:--`
- `▶` で次の有効時刻へ再開します

### relative（`M:SS` / 分）
- ソース: `remaining_seconds` と `initial_seconds`
- `⏸` で一時停止、`▶` で再開
- `⏹` は停止 + 初期値へリセット
- 完了後、未解除アラート中は `00:00`
- アラート解除後の Remaining は最後に設定した相対値を表示
- `▶` で新規カウントダウン開始

## 9. タイマー編集
- Remaining をクリック: 相対時間として再設定
- End Time をクリック: 絶対時刻として再設定
- Label は通常タブ内で各行直接編集可能
- 各行の `⚙` でタイマー設定ダイアログを開けます

## 10. タイマー設定ダイアログ
設定ダイアログは repeat 関連設定を扱います。

### absolute timer の repeat
- 曜日トグル `Sun Mon Tue Wed Thu Fri Sat`
- すべて初期値 OFF
- ON にした曜日だけが、その `HH:MM` の有効発火曜日になります
- 発火直後に、次の有効曜日の同じ `HH:MM` へ即時再スケジュールされます
- 同じ曜日に再度すぐ発火し直すことはありません
- アプリ停止中やスリープ中に missed した過去分は再生しません
- stop 中は一切発火せず、再開時点から見て次の有効曜日を再計算します

### relative timer の repeat
- `Restart automatically when this relative timer reaches zero`
- 初期値 OFF
- ON のときは 0 到達後に同じ duration で即次サイクルへ入ります
- 放置しても内部では cycle を継続します
- ただし同一タイマーの alert は重複して積みません

### タイプ変更時の扱い
- absolute 用曜日設定と relative 用 repeat 設定は両方保存されます
- 現在のタイマー型に関係ない設定は表示されたまま disabled になります
- 後で型を戻すと、以前の設定がそのまま復活します

## 11. 削除・Trash・復元
- `ⓧ`: soft delete（`Trash` タブへ移動）
- タイマーが Trash に入ると、直前にいた通常タブを記録します
- `Trash` の `↩`: 記録された元タブへ復元
- 元タブがもう存在しない場合は `General` へ復元
- `Trash` の `🗑`: その項目を完全削除
- `Empty Trash`: Trash を全削除

## 12. 終了アラート
満了時に `Time is up!` を全画面帯で表示します。

解除:
- `ESC`
- `Enter`
- クリック

注意:
- relative repeat 中でも、同一タイマーの同種 alert が大量にキューされないよう重複抑止します

## 13. 自動保存 / 復元
- 保存先: `timer_state.json`
- autosave と終了時保存に対応
- 起動時に自動復元します
- 旧形式ファイルも互換読込します

新しい保存データには以下が含まれます。
- タブ一覧
- 選択中タブ ID
- タブごとのタイマー順序
- 各タイマーの `tab_id`
- 各タイマーの `last_non_trash_tab_id`
- absolute repeat weekday 設定
- relative repeat 設定

旧形式の `timers` / `trash` だけを持つ状態ファイルを読み込んだ場合:
- 通常タイマーは `General`
- ゴミ箱タイマーは `Trash`
として移行されます。

## 14. ファイル
- `timer_app.py`: アプリ本体
- `timer_state.json`: 保存状態
- `README.md`: 日本語マニュアル
- `README_EN.md`: English manual
