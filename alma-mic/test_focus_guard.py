"""Deterministic focus-guard tests.

Every test replaces the narrow Win32 boundary.  No native SendInput call is made,
no window is focused, and auto-Enter is never enabled.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import typer
import voice_commands


HERE = Path(__file__).resolve().parent
OPENAI_APP = (
    r"C:\Program Files\WindowsApps\OpenAI.CodexBeta_26.715.3651.0_x64__2p2nqsd0c76g0"
    r"\app\ChatGPT (Beta).exe"
)
CLAUDE_APP = (
    r"C:\Program Files\WindowsApps\Claude_1.20186.9.0_x64__pzs8sxrjxfjjc"
    r"\app\claude.exe"
)


class FocusGuardTests(unittest.TestCase):
    def _win32(self, hwnds, titles, identities, accepted=0):
        stack = ExitStack()
        foreground = stack.enter_context(
            mock.patch.object(typer._win32, "foreground_hwnd", side_effect=list(hwnds))
        )
        window_title = stack.enter_context(
            mock.patch.object(typer._win32, "window_title", side_effect=list(titles))
        )
        process_identity = stack.enter_context(
            mock.patch.object(
                typer._win32, "process_identity", side_effect=list(identities)
            )
        )
        send_input = stack.enter_context(
            mock.patch.object(typer._win32, "send_input", return_value=accepted)
        )
        return stack, foreground, window_title, process_identity, send_input

    def test_win32_process_identity_reads_real_packaged_path(self):
        def get_owner(_hwnd, pid_pointer):
            pid_pointer._obj.value = 19024
            return 4401

        def query_image(_handle, _flags, buffer, size_pointer):
            buffer.value = OPENAI_APP
            size_pointer._obj.value = len(OPENAI_APP)
            return True

        with (
            mock.patch.object(typer.user32, "GetWindowThreadProcessId", side_effect=get_owner),
            mock.patch.object(typer.kernel32, "OpenProcess", return_value=8801),
            mock.patch.object(
                typer.kernel32, "QueryFullProcessImageNameW", side_effect=query_image
            ),
            mock.patch.object(typer.kernel32, "CloseHandle", return_value=True) as close_handle,
        ):
            identity = typer._Win32Api().process_identity(4101)

        self.assertEqual((19024, OPENAI_APP), identity)
        close_handle.assert_called_once_with(8801)

    def test_win32_unreadable_process_fails_closed_and_closes_handle(self):
        def get_owner(_hwnd, pid_pointer):
            pid_pointer._obj.value = 19100
            return 4402

        with (
            mock.patch.object(typer.user32, "GetWindowThreadProcessId", side_effect=get_owner),
            mock.patch.object(typer.kernel32, "OpenProcess", return_value=8802),
            mock.patch.object(typer.kernel32, "QueryFullProcessImageNameW", return_value=False),
            mock.patch.object(typer.kernel32, "CloseHandle", return_value=True) as close_handle,
        ):
            identity = typer._Win32Api().process_identity(4102)

        self.assertEqual((0, ""), identity)
        close_handle.assert_called_once_with(8802)

    def test_allowed_chat_titles_send_only_after_same_hwnd_recheck(self):
        for title, image_path in (
            ("ChatGPT", OPENAI_APP),
            ("ChatGPT (Beta)", OPENAI_APP),
            ("Research notes | Claude", CLAUDE_APP),
            ("Report on all projects — Codex", OPENAI_APP),
        ):
            with self.subTest(title=title):
                stack, foreground, window_title, process_identity, send_input = self._win32(
                    hwnds=(4101, 4101),
                    titles=(title, title),
                    identities=((9901, image_path), (9901, image_path)),
                    accepted=4,
                )
                with stack:
                    accepted = typer.type_text("אב", enter=False)

                self.assertEqual(4, accepted)
                self.assertEqual(2, foreground.call_count)
                self.assertEqual([mock.call(4101), mock.call(4101)], window_title.call_args_list)
                self.assertEqual([mock.call(4101), mock.call(4101)], process_identity.call_args_list)
                send_input.assert_called_once()
                self.assertEqual(4, len(send_input.call_args.args[0]))

    def test_denied_titles_never_reach_sendinput(self):
        for title in (
            "Windows Terminal",
            "ChatGPT - Windows Terminal",
            "Address bar - ChatGPT",
            "PowerShell | Claude",
            "ChatGPT - Google Chrome",
            "Claude — Microsoft Edge",
            "Untitled - Notepad",
            "Completely arbitrary",
        ):
            with self.subTest(title=title):
                stack, _foreground, _window_title, _process_identity, send_input = self._win32(
                    hwnds=(5101,),
                    titles=(title,),
                    identities=((9911, OPENAI_APP),),
                )
                with stack, self.assertRaises(typer.FocusGuardError):
                    typer.type_text("must not type", enter=False)
                send_input.assert_not_called()

    def test_empty_or_unreadable_foreground_fails_closed(self):
        for hwnd, title in ((6101, ""), (0, "")):
            with self.subTest(hwnd=hwnd):
                stack, _foreground, _window_title, _process_identity, send_input = self._win32(
                    hwnds=(hwnd,),
                    titles=(title,),
                    identities=((9921, OPENAI_APP) if hwnd else (0, ""),),
                )
                with stack, self.assertRaises(typer.FocusGuardError):
                    typer.type_text("must not type", enter=False)
                send_input.assert_not_called()

    def test_approved_title_on_spoof_process_fails_closed(self):
        for title, image_path in (
            ("ChatGPT", r"C:\Windows\System32\notepad.exe"),
            ("Codex", r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
            ("Claude", r"C:\Users\<user>\.local\bin\claude.exe"),
            ("Claude", OPENAI_APP),
            ("ChatGPT", CLAUDE_APP),
        ):
            with self.subTest(title=title, image_path=image_path):
                stack, _foreground, _window_title, _process_identity, send_input = self._win32(
                    hwnds=(6201,),
                    titles=(title,),
                    identities=((9961, image_path),),
                )
                with stack, self.assertRaises(typer.FocusGuardError):
                    typer.type_text("must not type", enter=False)
                send_input.assert_not_called()

    def test_unreadable_process_identity_fails_closed(self):
        for identity in ((0, ""), (9971, "")):
            with self.subTest(identity=identity):
                stack, _foreground, _window_title, _process_identity, send_input = self._win32(
                    hwnds=(6301,), titles=("ChatGPT",), identities=(identity,)
                )
                with stack, self.assertRaises(typer.FocusGuardError):
                    typer.type_text("must not type", enter=False)
                send_input.assert_not_called()

    def test_focus_race_between_checks_fails_closed(self):
        stack, foreground, _window_title, _process_identity, send_input = self._win32(
            hwnds=(7101, 7102),
            titles=("ChatGPT", "Claude"),
            identities=((9931, OPENAI_APP), (9932, CLAUDE_APP)),
        )
        with stack, self.assertRaises(typer.FocusChangedError):
            typer.type_text("must not cross windows", enter=False)

        self.assertEqual(2, foreground.call_count)
        send_input.assert_not_called()

    def test_process_race_between_checks_fails_closed(self):
        stack, _foreground, _window_title, process_identity, send_input = self._win32(
            hwnds=(7151, 7151),
            titles=("ChatGPT (Beta)", "ChatGPT (Beta)"),
            identities=((9981, OPENAI_APP), (9982, OPENAI_APP)),
        )
        with stack, self.assertRaises(typer.FocusChangedError):
            typer.type_text("must not cross processes", enter=False)

        self.assertEqual(2, process_identity.call_count)
        send_input.assert_not_called()

    def test_allowed_title_change_between_checks_is_a_race(self):
        stack, _foreground, _window_title, _process_identity, send_input = self._win32(
            hwnds=(7181, 7181),
            titles=("ChatGPT", "Codex"),
            identities=((9991, OPENAI_APP), (9991, OPENAI_APP)),
        )
        with stack, self.assertRaises(typer.FocusChangedError):
            typer.type_text("must not cross titles", enter=False)
        send_input.assert_not_called()

    def test_same_hwnd_becoming_disallowed_before_send_fails_closed(self):
        stack, _foreground, _window_title, _process_identity, send_input = self._win32(
            hwnds=(7201, 7201),
            titles=("Codex", "Codex - Windows Terminal"),
            identities=((9941, OPENAI_APP), (9941, OPENAI_APP)),
        )
        with stack, self.assertRaises(typer.FocusGuardError):
            typer.type_text("must not type", enter=False)
        send_input.assert_not_called()

    def test_voice_command_path_uses_the_same_guard(self):
        cfg = SimpleNamespace(enable_voice_commands=True, voice_commands={})
        command = voice_commands.apply("slash help", cfg)
        self.assertEqual("/help", command)

        stack, _foreground, _window_title, _process_identity, send_input = self._win32(
            hwnds=(8101, 8101),
            titles=("Claude", "Claude"),
            identities=((9951, CLAUDE_APP), (9951, CLAUDE_APP)),
            accepted=12,
        )
        with stack:
            accepted = typer.type_text(command + " ", enter=False)

        self.assertEqual(12, accepted)
        send_input.assert_called_once()

    def test_pipeline_and_all_native_typing_are_centralized(self):
        pipeline_tree = ast.parse((HERE / "pipeline.py").read_text(encoding="utf-8"))
        pipeline_calls = [
            node
            for node in ast.walk(pipeline_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "type_text"
        ]
        self.assertEqual(1, len(pipeline_calls), "normal/command output must use typer.type_text")

        typer_tree = ast.parse((HERE / "typer.py").read_text(encoding="utf-8"))
        guarded_bursts = [
            node
            for node in ast.walk(typer_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_guarded_send"
        ]
        self.assertEqual(
            2,
            len(guarded_bursts),
            "both the text burst and the delayed Enter burst must use the guard",
        )

        native_send_sites = []
        for source_path in (HERE / "typer.py", HERE / "pipeline.py", HERE / "voice_commands.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "SendInput"
                ):
                    native_send_sites.append((source_path.name, node.lineno))

        self.assertEqual(1, len(native_send_sites))
        self.assertEqual("typer.py", native_send_sites[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
