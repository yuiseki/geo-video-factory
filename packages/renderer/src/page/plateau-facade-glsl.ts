/**
 * GLSL for the walls of untextured PLATEAU buildings, spliced into the facade shader of
 * plateau-materials.ts (it uses that shader's facadeWall, facadeAxis, buildingRnd, plateauTall...).
 * Tall buildings get a curtain wall, low ones a house facade. Estimates for the picture.
 */
import * as THREE from "three";

const blankTexture = new THREE.DataTexture(new Uint8Array([128, 128, 128, 255]), 1, 1, THREE.RGBAFormat);
blankTexture.needsUpdate = true;

/**
 * Aerial photo draped on the roofs of untextured PLATEAU buildings (enhanced render only).
 * Set once per scene from the manifest's roof_texture; off (0) by default.
 */
export const plateauRoofUniforms = {
  uPlateauRoofPhoto: { value: blankTexture as THREE.Texture },
  uPlateauRoofMin: { value: new THREE.Vector2(0, 0) },
  uPlateauRoofSize: { value: new THREE.Vector2(1, 1) },
  uPlateauRoofOn: { value: 0 },
};

// Curtain wall for untextured walls: storeys, mullions, glass reflecting the sky, floor slabs.
// An estimate for the picture, never a survey of the real facade.
export const UNTEXTURED_FACADE = `float curtainWall = facadeWall * plateauTall;
float houseWall = facadeWall * (1.0 - plateauTall);
float curtainStorey = 3.7 + buildingRnd * 0.5;
float curtainMull = 1.35 + buildingRnd2 * 0.7;
float cfy = vPlateauWorldPos.z / curtainStorey;
float cfx = facadeAxis / curtainMull;
float caax = max(fwidth(cfx), 1e-4);
float caay = max(fwidth(cfy), 1e-4);
float cwx = fract(cfx);
float cwy = fract(cfy);
float cgx = smoothstep(0.07 - caax, 0.07 + caax, cwx) * (1.0 - smoothstep(0.93 - caax, 0.93 + caax, cwx));
float cgy = smoothstep(0.24 - caay, 0.24 + caay, cwy) * (1.0 - smoothstep(0.93 - caay, 0.93 + caay, cwy));
float cdetail = 1.0 - smoothstep(0.25, 0.6, max(caax, caay));
float curtainGlass = curtainWall * mix(0.86 * 0.69, cgx * cgy, cdetail);
float cpanel = plateauHash(vec2(floor(cfx), floor(cfy)) + vPlateauFeatureId * 0.37);
float cheight = clamp(vPlateauWorldPos.z / 220.0, 0.0, 1.0);
vec3 csky = mix(vec3(0.33, 0.40, 0.48), vec3(0.66, 0.73, 0.80), 0.25 + 0.55 * cheight);
csky = mix(csky, vec3(0.20, 0.24, 0.27), step(0.55, buildingRnd2) * 0.45);
float csun = max(dot(normalize(facadeN.xy + 1e-5), vec2(-0.55, -0.83)), 0.0);
vec3 cglass = csky * (0.86 + 0.20 * cpanel) * (0.72 + 0.28 * csun);
gl_FragColor.rgb = mix(gl_FragColor.rgb, cglass, curtainGlass * 0.9);
float cslab = curtainWall * (1.0 - smoothstep(0.0, 0.06, min(cwy, 1.0 - cwy))) * cdetail;
gl_FragColor.rgb *= 1.0 - cslab * 0.18;
float clit = step(1.0 - uCityWindows * 0.7, cpanel);
gl_FragColor.rgb += vec3(1.0, 0.78, 0.5) * curtainGlass * clit * uCityWindows;
// Low buildings: small windows on storey rows and bay columns (a column is glazed or not), siding.
float hfy = vPlateauWorldPos.z / 2.85;
float hfx = facadeAxis / (3.3 + buildingRnd2 * 1.3);
float haax = max(fwidth(hfx), 1e-4);
float haay = max(fwidth(hfy), 1e-4);
float hwx = fract(hfx);
float hwy = fract(hfy);
float hcolumn = step(0.35, plateauHash(vec2(floor(hfx), vPlateauFeatureId * 0.731 + 11.0)));
float hx = smoothstep(0.28 - haax, 0.28 + haax, hwx) * (1.0 - smoothstep(0.72 - haax, 0.72 + haax, hwx));
float hy = smoothstep(0.32 - haay, 0.32 + haay, hwy) * (1.0 - smoothstep(0.82 - haay, 0.82 + haay, hwy));
float hdetail = 1.0 - smoothstep(0.18, 0.45, max(haax, haay));
float houseWindow = houseWall * mix(0.65 * 0.44 * 0.5, hcolumn * hx * hy, hdetail);
gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.24, 0.28, 0.33), houseWindow * 0.72);
float hsiding = houseWall * (1.0 - smoothstep(0.0, 0.12, fract(vPlateauWorldPos.z / 0.42))) * hdetail;
gl_FragColor.rgb *= 1.0 - hsiding * 0.10;
gl_FragColor.rgb += vec3(1.0, 0.72, 0.40) * houseWindow * step(1.0 - uCityWindows * 0.6, cpanel) * uCityWindows;
`;
