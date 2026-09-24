// Generated firmware profile dispatch.
#include "font.h"
struct FirmwareUi { lv_obj_t *room, *time, *prev, *next, *number; void (*bind)(); void (*cell)(size_t); const char *look; };
namespace standard_133 {
#include "standard_133/ui.h"
}
namespace compact_143 {
#include "compact_143/ui.h"
}
namespace standard_149 {
#include "standard_149/ui.h"
}
namespace standard_170 {
#include "standard_170/ui.h"
}
namespace standard_217 {
#include "standard_217/ui.h"
}
namespace standard_254 {
#include "standard_254/ui.h"
}
static FirmwareUi setup_firmware_ui(lv_obj_t *root, int dpi) {
if (dpi == 133) { using namespace standard_133; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "standard"}; }
if (dpi == 143) { using namespace compact_143; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "compact"}; }
if (dpi == 149) { using namespace standard_149; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "standard"}; }
if (dpi == 170) { using namespace standard_170; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "standard"}; }
if (dpi == 217) { using namespace standard_217; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "standard"}; }
if (dpi == 254) { using namespace standard_254; setup_firmware_ui(root);
return {lbl_room, lbl_time, page_prev, page_next, page_number, bind_firmware_ui, setup_firmware_cell, "standard"}; }
return {};
}
