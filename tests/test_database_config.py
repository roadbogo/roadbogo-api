import pytest
from sqlalchemy import event

from app.core.database import engine, set_session_time_zone_utc


class FakeCursor:
    def __init__(self, execute_error: Exception | None = None) -> None:
        self.execute_error = execute_error
        self.executed: list[str] = []
        self.close_calls = 0

    def execute(self, statement: str) -> None:
        self.executed.append(statement)
        if self.execute_error is not None:
            raise self.execute_error

    def close(self) -> None:
        self.close_calls += 1


class FakeDbapiConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return self.fake_cursor

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_session_time_zone_listener_sets_utc_without_transaction_calls(capsys) -> None:
    cursor = FakeCursor()
    connection = FakeDbapiConnection(cursor)

    set_session_time_zone_utc(connection, None)

    assert connection.cursor_calls == 1
    assert cursor.executed == ["SET time_zone = '+00:00'"]
    assert cursor.close_calls == 1
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
    assert "SET GLOBAL" not in cursor.executed[0]
    assert capsys.readouterr().out == ""


def test_session_time_zone_listener_closes_cursor_and_propagates_execute_error() -> None:
    expected_error = RuntimeError("execute failed")
    cursor = FakeCursor(expected_error)
    connection = FakeDbapiConnection(cursor)

    with pytest.raises(RuntimeError) as error:
        set_session_time_zone_utc(connection, None)

    assert error.value is expected_error
    assert cursor.close_calls == 1
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_session_time_zone_listener_is_registered_for_engine_connect() -> None:
    assert event.contains(engine, "connect", set_session_time_zone_utc)
