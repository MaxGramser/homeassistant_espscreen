export type FirmwarePreviewModule = {
  _preview_init(width: number, height: number, dpi: number, columns: number, rows: number): number;
  _preview_time(milliseconds: number, epoch: number, offset: number): void;
  _preview_touch(x: number, y: number, pressed: number): void;
  _preview_cancel(): void;
  _preview_render(): void;
  _preview_frame(): number;
  _preview_page(): number;
  ccall(name: string, returns: string | null, types: string[], args: unknown[]): any;
  HEAPU8: Uint8Array;
};
declare const createModule: (options?: Record<string, unknown>) => Promise<FirmwarePreviewModule>;
export default createModule;
