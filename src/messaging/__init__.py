"""メッセージングポート/アダプター層.

仕様: docs/specs/features/cli-adapter.md
"""

from src.messaging.port import IncomingMessage, MessagingPort

__all__ = ["IncomingMessage", "MessagingPort"]
