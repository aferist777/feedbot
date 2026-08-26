import React from "react";
import {Composition} from "remotion";
import {Reel} from "./Reel";
import {DEFAULT_PROPS, type ReelProps} from "./types";

export const Root: React.FC = () => (
  <Composition
    id="reel"
    component={Reel}
    defaultProps={DEFAULT_PROPS}
    fps={DEFAULT_PROPS.fps}
    width={DEFAULT_PROPS.width}
    height={DEFAULT_PROPS.height}
    durationInFrames={300}
    // Length comes from the props, not from a constant: every reel is its own
    // length, and the audio decides it.
    calculateMetadata={({props}: {props: ReelProps}) => {
      const last = props.beats.length
        ? props.beats[props.beats.length - 1].end
        : props.audio?.seconds ?? 10;
      const tail = 0.6; // let the final word land before the cut
      return {
        durationInFrames: Math.max(1, Math.round((last + tail) * props.fps)),
        fps: props.fps,
        width: props.width,
        height: props.height,
      };
    }}
  />
);
