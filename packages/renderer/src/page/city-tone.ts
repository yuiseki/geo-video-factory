/**
 * Tone calibration of the 3D city. The reference is the aerial photo on the ground: it is the
 * largest surface in the frame and nothing lights it, so every building surface is brought to it.
 *
 * A photo already contains its light. Lighting it below its albedo and passing it through a film
 * curve darkens it a second time, so the light returns the albedo of an upward face and the
 * renderer writes display colors without tone mapping (city-light-rig.ts). A roof that carries
 * the aerial photo then shows the same values as the ground next to it.
 *
 * The constants below were measured on renders of Tokyo (2023 and 2025 PLATEAU) and Osaka, by
 * masking each surface kind and comparing display values (sRGB of the linear luminance).
 */

/**
 * Lambert share of the light on an upward face. The rough standard material adds about 5% of
 * specular on top (measured by rendering a gray plane from above), which makes it 1.
 */
export const UPWARD_LAMBERT = 0.95;

/**
 * PLATEAU photo textures are darker than the aerial photo of the same roofs. Seen from straight
 * above under a neutral light, the quantiles of the two follow aerial = plateau ^ gamma in linear
 * values, with gamma 0.56 to 0.62 across wards; a plain gain clips the bright roofs first.
 */
export const PLATEAU_PHOTO_GAMMA = 0.6;

/**
 * Linear gain on the palette color of untextured PLATEAU walls. The palette was authored under
 * the film curve; with this gain the median wall sits where the median photographed wall does.
 */
export const PALETTE_WALL_GAIN = 0.62;

/** The same for the vertex colors of city-proxy walls. Roofs are left to the photo. */
export const PROXY_WALL_GAIN = 0.45;

/** Ceiling for the linear base color of untextured buildings that have no palette color. */
export const UNTEXTURED_BASE_MAX = 0.28;

/**
 * Linear albedo of the unpainted white of untextured PLATEAU buildings. Pure white clips on every
 * roof under the neutral light; this value shows what white showed under the film curve.
 */
export const STUDY_MODEL_WHITE = 0.57;

/** Linear albedo of the unpainted city-proxy clay, kept at its former look in the same way. */
export const PROXY_CLAY: readonly [number, number, number] = [0.49, 0.49, 0.475];

/** A number as a GLSL float literal. */
export const glslFloat = (value: number): string => value.toFixed(3);
