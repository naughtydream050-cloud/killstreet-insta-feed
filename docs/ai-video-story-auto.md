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
- It records only successful AI video Story posts in `video_history.json`.
- It skips automatically if `video_history.json` already has a success record for the same JST date, unless `force_post=true` is used manually.
- It rotates products by selecting an unused product URL first, then the oldest used product URL.

Operational notes:

- HF/ZeroGPU quota or congestion can fail generation. In that case the workflow falls back to a 6-second MP4 made from the product image, so the daily Story can still post.
- The generated video is for worldview/teaser use. Product-detail posts should use fixed original product images or lower-motion edits because HF can alter garment text and print.
