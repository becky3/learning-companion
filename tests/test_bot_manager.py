"""Bot管理コマンドのテスト (AC10-AC18, Issue #580).

仕様: docs/specs/bot-process-guard.md
"""

from __future__ import annotations

import subprocess
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.bot_manager import (
    _get_child_pids_windows,
    _get_child_pids_unix,
    _kill_process_tree,
    _start_bot,
    _stop_bot,
    cmd_start,
    cmd_status,
    cmd_stop,
    cmd_restart,
    handle_command,
)


# ---------------------------------------------------------------------------
# _get_child_pids テスト
# ---------------------------------------------------------------------------


class TestGetChildPids:
    """子プロセスPID取得のテスト."""

    def test_get_child_pids_windows_returns_pids(self) -> None:
        """Windows: wmic出力から子プロセスPIDを取得する."""
        mock_result = MagicMock()
        mock_result.stdout = "ProcessId\n111\n222\n\n"
        with patch("src.bot_manager.subprocess.run", return_value=mock_result):
            pids = _get_child_pids_windows(9999)
        assert pids == [111, 222]

    def test_get_child_pids_windows_empty(self) -> None:
        """Windows: 子プロセスがない場合は空リストを返す."""
        mock_result = MagicMock()
        mock_result.stdout = "ProcessId\n\n"
        with patch("src.bot_manager.subprocess.run", return_value=mock_result):
            pids = _get_child_pids_windows(9999)
        assert pids == []

    def test_get_child_pids_windows_wmic_not_found(self) -> None:
        """Windows: wmicが見つからない場合は空リストを返す."""
        with patch("src.bot_manager.subprocess.run", side_effect=FileNotFoundError()):
            pids = _get_child_pids_windows(9999)
        assert pids == []

    def test_get_child_pids_unix_returns_pids(self) -> None:
        """Unix: pgrep出力から子プロセスPIDを取得する."""
        mock_result = MagicMock()
        mock_result.stdout = "111\n222\n"
        with patch("src.bot_manager.subprocess.run", return_value=mock_result):
            pids = _get_child_pids_unix(9999)
        assert pids == [111, 222]

    def test_get_child_pids_unix_pgrep_not_found(self) -> None:
        """Unix: pgrepが見つからない場合は空リストを返す."""
        with patch("src.bot_manager.subprocess.run", side_effect=FileNotFoundError()):
            pids = _get_child_pids_unix(9999)
        assert pids == []

    def test_get_child_pids_windows_wmic_timeout(self) -> None:
        """Windows: wmicがタイムアウトした場合は空リストを返す."""
        with patch(
            "src.bot_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="wmic", timeout=10),
        ):
            pids = _get_child_pids_windows(9999)
        assert pids == []

    def test_get_child_pids_unix_pgrep_timeout(self) -> None:
        """Unix: pgrepがタイムアウトした場合は空リストを返す."""
        with patch(
            "src.bot_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pgrep", timeout=5),
        ):
            pids = _get_child_pids_unix(9999)
        assert pids == []


# ---------------------------------------------------------------------------
# _kill_process_tree テスト
# ---------------------------------------------------------------------------


class TestKillProcessTree:
    """AC17: プロセスツリー停止のテスト."""

    def test_ac17_windows_kills_children_then_parent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC17: Windows で子プロセスが先に停止され、その後に本体が停止される."""
        monkeypatch.setattr("sys.platform", "win32")
        kill_order: list[int] = []

        wmic_result = MagicMock()
        wmic_result.stdout = "ProcessId\n111\n222\n\n"
        taskkill_result = MagicMock()

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "wmic":
                return wmic_result
            if cmd[0] == "taskkill":
                pid = int(cmd[2])
                kill_order.append(pid)
                return taskkill_result
            return MagicMock()

        with patch("src.bot_manager.subprocess.run", side_effect=fake_run):
            _kill_process_tree(9999)

        # 子プロセス(111, 222)が先、本体(9999)が最後
        assert kill_order == [111, 222, 9999]

    def test_ac17_unix_kills_children_then_parent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC17: Unix で子プロセスが先に停止され、その後に本体が停止される."""
        monkeypatch.setattr("sys.platform", "linux")
        kill_order: list[int] = []

        pgrep_result = MagicMock()
        pgrep_result.stdout = "111\n222\n"

        def fake_kill(pid: int, sig: int) -> None:
            kill_order.append(pid)

        with (
            patch("src.bot_manager.subprocess.run", return_value=pgrep_result),
            patch("src.bot_manager.os.kill", side_effect=fake_kill),
        ):
            _kill_process_tree(9999)

        assert kill_order == [111, 222, 9999]


# ---------------------------------------------------------------------------
# _stop_bot テスト
# ---------------------------------------------------------------------------


class TestStopBot:
    """停止処理のテスト."""

    def test_ac12_stop_running_bot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC12: 起動中のBotを停止し、PIDファイルを削除する."""
        pid_file = tmp_path / "bot.pid"
        pid_file.write_text("12345", encoding="utf-8")
        monkeypatch.setattr("src.process_guard.PID_FILE", pid_file)
        monkeypatch.setattr("src.bot_manager.remove_pid_file", lambda: pid_file.unlink(missing_ok=True))

        with (
            patch("src.bot_manager.is_process_alive", return_value=True),
            patch("src.bot_manager._kill_process_tree") as mock_kill,
            patch("src.bot_manager.read_pid_file", return_value=12345),
        ):
            result = _stop_bot()

        assert result is True
        mock_kill.assert_called_once_with(12345)

    def test_ac13_stop_not_running(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC13: Botが起動していない場合はFalseを返す."""
        with patch("src.bot_manager.read_pid_file", return_value=None):
            result = _stop_bot()

        assert result is False


# ---------------------------------------------------------------------------
# cmd_start テスト
# ---------------------------------------------------------------------------


class TestCmdStart:
    """--start コマンドのテスト."""

    def test_ac10_start_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC10: 正常起動時に Running (PID=xxxx) を表示する."""
        with (
            patch("src.bot_manager.read_pid_file", return_value=None),
            patch("src.bot_manager._start_bot", return_value=12345),
        ):
            cmd_start()

        captured = capsys.readouterr()
        assert "Running (PID=12345)" in captured.out

    def test_ac11_start_already_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC11: 既にBotが起動中の場合、Already running を表示して exit(1)."""
        with (
            patch("src.bot_manager.read_pid_file", return_value=12345),
            patch("src.bot_manager.is_process_alive", return_value=True),
            pytest.raises(SystemExit, match="1"),
        ):
            cmd_start()

        captured = capsys.readouterr()
        assert "Already running (PID=12345)" in captured.out

    def test_ac10_start_with_stale_pid(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC10: stale PIDファイルがある場合は削除して起動する."""
        with (
            patch("src.bot_manager.read_pid_file", return_value=99999),
            patch("src.bot_manager.is_process_alive", return_value=False),
            patch("src.bot_manager.remove_pid_file") as mock_remove,
            patch("src.bot_manager._start_bot", return_value=12345),
        ):
            cmd_start()

        mock_remove.assert_called_once()
        captured = capsys.readouterr()
        assert "Running (PID=12345)" in captured.out


# ---------------------------------------------------------------------------
# cmd_stop テスト
# ---------------------------------------------------------------------------


class TestCmdStop:
    """--stop コマンドのテスト."""

    def test_ac12_stop_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC12: 正常停止時に Stopped を表示する."""
        with patch("src.bot_manager._stop_bot", return_value=True):
            cmd_stop()

        captured = capsys.readouterr()
        assert "Stopped" in captured.out

    def test_ac13_stop_not_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC13: 未起動時に Not running を表示する."""
        with patch("src.bot_manager._stop_bot", return_value=False):
            cmd_stop()

        captured = capsys.readouterr()
        assert "Not running" in captured.out


# ---------------------------------------------------------------------------
# cmd_restart テスト
# ---------------------------------------------------------------------------


class TestCmdRestart:
    """--restart コマンドのテスト."""

    def test_ac14_restart_with_existing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC14: 既存プロセスあり→停止→起動."""
        with (
            patch("src.bot_manager._stop_bot", return_value=True),
            patch("src.bot_manager._start_bot", return_value=12345),
        ):
            cmd_restart()

        captured = capsys.readouterr()
        assert "Stopped" in captured.out
        assert "Running (PID=12345)" in captured.out

    def test_ac14_restart_without_existing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC14: 既存プロセスなし→起動のみ."""
        with (
            patch("src.bot_manager._stop_bot", return_value=False),
            patch("src.bot_manager._start_bot", return_value=12345),
        ):
            cmd_restart()

        captured = capsys.readouterr()
        assert "Stopped" not in captured.out
        assert "Running (PID=12345)" in captured.out


# ---------------------------------------------------------------------------
# cmd_status テスト
# ---------------------------------------------------------------------------


class TestCmdStatus:
    """--status コマンドのテスト."""

    def test_ac15_status_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC15: 起動中は Running (PID=xxxx) を表示し exit(0)."""
        with (
            patch("src.bot_manager.read_pid_file", return_value=12345),
            patch("src.bot_manager.is_process_alive", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_status()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Running (PID=12345)" in captured.out

    def test_ac15_status_not_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """AC15: 未起動時は Not running を表示し exit(1)."""
        with (
            patch("src.bot_manager.read_pid_file", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_status()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Not running" in captured.out


# ---------------------------------------------------------------------------
# _start_bot テスト
# ---------------------------------------------------------------------------


class TestStartBot:
    """起動処理のテスト."""

    def test_ac18_log_file_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC18: .tmp/bot.log にログが出力される（ディレクトリ自動作成、stderr にファイル渡し）."""
        log_dir = tmp_path / ".tmp"
        log_file = log_dir / "bot.log"
        monkeypatch.setattr("src.bot_manager.LOG_DIR", log_dir)
        monkeypatch.setattr("src.bot_manager.LOG_FILE", log_file)

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b"BOT_READY\n"

        with (
            patch("src.bot_manager.subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch("src.bot_manager._wait_for_ready"),
            patch("src.bot_manager.read_pid_file", return_value=12345),
        ):
            pid = _start_bot()

        assert pid == 12345
        assert log_dir.exists()
        # Popen に stderr としてファイルオブジェクトが渡されたことを確認
        call_kwargs = mock_popen.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("stderr") is not None

    def test_ac18_log_file_append_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC18: 既存ログファイルがある場合は追記モードで書き込まれる."""
        log_dir = tmp_path / ".tmp"
        log_dir.mkdir()
        log_file = log_dir / "bot.log"
        log_file.write_text("existing log\n", encoding="utf-8")
        monkeypatch.setattr("src.bot_manager.LOG_DIR", log_dir)
        monkeypatch.setattr("src.bot_manager.LOG_FILE", log_file)

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with (
            patch("src.bot_manager.subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch("src.bot_manager._wait_for_ready"),
            patch("src.bot_manager.read_pid_file", return_value=12345),
        ):
            pid = _start_bot()

        assert pid == 12345
        # Popen の stderr に渡されたファイルが追記モードであることを確認
        call_kwargs = mock_popen.call_args
        stderr_file = call_kwargs.kwargs.get("stderr")
        assert stderr_file is not None
        # 既存の内容が保持されている（上書きされていない）
        content = log_file.read_text(encoding="utf-8")
        assert "existing log" in content

    def test_ac10_pid_file_fallback_to_proc_pid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC10: PIDファイルが読めない場合は proc.pid にフォールバックする."""
        log_dir = tmp_path / ".tmp"
        log_file = log_dir / "bot.log"
        monkeypatch.setattr("src.bot_manager.LOG_DIR", log_dir)
        monkeypatch.setattr("src.bot_manager.LOG_FILE", log_file)

        mock_proc = MagicMock()
        mock_proc.pid = 99999

        with (
            patch("src.bot_manager.subprocess.Popen", return_value=mock_proc),
            patch("src.bot_manager._wait_for_ready"),
            patch("src.bot_manager.read_pid_file", return_value=None),
        ):
            pid = _start_bot()

        assert pid == 99999

    def test_ac16_start_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC16: タイムアウト時にエラー終了する."""
        log_dir = tmp_path / ".tmp"
        log_file = log_dir / "bot.log"
        monkeypatch.setattr("src.bot_manager.LOG_DIR", log_dir)
        monkeypatch.setattr("src.bot_manager.LOG_FILE", log_file)

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        def timeout_wait(proc: object) -> None:
            raise SystemExit(1)

        with (
            patch("src.bot_manager.subprocess.Popen", return_value=mock_proc),
            patch("src.bot_manager._wait_for_ready", side_effect=timeout_wait),
            patch("src.bot_manager._kill_process_tree"),
            patch("src.bot_manager.remove_pid_file"),
            pytest.raises(SystemExit),
        ):
            _start_bot()

    def test_ac10_start_crash_cleanup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC10: 子プロセス異常終了時にクリーンアップされる."""
        log_dir = tmp_path / ".tmp"
        log_file = log_dir / "bot.log"
        monkeypatch.setattr("src.bot_manager.LOG_DIR", log_dir)
        monkeypatch.setattr("src.bot_manager.LOG_FILE", log_file)

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        def crash_wait(proc: object) -> None:
            raise SystemExit(1)

        with (
            patch("src.bot_manager.subprocess.Popen", return_value=mock_proc),
            patch("src.bot_manager._wait_for_ready", side_effect=crash_wait),
            patch("src.bot_manager._kill_process_tree") as mock_kill,
            patch("src.bot_manager.remove_pid_file") as mock_remove,
            pytest.raises(SystemExit),
        ):
            _start_bot()

        mock_kill.assert_called_once_with(12345)
        mock_remove.assert_called_once()


# ---------------------------------------------------------------------------
# _wait_for_ready テスト (Windows)
# ---------------------------------------------------------------------------


class TestWaitForReadyWindows:
    """Windows向け BOT_READY 待ちのテスト."""

    def test_receives_bot_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BOT_READY を受信したら正常終了する."""
        monkeypatch.setattr("sys.platform", "win32")

        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [b"BOT_READY\n", b""]

        from src.bot_manager import _wait_for_ready_windows
        _wait_for_ready_windows(mock_proc, timeout=5)

    def test_pipe_closed_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """パイプが閉じた場合は exit(1)."""
        monkeypatch.setattr("sys.platform", "win32")

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.poll.return_value = 1

        from src.bot_manager import _wait_for_ready_windows
        with pytest.raises(SystemExit, match="1"):
            _wait_for_ready_windows(mock_proc, timeout=5)

    def test_ac16_timeout_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC16: タイムアウト時に exit(1)."""
        monkeypatch.setattr("sys.platform", "win32")

        mock_proc = MagicMock()
        # readline がブロックし続ける（何も返さない）ことでタイムアウトを発生させる
        import threading
        block_event = threading.Event()
        def blocking_readline() -> bytes:
            block_event.wait()
            return b""
        mock_proc.stdout.readline.side_effect = blocking_readline

        from src.bot_manager import _wait_for_ready_windows
        with pytest.raises(SystemExit, match="1"):
            _wait_for_ready_windows(mock_proc, timeout=0.1)
        block_event.set()  # テスト終了後にスレッドを解放


# ---------------------------------------------------------------------------
# _wait_for_ready テスト (Unix)
# ---------------------------------------------------------------------------


class TestWaitForReadyUnix:
    """Unix向け BOT_READY 待ちのテスト."""

    def test_receives_bot_ready(self) -> None:
        """BOT_READY を受信したら正常終了する."""
        mock_proc = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stdout.readline.return_value = b"BOT_READY\n"

        from src.bot_manager import _wait_for_ready_unix
        with patch("select.select", return_value=([3], [], [])):
            _wait_for_ready_unix(mock_proc, timeout=5)

    def test_pipe_closed_exits(self) -> None:
        """パイプが閉じた場合は exit(1)."""
        mock_proc = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        mock_proc.stdout.readline.return_value = b""
        mock_proc.poll.return_value = 1

        from src.bot_manager import _wait_for_ready_unix
        with (
            patch("select.select", return_value=([3], [], [])),
            pytest.raises(SystemExit, match="1"),
        ):
            _wait_for_ready_unix(mock_proc, timeout=5)

    def test_ac16_timeout_exits(self) -> None:
        """AC16: select タイムアウト時に exit(1)."""
        mock_proc = MagicMock()
        mock_proc.stdout.fileno.return_value = 3

        from src.bot_manager import _wait_for_ready_unix
        with (
            patch("select.select", return_value=([], [], [])),
            pytest.raises(SystemExit, match="1"),
        ):
            _wait_for_ready_unix(mock_proc, timeout=5)

    def test_ac16_remaining_negative_exits(self) -> None:
        """AC16: remaining が負になった場合もタイムアウトで exit(1)."""
        mock_proc = MagicMock()
        mock_proc.stdout.fileno.return_value = 3
        # 1行目はログ出力（BOT_READY でない）
        mock_proc.stdout.readline.return_value = b"some log line\n"

        from src.bot_manager import _wait_for_ready_unix
        with (
            patch("select.select", return_value=([3], [], [])),
            patch("time.monotonic", side_effect=[0.0, 100.0]),
            pytest.raises(SystemExit, match="1"),
        ):
            _wait_for_ready_unix(mock_proc, timeout=5)


# ---------------------------------------------------------------------------
# handle_command テスト
# ---------------------------------------------------------------------------


class TestHandleCommand:
    """handle_command のディスパッチテスト."""

    def test_dispatches_start(self) -> None:
        """--start が cmd_start に委譲される."""
        args = Namespace(start=True, restart=False, stop=False, status=False)
        with patch("src.bot_manager.cmd_start") as mock:
            handle_command(args)
        mock.assert_called_once()

    def test_dispatches_restart(self) -> None:
        """--restart が cmd_restart に委譲される."""
        args = Namespace(start=False, restart=True, stop=False, status=False)
        with patch("src.bot_manager.cmd_restart") as mock:
            handle_command(args)
        mock.assert_called_once()

    def test_dispatches_stop(self) -> None:
        """--stop が cmd_stop に委譲される."""
        args = Namespace(start=False, restart=False, stop=True, status=False)
        with patch("src.bot_manager.cmd_stop") as mock:
            handle_command(args)
        mock.assert_called_once()

    def test_dispatches_status(self) -> None:
        """--status が cmd_status に委譲される."""
        args = Namespace(start=False, restart=False, stop=False, status=True)
        with patch("src.bot_manager.cmd_status") as mock:
            handle_command(args)
        mock.assert_called_once()
