# AI video Story automation

This workflow generates one KILL STREET AI marketing video per day and posts it as an Instagram Story.

- Workflow: `.github/workflows/post_ai_video_story.yml`
- Schedule: JST 22:30
- Public output: `docs/story/generated/killstreet_ai_video_story_*.mp4`
- History: `video_history.json`
- Instagram API: official Graph API, `media_type=STORIES`, `video_url`
- Product selection: reads product URLs from `https://killstreet2.base.shop/` and avoids recently used products in `video_history.json`.

Safety rules:

- It does not post Reels or Feed.
- It does not use native Instagram link stickers.
- It does not modify `posted_history.json`.
- It does not modify `story_history.json`.
- It records AI video Story posts in `video_history.json`. HF generation attempts set `hf_attempted_at`; cooldown-only fallback posts do not.
- It skips automatically if `video_history.json` already has a success record for the same JST date, unless `force_post=true` is used manually.
- It rotates products by selecting an unused product URL first, then the oldest used product URL.
- It waits at least 26 hours between HF GPU generation attempts by default. During the cooldown it still posts a 6-second product-image MP4 fallback.

Operational notes:

- HF/ZeroGPU quota or congestion can fail generation. The workflow also avoids calling HF again until `HF_MIN_HOURS_BETWEEN_ATTEMPTS` has elapsed. In either case it falls back to a 6-second MP4 made from the product image, so the daily Story can still post.
- HF generation uses multiple Space candidates. The default primary is `multimodalart/Wan2.1-Fast`; the default secondary is `zerogpu-aoti/wan2-2-fp8da-aoti-image`.
- `ZeroGPU worker error` triggers one lighter retry on the same Space, then falls through to the next Space candidate. `quota_exceeded` and auth errors do not retry.
- History classification fields distinguish `cooldown_skip`, `quota_exceeded`, `worker_error`, `generation_success`, and `fallback_published`.
- The generated video is for worldview/teaser use. Product-detail posts should use fixed original product images or lower-motion edits because HF can alter garment text and print.
