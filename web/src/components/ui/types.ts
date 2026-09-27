// A step of the way up in the inspector's head: its text and, when that step can be opened, how.
export type Crumb = { text: string; open?: () => void; mono?: boolean };
