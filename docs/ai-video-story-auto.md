# AI video Story automation

This workflow generates one KILL STREET AI marketing video per day and posts it as an Instagram Story.

- Workflow: `.github/workflows/post_ai_video_story.yml`
- Schedule: JST 22:30
- Public output: `docs/story/generated/killstreet_ai_video_story_*.mp4`
- History: `video_history.json`
- Instagram API: official Graph API, `media_type=STORIES`, `video_url`

Safety rules:

- It does not post Reels or Feed.
- It does not use native Instagram link stickers.
- It does not modify `posted_history.json`.
- It does not modify `story_history.json`.
- It records only successful AI video Story posts in `video_history.json`.
- It skips automatically if `video_history.json` already has a success record for the same JST date, unless `force_post=true` is used manually.

Operational notes:

- HF/ZeroGPU quota or congestion can fail generation. In that case the workflow fails and does not post.
- The generated video is for worldview/teaser use. Product-detail posts should use fixed original product images or lower-motion edits because HF can alter garment text and print.
