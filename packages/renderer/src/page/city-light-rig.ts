/** The lights and the output transform of the 3D city (see city-tone.ts for the calibration). */
import * as THREE from 'three';
import { cityLight, FILL_COLOR, FILL_POSITION, SUN_POSITION, type CityLight } from './city-timeline.js';

export interface CityLightRig {
  ambient: THREE.AmbientLight;
  sun: THREE.DirectionalLight;
  fill: THREE.DirectionalLight;
}

/** The daylight rig; add the three lights to the scene. */
export function createCityLightRig(): CityLightRig {
  const ambient = new THREE.AmbientLight();
  const sun = new THREE.DirectionalLight();
  sun.position.set(...SUN_POSITION);
  const fill = new THREE.DirectionalLight();
  fill.color.setRGB(...FILL_COLOR);
  fill.position.set(...FILL_POSITION);
  const rig = { ambient, sun, fill };
  applyCityLight(rig, cityLight(0));
  return rig;
}

export function applyCityLight(rig: CityLightRig, light: CityLight): void {
  rig.ambient.intensity = light.ambient;
  rig.ambient.color.setRGB(...light.ambientColor);
  rig.sun.intensity = light.sun;
  rig.sun.color.setRGB(...light.sunColor);
  rig.fill.intensity = light.fill;
}

/**
 * sRGB out, no tone mapping. The building surfaces are photos or are matched to photos; a film
 * curve on top of them crushed the dark walls of the PLATEAU textures toward black.
 */
export function usePhotoNeutralOutput(renderer: Pick<THREE.WebGLRenderer, 'outputColorSpace' | 'toneMapping'>): void {
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
}
