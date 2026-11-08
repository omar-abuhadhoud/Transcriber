"""Queue cleanup regression tests; run with python -m unittest test_queue_cleanup."""

import os
from pathlib import Path
import queue
import shutil
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ctk_ui import theme
from ctk_ui.queue_page import QueuePage
from transcriber.chunk_log import ChunkLog
from transcriber.settings import load_settings, save_settings


class FakeItem(SimpleNamespace):
    @property
    def is_cancelled(self):
        return self.cancel_token.cancelled


class QueueCleanupTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).resolve().parent / ("queue_test_" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(self.remove_test_folder)
        # Exercise the real queue methods without opening a Tk window or loading CUDA.
        self.callbacks = []
        self.page = SimpleNamespace(
            items=[], running_item=None, job_lock=threading.RLock(),
            engine_lock=threading.Lock(), cleanup_in_progress=False, _clear_rows={},
            job_queue=queue.Queue(), total_duration=0,
            log_error=Mock(), update_total_progress=Mock(),
            update_total_duration_label=Mock(), after=lambda delay, fn: self.callbacks.append(fn),
            clear_completed_var=Mock(), clear_queued_var=Mock(), btn_clear=Mock(),
            chk_clear_completed=Mock(), chk_clear_queued=Mock(),
        )
        self.page.clear_completed_var.get.return_value = False
        self.page.clear_queued_var.get.return_value = False
        for name in ("_can_clear", "_clear_items", "clear_selected", "update_clear_button_state",
                     "delete_generated_files", "delete_item", "delete_recovery_file",
                     "purge_cancelled_jobs", "_clean_in_background", "_poll_cleanup"):
            setattr(self.page, name, getattr(QueuePage, name).__get__(self.page))
        self.page.update_engine_menu_state = self.page.update_clear_button_state
        self.ask = patch("ctk_ui.queue_page.messagebox.askyesno", return_value=True).start()
        self.info = patch("ctk_ui.queue_page.messagebox.showinfo").start()
        self.warning = patch("ctk_ui.queue_page.messagebox.showwarning").start()
        self.release = patch("ctk_ui.queue_page.transcribe_module.release_all_memory").start()
        self.addCleanup(patch.stopall)

    def remove_test_folder(self):
        assert self.folder.resolve().parent == Path(__file__).resolve().parent
        assert self.folder.name.startswith("queue_test_")
        shutil.rmtree(self.folder)

    def item(self, name, state, started=False):
        item = FakeItem(
            state=state, has_started=started, generated_files=set(),
            clearing=False, run_id=0, cancel_token=SimpleNamespace(cancelled=False),
            recovery_file=str(self.folder / (name + ".txt")),
            durationInSeconds=10, pack_forget=Mock(), destroy=Mock(),
        )
        item.cancel_now = lambda: setattr(item.cancel_token, "cancelled", True)
        item.set_clearing = lambda value: setattr(item, "clearing", value)
        self.page.items.append(item)
        self.page.total_duration += 10
        return item

    def clear_and_wait(self):
        self.page.clear_selected()
        if self.page.cleanup_in_progress:
            self.page.cleanup_thread.join(timeout=5)
            self.assertFalse(self.page.cleanup_thread.is_alive())
            self.callbacks.pop(0)()

    def test_completed_deletes_owned_files_and_releases_memory(self):
        done = self.item("done", "done", True)
        preview = self.folder / "preview.rtf"
        log = self.folder / "run.log"
        done.generated_files.update((str(preview), str(log)))
        source = self.folder / "source.mp3"
        export = self.folder / "saved.txt"
        for path in (Path(done.recovery_file), preview, log, source, export):
            path.write_text("content", encoding="utf-8")
        self.page.clear_completed_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [])
        self.assertFalse(Path(done.recovery_file).exists())
        self.assertFalse(preview.exists())
        self.assertFalse(log.exists())
        self.assertTrue(source.exists())
        self.assertTrue(export.exists())
        done.destroy.assert_called_once()
        self.release.assert_called_once()

    def test_queued_removes_only_never_started_items(self):
        idle = self.item("idle", "idle")
        waiting = self.item("waiting", "waiting")
        processing = self.item("processing", "processing", True)
        failed = self.item("failed", "error", True)
        cancelled = self.item("cancelled", "cancelled", True)
        done = self.item("done", "done", True)
        # The worker has claimed this row but its Tk status callback has not run.
        claimed = self.item("claimed", "waiting", True)
        self.page.running_item = claimed
        self.page.job_queue.put(waiting)
        self.page.clear_queued_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [processing, failed, cancelled, done, claimed])
        self.assertTrue(idle.is_cancelled)
        self.assertTrue(waiting.is_cancelled)
        self.assertTrue(self.page.job_queue.empty())
        self.assertEqual(self.page.job_queue.unfinished_tasks, 0)
        self.release.assert_not_called()

    def test_declining_confirmation_keeps_completed_files(self):
        done = self.item("done", "done", True)
        Path(done.recovery_file).write_text("transcript", encoding="utf-8")
        self.ask.return_value = False
        self.page.clear_completed_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [done])
        self.assertTrue(Path(done.recovery_file).exists())
        self.release.assert_not_called()

    def test_job_starting_during_confirmation_is_protected(self):
        waiting = self.item("waiting", "waiting")

        def approve(*args, **kwargs):
            waiting.has_started = True
            self.page.running_item = waiting
            return True

        self.ask.side_effect = approve
        self.page.clear_queued_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [waiting])
        self.assertFalse(waiting.is_cancelled)
        waiting.destroy.assert_not_called()

    def test_clear_completed_does_not_unload_model_used_by_running_job(self):
        self.item("done", "done", True)
        active = self.item("active", "processing", True)
        self.page.running_item = active
        self.page.clear_completed_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [active])
        self.assertFalse(active.is_cancelled)
        self.release.assert_not_called()

    def test_failed_cleanup_keeps_row_and_reports_failure(self):
        done = self.item("done", "done", True)
        self.page.clear_completed_var.get.return_value = True
        with patch("ctk_ui.queue_page.os.remove", side_effect=PermissionError("locked")):
            self.clear_and_wait()
        self.assertEqual(self.page.items, [done])
        done.destroy.assert_not_called()
        self.warning.assert_called_once()

    def test_button_enabled_only_when_selected_types_have_eligible_items(self):
        done = self.item("done", "done", True)
        queued = self.item("queued", "waiting")
        self.item("processing", "processing", True)
        for completed_checked in (False, True):
            for queued_checked in (False, True):
                for done_present in (False, True):
                    for queued_present in (False, True):
                        with self.subTest(completed=completed_checked, queued=queued_checked,
                                          done_present=done_present, queued_present=queued_present):
                            self.page.clear_completed_var.get.return_value = completed_checked
                            self.page.clear_queued_var.get.return_value = queued_checked
                            self.page.items = ([done] if done_present else []) + (
                                [queued] if queued_present else [])
                            self.page.update_clear_button_state()
                            enabled = (completed_checked and done_present) or (
                                queued_checked and queued_present)
                            self.assertEqual(
                                self.page.btn_clear.configure.call_args.kwargs["state"],
                                "normal" if enabled else "disabled")

    def test_both_checked_clears_both_types_with_one_confirmation(self):
        done = self.item("done", "done", True)
        queued = self.item("queued", "waiting")
        active = self.item("active", "processing", True)
        self.page.running_item = active
        self.page.clear_completed_var.get.return_value = True
        self.page.clear_queued_var.get.return_value = True
        self.clear_and_wait()
        self.assertEqual(self.page.items, [active])
        self.assertTrue(done.is_cancelled)
        self.assertTrue(queued.is_cancelled)
        self.ask.assert_called_once()
        self.assertIn("Completed: 1", self.ask.call_args.args[1])
        self.assertIn("Queued: 1", self.ask.call_args.args[1])

    def test_no_selection_or_no_matching_items_does_not_confirm(self):
        self.item("done", "done", True)
        self.clear_and_wait()
        self.ask.assert_not_called()
        self.page.clear_queued_var.get.return_value = True
        self.clear_and_wait()
        self.ask.assert_not_called()
        self.assertEqual(len(self.page.items), 1)

    def test_fifty_rows_update_together_after_background_cleanup(self):
        main_thread = threading.get_ident()
        started = threading.Event()
        proceed = threading.Event()
        self.addCleanup(proceed.set)
        rows = [self.item(str(number), "done", True) for number in range(50)]
        for item in rows:
            Path(item.recovery_file).write_text("transcript", encoding="utf-8")
            item.destroy.side_effect = lambda: self.assertEqual(threading.get_ident(), main_thread)
        original_cleanup = self.page.delete_generated_files
        cleanup_threads = []

        def slow_cleanup(paths):
            cleanup_threads.append(threading.get_ident())
            started.set()
            if not proceed.wait(timeout=5):
                raise RuntimeError("Test cleanup timed out")
            return original_cleanup(paths)

        def schedule(delay, fn):
            self.assertEqual(threading.get_ident(), main_thread)
            self.callbacks.append(fn)

        self.page.after = schedule
        self.page.delete_generated_files = slow_cleanup
        self.page.clear_completed_var.get.return_value = True
        self.page.clear_selected()
        self.assertTrue(started.wait(timeout=2))
        self.assertTrue(self.page.cleanup_in_progress)
        self.assertEqual(len(self.page.items), 50)
        self.page.btn_clear.configure.assert_called_with(
            text="Clearing...", state="disabled", fg_color=theme.TAB_HOVER)
        for item in rows:
            item.destroy.assert_not_called()
        # A second click cannot start another cleanup while the first is blocked.
        self.page.clear_selected()
        self.ask.assert_called_once()
        proceed.set()
        self.page.cleanup_thread.join(timeout=5)
        self.assertFalse(self.page.cleanup_thread.is_alive())
        self.assertTrue(all(identity != main_thread for identity in cleanup_threads))
        self.assertEqual(len(self.page.items), 50)
        self.assertTrue(all(not Path(item.recovery_file).exists() for item in rows))
        self.callbacks.pop(0)()
        self.assertEqual(self.page.items, [])
        self.assertEqual(self.page.total_duration, 0)
        self.page.update_total_duration_label.assert_called_once()
        self.page.update_total_progress.assert_called_once()
        self.assertFalse(self.page.cleanup_in_progress)

    def test_cleanup_does_not_wait_for_busy_model(self):
        self.item("done", "done", True)
        self.page.clear_completed_var.get.return_value = True
        with self.page.engine_lock:
            self.clear_and_wait()
        self.assertEqual(self.page.items, [])
        self.release.assert_not_called()

    def test_partial_failure_keeps_only_failed_rows(self):
        locked = self.item("locked", "done", True)
        cleared = self.item("cleared", "done", True)
        self.page.clear_completed_var.get.return_value = True
        original_remove = os.remove

        def remove(path):
            if path == locked.recovery_file:
                raise PermissionError("locked")
            return original_remove(path)

        with patch("ctk_ui.queue_page.os.remove", side_effect=remove):
            self.clear_and_wait()
        self.assertEqual(self.page.items, [locked])
        self.assertFalse(locked.clearing)
        locked.destroy.assert_not_called()
        cleared.destroy.assert_called_once()
        self.warning.assert_called_once()

    def test_logs_have_unique_owned_paths(self):
        paths = []
        with patch("transcriber.chunk_log.get_install_root", return_value=str(self.folder)):
            for _ in range(2):
                log = ChunkLog("same.mp3", 16000, 16000, [], 4,
                               artifact_callback=paths.append)
                log.close("Finished")
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(os.path.isfile(path) for path in paths))

    def test_checkbox_preferences_survive_saving_and_loading(self):
        with patch("transcriber.settings.get_user_data_dir", return_value=str(self.folder)):
            self.assertEqual(load_settings(), {})
            for completed in (False, True):
                for queued in (False, True):
                    preferences = {"clear_completed": completed, "clear_queued": queued,
                                   "other_preference": "preserved"}
                    save_settings(preferences)
                    self.assertEqual(load_settings(), preferences)

    def test_invalid_settings_fall_back_to_defaults(self):
        with patch("transcriber.settings.get_user_data_dir", return_value=str(self.folder)):
            for contents in ("invalid json", "[]", "null"):
                (self.folder / "settings.json").write_text(contents, encoding="utf-8")
                log_error = Mock()
                self.assertEqual(load_settings(log_error), {})
                log_error.assert_called_once()

    def test_failed_save_preserves_previous_settings(self):
        with patch("transcriber.settings.get_user_data_dir", return_value=str(self.folder)):
            save_settings({"clear_completed": True})
            with patch("transcriber.settings.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    save_settings({"clear_completed": False})
            self.assertEqual(load_settings(), {"clear_completed": True})
            self.assertEqual(list(self.folder.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
