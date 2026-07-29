/**
 * The one place the auth hero's robot is configured.
 *
 * Swapping in the final branded AgentVerse robot should mean editing
 * this file and dropping a new `.glb` into `public/models/` — nothing
 * else. `robot-model.tsx` reads every value from here and holds no
 * knowledge of which model is loaded, so a different rig with different
 * clip names is a config change rather than a component rewrite.
 *
 * ## Current model
 *
 * `RobotExpressive` by Tomás Laulhé, modified by Don McCurdy —
 * **CC0 (public domain)**, shipped in the three.js repository. Chosen
 * over the alternatives because it is genuinely licence-free (no
 * attribution obligation to track), it is a humanoid rather than a
 * mechanical arm, and it already carries an `Idle` and a `Wave` clip —
 * the two gestures the approved design calls for. 454 kB.
 *
 * Source: https://github.com/mrdoob/three.js/tree/dev/examples/models/gltf/RobotExpressive
 *
 * A replacement model must be checked against `REQUIRED_CLIPS` below;
 * `robot-model.tsx` degrades to a static pose rather than throwing if a
 * clip is missing, so a bad swap is visible rather than fatal.
 */

export interface RobotConfig {
  /** Path under `public/`. */
  readonly url: string;
  /** Clip played continuously underneath the gesture. */
  readonly idleClip: string;
  /** Gesture played on entry and then on a slow loop. */
  readonly waveClip: string;
  /** Seconds between waves. The design wants a welcome, not a metronome. */
  readonly waveIntervalSeconds: number;
  /** Cross-fade duration between idle and gesture, in seconds. */
  readonly crossFadeSeconds: number;
  readonly position: readonly [number, number, number];
  readonly rotation: readonly [number, number, number];
  readonly scale: number;
  /**
   * Retints the model's materials by name so a generic robot reads as
   * an AgentVerse one. Keys are material names inside the GLB — for the
   * current model, `Main`, `Grey`, and `Black`.
   *
   * A name that does not exist in a replacement model is ignored, which
   * is why this is a lookup rather than an array: a swap that changes
   * material names loses the tint but still renders.
   */
  readonly materialTints: Readonly<Record<string, { color: string; emissive?: string; emissiveIntensity?: number }>>;
}

export const ROBOT: RobotConfig = {
  url: "/models/robot.glb",
  idleClip: "Idle",
  waveClip: "Wave",
  waveIntervalSeconds: 9,
  crossFadeSeconds: 0.45,
  // Sits on the platform, turned a few degrees off-axis so the wave
  // reads as directed at the viewer rather than straight ahead.
  position: [0, -0.85, 0],
  rotation: [0, -0.18, 0],
  scale: 0.62,
  materialTints: {
    // The white body of the reference render.
    Main: { color: "#f4f3ff", emissive: "#2a1f5e", emissiveIntensity: 0.25 },
    // Joints and panel lines — cool grey so the violet rim light reads.
    Grey: { color: "#b9b6d6", emissive: "#1a1440", emissiveIntensity: 0.2 },
    // The visor. Emissive cyan is what makes the face glow in the dark
    // scene the way the reference does.
    Black: { color: "#0a0a18", emissive: "#22d3ee", emissiveIntensity: 1.6 },
  },
};

/** Clips a replacement model must provide for the hero to animate. */
export const REQUIRED_CLIPS = [ROBOT.idleClip, ROBOT.waveClip] as const;
