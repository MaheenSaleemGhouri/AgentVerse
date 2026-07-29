"use client";

/**
 * The composed 3D hero.
 *
 * Loaded only through `scene-loader.tsx`, which decides whether this
 * should mount at all — this module is the heavy one (three, drei,
 * postprocessing) and must never reach a bundle that does not use it.
 *
 * The canvas is `aria-hidden`: it is decoration. Everything the page
 * *means* is in the DOM around it (the logo, the tagline, the feature
 * cards, the forms), so a screen reader gets the message without being
 * read a robot.
 */

import { ContactShadows, Environment, PerspectiveCamera } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { Suspense } from "react";

import { Billboards, Drones, Particles } from "./atmosphere";
import { CityWindows, NeonCity } from "./neon-city";
import { Platform } from "./platform";
import { RobotModel } from "./robot-model";

export function AuthScene({ reducedMotion = false }: { reducedMotion?: boolean }): React.JSX.Element {
  return (
    <Canvas
      aria-hidden="true"
      // `dpr` capped at 1.5: past that the bloom pass costs more than it
      // shows on this scene, and a 3x retina display would quadruple the
      // fragment work for a background.
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      // `demand` would freeze the drones. `always` is correct here and
      // is the reason the scene is unmounted rather than paused when the
      // user prefers reduced motion.
      frameloop={reducedMotion ? "demand" : "always"}
      style={{ pointerEvents: "none" }}
    >
      <PerspectiveCamera makeDefault position={[0, 1.4, 7.6]} fov={42} />

      {/* Fog is what turns a box skyline into depth. Matched to the page
          background so towers dissolve rather than ending. */}
      <fog attach="fog" args={["#08061a", 12, 46]} />
      <color attach="background" args={["#08061a"]} />

      <ambientLight intensity={0.35} color="#8b7fd4" />
      {/* Key light from front-left, rim from behind-right — the two-light
          setup that gives the white robot its violet edge in the
          reference. */}
      <directionalLight position={[-4, 6, 5]} intensity={1.6} color="#e9d5ff" castShadow />
      <directionalLight position={[5, 3, -4]} intensity={2.2} color="#7c3aed" />
      <pointLight position={[0, 3, 4]} intensity={8} color="#22d3ee" distance={14} decay={2} />

      <Suspense fallback={null}>
        <Environment preset="night" />
        <NeonCity />
        <CityWindows />
        <Billboards />
        <Drones reducedMotion={reducedMotion} />
        <Particles reducedMotion={reducedMotion} />
        <Platform reducedMotion={reducedMotion} />
        <RobotModel reducedMotion={reducedMotion} />
        <ContactShadows
          position={[0, -1.16, 0]}
          opacity={0.55}
          scale={9}
          blur={2.6}
          far={4}
          color="#1a0b3d"
        />
      </Suspense>

      <EffectComposer enableNormalPass={false}>
        {/* Bloom is doing the heavy lifting: every emissive material in
            the scene — towers, rings, drones, visor — becomes glow here
            rather than being faked per-material. */}
        <Bloom
          intensity={1.15}
          luminanceThreshold={0.22}
          luminanceSmoothing={0.9}
          mipmapBlur
          radius={0.72}
        />
        <Vignette offset={0.28} darkness={0.62} />
      </EffectComposer>
    </Canvas>
  );
}

export default AuthScene;
