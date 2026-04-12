function looksLikeBase64(value) {
  if (typeof value !== "string") {
    return false;
  }

  const normalized = value.trim();
  if (!normalized || normalized.length < 16) {
    return false;
  }

  return /^[A-Za-z0-9+/=]+$/.test(normalized);
}

export function normalizeImageSrc(image, fallbackMimeType = "image/jpeg") {
  if (!image) {
    return null;
  }

  if (typeof image === "object") {
    const nestedValue =
      image.src ?? image.url ?? image.image ?? image.image_url ?? image.imageUrl ?? image.base64 ?? null;
    return normalizeImageSrc(nestedValue, fallbackMimeType);
  }

  if (typeof image !== "string") {
    return null;
  }

  const value = image.trim();
  if (!value) {
    return null;
  }

  if (
    value.startsWith("data:") ||
    value.startsWith("blob:") ||
    value.startsWith("http://") ||
    value.startsWith("https://") ||
    value.startsWith("/")
  ) {
    return value;
  }

  if (looksLikeBase64(value)) {
    return `data:${fallbackMimeType};base64,${value}`;
  }

  return null;
}
