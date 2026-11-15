import * as THREE from "three";

/** Brightness analysis of PLATEAU texture atlases (washed-out atlases are toned down). */

export interface TextureToneAnalysis {
  tone: number;
  bland: boolean;
}

const toneCache = new WeakMap<THREE.Texture, TextureToneAnalysis>();

function extractTexturePixels(image: unknown): Uint8Array | Uint8ClampedArray | null {
  if (!image || typeof image !== "object") {
    return null;
  }
  const dataImage = image as { data?: unknown; width?: number; height?: number };
  if (
    (dataImage.data instanceof Uint8Array || dataImage.data instanceof Uint8ClampedArray) &&
    dataImage.data.length >= 4
  ) {
    return dataImage.data;
  }
  if (typeof document === "undefined") {
    return null;
  }
  const width = Number(dataImage.width) || 0;
  const height = Number(dataImage.height) || 0;
  if (width <= 0 || height <= 0) {
    return null;
  }
  try {
    const size = 32;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) {
      return null;
    }
    ctx.drawImage(image as CanvasImageSource, 0, 0, size, size);
    return ctx.getImageData(0, 0, size, size).data;
  } catch {
    return null;
  }
}

export function analyzeTextureTone(texture?: THREE.Texture | null): TextureToneAnalysis {
  if (!texture) {
    return { tone: 1, bland: false };
  }
  const cached = toneCache.get(texture);
  if (cached) {
    return cached;
  }
  const pixels = extractTexturePixels(texture.image);
  if (!pixels) {
    return { tone: 1, bland: false };
  }
  let count = 0;
  let sum = 0;
  let sumSq = 0;
  let bright = 0;
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    const a = pixels[i + 3] ?? 0;
    if (a < 16) {
      continue;
    }
    const r = pixels[i] ?? 0;
    const g = pixels[i + 1] ?? 0;
    const b = pixels[i + 2] ?? 0;
    const y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    count++;
    sum += y;
    sumSq += y * y;
    if (y > 0.78) {
      bright++;
    }
  }
  if (!count) {
    return { tone: 1, bland: false };
  }
  const mean = sum / count;
  const variance = Math.max(0, sumSq / count - mean * mean);
  const spread = Math.sqrt(variance);
  const share = bright / count;
  let tone = 1;
  if (share > 0.42 || mean > 0.74) {
    tone = 0.64;
  } else if (share > 0.24 || mean > 0.64) {
    tone = 0.78;
  }
  const result = {
    tone,
    bland: spread < 0.105 && mean > 0.28
  };
  toneCache.set(texture, result);
  return result;
}
