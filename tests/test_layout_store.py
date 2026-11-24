"""Crash, conflict and mixed-migration tests against real files and locks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
from core import Grid
from layout_store import CommitUncertain, Conflict, LayoutStore
from page_layout import FORMAT, GridAdaptationRequired, LayoutError, delete_page, fingerprint
from layout_migrations import migrate_legacy


class LayoutStoreTests(unittest.TestCase):
    def test_explicit_fresh_start_preserves_backup_and_other_screens(self):
        original = json.dumps({'version': 1, 'screens': {'screen.a': [], 'screen.b': {'title': 'Other', 'tiles': []}}})
        self.path.write_text(original)
        store = self.store()
        pending, other = store.get('screen.a'), store.get('screen.b')
        self.assertEqual(pending['format'], 'legacy-v1')
        with self.assertRaises(Conflict): store.start_fresh('screen.a', 'stale', 'Home')
        fresh = store.start_fresh('screen.a', fingerprint(pending['payload']), 'Home')
        self.assertEqual(fresh['format'], 'pages-v2')
        self.assertEqual(len(fresh['layout']['pages']), 1)
        self.assertEqual(fresh['layout']['pages'][0]['tiles'], [])
        self.assertEqual(store.get('screen.b'), other)
        self.assertEqual(self.path.with_name('screens.v1.backup.json').read_text(), original)
        with self.assertRaises(Conflict): store.start_fresh('screen.a', fingerprint(pending['payload']), 'Home')

    def test_cached_snapshot_detects_other_writers_without_copying_unchanged_data(self):
        store = self.store()
        first = store.save('screen.a', self.document(), None)
        stamp, snapshot = store.snapshot_since(object())
        self.assertEqual(snapshot['screen.a'], first)
        snapshot['screen.a']['layout']['title'] = 'Not saved'
        with patch.object(store, '_locked', side_effect=AssertionError('unchanged read must not lock')):
            self.assertEqual(store.snapshot_since(stamp), (stamp, None))
        other = self.store()
        changed = deepcopy(first['layout']); changed['title'] = 'Changed elsewhere'
        other.save('screen.a', changed, first['revision'])
        new_stamp, snapshot = store.snapshot_since(stamp)
        self.assertNotEqual(new_stamp, stamp)
        self.assertEqual(snapshot['screen.a']['layout']['title'], 'Changed elsewhere')

    def test_dismissing_recovery_note_keeps_backup_and_layout_revision(self):
        original = json.dumps({'version': 1, 'screens': {'screen.a': {'title': 'Screen', 'tiles': [
            {'entity': 'light.a', 'slot': 0}, {'entity': 'light.b', 'slot': 80}]}}})
        self.path.write_text(original)
        store = self.store()
        before = store.get('screen.a')
        self.assertEqual(len(before['migration']['droppedTiles']), 1)
        with self.assertRaises(Conflict): store.dismiss_migration('screen.a', 'stale')
        after = store.dismiss_migration('screen.a', before['revision'])
        self.assertNotIn('migration', after)
        self.assertEqual(after['revision'], before['revision'])
        self.assertEqual(after['layout'], before['layout'])
        self.assertEqual(self.store().get('screen.a'), after)
        self.assertEqual(self.path.with_name('screens.v1.backup.json').read_text(), original)

    def test_grid_change_requires_explicit_commit_and_changes_revision_even_for_empty_pages(self):
        store = self.store()
        first = store.save('screen.a', self.document(), None)
        self.grids['screen.a'] = Grid(1, 4)
        before = self.path.read_bytes()
        with self.assertRaises(GridAdaptationRequired):
            store.save('screen.a', first['layout'], first['revision'])
        self.assertEqual(self.path.read_bytes(), before)
        updated = store.save('screen.a', first['layout'], first['revision'], adapt_grid=True)
        self.assertEqual(updated['sourceGrid'], {'columns': 1, 'rows': 4})
        self.assertNotEqual(updated['revision'], first['revision'])
        self.assertEqual(updated['layout'], first['layout'])
        with self.assertRaises(Conflict):
            store.save('screen.a', first['layout'], first['revision'], adapt_grid=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "screens.json"
        self.grids = {"screen.a": Grid(), "screen.b": Grid(3, 3)}

    def store(self):
        return LayoutStore(self.path, self.grids.get)

    def document(self, pages=1):
        return migrate_legacy({"title": "Screen", "pages": pages, "tiles": []}, Grid())["layout"]

    def legacy(self):
        # Whitespace and an unknown field in the pending record must survive
        # writes for another screen byte-for-byte, not just semantically.
        pending = '{ "title" : "Offline", "tiles":[], "future": { "a": 1 } }'
        text = '{"version":1,"screens":{"screen.a":{"title":"Screen","tiles":[]},"screen.unknown":' + pending + '}}'
        self.path.write_text(text)
        return text.encode(), pending

    def test_migration_is_durable_once_and_keeps_pending_payload(self):
        original, pending = self.legacy()
        store = self.store()
        first = store.records()
        self.assertEqual(self.path.with_name("screens.v1.backup.json").read_bytes(), original)
        self.assertEqual(first["screen.a"]["format"], FORMAT)
        self.assertEqual(first["screen.unknown"]["payload"], pending)
        self.assertEqual(self.store().records(), first)
        changed = deepcopy(first["screen.a"]["layout"])
        changed["title"] = "Changed"
        store.save("screen.a", changed, first["screen.a"]["revision"])
        store.save_settings("screen.a", {"brightness": 75})
        store.rename("screen.a", "screen.renamed")
        self.assertEqual(self.store().get("screen.unknown")["payload"], pending)
        self.assertEqual(self.path.with_name("screens.v1.backup.json").read_bytes(), original)

    def test_offline_known_grid_converts_without_device_contact(self):
        self.path.write_text(json.dumps({"version": 1, "screens": {
            "screen.b": {"title": "Offline", "tiles": [{"entity": f"sensor.a{i}"} for i in range(10)]}}}))
        record = self.store().get("screen.b")
        self.assertEqual(record["sourceGrid"], {"columns": 3, "rows": 3})
        self.assertEqual([len(p["tiles"]) for p in record["layout"]["pages"]], [9, 1])

    def test_pending_conversion_resumes_and_ids_do_not_regenerate(self):
        self.path.write_text('{"version":1,"screens":{"screen.later":{"title":"Later","tiles":[]}}}')
        store = self.store()
        self.assertEqual(store.get("screen.later")["format"], "legacy-v1")
        self.grids["screen.later"] = Grid()
        converted = store.retry_migrations()["screen.later"]
        self.assertEqual(converted["format"], FORMAT)
        self.assertEqual(store.retry_migrations()["screen.later"], converted)
        self.assertEqual(self.store().get("screen.later"), converted)

    def test_normal_reads_saves_and_restarts_never_repeat_a_completed_migration(self):
        self.legacy()
        store = self.store()
        first = store.get("screen.a")
        with patch("layout_store.migrate_legacy", side_effect=AssertionError("repeated migration")), \
                patch.object(store, "_validate_records", wraps=store._validate_records) as validate:
            for _ in range(30):
                self.assertEqual(store.get("screen.a"), first)
            validate.assert_not_called()
            saved = store.save("screen.a", {**first["layout"], "title": "Edited"}, first["revision"])
            self.assertEqual(self.store().get("screen.a"), saved)
            # An unresolved record stays pending; the converted screen is skipped.
            self.assertEqual(store.retry_migrations()["screen.a"], saved)

    def test_settings_changed_while_pending_survive_later_conversion(self):
        payload = '{ "title": "Later", "tiles": [], "settings": {"brightness":80} }'
        self.path.write_text('{"version":1,"screens":{"screen.later":' + payload + '}}')
        store = self.store()
        store.save_settings("screen.later", {"brightness": 65})
        self.assertEqual(store.get("screen.later")["payload"], payload)
        self.grids["screen.later"] = Grid()
        saved = store.retry_migrations()["screen.later"]
        self.assertEqual(saved["settings"]["brightness"], 65)
        self.assertEqual(self.store().get("screen.later"), saved)

    def test_unknown_versions_invalid_json_and_duplicate_keys_preserve_original(self):
        for source in ('{"version":99,"screens":{}}', '{broken',
                       '{"version":1,"version":2,"screens":{}}',
                       '{"version":2,"screens":{"screen.a":{"format":"future-v3"}}}'):
            with self.subTest(source=source):
                self.path.write_text(source)
                with self.assertRaises(LayoutError): self.store()
                self.assertEqual(self.path.read_text(), source)

    def test_backup_failure_never_installs_v2(self):
        original, _ = self.legacy()
        with patch("layout_store.os.link", side_effect=OSError("backup failure")):
            with self.assertRaises(OSError): self.store()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name("screens.v1.backup.json").exists())
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_migration_replace_failure_preserves_original_and_valid_backup(self):
        original, _ = self.legacy()
        with patch("layout_store.os.replace", side_effect=OSError("replace failure")):
            with self.assertRaises(OSError): self.store()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.path.with_name("screens.v1.backup.json").read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.assertEqual(self.store().get("screen.a")["format"], FORMAT)

    def test_first_backup_survives_deliberate_v1_restore_and_new_edits(self):
        original, _ = self.legacy()
        self.store()
        restored = '{"version":1,"screens":{"screen.a":{"title":"New old edit","tiles":[]}}}'
        self.path.write_text(restored)
        self.assertEqual(self.store().get("screen.a")["layout"]["title"], "New old edit")
        self.assertEqual(self.path.with_name("screens.v1.backup.json").read_bytes(), original)
        other = [p for p in self.path.parent.glob("screens.v1.*.backup.json")]
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0].read_text(), restored)

    def test_failed_save_preserves_previous_file_and_draft(self):
        store = self.store()
        first = store.save("screen.a", self.document(), None)
        original = self.path.read_bytes()
        draft = deepcopy(first["layout"])
        draft["title"] = "Unsaved"
        with patch("layout_store.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError): store.save("screen.a", draft, first["revision"])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(draft["title"], "Unsaved")
        self.assertEqual(store.get("screen.a"), first)

    def test_directory_sync_failure_is_an_uncertain_commit_not_a_rollback(self):
        store = self.store()
        first = store.save("screen.a", self.document(), None)
        draft = {**first["layout"], "title": "Possibly saved"}
        with patch.object(store, "_directory_sync", side_effect=OSError("directory failure")):
            with self.assertRaises(CommitUncertain): store.save("screen.a", draft, first["revision"])
        recovered = self.store().get("screen.a")
        self.assertEqual(recovered["layout"], draft)
        self.assertNotEqual(recovered["revision"], first["revision"])

    def test_two_store_instances_cannot_lose_other_screens(self):
        first, second = self.store(), self.store()
        a, b = self.document(), self.document()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(first.save, "screen.a", a, None), pool.submit(second.save, "screen.b", b, None)]
            for future in futures: future.result(timeout=5)
        saved = self.store().records()
        self.assertEqual(saved["screen.a"]["layout"], a)
        self.assertEqual(saved["screen.b"]["layout"], b)

    def test_two_browsers_get_a_conflict_instead_of_last_writer_wins(self):
        one, two = self.store(), self.store()
        initial = one.save("screen.a", self.document(), None)
        winner = one.save("screen.a", {**initial["layout"], "title": "First"}, initial["revision"])
        with self.assertRaises(Conflict):
            two.save("screen.a", {**initial["layout"], "title": "Second"}, initial["revision"])
        self.assertEqual(two.get("screen.a"), winner)

    def test_undoing_content_does_not_reuse_an_old_save_revision(self):
        store = self.store()
        first = store.save("screen.a", self.document(), None)
        second = store.save("screen.a", {**first["layout"], "title": "Changed"}, first["revision"])
        restored = store.save("screen.a", first["layout"], second["revision"])
        self.assertNotEqual(restored["revision"], first["revision"])
        self.assertEqual(store.save("screen.a", restored["layout"], restored["revision"]), restored)

    def test_workspace_saves_do_not_change_layout_revision_and_reject_unknown_pages(self):
        store = self.store()
        first = store.save("screen.a", self.document(2), None)
        ids = [page["id"] for page in first["layout"]["pages"]]
        workspace = store.save_workspace("screen.a", first["revision"], {"revision": "", "positions": {ids[0]: {"x": 2, "y": 3}}})
        self.assertEqual(store.get("screen.a")["revision"], first["revision"])
        with self.assertRaises(LayoutError):
            store.save_workspace("screen.a", first["revision"], {"revision": workspace["revision"], "positions": {"draft-only": {"x": 0, "y": 0}}})
        with self.assertRaises(Conflict):
            store.save_workspace("screen.a", first["revision"], {"revision": "", "positions": {}})

    def test_page_deletion_and_workspace_cleanup_are_one_commit(self):
        store = self.store()
        first = store.save("screen.a", self.document(2), None)
        removed = first["layout"]["pages"][1]["id"]
        workspace = store.save_workspace("screen.a", first["revision"], {"revision": "", "positions": {removed: {"x": 1, "y": 2}}})
        draft = delete_page(first["layout"], removed, Grid())
        saved = store.save("screen.a", draft, first["revision"])
        self.assertEqual(saved["workspace"]["positions"], {})
        with self.assertRaises(Conflict): store.save_workspace("screen.a", first["revision"], workspace)
        self.assertEqual(self.store().get("screen.a"), saved)

    def test_changed_grid_requires_explicit_adaptation(self):
        store = self.store()
        first = store.save("screen.a", self.document(), None)
        self.grids["screen.a"] = Grid(3, 3)
        with self.assertRaises(GridAdaptationRequired): store.save("screen.a", first["layout"], first["revision"])
        self.assertEqual(store.get("screen.a")["sourceGrid"], {"columns": 2, "rows": 3})


if __name__ == "__main__":
    unittest.main()
