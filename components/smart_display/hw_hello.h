#pragma once
// The capability record in the hello (hw.h): `caps`, an object beside `features`, which the app reads for every screen
// whose firmware sends it (screen_manager/app/page_delivery.py, caps_of). The features "live" and "doorbell" stay
// beside it for an app that reads only those. Apart from hw.h so that hw.h stays free of ESPHome's JSON and a PC test
// includes it alone.
#include "esphome/components/json/json_util.h"

namespace hw {
void hello(JsonObject root);
}
