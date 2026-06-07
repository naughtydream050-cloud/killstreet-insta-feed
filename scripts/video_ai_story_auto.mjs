import { Client } from "@gradio/client";
import ffmpegInstaller from "@ffmpeg-installer/ffmpeg";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const DRY_RUN = (process.env.DRY_RUN || "false").trim().toLowerCase() === "true";
const FORCE_POST = (process.env.FORCE_POST || "false").trim().toLowerCase() === "true";
const HF_TOKEN = (process.env.HF_TOKEN || process.env.HUGGINGFACE_TOKEN || "").trim();
const IG_TOKEN = (process.env.INSTAGRAM_TOKEN || "").trim();
const IG_USER_ID = (process.env.IG_USER_ID || "").trim();
const GITHUB_REPOSITORY = (process.env.GITHUB_REPOSITORY || "naughtydream050-cloud/killstreet-insta-feed").trim();
const GITHUB_RUN_ID = (process.env.GITHUB_RUN_ID || String(Date.now())).trim();
const PAGES_BASE_URL = (process.env.PAGES_BASE_URL || `https://${GITHUB_REPOSITORY.split("/")[0]}.github.io/${GITHUB_REPOSITORY.split("/")[1]}`).replace(/\/$/, "");
const GRAPH_API_VERSION = (process.env.GRAPH_API_VERSION || "v25.0").trim();
const VIDEO_FALLBACK_STATIC = (process.env.VIDEO_FALLBACK_STATIC || "true").trim().toLowerCase() === "true";

const PRODUCT_TITLE = process.env.VIDEO_PRODUCT_TITLE || 'Classic "\u558B\u308A\u3059\u304E NO TALK" Buck T-Shirt';
const SHOP_URL_DISPLAY = process.env.SHOP_URL_DISPLAY || "KILLSTREET2.BASE.SHOP";
const CTA_TEXT = process.env.VIDEO_CTA_TEXT || "\u30D7\u30ED\u30D5\u30A3\u30FC\u30EB\u30EA\u30F3\u30AF\u304B\u3089\u8CFC\u5165";
const BRAND_TEXT = process.env.VIDEO_BRAND_TEXT || "KILL STREET";
const PRODUCT_PAGE_URL = process.env.VIDEO_PRODUCT_PAGE_URL || "https://killstreet2.base.shop/items/138177407";
const PRODUCT_IMAGE_URL = process.env.VIDEO_PRODUCT_IMAGE_URL || "";

const SPACE = process.env.HF_VIDEO_SPACE || "multimodalart/Wan2.1-Fast";
const SPACE_URL = process.env.HF_VIDEO_SPACE_URL || "https://multimodalart-wan2-1-fast.hf.space";
const ENDPOINT = process.env.HF_VIDEO_ENDPOINT || "/generate_video";

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, "docs", "story", "generated");
const WORK_DIR = path.join(ROOT, "docs", "story", "generated", "_ai_video_work");
const HISTORY_FILE = process.env.VIDEO_HISTORY_FILE || "video_history.json";
const PAYLOAD_FILE = process.env.VIDEO_STORY_PAYLOAD_FILE || ".video_story_payload.json";

const PROMPT =
  process.env.HF_VIDEO_PROMPT ||
  "A darkcore luxury fashion video, vertical 9:16, using the provided product model image as the exact starting frame. The model makes a very slow minimal forward step, with the upper body stable and arms barely moving. Preserve the clothing silhouette as much as possible. Slow cinematic motion, moody shadows, deep black tones, refined decayed aesthetic, no text, no logo imitation, no celebrity likeness.";
const NEGATIVE_PROMPT =
  process.env.HF_VIDEO_NEGATIVE_PROMPT ||
  "distorted clothing print, unreadable text, warped letters, changed graphic, new patterns, extra logos, deformed arms, deformed hands, strong body movement, fast walk, spinning, camera shake";

function utcNow() {
  return new Date();
}

function isoNow() {
  return utcNow().toISOString();
}

function jstDateKey(date = utcNow()) {
  const jst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  return jst.toISOString().slice(0, 10);
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n", "utf8");
}

function shortText(value, max = 800) {
  return String(value || "").slice(0, max);
}

async function fetchBuffer(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Fetch failed ${response.status}: ${url}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

async function findProductImageUrl() {
  if (PRODUCT_IMAGE_URL) {
    return PRODUCT_IMAGE_URL;
  }
  const response = await fetch(PRODUCT_PAGE_URL);
  if (!response.ok) {
    throw new Error(`Product page fetch failed: HTTP ${response.status}`);
  }
  const html = await response.text();
  const patterns = [
    /<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']/i,
    /<meta\s+content=["']([^"']+)["']\s+property=["']og:image["']/i,
    /"image"\s*:\s*"([^"]+)"/i,
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) {
      return match[1].replaceAll("\\/", "/");
    }
  }
  throw new Error("Could not find product image URL");
}

async function runFfmpeg(args) {
  await execFileAsync(ffmpegInstaller.path, args, {
    cwd: ROOT,
    maxBuffer: 40 * 1024 * 1024,
  });
}

function fontPath(bold = false) {
  const candidates = [
    bold ? "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" : "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    bold ? "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" : "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    bold ? "C\\:/Windows/Fonts/YuGothB.ttc" : "C\\:/Windows/Fonts/meiryo.ttc",
  ];
  for (const candidate of candidates) {
    const fsPath = candidate.replace(/^C\\:/, "C:");
    if (fs.existsSync(fsPath)) {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

function filterFilePath(filePath) {
  return path.relative(ROOT, filePath).replaceAll("\\", "/");
}

function drawText({ font, textfile, y, size, color = "white@0.96" }) {
  return `drawtext=fontfile='${font}':textfile='${filterFilePath(textfile)}':x=(w-text_w)/2:y=${y}:fontsize=${size}:fontcolor=${color}:line_spacing=8`;
}

async function writeOverlayTextFiles(textDir) {
  await mkdir(textDir, { recursive: true });
  const files = {
    brand: path.join(textDir, "brand.txt"),
    product: path.join(textDir, "product.txt"),
    shop: path.join(textDir, "shop.txt"),
    cta: path.join(textDir, "cta.txt"),
  };
  await writeFile(files.brand, BRAND_TEXT, "utf8");
  await writeFile(files.product, PRODUCT_TITLE, "utf8");
  await writeFile(files.shop, SHOP_URL_DISPLAY, "utf8");
  await writeFile(files.cta, CTA_TEXT, "utf8");
  return files;
}

function overlayFilters(files, inputLabel = "base") {
  return [
    `[${inputLabel}]drawbox=x=54:y=1488:w=972:h=322:color=black@0.56:t=fill[v1]`,
    `[v1]${drawText({ font: fontPath(true), textfile: files.brand, y: 106, size: 34, color: "white@0.82" })}[v2]`,
    `[v2]${drawText({ font: fontPath(true), textfile: files.product, y: 1530, size: 42 })}[v3]`,
    `[v3]${drawText({ font: fontPath(true), textfile: files.shop, y: 1634, size: 42, color: "white@0.94" })}[v4]`,
    `[v4]${drawText({ font: fontPath(false), textfile: files.cta, y: 1708, size: 36, color: "white@0.90" })}[v]`,
  ];
}

async function generateHfVideo(inputImage, rawVideo) {
  const inputBytes = await readFile(inputImage);
  const imageBlob = new Blob([inputBytes], { type: "image/jpeg" });
  const app = await Client.connect(SPACE_URL, HF_TOKEN ? { token: HF_TOKEN } : undefined);
  const result = await app.predict(ENDPOINT, [
    imageBlob,
    PROMPT,
    896,
    512,
    NEGATIVE_PROMPT,
    3.2,
    1.0,
    4,
    Math.floor(Date.now() / 1000) % 2147483647,
    false,
  ]);
  const first = result?.data?.[0];
  const video = first?.video || first;
  const videoUrl = video?.url || video?.path;
  if (!videoUrl) {
    throw new Error(`No video URL in HF result: ${shortText(JSON.stringify(result), 500)}`);
  }
  const response = await fetch(videoUrl, HF_TOKEN ? { headers: { Authorization: `Bearer ${HF_TOKEN}` } } : undefined);
  if (!response.ok) {
    throw new Error(`HF video download failed: HTTP ${response.status}`);
  }
  await writeFile(rawVideo, Buffer.from(await response.arrayBuffer()));
}

async function renderStoryVideo(rawVideo, storyVideo, textDir) {
  const files = await writeOverlayTextFiles(textDir);

  const filter = [
    "[0:v]setpts=1.875*PTS,fps=30,scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[base]",
    ...overlayFilters(files),
  ].join(";");

  await runFfmpeg([
    "-y",
    "-i",
    rawVideo,
    "-filter_complex",
    filter,
    "-map",
    "[v]",
    "-an",
    "-t",
    "6",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-r",
    "30",
    "-movflags",
    "+faststart",
    storyVideo,
  ]);
}

async function renderFallbackStoryVideo(inputImage, storyVideo, textDir) {
  const files = await writeOverlayTextFiles(textDir);
  const filter = [
    "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30[base]",
    ...overlayFilters(files),
  ].join(";");

  await runFfmpeg([
    "-y",
    "-loop",
    "1",
    "-t",
    "6",
    "-i",
    inputImage,
    "-filter_complex",
    filter,
    "-map",
    "[v]",
    "-an",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-r",
    "30",
    "-movflags",
    "+faststart",
    storyVideo,
  ]);
}

async function prepare() {
  const history = readJson(HISTORY_FILE, { videos: [] });
  const today = jstDateKey();
  const alreadyPostedToday = (history.videos || []).some((row) => String(row.posted_date_jst || "").slice(0, 10) === today);
  if (alreadyPostedToday && !FORCE_POST) {
    console.log(`[AI VIDEO] skip=already_posted_today date_jst=${today}`);
    writeJson(PAYLOAD_FILE, { skip: true, reason: "already_posted_today", posted_date_jst: today });
    return;
  }

  await mkdir(OUT_DIR, { recursive: true });
  await mkdir(WORK_DIR, { recursive: true });
  const safeRunId = GITHUB_RUN_ID.replace(/[^a-zA-Z0-9_-]/g, "");
  const baseName = `killstreet_ai_video_story_${today}_${safeRunId}`;
  const inputImage = path.join(WORK_DIR, `${baseName}_input.jpg`);
  const rawVideo = path.join(WORK_DIR, `${baseName}_raw.mp4`);
  const storyVideo = path.join(OUT_DIR, `${baseName}.mp4`);
  const publicVideoUrl = `${PAGES_BASE_URL}/story/generated/${baseName}.mp4`;

  const imageUrl = await findProductImageUrl();
  await writeFile(inputImage, await fetchBuffer(imageUrl));
  console.log(`[AI VIDEO] product_image_url=${imageUrl}`);
  console.log(`[AI VIDEO] hf_space=${SPACE}`);

  let generationMode = "hf_video";
  let hfError = "";
  if (!DRY_RUN) {
    try {
      await generateHfVideo(inputImage, rawVideo);
      await renderStoryVideo(rawVideo, storyVideo, path.join(WORK_DIR, `${baseName}_text`));
    } catch (error) {
      hfError = error?.message || String(error);
      console.log(`[AI VIDEO][WARN] HF generation failed: ${shortText(hfError, 500)}`);
      if (!VIDEO_FALLBACK_STATIC) {
        throw error;
      }
      generationMode = "static_product_video_fallback";
      console.log("[AI VIDEO] fallback=static_product_video");
      await renderFallbackStoryVideo(inputImage, storyVideo, path.join(WORK_DIR, `${baseName}_text`));
    }
  } else {
    console.log("[AI VIDEO][DRY RUN] generation/render skipped");
  }

  const payload = {
    skip: false,
    prepared_at: isoNow(),
    posted_date_jst: today,
    product_title: PRODUCT_TITLE,
    product_page_url: PRODUCT_PAGE_URL,
    product_image_url: imageUrl,
    generated_story_video_path: storyVideo,
    public_story_video_url: publicVideoUrl,
    history_file: HISTORY_FILE,
    settings: {
      space: SPACE,
      endpoint: ENDPOINT,
      duration: 3.2,
      steps: 4,
      output: "1080x1920 story mp4",
      generation_mode: generationMode,
      hf_error: hfError,
      static_fallback_enabled: VIDEO_FALLBACK_STATIC,
    },
  };
  writeJson(PAYLOAD_FILE, payload);
  if (!DRY_RUN) {
    const info = await stat(storyVideo);
    console.log(`[AI VIDEO] generated_story_video_path=${storyVideo}`);
    console.log(`[AI VIDEO] generated_story_video_bytes=${info.size}`);
  }
  console.log(`[AI VIDEO] public_story_video_url=${publicVideoUrl}`);
}

async function postPrepared(payloadPath) {
  const payload = readJson(payloadPath, null);
  if (!payload) {
    throw new Error(`Payload not found: ${payloadPath}`);
  }
  if (payload.skip) {
    console.log(`[AI VIDEO] post skipped: ${payload.reason}`);
    return;
  }
  if (DRY_RUN) {
    console.log("[AI VIDEO][DRY RUN] Instagram video story posting skipped");
    return;
  }
  if (!IG_TOKEN || !IG_USER_ID) {
    throw new Error("INSTAGRAM_TOKEN or IG_USER_ID is not set");
  }

  const api = `https://graph.facebook.com/${GRAPH_API_VERSION}`;
  const create = await fetch(`${api}/${IG_USER_ID}/media`, {
    method: "POST",
    body: new URLSearchParams({
      media_type: "STORIES",
      video_url: payload.public_story_video_url,
      access_token: IG_TOKEN,
    }),
  });
  const createJson = await create.json();
  console.log(`[AI VIDEO] create_container_http=${create.status}`);
  if (!create.ok || !createJson.id) {
    throw new Error(`Container creation failed: ${shortText(JSON.stringify(createJson))}`);
  }
  const containerId = createJson.id;
  console.log(`[AI VIDEO] container_id=${containerId}`);

  let status = "UNKNOWN";
  for (let i = 1; i <= 30; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10000));
    const statusResp = await fetch(`${api}/${containerId}?fields=status_code&access_token=${encodeURIComponent(IG_TOKEN)}`);
    const statusJson = await statusResp.json();
    status = statusJson.status_code || "UNKNOWN";
    console.log(`[AI VIDEO] poll=${i} status=${status}`);
    if (status === "FINISHED") {
      break;
    }
    if (status === "ERROR" || status === "EXPIRED") {
      throw new Error(`Container status failed: ${shortText(JSON.stringify(statusJson))}`);
    }
  }
  if (status !== "FINISHED") {
    throw new Error(`Container did not finish: ${status}`);
  }

  const publish = await fetch(`${api}/${IG_USER_ID}/media_publish`, {
    method: "POST",
    body: new URLSearchParams({
      creation_id: containerId,
      access_token: IG_TOKEN,
    }),
  });
  const publishJson = await publish.json();
  console.log(`[AI VIDEO] publish_http=${publish.status}`);
  if (!publish.ok || !publishJson.id) {
    throw new Error(`Publish failed: ${shortText(JSON.stringify(publishJson))}`);
  }
  const storyId = publishJson.id;
  console.log(`[AI VIDEO] SUCCESS story_id=${storyId}`);

  const history = readJson(HISTORY_FILE, {
    videos: [],
    _comment: "Automatically maintained by GitHub Actions. AI video story posting history only.",
    _schema: "posted stories generated from AI video; success records only",
  });
  history.videos = Array.isArray(history.videos) ? history.videos : [];
  history.videos.push({
    story_id: storyId,
    container_id: containerId,
    product_title: payload.product_title,
    video_url: payload.public_story_video_url,
    posted_date_jst: payload.posted_date_jst,
    posted_at: isoNow(),
    source: "hf_video_auto",
    generation_mode: payload.settings?.generation_mode || "unknown",
  });
  history.videos = history.videos.slice(-120);
  writeJson(HISTORY_FILE, history);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes("--prepare-only")) {
    await prepare();
    return;
  }
  const postIndex = args.indexOf("--post-prepared");
  if (postIndex >= 0) {
    await postPrepared(args[postIndex + 1] || PAYLOAD_FILE);
    return;
  }
  await prepare();
  await postPrepared(PAYLOAD_FILE);
}

main().catch((error) => {
  console.error(`[AI VIDEO][ERROR] ${error?.message || error}`);
  process.exitCode = 1;
});
