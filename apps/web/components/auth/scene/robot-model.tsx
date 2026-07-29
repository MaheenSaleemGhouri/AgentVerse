"use client";

/**
 * Loads and animates the hero robot.
 *
 * Holds no knowledge of *which* robot: every path, clip name, transform,
 * and tint comes from `robot-config.ts`, so replacing the model is an
 * asset swap plus a config edit. See that file for the licence.
 */

import { useAnimations, useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { AnimationAction, Group, Mesh } from "three";
import { LoopOnce, MeshStandardMaterial } from "three";

import { ROBOT } from "./robot-config";

useGLTF.preload(ROBOT.url);

export function RobotModel({ reducedMotion = false }: { reducedMotion?: boolean }): React.JSX.Element {
  const group = useRef<Group>(null);
  const { scene, animations } = useGLTF(ROBOT.url);

  // Cloning per mount rather than mutating the cached GLTF: `useGLTF`
  // memoises by URL, so tinting the shared scene would leak into any
  // other mount of the same model.
  const model = useMemo(() => {
    const cloned = scene.clone(true);
    cloned.traverse((child) => {
      const mesh = child as Mesh;
      if (!mesh.isMesh) return;
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      mesh.material = materials.map((source) => {
        const tint = ROBOT.materialTints[source.name];
        // A material the config does not name is left exactly as the
        // artist authored it — a replacement model with different
        // material names loses the tint but still renders correctly.
        const next = (source as MeshStandardMaterial).clone();
        if (tint) {
          next.color.set(tint.color);
          if (tint.emissive) next.emissive.set(tint.emissive);
          if (tint.emissiveIntensity !== undefined) next.emissiveIntensity = tint.emissiveIntensity;
        }
        return next;
      }) as MeshStandardMaterial[];
      if (Array.isArray(mesh.material) && mesh.material.length === 1) {
        mesh.material = mesh.material[0]!;
      }
    });
    return cloned;
  }, [scene]);

  const { actions, mixer } = useAnimations(animations, group);

  useEffect(() => {
    const idle = actions[ROBOT.idleClip];
    const wave = actions[ROBOT.waveClip];

    // Missing clips degrade to a static pose instead of throwing, so a
    // model swap with different clip names is visibly wrong rather than
    // a white screen.
    if (!idle) {
      if (process.env.NODE_ENV !== "production") {
        console.warn(
          `[auth-hero] "${ROBOT.idleClip}" not found in ${ROBOT.url}. ` +
            `Available: ${Object.keys(actions).join(", ")}`,
        );
      }
      return;
    }

    idle.reset().fadeIn(ROBOT.crossFadeSeconds).play();

    // A robot frozen mid-pose reads as broken, so reduced motion keeps
    // the idle loop (a slow breathe, not vestibular motion) and drops
    // only the gesture. WCAG 2.3.3 targets motion that conveys nothing.
    if (reducedMotion || !wave) {
      return () => {
        idle.fadeOut(ROBOT.crossFadeSeconds);
      };
    }

    let cancelled = false;
    const playWave = (): void => {
      if (cancelled) return;
      wave.reset().setLoop(LoopOnce, 1).play();
      wave.clampWhenFinished = true;
      wave.crossFadeFrom(idle, ROBOT.crossFadeSeconds, false);
    };

    const onFinished = (event: { action: AnimationAction }): void => {
      if (event.action !== wave || cancelled) return;
      idle.reset().play();
      idle.crossFadeFrom(wave, ROBOT.crossFadeSeconds, false);
    };
    mixer.addEventListener("finished", onFinished as never);

    // Waves once on entry — the welcome gesture the design is built
    // around — then settles into a slow interval.
    const entry = window.setTimeout(playWave, 700);
    const interval = window.setInterval(playWave, ROBOT.waveIntervalSeconds * 1000);

    return () => {
      cancelled = true;
      window.clearTimeout(entry);
      window.clearInterval(interval);
      mixer.removeEventListener("finished", onFinished as never);
      idle.fadeOut(ROBOT.crossFadeSeconds);
      wave.fadeOut(ROBOT.crossFadeSeconds);
    };
  }, [actions, mixer, reducedMotion]);

  // A hair of vertical drift on top of the baked idle, so the robot
  // reads as hovering over the platform rather than welded to it.
  useFrame((state) => {
    if (reducedMotion || !group.current) return;
    const t = state.clock.elapsedTime;
    group.current.position.y = ROBOT.position[1] + Math.sin(t * 0.7) * 0.045;
  });

  return (
    <group
      ref={group}
      position={[...ROBOT.position]}
      rotation={[...ROBOT.rotation]}
      scale={ROBOT.scale}
      // The scene is decorative; the page's meaning is in the panels.
      // Announcing a 3D robot to a screen reader adds noise, so the
      // whole canvas is hidden and the hero's text carries the message.
      dispose={null}
    >
      <primitive object={model} />
    </group>
  );
}
