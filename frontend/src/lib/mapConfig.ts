// Default map center / zoom configuration.
// Override via environment variables (NEXT_PUBLIC_MAP_CENTER_LAT/LNG/ZOOM)
// without changing code. Falls back to Nellaidhoo, Maldives.

export const DEFAULT_MAP_CENTER: [number, number] = [
  Number(process.env.NEXT_PUBLIC_MAP_CENTER_LAT ?? 6.7156),
  Number(process.env.NEXT_PUBLIC_MAP_CENTER_LNG ?? 72.9467),
];

export const DEFAULT_MAP_ZOOM = Number(process.env.NEXT_PUBLIC_MAP_ZOOM ?? 15);
export const PREVIEW_MAP_ZOOM = Number(process.env.NEXT_PUBLIC_PREVIEW_MAP_ZOOM ?? 16);
