"use client";

/**
 * The procedural skyline behind the robot.
 *
 * Not an attempt to reproduce the concept render's city, which is a
 * raster image — this recreates its *mood*: neon towers receding into
 * violet fog, lit windows, a wet floor throwing everything back.
 *
 * Built from three instanced meshes rather than hundreds of draw calls.
 * A skyline is the cheapest part of this scene to get wrong
 * performance-wise: 240 towers as individual meshes would cost 240 draw
 * calls a frame for geometry nobody looks directly at.
 */

import { Instance, Instances } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { InstancedMesh } from "three";
import { Color } from "three";

/** Deterministic pseudo-random so the skyline is identical every load.
 *  `Math.random()` would give a different city on every render pass and
 *  a different one on the server than the client. */
function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

interface Tower {
  readonly position: [number, number, number];
  readonly scale: [number, number, number];
  readonly color: Color;
}

/** Three depth bands. Nearer towers are larger, brighter, and fewer;
 *  distant ones dissolve into the fog, which is what creates depth
 *  without a single texture. */
const BANDS = [
  { count: 26, z: -14, spread: 34, minH: 6, maxH: 15, intensity: 1.0 },
  { count: 34, z: -24, spread: 48, minH: 8, maxH: 22, intensity: 0.62 },
  { count: 42, z: -38, spread: 66, minH: 10, maxH: 30, intensity: 0.34 },
] as const;

const PALETTE = ["#7c3aed", "#a855f7", "#4c1d95", "#2563eb", "#22d3ee", "#c026d3"] as const;

function useTowers(): Tower[] {
  return useMemo(() => {
    const random = seeded(20260729);
    const towers: Tower[] = [];

    for (const band of BANDS) {
      for (let i = 0; i < band.count; i += 1) {
        const height = band.minH + random() * (band.maxH - band.minH);
        const x = (random() - 0.5) * band.spread;
        // The centre is left clear so the robot is never occluded — the
        // one place this generator is not free to place geometry.
        if (Math.abs(x) < 4.5 && band.z > -20) continue;

        const width = 1.1 + random() * 2.2;
        const color = new Color(PALETTE[Math.floor(random() * PALETTE.length)]!);
        color.multiplyScalar(band.intensity);

        towers.push({
          position: [x, height / 2 - 2, band.z + (random() - 0.5) * 6],
          scale: [width, height, width * (0.7 + random() * 0.6)],
          color,
        });
      }
    }
    return towers;
  }, []);
}

export function NeonCity(): React.JSX.Element {
  const towers = useTowers();

  return (
    <Instances limit={towers.length} castShadow={false} receiveShadow={false}>
      <boxGeometry args={[1, 1, 1]} />
      {/* Emissive rather than lit: a hundred towers each catching a real
          light would need a hundred light calculations. The bloom pass
          turns emission into the glow the design is built on. */}
      <meshStandardMaterial
        toneMapped={false}
        emissiveIntensity={1}
        roughness={0.35}
        metalness={0.6}
      />
      {towers.map((tower, index) => (
        <Instance
          key={index}
          position={tower.position}
          scale={tower.scale}
          color={tower.color}
        />
      ))}
    </Instances>
  );
}

/**
 * Window lights: small emissive quads scattered over the skyline, drifting
 * in brightness so the city reads as inhabited rather than modelled.
 */
export function CityWindows(): React.JSX.Element {
  const ref = useRef<InstancedMesh>(null);
  const lights = useMemo(() => {
    const random = seeded(31337);
    return Array.from({ length: 150 }, () => ({
      position: [
        (random() - 0.5) * 56,
        random() * 22 - 1,
        -12 - random() * 28,
      ] as [number, number, number],
      color: new Color(random() > 0.5 ? "#22d3ee" : "#e9d5ff"),
      phase: random() * Math.PI * 2,
    }));
  }, []);

  const group = useRef<{ material?: { opacity: number } }>(null);
  useFrame((state) => {
    if (!group.current?.material) return;
    group.current.material.opacity = 0.55 + Math.sin(state.clock.elapsedTime * 0.6) * 0.12;
  });

  return (
    <Instances limit={lights.length} ref={ref as never}>
      <planeGeometry args={[0.14, 0.22]} />
      <meshBasicMaterial toneMapped={false} transparent opacity={0.6} ref={group as never} />
      {lights.map((light, index) => (
        <Instance key={index} position={light.position} color={light.color} />
      ))}
    </Instances>
  );
}
