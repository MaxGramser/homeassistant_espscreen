// What the builds leave in the add-on's /data (its build_files.py, docs/BUILDS.md "Build files"): the sizes it measured
// and the words the editor shows them in.
import { editorNumber } from "../i18n";

export type BuildFileSizes = { folders: number; screens: number; cache: number; tools: number; total: number; at: number };
export type BuildFilesView = {
  sizes: BuildFileSizes | null; auto: boolean; offer: boolean; cleaning: "folders" | "all" | null;
  last: { level: "folders" | "all"; at: number; freed: number | null; automatic: boolean } | null; offer_bytes: number;
};

const GB = 1024 ** 3, MB = 1024 ** 2;
/** A size as a person reads it: "6.2 GB" from one gigabyte on, "350 MB" below, "0 MB" for nothing. */
export function sizeText(bytes: number) {
  if (bytes >= GB) return `${editorNumber((bytes / GB).toFixed(1))} GB`;
  return `${editorNumber(String(Math.round(bytes / MB)))} MB`;
}

/** What the clean-up of `level` frees, as measured last. */
export function freedBy(sizes: BuildFileSizes | null | undefined, level: "folders" | "all") {
  if (!sizes) return 0;
  return level === "all" ? sizes.total : sizes.folders;
}
