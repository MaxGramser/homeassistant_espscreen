"""The vacuum card of the module (module_vacuum_card.h): what the add-on sends beside the robot's own state
(screen_manager/app/vacuum_card.py) and the map it cleans up and draws in the screen's look (vacuum_map.py).

The card shows only what a robot offers: a map on its device, the areas linked to its segments in Home Assistant (in
Home Assistant's order of floors and areas, only those of the map it is on), its routines, why it stopped and how far it
is. A robot without any of it gets none of it."""
import importlib.util
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import vacuum_card  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
ROBOT = 'vacuum.robot'
CLEAN_AREA, FULL = 16384, 4 | 8 | 16 | 32 | 512 | 4096 | 8192 | 16384


def entry(entity, **more):
    return {'entity_id': entity, 'device_id': 'dev', 'platform': 'roborock', **more}


def robot(features=FULL, state='docked', mapping=None, segments=None):
    """(states, device entries, registry index) of a robot with a map, rooms, routines and its sensors."""
    states = {
        ROBOT: {'state': state, 'attributes': {'friendly_name': 'Robot', 'supported_features': features}},
        'image.robot_home': {'state': '2026-09-15T08:00:00+00:00', 'attributes': {}},
        'select.robot_selected_map': {'state': 'Home', 'attributes': {'options': ['Home', 'Upstairs']}},
        'button.robot_kitchen_clean': {'state': 'unknown', 'attributes': {'friendly_name': 'Robot Kitchen clean'}},
        'button.robot_reset_filter': {'state': 'unknown', 'attributes': {}},
        'sensor.robot_vacuum_error': {'state': 'none', 'attributes': {'device_class': 'enum'}},
        'sensor.robot_cleaning_progress': {'state': '45', 'attributes': {'unit_of_measurement': '%'}},
        'sensor.robot_cleaning_area': {'state': '18.4', 'attributes': {'unit_of_measurement': 'm²'}},
    }
    options = {'vacuum': {'area_mapping': mapping if mapping is not None else {'kitchen': ['0_17'], 'living_room': ['0_18'], 'bedroom': ['1_20']},
                          'last_seen_segments': segments if segments is not None else [
                              {'id': '0_17', 'name': 'Kitchen', 'group': 'Home'}, {'id': '0_18', 'name': 'Living room', 'group': 'Home'},
                              {'id': '1_20', 'name': 'Bedroom', 'group': 'Upstairs'}]}}
    device = [entry(ROBOT, options=options), entry('image.robot_home', original_name='Home', entity_category='diagnostic'),
              entry('select.robot_selected_map', translation_key='selected_map'),
              entry('button.robot_kitchen_clean', original_name='Kitchen clean'),
              entry('button.robot_reset_filter', entity_category='config'),
              entry('sensor.robot_vacuum_error', translation_key='vacuum_error'),
              entry('sensor.robot_cleaning_progress', translation_key='clean_percent'),
              entry('sensor.robot_cleaning_area', translation_key='cleaning_area')]
    return states, device, {item['entity_id']: item for item in device}


AREAS = [{'area_id': 'hall', 'name': 'Hall', 'icon': 'mdi:door', 'floor_id': 'ground'},
         {'area_id': 'living_room', 'name': 'Living room', 'icon': 'mdi:sofa', 'floor_id': 'ground'},
         {'area_id': 'kitchen', 'name': 'Kitchen', 'icon': None, 'floor_id': 'ground'},
         {'area_id': 'bedroom', 'name': 'Bedroom', 'icon': 'mdi:bed', 'floor_id': 'first'}]
FLOORS = [{'floor_id': 'ground', 'name': 'Ground floor'}, {'floor_id': 'first', 'name': 'First floor'}]


class Payload(unittest.TestCase):
    def test_a_full_robot_brings_its_map_rooms_and_routines(self):
        states, device, entries = robot()
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS, device_name='Robot', glyph=lambda icon: 'F04B9' if icon == 'mdi:sofa' else None)
        self.assertEqual(out['map'], {'e': 'image.robot_home', 'm': '2026-09-15T08:00:00+00:00'})
        # Only the areas of the map it is on (Home): the bedroom lies on the other map, which it would skip.
        self.assertEqual(out['rooms'], [['living_room', 'Living room', 'F04B9', 0], ['kitchen', 'Kitchen', '', 0]])
        self.assertNotIn('floors', out)
        # The routines run something; a reset of a consumable is no routine.
        self.assertEqual(out['rt'], [['button.robot_kitchen_clean', 'Kitchen clean']])
        # Docked: no progress, no error.
        self.assertNotIn('pg', out)
        self.assertNotIn('err', out)

    def test_rooms_on_two_floors_name_their_floors_in_home_assistants_order(self):
        states, device, entries = robot(segments=[{'id': '0_17', 'name': 'Kitchen', 'group': 'Home'}, {'id': '0_18', 'name': 'Living', 'group': 'Home'},
                                                  {'id': '1_20', 'name': 'Bedroom', 'group': 'Home'}])
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS)
        self.assertEqual([r[0] for r in out['rooms']], ['living_room', 'kitchen', 'bedroom'])
        self.assertEqual([r[3] for r in out['rooms']], [0, 0, 1])
        self.assertEqual(out['floors'], ['Ground floor', 'First floor'])

    def test_by_area_without_links_is_home_assistants_empty_state(self):
        states, device, entries = robot(mapping={})
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS)
        self.assertEqual(out.get('unmapped'), 1)
        self.assertNotIn('rooms', out)

    def test_a_robot_that_cannot_clean_by_area_offers_no_rooms(self):
        states, device, entries = robot(features=FULL & ~CLEAN_AREA)
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS)
        self.assertNotIn('rooms', out)
        self.assertNotIn('unmapped', out)

    def test_cleaning_brings_progress_and_floor_and_an_error_its_reason(self):
        states, device, entries = robot(state='cleaning')
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS)
        self.assertEqual((out['pg'], out['ar']), (45, 18.4))
        states['sensor.robot_vacuum_error']['state'] = 'main_brush_jammed'
        words = {'component.roborock.entity.sensor.vacuum_error.state.main_brush_jammed': 'Main brush jammed'}
        out = vacuum_card.payload(ROBOT, states, device, entries, AREAS, FLOORS, words=words)
        self.assertEqual(out['err'], 'Main brush jammed')

    def test_a_bare_robot_sends_nothing(self):
        states = {ROBOT: {'state': 'docked', 'attributes': {'supported_features': 16 | 8192}}}
        self.assertIsNone(vacuum_card.payload(ROBOT, states, [entry(ROBOT)], {ROBOT: entry(ROBOT)}))

    def test_an_area_id_that_is_no_slug_never_leaves(self):
        states, device, entries = robot(mapping={'kitchen': ['0_17'], "x'); evil": ['0_18']},
                                        segments=[{'id': '0_17', 'name': 'K', 'group': 'Home'}, {'id': '0_18', 'name': 'L', 'group': 'Home'}])
        areas = AREAS + [{'area_id': "x'); evil", 'name': 'Odd', 'floor_id': 'ground'}]
        out = vacuum_card.payload(ROBOT, states, device, entries, areas, FLOORS)
        self.assertEqual([r[0] for r in out['rooms']], ['kitchen'])

    def test_related_entities_follow_the_card(self):
        states, device, _ = robot()
        related = vacuum_card.related(ROBOT, device, states)
        for entity in ('image.robot_home', 'select.robot_selected_map', 'sensor.robot_vacuum_error', 'button.robot_kitchen_clean'):
            self.assertIn(entity, related)
        self.assertNotIn('button.robot_reset_filter', related)


@unittest.skipUnless(HAS_PIL, 'Pillow')
class Map(unittest.TestCase):
    def drawn(self):
        """A robot's map as an integration draws it: 4-pixel cells, two loud rooms, walls, a hatched carpet, a speck."""
        from PIL import Image, ImageDraw
        cells = Image.new('RGBA', (60, 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(cells)
        wall = (93, 109, 126, 255)
        d.rectangle((0, 0, 30, 29), fill=(217, 136, 128, 255), outline=wall)
        d.rectangle((30, 0, 59, 29), fill=(133, 193, 233, 255), outline=wall)
        for x in range(36, 50):
            for y in range(8, 20):
                if (x + y) % 2:
                    cells.putpixel((x, y), (169, 247, 169, 255))
        cells.putpixel((10, 10), (0, 0, 0, 255))
        image = cells.resize((240, 120), Image.NEAREST)
        out = io.BytesIO()
        image.save(out, 'PNG')
        return out.getvalue()

    def test_the_map_is_read_as_a_drawing(self):
        import vacuum_map
        drawing = vacuum_map.read(self.drawn())
        self.assertEqual(drawing.g, 4)
        self.assertTrue(drawing.flat)
        self.assertEqual(len(drawing.rooms), 2)
        self.assertEqual(drawing.walls, (93, 109, 126, 255))

    def test_rendered_in_both_looks_at_exactly_the_box(self):
        import vacuum_map
        from PIL import Image
        drawing = vacuum_map.read(self.drawn())
        for dark in (False, True):
            body = vacuum_map.render(drawing, (300, 120), 0x112233 if dark else 0xFFFFFF, dark)
            with Image.open(io.BytesIO(body)) as image:
                self.assertEqual(image.size, (300, 120))
                # The empty sides are the card's colour; the hatch and the speck are gone into the room.
                self.assertEqual(image.getpixel((2, 60)), (0x11, 0x22, 0x33) if dark else (255, 255, 255))
                palette = vacuum_map.DARK if dark else vacuum_map.LIGHT
                colours = {c for _, c in image.getcolors(1 << 16)}
                self.assertNotIn((169, 247, 169), colours)
                self.assertIn(palette['rooms'][0], colours)


if __name__ == '__main__':
    unittest.main()
