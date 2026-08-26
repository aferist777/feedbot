// unDraw illustrations, tied to the icon the beat already carries.
//
// The model is not asked to name an illustration — 1263 names would bloat the
// prompt and it would guess. It names an icon from the catalogue, and that
// icon maps here. An icon with no illustration falls back to the icon itself,
// which is why nothing ever renders empty.

import {
  SvgBugFixing, SvgCloudHosting, SvgCodeReview, SvgCodeTyping, SvgDataReport,
  SvgDataTrends, SvgDeliveries, SvgDesignNotes, SvgDeveloperActivity,
  SvgFileSearching, SvgGrowthAnalytics, SvgInProgress, SvgLightbulbMoment,
  SvgMailSent, SvgMobileApps, SvgOnlineShopping, SvgPersonalNotebook,
  SvgProgrammer, SvgSafe, SvgSecureServer, SvgServerDown, SvgServerStatus,
  SvgSettings, SvgSocialGrowth, SvgSpeechToText, SvgTaskList, SvgTimeManagement,
  SvgUploadImage, SvgWebDevices, SvgWorkTime,
} from "iblis-react-undraw";
import React from "react";
import type {Theme} from "./types";

type Art = React.FC<Record<string, unknown>>;

// One illustration per icon, only where a real match exists. Half the
// catalogue has none, and that is fine — a wrong illustration is worse than
// none, because the viewer spends the beat working out what it means.
const BY_ICON: Record<string, Art> = {
  server: SvgServerStatus as Art,
  terminal: SvgCodeTyping as Art,
  database: SvgDataReport as Art,
  container: SvgCloudHosting as Art,
  cloud: SvgCloudHosting as Art,
  wifi: SvgWebDevices as Art,
  lock: SvgSafe as Art,
  shield: SvgSecureServer as Art,
  bug: SvgBugFixing as Art,
  alert: SvgServerDown as Art,
  clock: SvgTimeManagement as Art,
  calendar: SvgWorkTime as Art,
  "trending-up": SvgGrowthAnalytics as Art,
  "trending-down": SvgDataTrends as Art,
  coins: SvgOnlineShopping as Art,
  package: SvgDeliveries as Art,
  code: SvgProgrammer as Art,
  "git-branch": SvgCodeReview as Art,
  cpu: SvgDeveloperActivity as Art,
  monitor: SvgWebDevices as Art,
  smartphone: SvgMobileApps as Art,
  mail: SvgMailSent as Art,
  "message-circle": SvgSpeechToText as Art,
  users: SvgSocialGrowth as Art,
  search: SvgFileSearching as Art,
  settings: SvgSettings as Art,
  wrench: SvgInProgress as Art,
  upload: SvgUploadImage as Art,
  "file-text": SvgPersonalNotebook as Art,
  lightbulb: SvgLightbulbMoment as Art,
  book: SvgDesignNotes as Art,
  "shopping-cart": SvgOnlineShopping as Art,
  activity: SvgGrowthAnalytics as Art,
  check: SvgTaskList as Art,
};

export const hasArt = (icon: string) => Boolean(BY_ICON[icon]);

export const Illustration: React.FC<{
  icon: string;
  theme: Theme;
  height?: number;
  style?: React.CSSProperties;
}> = ({icon, theme, height = 620, style}) => {
  const Art = BY_ICON[icon];
  if (!Art) return null;
  return (
    <Art
      // unDraw ships one purple and two greys; recolouring them to the feed's
      // own palette is what stops every reel looking like a landing page.
      primarycolor={theme.accent}
      accentcolor={theme.ink}
      haircolor={theme.dim}
      skincolor="#d8b0a0"
      style={{height, width: "100%", ...style}}
    />
  );
};
