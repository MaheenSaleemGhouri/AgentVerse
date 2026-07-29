"use client";

/**
 * The things that make the city feel alive: drones crossing the skyline,
 * holographic billboards, and drifting particles.
 *
 * All three are deliberately cheap. They sit behind the robot and are
 * read peripherally, so detail spent here is detail wasted — what
 * matters is that something is always moving.
 */

import { Float, Text } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { Group, Points } from "three";
import { AdditiveBlending, BufferAttribute, BufferGeometry, Color } from "three";

function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

/** Hover vehicles: emissive slivers tracking across the skyline on
 *  looping paths, each with its own speed and altitude. */
export function Drones({ reducedMotion = false }: { reducedMotion?: boolean }): React.JSX.Element {
  const group = useRef<Group>(null);

  const drones = useMemo(() => {
    const random = seeded(90210);
    return Array.from({ length: 14 }, () => ({
      y: 3 + random() * 12,
      z: -10 - random() * 26,
      speed: 0.6 + random() * 1.4,
      offset: random() * 60,
      direction: random() > 0.5 ? 1 : -1,
      color: random() > 0.45 ? "#22d3ee" : "#f0abfc",
      scale: 0.5 + random() * 0.8,
    }));
  }, []);

  useFrame((state) => {
    if (reducedMotion || !group.current) return;
    const t = state.clock.elapsedTime;
    group.current.children.forEach((child, index) => {
      const drone = drones[index];
      if (!drone) return;
      // Wraps through a 60-unit corridor. Modulo rather than a tween so
      // there is no seam and no state to keep between frames.
      const travelled = ((t * drone.speed + drone.offset) % 60) - 30;
      child.position.x = travelled * drone.direction;
      child.position.y = drone.y + Math.sin(t * 0.9 + index) * 0.25;
    });
  });

  return (
    <group ref={group}>
      {drones.map((drone, index) => (
        <group key={index} position={[0, drone.y, drone.z]} scale={drone.scale}>
          <mesh>
            <capsuleGeometry args={[0.06, 0.5, 4, 8]} />
            <meshBasicMaterial color={drone.color} toneMapped={false} />
          </mesh>
          {/* Trail. Sells speed far more cheaply than motion blur. */}
          <mesh position={[-0.7 * drone.direction, 0, 0]}>
            <boxGeometry args={[1.4, 0.02, 0.02]} />
            <meshBasicMaterial color={drone.color} toneMapped={false} transparent opacity={0.35} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

/** The four billboards from the reference, as emissive text planes
 *  floating at depth. Real text rather than a texture, so the copy is
 *  editable and never ships as a blurry raster. */
const BILLBOARDS = [
  { text: "AI AGENTS", position: [-13, 11, -20], rotation: 0.42, color: "#22d3ee" },
  { text: "BUILD · AUTOMATE · SCALE", position: [-8.5, 15.5, -27], rotation: 0.24, color: "#c084fc" },
  { text: "MCP · CONNECT ANYTHING", position: [11, 12.5, -21], rotation: -0.38, color: "#f0abfc" },
  { text: "THE FUTURE IS AGENTIC", position: [15, 16, -29], rotation: -0.22, color: "#60a5fa" },
] as const;

export function Billboards(): React.JSX.Element {
  return (
    <group>
      {BILLBOARDS.map((billboard) => (
        <Float
          key={billboard.text}
          speed={1.1}
          rotationIntensity={0.08}
          floatIntensity={0.35}
          position={[...billboard.position]}
        >
          <group rotation={[0, billboard.rotation, 0]}>
            <mesh>
              <planeGeometry args={[billboard.text.length * 0.32 + 1.4, 1.9]} />
              <meshBasicMaterial
                color="#1a1140"
                transparent
                opacity={0.42}
                toneMapped={false}
              />
            </mesh>
            <Text
              position={[0, 0, 0.06]}
              fontSize={0.52}
              color={billboard.color}
              anchorX="center"
              anchorY="middle"
              letterSpacing={0.08}
              outlineWidth={0.008}
              outlineColor={billboard.color}
            >
              {billboard.text}
            </Text>
          </group>
        </Float>
      ))}
    </group>
  );
}

/** Slow-drifting motes. The one element that fills the empty volume
 *  between the robot and the city. */
export function Particles({ reducedMotion = false }: { reducedMotion?: boolean }): React.JSX.Element {
  const points = useRef<Points>(null);
  const COUNT = 420;

  const geometry = useMemo(() => {
    const random = seeded(4242);
    const positions = new Float32Array(COUNT * 3);
    const colors = new Float32Array(COUNT * 3);
    const violet = new Color("#a855f7");
    const cyan = new Color("#22d3ee");

    for (let i = 0; i < COUNT; i += 1) {
      positions[i * 3] = (random() - 0.5) * 40;
      positions[i * 3 + 1] = random() * 18 - 2;
      positions[i * 3 + 2] = (random() - 0.5) * 34 - 6;
      const tint = random() > 0.5 ? violet : cyan;
      colors[i * 3] = tint.r;
      colors[i * 3 + 1] = tint.g;
      colors[i * 3 + 2] = tint.b;
    }

    const buffer = new BufferGeometry();
    buffer.setAttribute("position", new BufferAttribute(positions, 3));
    buffer.setAttribute("color", new BufferAttribute(colors, 3));
    return buffer;
  }, []);

  useFrame((state) => {
    if (reducedMotion || !points.current) return;
    // Rotating the whole cloud rather than each mote: one matrix update
    // instead of 420 attribute writes a frame.
    points.current.rotation.y = state.clock.elapsedTime * 0.014;
  });

  return (
    <points ref={points} geometry={geometry}>
      <pointsMaterial
        size={0.055}
        vertexColors
        transparent
        opacity={0.75}
        depthWrite={false}
        blending={AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
