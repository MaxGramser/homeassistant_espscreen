#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_camera_view.cpp -o /tmp/test_camera_view && /tmp/test_camera_view
#include "../components/smart_display/camera_view.h"
#include <cassert>

using namespace camera_view;

int main() {
  Feed feed;
  assert(!feed.open() && !feed.should_ask(0) && !feed.should_load(0));

  // Opening asks at once; a link that does not come is asked for again after ASK_AGAIN_MS.
  feed.open("camera.front_door");
  assert(feed.should_ask(1000));
  feed.ask(1000);
  assert(!feed.should_ask(1000 + ASK_AGAIN_MS - 1));
  assert(feed.should_ask(1000 + ASK_AGAIN_MS));

  // A link loads at once, then every REFRESH_MS from the start of the last load.
  feed.link("http://192.168.1.2:8098/camera/abcdefghijklmnopqrstuvwx.jpg");
  assert(!feed.should_ask(2000) && feed.should_load(2000));
  feed.start(2000);
  assert(!feed.should_load(2100) && !feed.should_ask(2100));
  feed.finish(2300, true);
  assert(feed.shown && !feed.should_load(2000 + REFRESH_MS - 1) && feed.should_load(2000 + REFRESH_MS));

  // A load that ends near the next start still leaves GAP_MS for touch and drawing before the next one.
  const uint32_t slow_end = 5000 + REFRESH_MS - 100;
  feed.start(5000);
  feed.finish(slow_end, true);
  assert(!feed.should_load(5000 + REFRESH_MS) && !feed.should_load(slow_end + GAP_MS - 1) && feed.should_load(slow_end + GAP_MS));
  // An ordinary load keeps the rhythm: the next start is REFRESH_MS after this one, however quickly it ended.
  feed.start(20000);
  feed.finish(20000 + REFRESH_MS / 2, true);
  assert(!feed.should_load(20000 + REFRESH_MS - 1) && feed.should_load(20000 + REFRESH_MS));

  // Failures keep the link until MAX_FAILURES in a row; then a new link is asked for, the image stays shown.
  uint32_t now = 10000;
  for (uint8_t i = 0; i < MAX_FAILURES; ++i) {
    assert(!feed.url.empty());
    feed.start(now);
    feed.finish(now + 100, false);
    now += REFRESH_MS;
  }
  assert(feed.url.empty() && feed.shown && feed.should_ask(now));

  // An app without an image answers an empty link: nothing loads, and the view asks again later.
  feed.ask(now);
  feed.link("");
  assert(feed.empty && !feed.should_load(now) && !feed.should_ask(now + 1) && feed.should_ask(now + ASK_AGAIN_MS));

  // A success after a failure starts the count again.
  feed.link("http://192.168.1.2:8098/camera/abcdefghijklmnopqrstuvwx.jpg");
  feed.start(now); feed.finish(now + 10, false);
  feed.start(now + REFRESH_MS); feed.finish(now + REFRESH_MS + 10, true);
  assert(feed.failures == 0 && !feed.url.empty());

  // Opening another camera forgets everything of the last one; millis() 0 still counts as a start.
  feed.open("image.doorbell_snapshot");
  assert(feed.url.empty() && !feed.shown && feed.should_ask(0));
  feed.link("http://h/camera/x.jpg");
  feed.start(0);
  feed.finish(10, true);
  assert(!feed.should_load(REFRESH_MS - 1) && feed.should_load(REFRESH_MS + 1));

  // The live pictures of a page's camera tiles (firmware 0.2.77+) load at the tiles' own pace instead of REFRESH_MS.
  Feed tiles;
  tiles.open("camera.front_door,camera.garden", false, 15000);
  tiles.ask(0);
  tiles.link("http://h/camera/tiles.bmp");
  tiles.start(100);
  tiles.finish(400, true);
  assert(!tiles.should_load(100 + 15000 - 1) && tiles.should_load(100 + 15000));
  assert(tiles.every == 15000 && feed.every == REFRESH_MS);
  // Without a picture (an empty link) they ask again at that pace, not every ASK_AGAIN_MS.
  tiles.open("camera.front_door", false, 30000);
  tiles.ask(0);
  tiles.link("");
  assert(tiles.empty && !tiles.should_ask(ASK_AGAIN_MS) && !tiles.should_ask(30000 - 1) && tiles.should_ask(30000));

  // An album cover (firmware 0.2.64+) loads once per link: it stays on screen, never refreshed on a clock.
  Feed cover;
  cover.open("media_player.office", true);
  assert(cover.once && cover.should_ask(0));
  cover.ask(0);
  cover.link("http://h/camera/cover.bmp");
  assert(cover.should_load(100));
  cover.start(100);
  cover.finish(400, true);
  assert(cover.loaded && cover.shown && !cover.should_load(400 + GAP_MS) && !cover.should_load(400 + 10 * REFRESH_MS) && !cover.should_ask(400 + ASK_AGAIN_MS));
  // A failed load is tried again after the gap; three failures forget the link so the card asks for a new one.
  cover.link("http://h/camera/cover2.bmp");
  assert(!cover.loaded && cover.should_load(1000));
  cover.start(1000); cover.finish(1100, false);
  assert(!cover.should_load(1100 + GAP_MS - 1) && cover.should_load(1100 + GAP_MS));
  cover.start(2000); cover.finish(2100, false);
  cover.start(3000); cover.finish(3100, false);
  assert(cover.url.empty() && cover.should_ask(3100));
  // A new link (a new picture in Home Assistant) loads again, once.
  cover.ask(3100);
  cover.link("http://h/camera/cover3.bmp");
  cover.start(3200); cover.finish(3500, true);
  assert(cover.loaded && !cover.should_load(3500 + 10 * REFRESH_MS));
  // A player without a picture (or an app from before covers) answers an empty link: asked once, then left alone.
  Feed bare;
  bare.open("media_player.radio", true);
  bare.ask(0);
  bare.link("");
  assert(bare.empty && !bare.should_ask(ASK_AGAIN_MS) && !bare.should_ask(100 * ASK_AGAIN_MS) && !bare.should_load(ASK_AGAIN_MS));
  // A page of maps alone (firmware 0.30.0+) loads once too, but the app draws a map itself, so an answer without a
  // picture is a failure on the way: asked for again after ASK_AGAIN_MS, then twice as long each time up to
  // ASK_AGAIN_MAX_MS. Before, one such answer left the cards without their map until the page turned (discussion 105).
  Feed maps;
  maps.open("person.one,screen.map", true, 15000, true);
  assert(maps.once && maps.again && maps.should_ask(0));
  maps.ask(0);
  maps.link("");
  assert(maps.empty && maps.empties == 1 && !maps.should_load(ASK_AGAIN_MS) && maps.animation_ready());
  assert(!maps.should_ask(ASK_AGAIN_MS - 1) && maps.should_ask(ASK_AGAIN_MS));
  uint32_t at = ASK_AGAIN_MS;
  for (uint32_t wait : {2 * ASK_AGAIN_MS, 4 * ASK_AGAIN_MS, 8 * ASK_AGAIN_MS, 16 * ASK_AGAIN_MS, ASK_AGAIN_MAX_MS, ASK_AGAIN_MAX_MS}) {
    maps.ask(at);
    maps.link("");
    assert(!maps.should_ask(at + wait - 1) && maps.should_ask(at + wait));
    at += wait;
  }
  // The picture that comes then loads once and stays, and the count starts again.
  maps.ask(at);
  maps.link("http://h/camera/maps.bmp");
  assert(maps.empties == 0 && maps.should_load(at));
  maps.start(at); maps.finish(at + 300, true);
  assert(maps.loaded && !maps.should_load(at + 100 * REFRESH_MS) && !maps.should_ask(at + 100 * ASK_AGAIN_MS));
  // A page of covers alone keeps its rule: asked once, then left alone.
  assert(!bare.again && !cover.again);
  // Background media titles wait for the first image, and pause on refresh or
  // retry. Missing images and failed downloads still permit fallback motion.
  Feed background;
  background.open("media_player.background", true);
  assert(!background.animation_ready());
  background.ask(10);
  assert(!background.animation_ready());
  background.link("http://h/background.bmp");
  assert(!background.animation_ready());
  background.start(20);
  assert(!background.animation_ready());
  background.finish(30, true);
  assert(background.animation_ready());
  background.start(40);
  assert(!background.animation_ready());
  background.finish(50, false);
  assert(background.animation_ready());
  background.link("http://h/new-track.bmp");
  assert(!background.animation_ready());
  background.start(60);background.finish(70, false);
  assert(background.animation_ready());
  background.start(900);
  assert(!background.animation_ready());
  background.finish(950, true);
  assert(background.animation_ready());
  background.open("media_player.other", true);
  assert(!background.animation_ready());
  background.link("");
  assert(background.animation_ready());
  // A camera feed keeps its clock: open() without the flag.
  Feed live;
  live.open("camera.front_door");
  assert(!live.once);
  // A page that comes back with its camera picture kept (firmware 0.3.2+): the link is asked for as usual, the next
  // load waits until the kept picture is as old as the feed's pace, and a new link does not undo that.
  Feed back;
  back.open("camera.front_door", false, 15000);
  back.resume(100000);
  assert(back.should_ask(101000));
  back.ask(101000);
  back.link("http://192.168.1.2:8098/camera/abcdefghijklmnopqrstuvwx.jpg");
  assert(!back.should_load(101000) && !back.should_load(114999) && back.should_load(115000));
  // Nothing loads between two quick page turns.
  assert(!settled(10500, 10000) && settled(10000 + SETTLE_MS, 10000));

  // Pictures load while the tiles are seen (GitHub #161): a screen in use, whatever its levels.
  assert(tiles_seen(true, false, 0) && tiles_seen(true, true, 0));
  // In standby the dimmed tiles are seen without a screensaver over them, from SEEN_LEVEL % on.
  assert(tiles_seen(false, false, SEEN_LEVEL) && tiles_seen(false, false, 40));
  assert(!tiles_seen(false, false, SEEN_LEVEL - 1) && !tiles_seen(false, false, 0));
  // A screensaver covers them, the clock as much as a camera, at any level.
  assert(!tiles_seen(false, true, 40) && !tiles_seen(false, true, 100));
  return 0;
}
