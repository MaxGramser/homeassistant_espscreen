export type FirmwarePreviewModule = {
  _preview_init(width: number, height: number, dpi: number, columns: number, rows: number): number;
  // A board without pictures (firmware 0.46.0); a build from before has no such export.
  _preview_pictures?(on: number): void;
  // The screen's Dark mode (app 0.4.86).
  _preview_dark?(on: number): void;
  _preview_settings?(message: number): void;
  _preview_extras?(message: number): void;
  _preview_settings_controls?(on: number): void;
  _preview_next_setting?(): number;
  _preview_time(milliseconds: number, epoch: number, offset: number): void;
  _preview_touch(x: number, y: number, pressed: number): void;
  _preview_cancel(): void;
  _preview_render(): void;
  _preview_frame(): number;
  _preview_page(): number;
  // Another page on the glass, as a swipe brings it (the editor reads a page's cards from the frame).
  _preview_show?(page: number): number;
  _preview_image_buffer(id: number, size: number): number;
  _preview_image_ready(id: number, success: number): number;
  ccall(name: string, returns: string | null, types: string[], args: unknown[]): any;
  HEAPU8: Uint8Array;
  // A plugin's own code (load.ts): its module is written into the preview's file system and loaded from there.
  FS?: { writeFile(path: string, data: Uint8Array): void };
  loadDynamicLibrary?(path: string, flags: { loadAsync: boolean; global: boolean; nodelete: boolean }): Promise<unknown>;
  // The plugins whose module this preview loaded (load.ts), started after _preview_init (startPlugins).
  plugins?: { id: string; path: string }[];
};
declare const createModule: (options?: Record<string, unknown>) => Promise<FirmwarePreviewModule>;
export default createModule;
