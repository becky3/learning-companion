"""メッセージングポート/アダプター層.

仕様: docs/specs/f11-cli-adapter.md
"""

from src.messaging.port import IncomingMessage, MessagingPort

__all__ = ["IncomingMessage", "MessagingPort"]
