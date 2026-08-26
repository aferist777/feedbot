// Технический: the beat's own scene, dressed as a machine would show it.
//
// The previous version could only print a line of monospace. Now the scene the
// model chose does the showing — a log, a flow, a comparison — and this pack
// decides how it is framed: mono type, a scan line, a corner label.

import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import {density} from "../motion";
import {SCENES} from "../scenes";
import {SKINS, type Beat, type Theme} from "../types";

const MONO = '"Cascadia Mono", Consolas, monospace';

export const Tech: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const now = frame / fps + beat.start;
  const Scene = SCENES[beat.scene] ?? SCENES.line;
  const {drift, event} = density(now, beat.start, beat.words.map((w) => w.start));

  const arrive = interpolate(frame, [0, fps * 0.28], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <div style={{width: "100%", minWidth: 0, position: "relative"}}>
      {/* The grid drifts the whole time — the frame is never completely still. */}
      <div style={{
        position: "absolute", inset: -200, opacity: 0.05,
        backgroundImage:
          `linear-gradient(${theme.ink} 1px, transparent 1px),`
          + `linear-gradient(90deg, ${theme.ink} 1px, transparent 1px)`,
        backgroundSize: "64px 64px",
        transform: `translateY(${drift * 16 - 8}px)`,
      }} />

      {/* A scan line sweeps down on the beat's accents, the way a terminal
          redraws — cheap, and it reads as "machine" instantly. */}
      <div style={{
        position: "absolute", left: -80, right: -80,
        top: `${(1 - event) * height * 0.5}px`,
        height: 2, background: theme.accent, opacity: event * 0.5,
      }} />

      <div style={{
        transform: `translateY(${(1 - arrive) * 18}px)`,
        opacity: arrive,
      }}>
        {/* The caption goes here rather than at the foot of the frame: this
            pack looks like a machine's output, and machines label at the top.
            The scene name used to be printed here while it was being built —
            useful then, debug noise now. */}
        {beat.on_screen && beat.scene !== "log" && beat.scene !== "alert" ? (
          <div style={{
            fontFamily: MONO, fontSize: theme.captionSize * 0.8, color: theme.accent,
            marginBottom: 18, letterSpacing: 0.5, overflowWrap: "anywhere",
          }}>
            {"› "}{beat.on_screen}
          </div>
        ) : null}
        <Scene beat={beat} theme={theme} now={now} skin={SKINS.tech} src={beat.photo} />
      </div>
    </div>
  );
};
