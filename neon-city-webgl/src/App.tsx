import { Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import {
  AdaptiveDpr,
  Clone,
  Environment,
  Float,
  Html,
  Lightformer,
  MeshReflectorMaterial,
  PerformanceMonitor,
  Preload,
  Sparkles,
  Stars,
  Text,
  useAnimations,
  useGLTF,
  useProgress,
} from '@react-three/drei';
import { Bloom, ChromaticAberration, EffectComposer, Noise, Vignette } from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import { Color, Depth, LayerMaterial, Noise as LaminaNoise } from 'lamina';
import gsap from 'gsap';
import { createNoise2D } from 'simplex-noise';
import { easing } from 'maath';
import * as THREE from 'three';

type QualityTier = 0 | 1 | 2;
type BuildingVariant = 'box' | 'stepped' | 'tapered' | 'tower';

type BuildingSpec = {
  accent: string;
  baseColor: string;
  position: [number, number, number];
  scale: [number, number, number];
  variant: BuildingVariant;
  hasAntenna: boolean;
};

type LightOrb = {
  color: string;
  laneOffset: number;
  speed: number;
  x: number;
  zOffset: number;
  length: number;
};

type SignSpec = {
  color: string;
  position: [number, number, number];
  rotationY: number;
  text: string;
  fontSize: number;
  vertical?: boolean;
};

const BUILDING_COLORS = ['#111827', '#151a2d', '#191f34', '#20263e', '#0f1520'];
const ACCENT_COLORS = ['#04d9ff', '#ff3d81', '#7c5cff', '#ff9d00', '#00ff88', '#ff6b35'];
const WALK_PATH = [
  new THREE.Vector3(7.5, 0, -24),
  new THREE.Vector3(10.5, 0, -4),
  new THREE.Vector3(9.5, 0, 20),
  new THREE.Vector3(6.8, 0, 34),
  new THREE.Vector3(5.8, 0, 6),
  new THREE.Vector3(7.5, 0, -24),
];

const CAMERA_PATH = [
  new THREE.Vector3(-24, 14, 42),
  new THREE.Vector3(-10, 10, 20),
  new THREE.Vector3(0, 9, 12),
  new THREE.Vector3(14, 11, 18),
  new THREE.Vector3(26, 16, 46),
  new THREE.Vector3(0, 18, 72),
  new THREE.Vector3(-24, 14, 42),
];

function createWindowTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.fillStyle = '#06070d';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let y = 10; y < canvas.height - 14; y += 16) {
    for (let x = 8; x < canvas.width - 12; x += 14) {
      const lit = Math.random() > 0.32;
      ctx.fillStyle = lit
        ? `rgba(${30 + Math.floor(Math.random() * 120)}, ${120 + Math.floor(Math.random() * 100)}, ${180 + Math.floor(Math.random() * 70)}, ${0.7 + Math.random() * 0.25})`
        : 'rgba(7, 12, 24, 0.92)';
      ctx.fillRect(x, y, 8, 10);
    }
  }

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  for (let y = 0; y < canvas.height; y += 16) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(1.5, 8);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function createBuildingSpecs(quality: QualityTier): BuildingSpec[] {
  const noise2D = createNoise2D();
  const step = quality === 0 ? 10 : 8;
  const zStart = -120;
  const zEnd = 84;
  const rows: BuildingSpec[] = [];

  for (let x = -54; x <= 54; x += step) {
    if (Math.abs(x) < 15) continue;

    for (let z = zStart; z <= zEnd; z += step) {
      if (quality === 0 && Math.abs(z) > 70 && Math.random() > 0.55) continue;

      const noise = noise2D(x * 0.055, z * 0.045);
      const width = 3.8 + Math.abs(noise2D(x * 0.1, z * 0.03)) * 3.2;
      const depth = 3.6 + Math.abs(noise2D(z * 0.09, x * 0.03)) * 3.4;
      const height = 10 + Math.pow(Math.abs(noise), 0.75) * (quality === 2 ? 62 : quality === 1 ? 48 : 34);

      const variantNoise = noise2D(x * 0.22, z * 0.17);
      let variant: BuildingVariant = 'box';
      if (height > 35 && variantNoise > 0.3) variant = 'stepped';
      else if (height > 25 && variantNoise < -0.3) variant = 'tapered';
      else if (height > 45 && Math.abs(variantNoise) < 0.15) variant = 'tower';

      const hasAntenna = height > 30 && noise2D(x * 0.5, z * 0.4) > 0.4;

      rows.push({
        accent: ACCENT_COLORS[Math.floor(Math.abs(noise2D(x * 0.3, z * 0.18)) * ACCENT_COLORS.length) % ACCENT_COLORS.length],
        baseColor: BUILDING_COLORS[Math.floor(Math.abs(noise2D(x * 0.14, z * 0.11)) * BUILDING_COLORS.length) % BUILDING_COLORS.length],
        position: [x, height / 2 - 0.5, z],
        scale: [width, height, depth],
        variant,
        hasAntenna,
      });
    }
  }

  return rows;
}

function createTrafficOrbs(count: number): LightOrb[] {
  const orbs: LightOrb[] = [];
  for (let index = 0; index < count; index += 1) {
    const outbound = index % 2 === 0;
    orbs.push({
      color: outbound ? '#ff7c3d' : '#2de2ff',
      laneOffset: outbound ? -1.9 : 1.9,
      speed: outbound ? 0.06 + (index % 5) * 0.004 : -0.05 - (index % 4) * 0.005,
      x: outbound ? -2.7 + (index % 3) * 0.6 : 2.7 - (index % 3) * 0.6,
      zOffset: (index / count) * 1.1,
      length: 0.6 + Math.random() * 0.8,
    });
  }
  return orbs;
}

function createNeonSigns(): SignSpec[] {
  return [
    { color: '#04d9ff', position: [-21, 12, -12], rotationY: 0.2, text: 'NOVA', fontSize: 3.2 },
    { color: '#ff4d9d', position: [18, 14, 12], rotationY: -0.22, text: 'BYTE', fontSize: 3.2 },
    { color: '#7c5cff', position: [-30, 18, 28], rotationY: 0.35, text: 'SKY', fontSize: 3.0 },
    { color: '#ff9d00', position: [29, 16, -26], rotationY: -0.28, text: 'ARC', fontSize: 3.0 },
    { color: '#00ff88', position: [-18, 22, -40], rotationY: 0.15, text: 'PULSE', fontSize: 2.6 },
    { color: '#ff3d81', position: [24, 10, 32], rotationY: -0.18, text: 'GRID', fontSize: 2.8 },
    { color: '#04d9ff', position: [-38, 15, 8], rotationY: 0.5, text: '\u30CD\u30AA\u30F3', fontSize: 2.4, vertical: true },
    { color: '#ff6b35', position: [35, 20, -10], rotationY: -0.4, text: '\u672A\u6765', fontSize: 2.2, vertical: true },
    { color: '#7c5cff', position: [-15, 8, 50], rotationY: 0.1, text: 'DRIFT', fontSize: 2.4 },
    { color: '#ff9d00', position: [12, 25, -50], rotationY: -0.12, text: 'APEX', fontSize: 2.6 },
  ];
}

function App() {
  const [quality, setQuality] = useState<QualityTier>(2);

  return (
    <div className="app-shell">
      <Canvas
        camera={{ fov: 42, near: 0.1, far: 300, position: [0, 12, 38] }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
        shadows
      >
        <color attach="background" args={['#04050c']} />
        <fog attach="fog" args={['#050611', 34, 150]} />
        <PerformanceMonitor
          onDecline={() => setQuality((current) => Math.max(0, current - 1) as QualityTier)}
          onIncline={() => setQuality((current) => Math.min(2, current + 1) as QualityTier)}
        >
          <AdaptiveDpr pixelated />
          <Suspense fallback={null}>
            <NeonCityScene quality={quality} />
            <Preload all />
          </Suspense>
        </PerformanceMonitor>
      </Canvas>
      <LoadingOverlay />
    </div>
  );
}

function LoadingOverlay() {
  const { active, progress } = useProgress();

  return (
    <div className={`loading-overlay${active ? ' loading-overlay--visible' : ' loading-overlay--hidden'}`}>
      <div className="loading-card">
        <div className="loading-title">Neon City</div>
        <div className="loading-copy">Streaming a fullscreen WebGL skyline into view.</div>
        <div className="loading-meter">
          <span style={{ width: `${Math.max(progress, 6)}%` }} />
        </div>
      </div>
    </div>
  );
}

function NeonCityScene({ quality }: { quality: QualityTier }) {
  return (
    <>
      <ambientLight intensity={0.35} color="#5f6fd8" />
      <hemisphereLight args={['#4f6bff', '#090a12', 0.5]} />
      <directionalLight
        color="#ff7eb6"
        intensity={2.8}
        position={[-16, 20, 12]}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <spotLight color="#00d4ff" intensity={100} position={[12, 20, -16]} angle={0.25} penumbra={0.85} distance={120} />
      <spotLight color="#ff6b35" intensity={60} position={[-20, 15, -30]} angle={0.3} penumbra={0.9} distance={80} />
      <SkyDome />
      <Environment resolution={quality === 2 ? 256 : 128}>
        <Lightformer intensity={4.5} color="#ff3f81" scale={[60, 8, 1]} position={[0, 18, -40]} />
        <Lightformer intensity={3.2} color="#04d9ff" scale={[26, 8, 1]} position={[-22, 10, 22]} rotation-y={0.45} />
        <Lightformer intensity={3.2} color="#7c5cff" scale={[26, 8, 1]} position={[22, 12, 6]} rotation-y={-0.42} />
        <Lightformer intensity={2.2} color="#ff9d00" scale={[12, 4, 1]} position={[0, 5, 50]} rotation-x={Math.PI / 2} />
      </Environment>
      <CameraRig />
      <CityBlocks quality={quality} />
      <RoadDeck quality={quality} />
      <TrafficStreams quality={quality} />
      <RainSystem quality={quality} />
      <StreetFog quality={quality} />
      <Walker />
      <NeonSigns />
      <Holograms quality={quality} />
      <Sparkles
        count={quality === 2 ? 160 : quality === 1 ? 110 : 60}
        color="#82d1ff"
        scale={[70, 25, 120]}
        size={quality === 0 ? 1.8 : 2.4}
        speed={0.25}
        opacity={0.6}
        position={[0, 10, 0]}
      />
      <Stars radius={120} depth={80} count={quality === 2 ? 4200 : quality === 1 ? 2600 : 1400} factor={2.4} fade />
      <EffectComposer multisampling={0}>
        <Bloom
          intensity={quality === 2 ? 1.35 : quality === 1 ? 1.05 : 0.85}
          luminanceThreshold={0.2}
          luminanceSmoothing={0.85}
          mipmapBlur
        />
        <ChromaticAberration offset={new THREE.Vector2(0.00035, 0.0007)} />
        <Noise blendFunction={BlendFunction.SOFT_LIGHT} opacity={quality === 0 ? 0.05 : 0.08} premultiply />
        <Vignette eskil={false} offset={0.16} darkness={0.95} />
      </EffectComposer>
    </>
  );
}

function SkyDome() {
  return (
    <mesh scale={180}>
      <sphereGeometry args={[1, 64, 64]} />
      <LayerMaterial side={THREE.BackSide}>
        <Color color="#050611" alpha={1} mode="normal" />
        <Depth colorA="#0f1228" colorB="#ff4d8d" alpha={0.84} mode="normal" near={0} far={1} origin={[0, 0.9, 0]} />
        <LaminaNoise type="perlin" scale={2.5} colorA="#00b3ff" colorB="#060611" alpha={0.16} mode="softlight" />
      </LayerMaterial>
    </mesh>
  );
}

function CameraRig() {
  const progressRef = useRef({ value: 0 });
  const path = useMemo(() => new THREE.CatmullRomCurve3(CAMERA_PATH, true, 'catmullrom', 0.25), []);

  useEffect(() => {
    const tween = gsap.to(progressRef.current, { value: 1, duration: 32, ease: 'none', repeat: -1 });
    return () => { tween.kill(); };
  }, []);

  useFrame((state, delta) => {
    const t = progressRef.current.value % 1;
    const cameraTarget = path.getPointAt(t);
    const lookTarget = path.getPointAt((t + 0.022) % 1);
    const parallax = new THREE.Vector3(state.pointer.x * 2.2, Math.max(-0.6, state.pointer.y) * 1.2, 0);
    const desired = cameraTarget.clone().add(parallax);
    easing.damp3(state.camera.position, desired.toArray(), 0.24, delta);
    state.camera.lookAt(lookTarget.x, lookTarget.y + 1.8 + state.pointer.y * 0.6, lookTarget.z - 4);
  });

  return null;
}

function CityBlocks({ quality }: { quality: QualityTier }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const accentRef = useRef<THREE.InstancedMesh>(null);
  const buildings = useMemo(() => createBuildingSpecs(quality), [quality]);
  const windows = useMemo(() => createWindowTexture(), []);
  const accentGeometry = useMemo(() => new THREE.BoxGeometry(1, 1, 1), []);

  useLayoutEffect(() => {
    if (!meshRef.current || !accentRef.current) return;

    const mainMatrix = new THREE.Matrix4();
    const accentMatrix = new THREE.Matrix4();
    const mainScale = new THREE.Vector3();
    const accentScale = new THREE.Vector3();
    const position = new THREE.Vector3();
    const rotation = new THREE.Quaternion();

    buildings.forEach((building, index) => {
      position.set(...building.position);
      const [w, h, d] = building.scale;

      if (building.variant === 'tapered') {
        mainScale.set(w * 0.85, h, d * 0.85);
      } else if (building.variant === 'tower') {
        mainScale.set(w * 0.7, h * 1.15, d * 0.7);
      } else {
        mainScale.set(w, h, d);
      }

      mainMatrix.compose(position, rotation, mainScale);
      meshRef.current!.setMatrixAt(index, mainMatrix);
      meshRef.current!.setColorAt(index, new THREE.Color(building.baseColor));

      const signHeight = h * 0.035 + 0.2;
      if (building.variant === 'stepped') {
        accentScale.set(w * 0.75, signHeight * 3, d * 0.75);
        accentMatrix.compose(
          new THREE.Vector3(building.position[0], building.position[1] + h / 2 - signHeight * 2, building.position[2]),
          rotation,
          accentScale,
        );
      } else {
        accentScale.set(Math.max(1.4, w * 0.62), signHeight, Math.max(1.1, d * 0.62));
        accentMatrix.compose(
          new THREE.Vector3(building.position[0], building.position[1] + h / 2 + signHeight * 0.42, building.position[2]),
          rotation,
          accentScale,
        );
      }
      accentRef.current!.setMatrixAt(index, accentMatrix);
      accentRef.current!.setColorAt(index, new THREE.Color(building.accent));
    });

    meshRef.current.instanceMatrix.needsUpdate = true;
    meshRef.current.instanceColor!.needsUpdate = true;
    accentRef.current.instanceMatrix.needsUpdate = true;
    accentRef.current.instanceColor!.needsUpdate = true;
  }, [buildings]);

  const antennas = useMemo(() => buildings.filter((b) => b.hasAntenna), [buildings]);

  return (
    <group>
      <instancedMesh ref={meshRef} args={[undefined, undefined, buildings.length]} castShadow receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          color="#171e31"
          emissive="#0b1633"
          emissiveIntensity={1.55}
          emissiveMap={windows || undefined}
          map={windows || undefined}
          metalness={0.4}
          roughness={0.58}
          vertexColors
        />
      </instancedMesh>
      <instancedMesh ref={accentRef} args={[accentGeometry, undefined, buildings.length]}>
        <meshBasicMaterial toneMapped={false} vertexColors />
      </instancedMesh>
      {quality >= 1 && antennas.map((building, i) => (
        <group key={`ant-${i}`} position={[building.position[0], building.position[1] + building.scale[1] / 2, building.position[2]]}>
          <mesh>
            <cylinderGeometry args={[0.08, 0.12, 4, 6]} />
            <meshStandardMaterial color="#1a2040" metalness={0.8} roughness={0.3} />
          </mesh>
          <mesh position={[0, 2.2, 0]}>
            <sphereGeometry args={[0.2, 8, 8]} />
            <meshBasicMaterial color={building.accent} toneMapped={false} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function RoadDeck({ quality }: { quality: QualityTier }) {
  const stripeCount = quality === 2 ? 32 : quality === 1 ? 22 : 14;

  return (
    <group position={[0, -0.1, 0]}>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[120, 240]} />
        <MeshReflectorMaterial
          blur={[120, 50]}
          color="#060913"
          depthScale={0.75}
          metalness={0.55}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.3}
          mirror={0.35}
          mixBlur={0.6}
          mixStrength={55}
          opacity={0.95}
          resolution={quality === 2 ? 1024 : 512}
          roughness={0.95}
        />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.012, 0]}>
        <planeGeometry args={[12, 220]} />
        <meshStandardMaterial color="#080b12" emissive="#040812" emissiveIntensity={0.65} roughness={0.98} metalness={0.2} />
      </mesh>
      {/* Sidewalks */}
      <mesh rotation-x={-Math.PI / 2} position={[-7.5, 0.04, 0]}>
        <planeGeometry args={[2.2, 220]} />
        <meshStandardMaterial color="#0a0e18" emissive="#060a14" emissiveIntensity={0.3} roughness={0.95} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[7.5, 0.04, 0]}>
        <planeGeometry args={[2.2, 220]} />
        <meshStandardMaterial color="#0a0e18" emissive="#060a14" emissiveIntensity={0.3} roughness={0.95} />
      </mesh>
      {Array.from({ length: stripeCount }, (_, index) => (
        <mesh key={index} position={[0, 0.025, -105 + index * 7]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[0.18, 3.2]} />
          <meshBasicMaterial color="#ffd35c" transparent opacity={0.62} toneMapped={false} />
        </mesh>
      ))}
      <mesh position={[-5.9, 0.01, 0]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[0.32, 220]} />
        <meshBasicMaterial color="#05d9ff" transparent opacity={0.32} toneMapped={false} />
      </mesh>
      <mesh position={[5.9, 0.01, 0]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[0.32, 220]} />
        <meshBasicMaterial color="#ff4d9d" transparent opacity={0.28} toneMapped={false} />
      </mesh>
      {/* Intersection light pools */}
      {quality >= 1 && [-40, 0, 40].map((z) => (
        <mesh key={`pool-${z}`} rotation-x={-Math.PI / 2} position={[0, 0.02, z]}>
          <circleGeometry args={[4, 32]} />
          <meshBasicMaterial color="#04d9ff" transparent opacity={0.04} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

function TrafficStreams({ quality }: { quality: QualityTier }) {
  const orbs = useMemo(() => createTrafficOrbs(quality === 2 ? 28 : quality === 1 ? 18 : 10), [quality]);
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    const elapsed = state.clock.elapsedTime;
    groupRef.current?.children.forEach((child, index) => {
      if (index >= orbs.length) return;
      const orb = orbs[index];
      const wrapped = ((elapsed * orb.speed + orb.zOffset) % 1 + 1) % 1;
      child.position.set(orb.x, 0.4, THREE.MathUtils.lerp(80, -90, wrapped));
      child.scale.set(1, 1, orb.length);
    });
  });

  return (
    <group ref={groupRef}>
      {orbs.map((orb, index) => (
        <mesh key={`${orb.color}-${index}`} position={[orb.x, 0.4, 0]}>
          <capsuleGeometry args={[0.12, 0.4, 4, 8]} />
          <meshBasicMaterial color={orb.color} toneMapped={false} transparent opacity={0.85} />
        </mesh>
      ))}
    </group>
  );
}

function RainSystem({ quality }: { quality: QualityTier }) {
  const count = quality === 2 ? 2000 : quality === 1 ? 1000 : 400;
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const drops = useMemo(() => {
    const arr: { x: number; y: number; z: number; speed: number }[] = [];
    for (let i = 0; i < count; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 100,
        y: Math.random() * 60,
        z: (Math.random() - 0.5) * 180,
        speed: 12 + Math.random() * 8,
      });
    }
    return arr;
  }, [count]);

  const matrix = useMemo(() => new THREE.Matrix4(), []);

  useFrame((state, delta) => {
    if (!meshRef.current) return;
    for (let i = 0; i < drops.length; i++) {
      const drop = drops[i];
      drop.y -= drop.speed * delta;
      if (drop.y < -1) {
        drop.y = 55 + Math.random() * 10;
        drop.x = (Math.random() - 0.5) * 100;
        drop.z = (Math.random() - 0.5) * 180;
      }
      matrix.makeTranslation(drop.x, drop.y, drop.z);
      meshRef.current.setMatrixAt(i, matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <cylinderGeometry args={[0.01, 0.01, 0.6, 3]} />
      <meshBasicMaterial color="#6ba8d4" transparent opacity={0.18} toneMapped={false} />
    </instancedMesh>
  );
}

function StreetFog({ quality }: { quality: QualityTier }) {
  if (quality === 0) return null;

  const matRef = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((state) => {
    if (!matRef.current) return;
    matRef.current.opacity = 0.06 + Math.sin(state.clock.elapsedTime * 0.3) * 0.02;
  });

  return (
    <mesh rotation-x={-Math.PI / 2} position={[0, 1.5, 0]}>
      <planeGeometry args={[80, 180]} />
      <meshBasicMaterial ref={matRef} color="#1a3050" transparent opacity={0.06} depthWrite={false} />
    </mesh>
  );
}

function Holograms({ quality }: { quality: QualityTier }) {
  if (quality === 0) return null;

  const matRef1 = useRef<THREE.MeshBasicMaterial>(null);
  const matRef2 = useRef<THREE.MeshBasicMaterial>(null);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (matRef1.current) matRef1.current.opacity = 0.12 + Math.sin(t * 1.5) * 0.06;
    if (matRef2.current) matRef2.current.opacity = 0.10 + Math.sin(t * 1.2 + 1) * 0.05;
  });

  return (
    <group>
      <mesh position={[-22, 18, -18]} rotation={[0, 0.3, 0]}>
        <planeGeometry args={[5, 8]} />
        <meshBasicMaterial ref={matRef1} color="#04d9ff" transparent opacity={0.12} side={THREE.DoubleSide} toneMapped={false} depthWrite={false} />
      </mesh>
      <mesh position={[26, 15, 20]} rotation={[0, -0.25, 0]}>
        <planeGeometry args={[4, 6]} />
        <meshBasicMaterial ref={matRef2} color="#ff3d81" transparent opacity={0.10} side={THREE.DoubleSide} toneMapped={false} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Walker() {
  const groupRef = useRef<THREE.Group>(null);
  const path = useMemo(() => new THREE.CatmullRomCurve3(WALK_PATH, true, 'catmullrom', 0.2), []);
  const model = useGLTF('/robots/RobotExpressive.glb');
  const { actions, names } = useAnimations(model.animations, groupRef);

  useEffect(() => {
    model.scene.traverse((child) => {
      if ('castShadow' in child) child.castShadow = true;
      if ('receiveShadow' in child) child.receiveShadow = true;
    });
  }, [model.scene]);

  useEffect(() => {
    const clipName = names.find((name) => /walk/i.test(name)) || names[0];
    const action = clipName ? actions[clipName] : undefined;
    action?.reset().fadeIn(0.35).play();
    if (action) action.timeScale = 1.1;
    return () => { action?.fadeOut(0.2); };
  }, [actions, names]);

  useFrame((state) => {
    if (!groupRef.current) return;
    const t = (state.clock.elapsedTime * 0.055) % 1;
    const position = path.getPointAt(t);
    const tangent = path.getTangentAt(t);
    groupRef.current.position.set(position.x, 0.04, position.z);
    groupRef.current.rotation.y = Math.atan2(tangent.x, tangent.z);
  });

  return (
    <group ref={groupRef} scale={1.65}>
      <Clone object={model.scene} />
      <Float speed={1.5} rotationIntensity={0.1} floatIntensity={0.2}>
        <mesh position={[0, 3.8, 0]}>
          <sphereGeometry args={[0.45, 16, 16]} />
          <meshBasicMaterial color="#04d9ff" toneMapped={false} transparent opacity={0.22} />
        </mesh>
      </Float>
    </group>
  );
}

function NeonSigns() {
  const signs = useMemo(() => createNeonSigns(), []);

  return (
    <group>
      {signs.map((sign) => (
        <Float key={sign.text} speed={1.6} rotationIntensity={0.1} floatIntensity={0.28}>
          <Text
            position={sign.position}
            rotation={[0, sign.rotationY, sign.vertical ? Math.PI / 2 : 0]}
            fontSize={sign.fontSize}
            color={sign.color}
            letterSpacing={sign.vertical ? 0.3 : 0.12}
            anchorX="center"
            anchorY="middle"
            outlineColor="#05070d"
            outlineWidth={0.12}
            fillOpacity={0.95}
          >
            {sign.text}
          </Text>
        </Float>
      ))}
      <Html position={[0, 0, 0]} style={{ display: 'none' }} />
    </group>
  );
}

useGLTF.preload('/robots/RobotExpressive.glb');

export default App;
