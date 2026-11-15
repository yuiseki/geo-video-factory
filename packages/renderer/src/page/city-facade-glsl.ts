/**
 * GLSL for the walls of city-proxy buildings, spliced into the material of city-materials.ts.
 * The facade kind comes from the pipeline (facade_archetypes.py, guessed from the roof in the
 * aerial photo) through _STYLE.x:
 *   0 house (siding, small windows)   1 sturdy (regular windows)    2 shed (slats, no windows)
 *   3 apartment (balconies)            4 factory (ribs, high band)   5 office (ribbon windows)
 *   6 old house (boards, small windows)
 * Uses: vCityUv (meters along the wall, meters above ground), vCityStyle, vCityBatch, vCityUp,
 * vCityPaint, cityHash, uCityWindows, uCityNight. Estimates for the picture, never survey data.
 */
export const CITY_FACADE = `float cityWall = 1.0 - step(0.35, abs(vCityUp));
float cityStyle = floor(vCityStyle.x + 0.5);
float sHouse = 1.0 - step(0.5, abs(cityStyle - 0.0));
float sRc = 1.0 - step(0.5, abs(cityStyle - 1.0));
float sShed = 1.0 - step(0.5, abs(cityStyle - 2.0));
float sApt = 1.0 - step(0.5, abs(cityStyle - 3.0));
float sFac = 1.0 - step(0.5, abs(cityStyle - 4.0));
float sOff = 1.0 - step(0.5, abs(cityStyle - 5.0));
float sOld = 1.0 - step(0.5, abs(cityStyle - 6.0));
float cityHouse = sHouse + sOld;
float cityEave = vCityStyle.y;
float cityR = cityHash(vec2(vCityBatch, 3.7));
float cityStorey = cityHouse * 2.85 + (sRc + sApt + sOff + sShed) * 3.2 + sFac * 4.5;
float cityBay = cityHouse * (3.3 + cityR * 1.3) + sRc * (2.6 + cityR * 0.8) + sApt * (3.0 + cityR * 0.6)
  + sOff * (1.6 + cityR * 0.4) + sFac * (4.0 + cityR * 1.0) + sShed * 3.0;
float cityFy = vCityUv.y / cityStorey;
float cityFx = vCityUv.x / cityBay;
vec2 cityCellId = vec2(floor(cityFx) + vCityBatch * 7.13, floor(cityFy) + vCityBatch * 1.37);
float cityWx = fract(cityFx);
float cityWy = fract(cityFy);
float cityAaX = max(fwidth(cityFx), 1e-4);
float cityAaY = max(fwidth(cityFy), 1e-4);
// Windows are rectangles on a regular grid: one row per storey, one column per bay. Houses decide
// per column whether a bay is glazed, so a column is either glazed from bottom to top or not.
float cityColumn = cityHash(vec2(floor(cityFx), vCityBatch * 0.731 + 11.0));
float cityPresent = cityHouse * step(0.35, cityColumn) + sRc + sApt + sOff + sFac;
float cityHalf = sHouse * 0.22 + sOld * 0.17 + sRc * 0.34 + sApt * 0.46 + sOff * 0.48 + sFac * 0.40;
float cityY0 = cityHouse * 0.32 + sRc * 0.32 + sApt * 0.40 + sOff * 0.38;
float cityY1 = cityHouse * 0.82 + sRc * 0.82 + sApt * 0.92 + sOff * 0.88;
float cityInX = smoothstep(0.5 - cityHalf - cityAaX, 0.5 - cityHalf + cityAaX, cityWx) * (1.0 - smoothstep(0.5 + cityHalf - cityAaX, 0.5 + cityHalf + cityAaX, cityWx));
float cityRowY = smoothstep(cityY0 - cityAaY, cityY0 + cityAaY, cityWy) * (1.0 - smoothstep(cityY1 - cityAaY, cityY1 + cityAaY, cityWy));
// factories: one band of high windows under the eave instead of storey rows
float cityAaV = max(fwidth(vCityUv.y), 1e-4);
float cityHighBand = smoothstep(cityEave - 1.9 - cityAaV, cityEave - 1.9 + cityAaV, vCityUv.y) * (1.0 - smoothstep(cityEave - 1.0 - cityAaV, cityEave - 1.0 + cityAaV, vCityUv.y));
float cityInY = mix(cityRowY, cityHighBand, sFac);
float cityBelow = step(0.7, vCityUv.y) * step(vCityUv.y, cityEave - 0.45);
float cityWindow = cityWall * cityPresent * cityInX * cityInY * cityBelow * vCityPaint;
// Prefilter: when a storey covers only a few pixels, use the average window coverage instead of
// the pattern, so distant walls do not shimmer as black speckles.
float cityPx = max(fwidth(vCityUv.x), fwidth(vCityUv.y));
float cityDetail = 1.0 - smoothstep(0.18, 0.45, cityPx / cityStorey);
float cityShare = sHouse * 0.65 * 0.44 * 0.5 + sOld * 0.65 * 0.34 * 0.5 + sRc * 0.68 * 0.5 + sApt * 0.92 * 0.52 + sOff * 0.96 * 0.5 + sFac * 0.8 * 0.12;
float cityCoverage = vCityPaint * cityWall * cityBelow * cityShare;
float cityGlassMix = mix(cityCoverage, cityWindow, cityDetail);
vec3 cityGlass = mix(vec3(0.20, 0.24, 0.29), vec3(0.42, 0.48, 0.56), cityHash(cityCellId + 9.1));
cityGlass = mix(cityGlass, vec3(0.30, 0.40, 0.50) + 0.10 * cityHash(cityCellId + 3.3), sOff);
cityGlass = mix(cityGlass, vec3(0.16, 0.18, 0.21), sApt * 0.6);
gl_FragColor.rgb = mix(gl_FragColor.rgb, mix(vec3(0.27, 0.31, 0.37), cityGlass, cityDetail), cityGlassMix * 0.72);
float cityBand = cityWall * (1.0 - sShed - sFac) * (1.0 - smoothstep(0.0, 0.05, min(cityWy, 1.0 - cityWy))) * step(1.0, vCityUv.y) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - cityBand * 0.08;
// Apartments: a light balcony railing along the bottom of every storey above the ground floor.
float cityBalcony = cityWall * sApt * step(cityStorey, vCityUv.y) * smoothstep(0.02, 0.05, cityWy) * (1.0 - smoothstep(0.30, 0.34, cityWy)) * cityDetail * vCityPaint;
gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.86, 0.86, 0.84), cityBalcony * 0.55);
// No wall stays flat: siding on houses, boards on old houses, ribs on factories, slats on sheds.
float citySiding = cityWall * sHouse * (1.0 - smoothstep(0.0, 0.12, fract(vCityUv.y / 0.42))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - citySiding * 0.10;
float cityBoards = cityWall * sOld * (1.0 - smoothstep(0.0, 0.15, fract(vCityUv.x / 0.24))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - cityBoards * 0.12;
float cityRibs = cityWall * sFac * (1.0 - smoothstep(0.0, 0.35, fract(vCityUv.x / 0.32))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - cityRibs * 0.14;
float citySlat = cityWall * sShed * (1.0 - smoothstep(0.0, 0.25, fract(vCityUv.x / 0.55))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - citySlat * 0.22;
gl_FragColor.rgb *= mix(1.0, mix(0.72, 1.0, smoothstep(0.2, 2.4, vCityUv.y)), cityWall);
float cityLitShare = uCityWindows * (0.45 + 0.4 * cityR);
float cityLit = step(1.0 - cityLitShare, cityHash(cityCellId + 4.2));
vec3 cityWarm = mix(vec3(1.0, 0.72, 0.40), vec3(0.85, 0.92, 1.0), step(0.85, cityHash(cityCellId + 2.3)));
vec3 cityWarmAvg = mix(vec3(1.0, 0.72, 0.40), vec3(0.85, 0.92, 1.0), 0.15);
vec3 cityGlow = mix(cityWarmAvg * cityCoverage * cityLitShare * 0.9, cityWarm * cityWindow * cityLit, cityDetail);
gl_FragColor.rgb = mix(gl_FragColor.rgb, gl_FragColor.rgb * vec3(0.90, 0.93, 1.02), uCityNight);
gl_FragColor.rgb += cityGlow * uCityWindows * 1.2;
`;
