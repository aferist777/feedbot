// The frame every pack lives inside: background, safe areas, the audio track,
// and one sequence per beat. Packs only draw; timing belongs here.

import React from "react";
import {AbsoluteFill, Audio, Sequence, staticFile} from "remotion";
import {Cinema} from "./packs/cinema";
import {Numbers} from "./packs/numbers";
import {Caption, Talk} from "./packs/talk";
import {Tech} from "./packs/tech";
import {Toon} from "./packs/toon";
import type {Beat, ReelProps, Theme} from "./types";

const PACKS: Record<string, React.FC<{beat: Beat; theme: Theme}>> = {
  talk: Talk,
  tech: Tech,
  numbers: Numbers,
  toon: Toon,
  cinema: Cinema,
};

// Packs that already show the caption themselves, or deliberately show none:
// the terminal prints it in its title bar, the card has no room, and cinema
// shows one phrase at a time on purpose.
const CAPTIONLESS = new Set(["cinema", "toon", "tech"]);

const backdrop = (theme: Theme): React.CSSProperties => {
  if (theme.background === "flat") return {backgroundColor: theme.bg};
  if (theme.background === "vignette") {
    return {
      backgroundColor: theme.bg,
      backgroundImage:
        `radial-gradient(circle at 50% 42%, ${theme.bg}00 0%, #00000088 100%)`,
    };
  }
  return {
    backgroundColor: theme.bg,
    backgroundImage:
      `linear-gradient(160deg, ${theme.bg} 0%, #1b1f27 55%, ${theme.bg} 100%)`,
  };
};

export const Reel: React.FC<ReelProps> = ({pack, theme, beats, audio, fps}) => {
  const Draw = PACKS[pack] ?? Talk;

  return (
    <AbsoluteFill style={backdrop(theme)}>
      {audio ? (
        // One file for the whole reel. Speed is applied here rather than at
        // synthesis, and the word timings arrive already divided by it.
        <Audio src={staticFile(audio.file)} playbackRate={audio.tempo} />
      ) : null}

      {beats.map((beat) => {
        const from = Math.round(beat.start * fps);
        const to = Math.round(beat.end * fps);
        return (
          <Sequence key={beat.index} from={from} durationInFrames={Math.max(1, to - from)}>
            <AbsoluteFill style={{
              paddingTop: theme.safeTop,
              paddingBottom: theme.safeBottom,
              paddingLeft: 72,
              paddingRight: 72,
              justifyContent: "space-between",
              // The last line of defence. A pack that miscalculates its own
              // size gets cropped at the safe area instead of bleeding into
              // the platform's interface — a clipped frame is recoverable,
              // text under the Instagram buttons is not.
              overflow: "hidden",
            }}>
              <div style={{flex: 1, minWidth: 0, minHeight: 0, display: "flex",
                alignItems: "center", overflow: "hidden"}}>
                <Draw beat={beat} theme={theme} />
              </div>
              {CAPTIONLESS.has(pack) ? null : <Caption beat={beat} theme={theme} />}
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
