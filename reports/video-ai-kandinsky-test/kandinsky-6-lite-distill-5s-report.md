# Kandinsky 6.0 Lite Distill 5s実機検証

- Space: `hugging-apps/kandinsky-6-lite-distill-5s`
- API: `https://hugging-apps-kandinsky-6-lite-distill-5s.hf.space` / `/generate`
- 入力: `reports/video-ai-runway-test/138177407_classic_no_talk.jpg`
- 実行経路: Gradio API（HF_TOKENは存在確認のみ。値は出力・保存していない）
- 生成時間: 113.346秒
- 出力: `kandinsky-6-lite-distill-5s-classic-no-talk.mp4`
- MP4: 5.061950秒、528x784、24fps、H.264 + AAC、901,647 bytes
- ZeroGPU: Space UIで `Running on Zero` を確認。具体的なGPU型番は公開UI/APIから取得できず未確定
- 無料条件: Hugging Face ZeroGPUの無料枠を使用。課金API・有料GPUは使用していない
- Instagram投稿: なし
- UI: Space UIと生成フォームは表示確認。埋め込みファイル選択イベントを自動操作側で受け取れず、同一Spaceの公開Gradio APIで実機生成を完了

## 統合

`scripts/video_ai_story_auto.mjs` にKandinskyを最初のHF候補として追加。入力は実測契約どおり `[prompt, first_frame_image, false, seed]`。既存Wan候補、26時間cooldown、静止画fallback、通常Story、商品Feed、履歴ファイルは変更していない。

Kandinskyの5秒入力には旧Wan用の1.875倍スローを適用せず、通常速度で6秒へパディングし、既存の1080x1920 Story整形へ渡す。

## 検証

- `node --check scripts/video_ai_story_auto.mjs`: PASS
- Kandinsky API実機MP4: PASS
- 6秒・1080x1920 renderer互換テスト: PASS
- `DRY_RUN=true` prepare: PASS
- dry-runで `posted_history.json` / `story_history.json` は不変
- token漏洩スキャン: PASS
- Jev health: AVAILABLE、Harness worker Gate: PASS
- commit: `c4a607644544f78eaf54a1c6f924995381139e19`
