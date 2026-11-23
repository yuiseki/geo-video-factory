import * as THREE from 'three';
import type { PlateauBuildingsConfig } from '../types.js';
import { localMeters } from './city-timeline.js';
import type { PlateauFacadeTextureUniforms } from './plateau-facade-glsl.js';
import { applyWetGroundShader } from './plateau-materials.js';

function makeGlowTex(r: number, g: number, b: number, peakAlpha: number): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 128;
  const ctx = c.getContext('2d')!;
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  grad.addColorStop(0, `rgba(${r},${g},${b},${peakAlpha})`);
  grad.addColorStop(0.45, `rgba(${r},${g},${b},${peakAlpha * 0.45})`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeStreakTex(r: number, g: number, b: number, peakAlpha: number): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 256;
  const ctx = c.getContext('2d')!;
  const grad = ctx.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0.0, `rgba(${r},${g},${b},0)`);
  grad.addColorStop(0.12, `rgba(${r},${g},${b},${peakAlpha})`);
  grad.addColorStop(0.55, `rgba(${r},${g},${b},${peakAlpha * 0.55})`);
  grad.addColorStop(1.0, `rgba(${r},${g},${b},0)`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 256);
  ctx.globalCompositeOperation = 'destination-in';
  const hGrad = ctx.createLinearGradient(0, 0, 128, 0);
  hGrad.addColorStop(0.0, 'rgba(0,0,0,0)');
  hGrad.addColorStop(0.25, 'rgba(0,0,0,1)');
  hGrad.addColorStop(0.75, 'rgba(0,0,0,1)');
  hGrad.addColorStop(1.0, 'rgba(0,0,0,0)');
  ctx.fillStyle = hGrad;
  ctx.fillRect(0, 0, 128, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeDotGlow(hex: string, peak: number): THREE.CanvasTexture {
  const col = new THREE.Color(hex);
  return makeGlowTex(Math.round(col.r * 255), Math.round(col.g * 255), Math.round(col.b * 255), peak);
}

function sampleBillboardRgb(img: HTMLImageElement): [number, number, number] {
  const c = document.createElement('canvas');
  c.width = 16;
  c.height = 16;
  const ctx = c.getContext('2d');
  if (!ctx) return [180, 190, 220];
  ctx.drawImage(img, 0, 0, 16, 16);
  const d = ctx.getImageData(0, 0, 16, 16).data;
  let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) {
    const lum = d[i]! + d[i + 1]! + d[i + 2]!;
    if (lum > 90) { r += d[i]!; g += d[i + 1]!; b += d[i + 2]!; n++; }
  }
  if (!n) return [160, 175, 210];
  return [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
}

export async function populatePlateauStreetScene(
  scene: THREE.Scene,
  config: PlateauBuildingsConfig,
  center: [number, number],
  facadeUniforms: PlateauFacadeTextureUniforms,
): Promise<void> {
  if (config.facadeTextures && config.appearance !== false) {
    const loadTiled = async (src: string) => {
      const texture = await new THREE.TextureLoader().loadAsync(new URL(src, window.location.origin + '/').href);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.anisotropy = 8;
      return texture;
    };
    const ft = config.facadeTextures;
    if (ft.atlas) {
      facadeUniforms.uComfyAtlas.value = await loadTiled(ft.atlas);
      facadeUniforms.uComfyAtlas.value.wrapS = THREE.ClampToEdgeWrapping;
      facadeUniforms.uComfyAtlas.value.wrapT = THREE.ClampToEdgeWrapping;
      facadeUniforms.uComfyAtlasOn.value = 1;
    }
    if (ft.glass) facadeUniforms.uComfyGlass.value = await loadTiled(ft.glass);
    if (ft.shutter) facadeUniforms.uComfyShutter.value = await loadTiled(ft.shutter);
    if (!ft.shutter && ft.glass) facadeUniforms.uComfyShutter.value = facadeUniforms.uComfyGlass.value;
    if (!ft.glass && ft.shutter) facadeUniforms.uComfyGlass.value = facadeUniforms.uComfyShutter.value;
    facadeUniforms.uComfyWallMix.value = ft.wallMix ?? 1;
    if (ft.tileMeters) facadeUniforms.uComfyTileMeters.value.set(ft.tileMeters[0], ft.tileMeters[1]);
    if (ft.groundZ !== undefined) facadeUniforms.uComfyGroundZ.value = ft.groundZ;
    if (ft.shutterHeight !== undefined) facadeUniforms.uComfyShutterHeight.value = ft.shutterHeight;
  }

  if (config.billboards?.length) {
    const frameMat = new THREE.MeshBasicMaterial({ color: 0x12141a });
    const groundZ = config.facadeTextures?.groundZ ?? 15;
    for (const bb of config.billboards) {
      const texture = await new THREE.TextureLoader().loadAsync(new URL(bb.src, window.location.origin + '/').href);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 8;
      const glow = bb.glow ?? 1.0;
      const frontMat = new THREE.MeshBasicMaterial({
        map: texture,
        color: new THREE.Color().setScalar(glow),
        toneMapped: false,
      });
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(bb.widthM, bb.heightM, 0.45),
        [frameMat, frameMat, frameMat, frameMat, frontMat, frameMat],
      );
      const [lx, ly] = localMeters(bb.center, center);
      mesh.position.set(lx, ly, bb.altitudeM);
      mesh.rotation.order = 'ZYX';
      mesh.rotation.x = Math.PI / 2;
      mesh.rotation.z = ((180 - bb.bearing) * Math.PI) / 180;
      scene.add(mesh);

      const [cr, cg, cb] = sampleBillboardRgb(texture.image as HTMLImageElement);
      const azRad = (bb.bearing * Math.PI) / 180;
      const fx = Math.sin(azRad);
      const fy = Math.cos(azRad);

      const haloMat = new THREE.MeshBasicMaterial({
        map: makeGlowTex(cr, cg, cb, Math.min(0.45, 0.28 * glow)),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
        side: THREE.DoubleSide,
      });
      const halo = new THREE.Mesh(new THREE.PlaneGeometry(bb.widthM * 1.55, bb.heightM * 1.55), haloMat);
      halo.position.set(lx - fx * 0.25, ly - fy * 0.25, bb.altitudeM);
      halo.rotation.order = 'ZYX';
      halo.rotation.x = Math.PI / 2;
      halo.rotation.z = ((180 - bb.bearing) * Math.PI) / 180;
      scene.add(halo);

      const reflMat = new THREE.MeshBasicMaterial({
        map: makeStreakTex(cr, cg, cb, Math.min(0.55, 0.38 * glow)),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      });
      const reflLen = Math.max(42, bb.heightM * 4.5);
      const refl = new THREE.Mesh(new THREE.PlaneGeometry(bb.widthM * 1.45, reflLen), reflMat);
      refl.position.set(lx + fx * (reflLen * 0.5), ly + fy * (reflLen * 0.5), groundZ + 0.18);
      refl.rotation.z = ((180 - bb.bearing) * Math.PI) / 180;
      scene.add(refl);
    }
  }

  if (config.groundPlane) {
    const gp = config.groundPlane;
    const texture = await new THREE.TextureLoader().loadAsync(new URL(gp.src, window.location.origin + '/').href);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 16;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.magFilter = THREE.LinearFilter;
    const [w, s, e, n] = gp.bbox;
    const [x0, y0] = localMeters([w, s], center);
    const [x1, y1] = localMeters([e, n], center);
    const mat = new THREE.MeshBasicMaterial({
      map: texture,
      color: new THREE.Color().setScalar(gp.brightness ?? 1.0),
      toneMapped: false,
    });
    applyWetGroundShader(mat);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(Math.abs(x1 - x0), Math.abs(y1 - y0)), mat);
    plane.position.set((x0 + x1) * 0.5, (y0 + y1) * 0.5, gp.altitudeM ?? 0.05);
    scene.add(plane);
  }

  if (config.streetProps?.length) {
    const poleMat = new THREE.MeshBasicMaterial({ color: 0x1b1e26 });
    for (const sp of config.streetProps) {
      const [lx, ly] = localMeters(sp.center, center);
      const z0 = sp.altitudeM ?? (config.facadeTextures?.groundZ ?? 0);
      const h = sp.heightM ?? 6.2;
      const bearRad = ((180 - (sp.bearing ?? 0)) * Math.PI) / 180;
      const group = new THREE.Group();
      group.position.set(lx, ly, z0);
      group.rotation.z = bearRad;

      if (sp.kind === 'lamp' || sp.kind === 'signal') {
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.14, h, 8), poleMat);
        pole.rotation.x = Math.PI / 2;
        pole.position.set(0, 0, h * 0.5);
        group.add(pole);

        if (sp.kind === 'lamp') {
          const lampCol = sp.color ?? '#cfe6ff';
          const bulb = new THREE.Mesh(
            new THREE.SphereGeometry(0.28, 10, 8),
            new THREE.MeshBasicMaterial({ color: lampCol, toneMapped: false }),
          );
          bulb.position.set(0, 0, h);
          group.add(bulb);
          const halo = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: makeDotGlow(lampCol, 0.85),
              transparent: true,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              toneMapped: false,
            }),
          );
          halo.position.set(0, 0, h);
          halo.scale.set(4.5, 4.5, 1);
          group.add(halo);
          const pool = new THREE.Mesh(
            new THREE.PlaneGeometry(11, 11),
            new THREE.MeshBasicMaterial({
              map: makeDotGlow(lampCol, 0.32),
              transparent: true,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              toneMapped: false,
            }),
          );
          pool.position.set(0, 0, 0.16);
          group.add(pool);
        } else {
          const armLen = sp.widthM ?? 2.8;
          const arm = new THREE.Mesh(new THREE.BoxGeometry(armLen, 0.12, 0.12), poleMat);
          arm.position.set(armLen * 0.4, 0, h - 0.6);
          const box = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.35, 0.42), poleMat);
          box.position.set(armLen * 0.65, 0, h - 0.6);
          const sigCol = sp.color ?? '#ff2a3c';
          const light = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: makeDotGlow(sigCol, 0.95),
              transparent: true,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              toneMapped: false,
            }),
          );
          light.position.set(armLen * 0.65, -0.22, h - 0.6);
          light.scale.set(1.6, 1.6, 1);
          group.add(arm, box, light);
        }
      } else if (sp.kind === 'arch') {
        const span = sp.widthM ?? 8.5;
        const archCol = sp.color ?? '#c8a6ff';
        const leftPillar = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.45, h), poleMat);
        leftPillar.position.set(-span * 0.5, 0, h * 0.5);
        const rightPillar = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.45, h), poleMat);
        rightPillar.position.set(span * 0.5, 0, h * 0.5);
        const beam = new THREE.Mesh(
          new THREE.BoxGeometry(span + 0.6, 0.55, 1.1),
          new THREE.MeshBasicMaterial({ color: archCol, toneMapped: false }),
        );
        beam.position.set(0, 0, h);
        const glow = new THREE.Mesh(
          new THREE.PlaneGeometry(span * 1.6, 6.0),
          new THREE.MeshBasicMaterial({
            map: makeDotGlow(archCol, 0.55),
            transparent: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            toneMapped: false,
            side: THREE.DoubleSide,
          }),
        );
        glow.position.set(0, 0, h);
        glow.rotation.x = Math.PI / 2;
        const floorGlow = new THREE.Mesh(
          new THREE.PlaneGeometry(span * 1.4, 24),
          new THREE.MeshBasicMaterial({
            map: makeDotGlow('#9b7cff', 0.45),
            transparent: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            toneMapped: false,
          }),
        );
        floorGlow.position.set(0, 8, 0.16);
        group.add(leftPillar, rightPillar, beam, glow, floorGlow);
      } else if (sp.kind === 'wash') {
        const w = sp.widthM ?? 14;
        const washCol = sp.color ?? '#ffe8c2';
        const c = document.createElement('canvas');
        c.width = 64;
        c.height = 256;
        const ctx = c.getContext('2d')!;
        const col = new THREE.Color(washCol);
        const r = Math.round(col.r * 255), g = Math.round(col.g * 255), b = Math.round(col.b * 255);
        const grad = ctx.createLinearGradient(0, 0, 0, 256);
        grad.addColorStop(0.0, `rgba(${r},${g},${b},0)`);
        grad.addColorStop(0.08, `rgba(${r},${g},${b},0.55)`);
        grad.addColorStop(0.32, `rgba(${r},${g},${b},0.22)`);
        grad.addColorStop(0.75, `rgba(${r},${g},${b},0.05)`);
        grad.addColorStop(1.0, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, 64, 256);
        const washTex = new THREE.CanvasTexture(c);
        washTex.colorSpace = THREE.SRGBColorSpace;
        const washMesh = new THREE.Mesh(
          new THREE.PlaneGeometry(w, h),
          new THREE.MeshBasicMaterial({
            map: washTex,
            transparent: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            toneMapped: false,
            side: THREE.DoubleSide,
          }),
        );
        washMesh.rotation.x = Math.PI / 2;
        washMesh.position.set(0, 0, -h * 0.5);
        group.add(washMesh);
        const count = 6;
        const dotTex = makeDotGlow(washCol, 0.95);
        for (let i = 0; i < count; i++) {
          const sx = -w * 0.42 + (w * 0.84 * i) / (count - 1);
          const spSprite = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: dotTex,
              transparent: true,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              toneMapped: false,
            }),
          );
          spSprite.position.set(sx, -0.35, 0);
          spSprite.scale.set(2.2, 2.2, 1);
          group.add(spSprite);
        }
      } else if (sp.kind === 'kiosk') {
        const kw = sp.widthM ?? 5.4;
        const kd = 2.8;
        const kh = sp.heightM ?? 2.8;
        const glassMat = new THREE.MeshBasicMaterial({ color: 0x384858, transparent: true, opacity: 0.55, toneMapped: false });
        const roofMat = new THREE.MeshBasicMaterial({ color: 0x222630, toneMapped: false });
        const body = new THREE.Mesh(new THREE.BoxGeometry(kw, kd, kh), glassMat);
        body.position.set(0, 0, kh * 0.5);
        const roof = new THREE.Mesh(new THREE.BoxGeometry(kw + 0.6, kd + 0.6, 0.28), roofMat);
        roof.position.set(0, 0, kh + 0.14);
        const signBand = new THREE.Mesh(
          new THREE.BoxGeometry(kw * 0.55, 0.14, 0.36),
          new THREE.MeshBasicMaterial({ color: sp.color ?? '#24c87a', toneMapped: false }),
        );
        signBand.position.set(0, -kd * 0.52, kh - 0.25);
        const innerLight = new THREE.Mesh(
          new THREE.BoxGeometry(kw * 0.75, kd * 0.6, kh * 0.45),
          new THREE.MeshBasicMaterial({ color: '#ffd9a0', transparent: true, opacity: 0.42, toneMapped: false }),
        );
        innerLight.position.set(0, 0, kh * 0.45);
        group.add(body, roof, signBand, innerLight);
      }
      scene.add(group);
    }
  }
}
