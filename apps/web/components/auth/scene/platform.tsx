"use client";

/**
 * The glowing circular dais the robot stands on, and the reflective
 * floor it sits in — the two elements that anchor the robot in the
 * scene rather than leaving it floating in fog.
 */

import { MeshReflectorMaterial } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Mesh, MeshStandardMaterial } from "three";

export function Platform({ reducedMotion = false }: { reducedMotion?: boolean }): React.JSX.Element {
  const innerRing = useRef<Mesh>(null);
  const outerRing = useRef<Mesh>(null);

  useFrame((state) => {
    if (reducedMotion) return;
    const t = state.clock.elapsedTime;
    // Counter-rotating rings, slowly. The reference shows a dais that
    // feels powered rather than static; opposing directions read as
    // machinery where a single spin reads as a loading spinner.
    if (innerRing.current) innerRing.current.rotation.z = t * 0.18;
    if (outerRing.current) outerRing.current.rotation.z = -t * 0.11;

    const pulse = 1.6 + Math.sin(t * 1.4) * 0.5;
    for (const ring of [innerRing.current, outerRing.current]) {
      const material = ring?.material as MeshStandardMaterial | undefined;
      if (material) material.emissiveIntensity = pulse;
    }
  });

  return (
    <group position={[0, -0.9, 0]}>
      {/* Reflective floor. The wet-ground reflection is most of what
          makes the reference feel cinematic, and it is one material
          rather than a second render of the scene. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.06, 0]} receiveShadow>
        <planeGeometry args={[90, 90]} />
        <MeshReflectorMaterial
          blur={[420, 120]}
          resolution={512}
          mixBlur={1}
          mixStrength={22}
          roughness={0.85}
          depthScale={1.1}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.35}
          color="#07060f"
          metalness={0.7}
          mirror={0}
        />
      </mesh>

      {/* Dais body — three stacked cylinders, widest at the bottom, as
          in the reference. */}
      <mesh position={[0, -0.02, 0]} receiveShadow castShadow>
        <cylinderGeometry args={[2.5, 2.75, 0.28, 64]} />
        <meshStandardMaterial color="#12102a" metalness={0.85} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.16, 0]} receiveShadow castShadow>
        <cylinderGeometry args={[2.15, 2.3, 0.16, 64]} />
        <meshStandardMaterial
          color="#1b1640"
          metalness={0.9}
          roughness={0.22}
          emissive="#7c3aed"
          emissiveIntensity={0.35}
        />
      </mesh>
      <mesh position={[0, 0.28, 0]} receiveShadow>
        <cylinderGeometry args={[1.85, 1.95, 0.1, 64]} />
        <meshStandardMaterial color="#0d0b20" metalness={0.8} roughness={0.35} />
      </mesh>

      {/* Pulsing rings. */}
      <mesh ref={innerRing} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.35, 0]}>
        <ringGeometry args={[1.15, 1.35, 96]} />
        <meshStandardMaterial
          color="#22d3ee"
          emissive="#22d3ee"
          emissiveIntensity={1.8}
          toneMapped={false}
          transparent
          opacity={0.9}
        />
      </mesh>
      <mesh ref={outerRing} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.34, 0]}>
        <ringGeometry args={[1.55, 1.72, 96]} />
        <meshStandardMaterial
          color="#a855f7"
          emissive="#a855f7"
          emissiveIntensity={1.6}
          toneMapped={false}
          transparent
          opacity={0.8}
        />
      </mesh>

      {/* Upward light cone from the dais, which is what lifts the robot
          off the background in the reference. */}
      <pointLight position={[0, 0.6, 0]} color="#a855f7" intensity={14} distance={7} decay={2} />
      <pointLight position={[0, 1.6, 1.2]} color="#22d3ee" intensity={6} distance={9} decay={2} />
    </group>
  );
}
