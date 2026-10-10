// The clocks of the mockup at one moment, as the screens draw them in their language: the time and date of the top bar
// and the screensaver, and a clock card's faces (digital, flip, analog, bedside). Every place that draws a clock takes
// its sample of the editor's one clock (the store's now), so they all show the same minute.
import { t } from "../i18n";
import { clockText, dateText } from "./topbar";

export type ClockSample = {
  /** The time as the top bar writes it: "19:05", or "7:05 PM" on a 12-hour clock. */
  time: string;
  /** The time without AM or PM, which a card writes beside it: "19:05", "7:05". */
  digits: string;
  /** The top bar's date: "Sa 10 Oct". */
  date: string;
  /** A clock card's date: "Saturday 10 October". */
  longDate: string;
  /** The day under a wide flip clock: "Saturday 10 Oct". */
  flipDate: string;
  /** A flip clock's blocks: "07" "05" on 24 hours, "7" "05" on 12. */
  hours: string;
  minutes: string;
  /** "AM" or "PM" in the screens' words. */
  amPm: string;
  /** The hands of an analog clock, in degrees from twelve. */
  hourAngle: number;
  minuteAngle: number;
};

export function clockSample(at: number | Date, clock24: boolean, locale = "en"): ClockSample {
  const now = new Date(at), hour = now.getHours(), minute = now.getMinutes();
  const say = (key: string, named: Record<string, unknown> = {}) => t(key, named, { locale });
  return {
    time: clockText(clock24, now, locale),
    digits: clockText(clock24, now),
    date: dateText(now, locale),
    longDate: say("screen.date.full", { weekday: say(`screen.date.weekdays.${now.getDay()}`), day: now.getDate(), month: say(`screen.date.months.${now.getMonth()}`) }),
    flipDate: `${say(`screen.date.weekdays.${now.getDay()}`)} ${say("screen.date.day_month", { day: now.getDate(), month: say(`screen.date.months_short.${now.getMonth()}`) })}`,
    hours: clock24 ? String(hour).padStart(2, "0") : String(hour % 12 || 12),
    minutes: String(minute).padStart(2, "0"),
    amPm: say(`screen.time.${hour < 12 ? "am" : "pm"}`),
    hourAngle: (hour % 12 + minute / 60) * 30,
    minuteAngle: minute * 6,
  };
}
